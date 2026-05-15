# -*- coding: utf-8 -*-
"""
Сохранение результатов пайплайна в БД.

Использует существующие модели:
  - AdaptiveTask (основная таблица задач)
  - TaskGenerationLog (попытки, итерации, вердикты) — новая
  - ManualReviewQueue (не прошедшие 4 итерации) — новая
  - CostLog (токены × цена) — новая
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from pipeline.schemas import GeneratorOutput, PipelineResult
from pipeline.runner import IterationLog

logger = logging.getLogger("pipeline.persistence")


# ─── Маппинг subject → topic для AdaptiveTask ─────────────────────────────────
SUBJECT_TO_TOPIC = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "number_theory": "Теория чисел",
    "combinatorics": "Комбинаторика",
    "logic": "Логика",
    "set_theory": "Теория множеств",
    "probability": "Теория вероятностей",
}


def save_task_to_adaptive(
    result: PipelineResult,
    subject: str,
    grade: int,
    level: int,
    pipeline_run_id: str,
) -> int:
    """
    Сохраняет успешно сгенерированную задачу в adaptive_tasks.

    Returns:
        ID созданной AdaptiveTask
    """
    from models import db, AdaptiveTask

    if not result.task:
        raise ValueError("PipelineResult.task is None — nothing to save")

    task = result.task
    topic_ru = SUBJECT_TO_TOPIC.get(subject, subject)

    # Минимальное "решение" (само-описание) — реальное решение генерируется
    # тьютором по запросу. Однако нам нужно записать non-empty solution.
    solution_md = _build_solution_skeleton(task)
    criteria_1 = "1 балл — частичное продвижение: есть ключевая идея, но решение не доведено до конца."
    criteria_2 = "2 балла — задача решена полностью с обоснованием каждого шага."

    new_task = AdaptiveTask(
        class_level=grade,
        difficulty_level=level,
        topic=topic_ru,
        subtopic=None,
        task_text=task.statement,
        solution=solution_md,
        criteria_1_point=criteria_1,
        criteria_2_points=criteria_2,
        correct_answer=task.expected_answer_short,
        is_flagged=False,
        # Доп. поля если есть в БД (см. add_task_source)
    )

    # source / pipeline_run_id (если колонки существуют)
    try:
        new_task.source = "openrouter_pipeline"
    except Exception:
        pass

    db.session.add(new_task)
    db.session.flush()
    task_id = new_task.id

    logger.info("✓ Saved AdaptiveTask id=%d (subject=%s, grade=%d, level=%d)", task_id, subject, grade, level)
    return task_id


def _build_solution_skeleton(task: GeneratorOutput) -> str:
    """Формирует placeholder-решение из key_ideas и techniques."""
    lines = ["**Идея решения:**"]
    if task.key_ideas:
        for idea in task.key_ideas:
            lines.append(f"- {idea}")
    else:
        lines.append("- (генерируется тьютором по запросу)")

    if task.techniques:
        lines.append("\n**Используемые приёмы:**")
        for t in task.techniques:
            lines.append(f"- {t}")

    lines.append(f"\n**Ответ:** {task.expected_answer_short}")
    return "\n".join(lines)


def deprecate_old_tasks(subject: str, grade: int, level: int, exclude_ids: Optional[List[int]] = None) -> int:
    """
    Помечает старые задачи как deprecated (без удаления).
    Использует поле is_flagged=True + flagged_reason='deprecated_by_pipeline'.

    Returns:
        количество помеченных задач
    """
    from models import db, AdaptiveTask

    topic_ru = SUBJECT_TO_TOPIC.get(subject, subject)
    q = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == grade,
        AdaptiveTask.difficulty_level == level,
        AdaptiveTask.topic == topic_ru,
        AdaptiveTask.is_flagged == False,
    )
    if exclude_ids:
        q = q.filter(~AdaptiveTask.id.in_(exclude_ids))

    rows = q.all()
    for t in rows:
        t.is_flagged = True
        t.flagged_reason = "deprecated_by_pipeline"
    db.session.flush()
    logger.info("Deprecated %d old tasks (subject=%s, grade=%d, level=%d)", len(rows), subject, grade, level)
    return len(rows)


# ─── Запись в новые таблицы (через raw SQL для независимости от модели) ──────

def log_generation_attempt(
    run_id: str,
    subject: str,
    grade: int,
    level: int,
    result: PipelineResult,
    iter_logs: List[IterationLog],
    saved_task_id: Optional[int] = None,
) -> None:
    """Пишет одну строку в task_generation_log + детали итераций."""
    from models import db
    from sqlalchemy import text

    iterations_json = json.dumps(
        [
            {
                "iteration": il.iteration,
                "stage": il.stage,
                "verdict": il.verdict,
                "model": il.model,
                "input_tokens": il.input_tokens,
                "output_tokens": il.output_tokens,
                "cost_usd": round(il.cost_usd, 6),
                "latency_s": round(il.latency_s, 2),
                "fix_hint": il.fix_hint[:500] if il.fix_hint else "",
            }
            for il in iter_logs
        ],
        ensure_ascii=False,
    )

    db.session.execute(
        text("""
            INSERT INTO task_generation_log
                (run_id, subject, grade, level, success, iterations_used,
                 total_input_tokens, total_output_tokens, total_cost_usd,
                 saved_task_id, sent_to_review, iterations_detail_json,
                 error, created_at)
            VALUES
                (:run_id, :subject, :grade, :level, :success, :iters,
                 :tin, :tout, :cost,
                 :task_id, :review, :details,
                 :error, :created_at)
        """),
        {
            "run_id": run_id,
            "subject": subject,
            "grade": grade,
            "level": level,
            "success": 1 if result.success else 0,
            "iters": result.iterations,
            "tin": result.total_tokens_input,
            "tout": result.total_tokens_output,
            "cost": result.total_cost_usd,
            "task_id": saved_task_id,
            "review": 1 if result.sent_to_review else 0,
            "details": iterations_json,
            "error": result.error or "",
            "created_at": datetime.utcnow(),
        },
    )

    # Cost log
    for il in iter_logs:
        if il.model and (il.input_tokens or il.output_tokens):
            db.session.execute(
                text("""
                    INSERT INTO cost_log
                        (run_id, stage, model, input_tokens, output_tokens,
                         cost_usd, latency_s, created_at)
                    VALUES
                        (:run_id, :stage, :model, :tin, :tout, :cost, :lat, :created_at)
                """),
                {
                    "run_id": run_id,
                    "stage": il.stage,
                    "model": il.model,
                    "tin": il.input_tokens,
                    "tout": il.output_tokens,
                    "cost": il.cost_usd,
                    "lat": il.latency_s,
                    "created_at": datetime.utcnow(),
                },
            )

    db.session.flush()


def push_to_manual_review(
    run_id: str,
    subject: str,
    grade: int,
    level: int,
    result: PipelineResult,
) -> None:
    """Кладёт неудачную задачу в manual_review_queue."""
    from models import db
    from sqlalchemy import text

    task_json = result.task.model_dump_json(ensure_ascii=False) if result.task else "{}"
    v_json = result.validator_result.model_dump_json(ensure_ascii=False) if result.validator_result else "{}"
    c_json = result.calibrator_result.model_dump_json(ensure_ascii=False) if result.calibrator_result else "{}"

    db.session.execute(
        text("""
            INSERT INTO manual_review_queue
                (run_id, subject, grade, level, task_json,
                 validator_json, calibrator_json, reason, status, created_at)
            VALUES
                (:run_id, :subject, :grade, :level, :task_json,
                 :v, :c, :reason, 'pending', :created_at)
        """),
        {
            "run_id": run_id,
            "subject": subject,
            "grade": grade,
            "level": level,
            "task_json": task_json,
            "v": v_json,
            "c": c_json,
            "reason": result.error or "max_iterations_reached",
            "created_at": datetime.utcnow(),
        },
    )
    db.session.flush()
    logger.info("📋 Pushed to manual_review_queue: run_id=%s", run_id)
