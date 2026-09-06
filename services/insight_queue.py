# -*- coding: utf-8 -*-
"""Очередь «Банка неточностей»: воркер с потолком 5 + off-peak планировщик.

Правила (ТЗ, разделы 3, 5, 7):
  - Потолок конкурентности — 5 одновременных вызовов модели (semaphore).
  - Глубокий разбор (stage=deep) — только off-peak.
  - Подбор тренировочных задач: сначала база (daily_task_bank / task_bank /
    adaptive_tasks), потом генерация.
  - Дедупликация: title_normalized или пересечение tags >= 2 → increment
    occurrences, добавить 3 задачи, уведомление kind=repeat.
  - Лимит на срез: максимум 3 неточности с одного среза (по severity).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 5
QUEUE_POLL_INTERVAL = 3.0

# Off-peak окно (по Москве, UTC+3). Настраивается env.
# Дефолт: вечер/ночь 19:00–04:00 — вывод дешевле вдвое.
OFF_PEAK_START = int(os.environ.get("INSIGHT_OFF_PEAK_START", "19") or "19")
OFF_PEAK_END = int(os.environ.get("INSIGHT_OFF_PEAK_END", "4") or "4")

_MOSCOW_OFFSET = timedelta(hours=3)

_semaphore = threading.Semaphore(MAX_CONCURRENCY)
_worker_started = False
_worker_lock = threading.Lock()


# ─── Off-peak ─────────────────────────────────────────────────────────────

def _moscow_now() -> datetime:
    """Текущее московское время (UTC+3, без перехода на летнее)."""
    return datetime.now(timezone.utc).astimezone(timezone(_MOSCOW_OFFSET)).replace(tzinfo=None)


def is_off_peak(now: Optional[datetime] = None) -> bool:
    """True, если сейчас off-peak (по Москве: вечер/ночь 19:00–04:00).

    Если передан ``now`` — считаем его московским локальным временем (для тестов).
    """
    now = now or _moscow_now()
    hour = now.hour
    if OFF_PEAK_START >= OFF_PEAK_END:
        # Окно переваливает через полночь, например 19..4.
        return hour >= OFF_PEAK_START or hour < OFF_PEAK_END
    return OFF_PEAK_START <= hour < OFF_PEAK_END


# ─── Вставка результата ───────────────────────────────────────────────────

def _parse_tags(raw) -> List[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def _tags_overlap(a: List[str], b: List[str], min_overlap: int = 2) -> bool:
    return len(set(a) & set(b)) >= min_overlap


def find_duplicate(user_id: int, title_normalized: str, tags: List[str]):
    """Найти существующую неточность с тем же title или пересечением тегов."""
    from models_insights import Insight

    by_title = Insight.query.filter_by(
        user_id=user_id, title_normalized=title_normalized
    ).first()
    if by_title:
        return by_title

    if tags:
        candidates = Insight.query.filter_by(user_id=user_id).all()
        for c in candidates:
            if _tags_overlap(_parse_tags(c.tags), tags):
                return c
    return None


def _existing_tags_for_pick(insight_tags: List[str]) -> List[str]:
    """Извлечь подтему/метод из тегов для подбора из базы."""
    return insight_tags


def _bank_tasks_for(insight: Dict[str, Any], difficulty: int) -> List[Dict[str, Any]]:
    """Подобрать задачи из базы по тегам и уровню ±1 (раздел 5 ТЗ).

    Приоритет: daily_task_bank -> task_bank -> adaptive_tasks.
    """
    tags = insight.get("tags") or []
    topic_terms = [t.split(":", 1)[1] for t in tags if t.startswith("topic:") and ":" in t]
    method_terms = [t.split(":", 1)[1] for t in tags if t.startswith("method:") and ":" in t]
    keywords = topic_terms + method_terms

    found: List[Dict[str, Any]] = []
    try:
        from models import DailyTaskBank
        q = DailyTaskBank.query
        if difficulty:
            q = q.filter(
                DailyTaskBank.level.in_(
                    [max(1, difficulty - 1), difficulty, difficulty + 1]
                )
            )
        rows = q.limit(30).all()

        def _to_dict(r):
            return {
                "statement": r.statement,
                "answer": r.answer,
                "solution": r.solution,
                "difficulty": r.level or difficulty,
                "bank_task_id": r.id,
                "bank": "daily_task_bank",
                "topic": r.subtopic,
            }

        # Проход 1: по пересечению тегов.
        for r in rows:
            hay = ((r.subtopic or "") + " " + (r.statement or "")).lower()
            if keywords and not any(k.lower() in hay for k in keywords):
                continue
            found.append(_to_dict(r))

        # Проход 2 (fallback): теги не совпали — берём по уровню ±1.
        if not found and rows:
            for r in rows:
                found.append(_to_dict(r))
    except Exception:  # noqa: BLE001
        pass

    return found[:6]


def _practice_from_bank(bank_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Превратить подобранные задачи базы в practice[] (source=bank)."""
    practice = []
    for t in bank_tasks:
        practice.append({
            "statement": t.get("statement") or "",
            "answer": t.get("answer") or "",
            "hint": "",
            "solution_sketch": t.get("solution") or "",
            "difficulty": int(t.get("difficulty") or 3),
            "visibility": "medium",  # переопределяется run_bank_select
            "why_this_task": "",
            "naive_path_cost": "",
            "_bank_task_id": t.get("bank_task_id"),
            "_bank": t.get("bank"),
            "source": "bank",
        })
    return practice


def run_bank_select(practice_item: Dict[str, Any], insight: Dict[str, Any]):
    """Дешёвый вызов (effort=low): получить why_this_task и visibility для
    задачи из базы, чтобы собрать градиент obvious/medium/hidden (раздел 5)."""
    from services import insight_prompts
    from services.insight_llm_client import get_insight_client

    client = get_insight_client()
    user_prompt = (
        "Отрабатываемый приём:\n"
        f"{insight.get('canonical_fact') or insight.get('title') or ''}\n\n"
        f"Задача:\n{practice_item.get('statement') or ''}\n\n"
        f"Ответ: {practice_item.get('answer') or ''}"
    )
    try:
        parsed, _meta = client.call_json(
            system_prompt=insight_prompts.BANK_SELECT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            effort="low",
        )
    except Exception:  # noqa: BLE001
        parsed = {}
    return parsed


def _assign_visibility_slots(practice: List[Dict[str, Any]], insight: Dict[str, Any]):
    """Распределить visibility по градиенту для задач из базы.

    Сначала пробуем получить visibility от модели; недобранные слоты закрываем
    по позиции: 0->obvious, 1->medium, 2->hidden.
    """
    from services.insight_validator import VISIBILITIES

    assigned: List[Optional[str]] = []
    for item in practice:
        meta = run_bank_select(item, insight)
        vis = meta.get("visibility") if meta.get("visibility") in VISIBILITIES else None
        if meta.get("why_this_task"):
            item["why_this_task"] = meta["why_this_task"]
        if meta.get("naive_path_cost"):
            item["naive_path_cost"] = meta["naive_path_cost"]
        assigned.append(vis)

    # Заполняем пропуски по порядку градиента.
    fallback = ["obvious", "medium", "hidden"]
    used = set(v for v in assigned if v)
    for i in range(len(practice)):
        if assigned[i] is None:
            for fb in fallback:
                if fb not in used:
                    practice[i]["visibility"] = fb
                    used.add(fb)
                    break
            else:
                practice[i]["visibility"] = "medium"
        else:
            practice[i]["visibility"] = assigned[i]


def _insert_insight(user_id: int, job, insight_data: Dict[str, Any], is_repeat: bool):
    """Создать/обновить неточность и её 3 задачи. Возвращает Insight."""
    from models import db
    from models_insights import Insight, InsightPracticeTask, normalize_title

    title = (insight_data.get("title") or "").strip()
    title_norm = normalize_title(title)
    tags = insight_data.get("tags") or []

    existing = find_duplicate(user_id, title_norm, tags)

    practice = insight_data.get("practice") or []
    # Собираем practice из банка, если задач не хватает (генерация доливает).
    difficulty = int(insight_data.get("severity") or 3)
    if len(practice) < 3:
        bank_tasks = _bank_tasks_for(insight_data, difficulty)
        bank_practice = _practice_from_bank(bank_tasks)
        if bank_practice:
            _assign_visibility_slots(bank_practice[:3], insight_data)
        needed = 3 - len(practice)
        practice = list(practice) + bank_practice[:needed]

    practice = practice[:3]

    if existing:
        existing.occurrences = (existing.occurrences or 0) + 1
        existing.updated_at = datetime.utcnow()
        if existing.status == "mastered":
            existing.status = "in_progress"
        insight = existing
        kind = "repeat"
    else:
        insight = Insight(
            user_id=user_id,
            job_id=getattr(job, "id", None),
            title=title,
            title_normalized=title_norm,
            type=insight_data.get("type") or "missing_fact",
            severity=max(1, min(3, int(insight_data.get("severity") or 1))),
            location_text=insight_data.get("where"),
            what_went_wrong=insight_data.get("what_went_wrong"),
            better_way=insight_data.get("better_way"),
            time_lost_estimate_min=insight_data.get("time_lost_estimate_min"),
            canonical_fact=insight_data.get("canonical_fact"),
            tags=json.dumps(tags, ensure_ascii=False),
            occurrences=1,
            source=getattr(job, "source", "regular") or "regular",
            source_task_id=getattr(job, "source_task_id", None),
        )
        db.session.add(insight)
        db.session.flush()
        kind = "new"

    # Задачи: при повторе добавляем 3 новые.
    for pos, p in enumerate(practice, start=1):
        if not isinstance(p, dict):
            continue
        db.session.add(InsightPracticeTask(
            insight_id=insight.id,
            position=pos,
            statement=p.get("statement") or "",
            answer=p.get("answer") or "",
            hint=p.get("hint") or "",
            solution_sketch=p.get("solution_sketch") or "",
            difficulty=max(1, min(5, int(p.get("difficulty") or 3))),
            visibility=p.get("visibility") or "medium",
            why_this_task=p.get("why_this_task") or "",
            naive_path_cost=p.get("naive_path_cost") or "",
            source=p.get("source") or "generated",
            bank_task_id=p.get("_bank_task_id"),
        ))

    insight.progress_total = (insight.progress_total or 0) + 3
    db.session.commit()
    return insight, kind


def _create_notification(user_id: int, insight: "Insight", kind: str, tasks_count: int):
    from models import db
    from models_insights import InsightNotification

    n = InsightNotification(
        user_id=user_id,
        kind=kind,
        insight_id=insight.id,
        insights_count=1,
        tasks_count=tasks_count,
        status="pending",
    )
    db.session.add(n)
    db.session.commit()
    return n


def _job_ctx(job) -> Dict[str, Any]:
    return {
        "user_id": job.user_id,
        "task_text": job.task_text,
        "correct_answer": job.correct_answer,
        "solution_ref": job.solution_ref,
        "user_solution": job.user_solution,
        "topic": job.topic,
        "difficulty_level": job.difficulty_level,
        "time_spent_sec": job.time_spent_sec,
        "etalon_time_sec": job.etalon_time_sec,
    }


def _process_screen(job) -> None:
    from models import db
    from services.insight_runner import run_screen

    res = run_screen(_job_ctx(job))
    job.reasoning_tokens = int(res.meta.get("reasoning_tokens") or 0)
    job.cost_usd = float(res.meta.get("cost_usd") or 0.0)

    if res.meta.get("error") and not res.raw:
        job.status = "failed"
        job.error = str(res.meta.get("error"))
        db.session.commit()
        return

    if not res.needs_deep_analysis:
        job.status = "skipped"
        job.skip_reason = res.skip_reason or "no_issue"
        db.session.commit()
        logger.info("[insight] screen skipped user=%s reason=%s", job.user_id, job.skip_reason)
        return

    # Нужен глубокий разбор — ставим задачу stage=deep.
    job.status = "done"
    job.preliminary_type = res.preliminary_type
    db.session.commit()
    enqueue_deep_for_screen(job)


def enqueue_deep_for_screen(screen_job) -> None:
    from models import db
    from models_insights import InsightJob

    deep = InsightJob(
        user_id=screen_job.user_id,
        stage="deep",
        status="queued",
        source=screen_job.source,
        source_task_id=screen_job.source_task_id,
        source_attempt_id=screen_job.source_attempt_id,
        task_text=screen_job.task_text,
        correct_answer=screen_job.correct_answer,
        solution_ref=screen_job.solution_ref,
        user_solution=screen_job.user_solution,
        topic=screen_job.topic,
        difficulty_level=screen_job.difficulty_level,
        time_spent_sec=screen_job.time_spent_sec,
        etalon_time_sec=screen_job.etalon_time_sec,
    )
    db.session.add(deep)
    db.session.commit()


def _process_deep(job) -> None:
    from models import db

    # Кнопка «Дать ещё 3 задачи»: прикрепляем к существующей неточности,
    # не запуская дорогой глубокий разбор заново.
    if getattr(job, "source", None) == "regenerate":
        _process_regenerate(job)
        return

    from services.insight_runner import run_deep

    res = run_deep(_job_ctx(job))
    job.reasoning_tokens = int(res.meta.get("reasoning_tokens") or 0)
    job.cost_usd = float(res.meta.get("cost_usd") or 0.0)
    job.attempts_count = (job.attempts_count or 0) + 1

    if res.meta.get("error") and not res.raw:
        job.status = "failed"
        job.error = str(res.meta.get("error"))
        db.session.commit()
        return

    # Короткое рассуждение → один повторный прогон, при повторе — failed.
    if res.reasoning_short:
        if job.attempts_count < 2:
            job.status = "queued"  # повторный прогон
            db.session.commit()
            logger.warning("[insight] deep reasoning short, retry user=%s", job.user_id)
            return
        job.status = "failed"
        job.error = "reasoning_short"
        db.session.commit()
        logger.warning("[insight] deep reasoning short, giving up user=%s", job.user_id)
        return

    if not res.valid:
        job.status = "skipped"
        job.skip_reason = res.skip_reason or res.validation_reason or "no_issue"
        db.session.commit()
        logger.info("[insight] deep skipped user=%s reason=%s", job.user_id, job.skip_reason)
        return

    # Вставка с дедупликацией и лимитом 3 на срез.
    created = []
    for insight_data in res.insights[:2]:
        try:
            insight, kind = _insert_insight(job.user_id, job, insight_data, is_repeat=False)
            _create_notification(job.user_id, insight, kind, tasks_count=3)
            created.append(insight)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("[insight] insert insight failed user=%s", job.user_id)

    job.status = "done"
    db.session.commit()


def _process_regenerate(job) -> None:
    """Прикрепить 3 новые задачи к существующей неточности (кнопка «Ещё 3»)."""
    from models import db
    from models_insights import Insight, InsightPracticeTask

    insight = db.session.get(Insight, job.source_task_id)
    if insight is None:
        job.status = "failed"
        job.error = "insight_not_found"
        db.session.commit()
        return

    difficulty = insight.severity or 2
    insight_data = {
        "title": insight.title,
        "type": insight.type,
        "severity": insight.severity,
        "canonical_fact": insight.canonical_fact,
        "tags": _parse_tags(insight.tags),
    }

    bank_tasks = _bank_tasks_for(insight_data, difficulty)
    practice = _practice_from_bank(bank_tasks)
    if practice:
        _assign_visibility_slots(practice[:3], insight_data)
    practice = practice[:3]

    for pos, p in enumerate(practice, start=1):
        db.session.add(InsightPracticeTask(
            insight_id=insight.id,
            position=pos,
            statement=p.get("statement") or "",
            answer=p.get("answer") or "",
            hint=p.get("hint") or "",
            solution_sketch=p.get("solution_sketch") or "",
            difficulty=max(1, min(5, int(p.get("difficulty") or 3))),
            visibility=p.get("visibility") or "medium",
            why_this_task=p.get("why_this_task") or "",
            naive_path_cost=p.get("naive_path_cost") or "",
            source=p.get("source") or "generated",
            bank_task_id=p.get("_bank_task_id"),
        ))

    insight.progress_total = (insight.progress_total or 0) + len(practice)
    insight.status = "in_progress"
    job.status = "done"
    db.session.commit()


def _pick_job():
    from models_insights import InsightJob

    # Скрининг выполняется всегда.
    screen = (
        InsightJob.query
        .filter_by(stage="screen", status="queued")
        .order_by(InsightJob.created_at)
        .first()
    )
    if screen:
        return screen

    # Глубокий разбор — только off-peak.
    if not is_off_peak():
        return None

    deep = (
        InsightJob.query
        .filter_by(stage="deep", status="queued")
        .order_by(InsightJob.created_at)
        .first()
    )
    return deep


def _run_job(job):
    try:
        if job.stage == "screen":
            _process_screen(job)
        else:
            _process_deep(job)
    except Exception:  # noqa: BLE001
        logger.exception("[insight] job %s failed unexpectedly", getattr(job, "id", "?"))
        try:
            from models import db
            job.status = "failed"
            job.error = "worker_exception"
            db.session.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        _semaphore.release()


def _queue_worker_loop(app):
    from models_insights import InsightJob

    logger.info("[insight] queue worker started (max=%s)", MAX_CONCURRENCY)
    while True:
        try:
            with app.app_context():
                from models import db

                # Возврат «зависших» processing в queued (>10 мин).
                cutoff = datetime.utcnow() - timedelta(minutes=10)
                stale = (
                    InsightJob.query.filter(
                        InsightJob.status == "processing",
                        InsightJob.updated_at < cutoff,
                    ).all()
                )
                for s in stale:
                    s.status = "queued"
                if stale:
                    db.session.commit()

                free = MAX_CONCURRENCY
                while free > 0:
                    job = _pick_job()
                    if job is None:
                        break
                    if not _semaphore.acquire(blocking=False):
                        break
                    job.status = "processing"
                    job.updated_at = datetime.utcnow()
                    job_id = job.id
                    db.session.commit()
                    threading.Thread(
                        target=_job_worker,
                        args=(app, job_id),
                        daemon=True,
                        name=f"insight-job-{job_id}",
                    ).start()
                    free -= 1
        except Exception:  # noqa: BLE001
            logger.exception("[insight] queue worker error")

        time.sleep(QUEUE_POLL_INTERVAL)


def _job_worker(app, job_id):
    from models import db
    from models_insights import InsightJob
    with app.app_context():
        job = db.session.get(InsightJob, job_id)
        if job is None:
            _semaphore.release()
            return
        _run_job(job)


def ensure_queue_worker(app=None):
    """Запустить воркер очереди один раз на процесс."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    t = threading.Thread(
        target=_queue_worker_loop,
        args=(app,),
        daemon=True,
        name="insight-queue",
    )
    t.start()
    logger.info("[insight] queue worker thread launched")


def enqueue_screen(
    *,
    user_id: int,
    task_text: str,
    correct_answer: str = "",
    solution_ref: str = "",
    user_solution: str = "",
    topic: str = "",
    difficulty_level: Optional[int] = None,
    time_spent_sec: Optional[int] = None,
    etalon_time_sec: Optional[int] = None,
    source: str = "regular",
    source_task_id: Optional[int] = None,
    source_attempt_id: Optional[int] = None,
) -> int:
    """Поставить решение в очередь на скрининг. Возвращает job.id."""
    from models import db
    from models_insights import InsightJob

    job = InsightJob(
        user_id=user_id,
        stage="screen",
        status="queued",
        source=source,
        source_task_id=source_task_id,
        source_attempt_id=source_attempt_id,
        task_text=task_text,
        correct_answer=correct_answer,
        solution_ref=solution_ref,
        user_solution=user_solution,
        topic=topic,
        difficulty_level=difficulty_level,
        time_spent_sec=time_spent_sec,
        etalon_time_sec=etalon_time_sec,
    )
    db.session.add(job)
    db.session.commit()
    return job.id


def enqueue_regenerate(insight) -> int:
    """Кнопка «Дать ещё 3 задачи» — та же генерация, в фоне, через очередь.

    Ставит deep-задачу с флагом source=regenerate; воркер подберёт 3 задачи
    (из базы или генерацией) и прикрепит к существующей неточности.
    """
    from models import db
    from models_insights import InsightJob, normalize_title

    tags = _parse_tags(insight.tags)
    insight_data = {
        "title": insight.title,
        "type": insight.type,
        "severity": insight.severity or 2,
        "canonical_fact": insight.canonical_fact,
        "tags": tags,
        "practice": [],  # пусто → воркер доберёт из базы/генерацией
    }

    job = InsightJob(
        user_id=insight.user_id,
        stage="deep",
        status="queued",
        source="regenerate",
        source_task_id=insight.source_task_id,
        task_text=insight.what_went_wrong,
        correct_answer="",
        solution_ref="",
        user_solution=insight.better_way,
        topic=insight.canonical_fact,
        difficulty_level=insight.severity,
        # Признак «прикрепить к существующей неточности» храним в error-поле
        # временно не будем — используем отдельную функцию-обработчик ниже.
        etalon_time_sec=None,
    )
    # Помечаем цель прикрепления через source_task_id = insight.id.
    job.source_task_id = insight.id
    db.session.add(job)
    db.session.commit()
    return job.id
