# -*- coding: utf-8 -*-
"""
daily_tasks/services.py — высокоуровневый сервис «Задачи дня».

Предоставляет API для:
* ``enqueue_daily_generation(user_id, triggered_by)`` — запуск фоновой генерации
* ``get_daily_tasks(user_id)`` — получение сегодняшнего сета с задачами
* ``get_job_status(user_id)`` — статус фонового джоба
* ``submit_answer(item_id, answer, time_spent)`` — сохранить ответ пользователя
* ``get_hint(item_id, hint_index)`` — получить подсказку для задачи

Пайплайн работает асинхронно (``asyncio``), но вызывается из синхронного
Flask-контекста через ``threading.Thread`` + ``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from models import db

from .models import DailyTaskSet, DailyTaskItem, DailyGenerationJob, TaskPool, UserTaskAssignment
from .pipeline.orchestrator import (
    PipelineResult,
    run_daily_generation_pipeline,
)
from .profile import build_profile

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Публичные функции
# ──────────────────────────────────────────────────────────────────────


def enqueue_daily_generation(
    user_id: int,
    triggered_by: str = "manual",
) -> Dict[str, Any]:
    """Создать/обновить сет на today и запустить фоновую генерацию.

    **Кэширование**: перед запуском AI-пайплайна проверяется ``task_pool``.
    Если для данного профиля уже есть готовый пул — задачи выдаются из него
    без вызова нейросетей (экономия ~$0.85 за генерацию).

    Параметры
    ---------
    user_id : int
        ID пользователя.
    triggered_by : str
        Триггер — ``'manual'``, ``'adaptive_test'`` или ``'cron'``.

    Возвращает
    ----------
    dict
        * ``daily_set_id`` — ID созданного/существующего сета
        * ``job_id`` — ID фонового джоба (или None, если генерация не нужна)
        * ``status`` — текущий статус сета
        * ``message`` — человеко-читаемое пояснение
    """
    today = date.today()

    # ── проверяем, есть ли уже сет на сегодня ─────────────────────────
    existing_set = DailyTaskSet.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    if existing_set and existing_set.status in ("ready", "generating"):
        logger.info(
            "Сет #%d на %s для user=%d уже %s, пропускаем",
            existing_set.id,
            today,
            user_id,
            existing_set.status,
        )
        return {
            "daily_set_id": existing_set.id,
            "job_id": None,
            "status": existing_set.status,
            "message": f"Сет на сегодня уже {existing_set.status}",
        }

    if existing_set and existing_set.status == "failed":
        # перезапускаем: удаляем старый failed-сет
        db.session.delete(existing_set)
        db.session.flush()

    # ── проверяем task_pool (кэш) ─────────────────────────────────────
    try:
        profile = build_profile(user_id)
        cache_key = compute_cache_key(profile)

        now = datetime.utcnow()
        pool: Optional[TaskPool] = TaskPool.query.filter(
            TaskPool.cache_key == cache_key,
            TaskPool.status.in_(["ready", "partial"]),
            (TaskPool.expires_at.is_(None)) | (TaskPool.expires_at > now),
        ).order_by(TaskPool.created_at.desc()).first()

        if pool:
            # ── Cache HIT ─────────────────────────────────────────────
            pool.used_count = (pool.used_count or 0) + 1

            tasks_data = _parse_json_field(pool.tasks, [])
            specs_data = _parse_json_field(pool.specs, [])
            selected_indices = _select_best_task_indices(tasks_data, n=5)

            daily_set = DailyTaskSet(
                user_id=user_id,
                target_date=today,
                status="ready",
                triggered_by=triggered_by,
                generated_at=datetime.utcnow(),
                class_level=profile.get("class_level"),
                reason_summary=(
                    f"Из общего пула (кэш), "
                    f"ключ: {cache_key[:12]}…"
                ),
            )
            db.session.add(daily_set)
            db.session.flush()

            for new_pos, idx in enumerate(selected_indices):
                task = tasks_data[idx] if idx < len(tasks_data) else {}
                spec = specs_data[idx] if idx < len(specs_data) else {}
                audit = task.get("_audit_entry", {})
                is_flagged = task.get("is_flagged", False)

                flag_reason = None
                if is_flagged and audit:
                    issues = audit.get("issues", [])
                    if issues:
                        flag_reason = "; ".join(
                            f"[{iss.get('code','?')}] {iss.get('description','')}"
                            for iss in issues[:3]
                        )

                item = DailyTaskItem(
                    daily_set_id=daily_set.id,
                    position=new_pos + 1,
                    slot_kind=spec.get("slot_kind"),
                    subject=spec.get("subject"),
                    topic=spec.get("topic"),
                    subtopic=spec.get("subtopic"),
                    difficulty_level=spec.get("difficulty_level"),
                    weakness_score=spec.get("weakness_score"),
                    reason=spec.get("reason"),
                    task_text=task.get("task_text", ""),
                    correct_answer=task.get("correct_answer"),
                    solution=task.get("solution"),
                    hints=json.dumps(task.get("hints", []), ensure_ascii=False),
                    gemini_spec_json=json.dumps(spec, ensure_ascii=False),
                    opus_iterations=task.get("_opus_iterations", 0),
                    gpt_audit_json=json.dumps(audit, ensure_ascii=False) if audit else None,
                    is_flagged=is_flagged,
                    flag_reason=flag_reason,
                    status="approved" if not is_flagged else "flagged",
                )
                db.session.add(item)

            # записываем привязку пользователя к пулу
            assignment = UserTaskAssignment(
                user_id=user_id,
                pool_id=pool.id,
                task_positions=json.dumps(selected_indices),
            )
            db.session.add(assignment)
            db.session.commit()

            logger.info(
                "Cache HIT для user=%d key=%s pool=%d → сет #%d (5 задач)",
                user_id, cache_key[:12], pool.id, daily_set.id,
            )

            return {
                "daily_set_id": daily_set.id,
                "job_id": None,
                "status": "ready",
                "message": "Задачи взяты из общего пула (кэш)",
            }

    except Exception as exc:
        # Если кэш упал — логируем и падаем сквозь на обычную генерацию
        logger.warning(
            "Cache check error для user=%d: %s — падаем на pipeline",
            user_id, exc,
        )

    # ── Cache MISS: создаём DailyTaskSet ──────────────────────────────
    daily_set = DailyTaskSet(
        user_id=user_id,
        target_date=today,
        status="generating",
        triggered_by=triggered_by,
    )
    db.session.add(daily_set)
    db.session.flush()  # получить daily_set.id

    # ── создаём DailyGenerationJob ────────────────────────────────────
    job = DailyGenerationJob(
        user_id=user_id,
        target_date=today,
        daily_set_id=daily_set.id,
        state="running",
        started_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()

    logger.info(
        "Создан сет #%s / джоб #%s для user=%d",
        daily_set.id,
        job.id,
        user_id,
    )

    # ── запускаем пайплайн в фоновом потоке ─────────────────────────
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_background_run,
        args=(app, user_id, today, daily_set.id, job.id),
        daemon=True,
    )
    thread.start()

    return {
        "daily_set_id": daily_set.id,
        "job_id": job.id,
        "status": "generating",
        "message": "Генерация запущена в фоне",
    }


def get_daily_tasks(user_id: int) -> Dict[str, Any]:
    """Получить сегодняшний сет задач для пользователя.

    Возвращает
    ----------
    dict
        * ``status`` — статус сета (или ``'no_set'`` если сета нет)
        * ``daily_set_id`` — ID сета
        * ``target_date`` — дата сета
        * ``reason_summary`` — краткое описание, почему эти темы
        * ``items`` — список задач (каждая с полями ``id``, ``position``, …)
        * ``job`` — информация о фоновом джобе (если есть)
    """
    today = date.today()
    daily_set = DailyTaskSet.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    if not daily_set:
        return {
            "status": "no_set",
            "daily_set_id": None,
            "target_date": today.isoformat(),
            "items": [],
            "job": None,
        }

    # ── сериализуем задачи ───────────────────────────────────────────
    items: List[Dict[str, Any]] = []
    for item in daily_set.items.order_by(DailyTaskItem.position).all():
        items.append({
            "id": item.id,
            "position": item.position,
            "slot_kind": item.slot_kind,
            "subject": item.subject,
            "topic": item.topic,
            "subtopic": item.subtopic,
            "difficulty_level": item.difficulty_level,
            "weakness_score": item.weakness_score,
            "reason": item.reason,
            "task_text": item.task_text,
            "correct_answer": item.correct_answer,
            "solution": item.solution,
            "hints": _parse_json_field(item.hints, []),
            "is_flagged": item.is_flagged,
            "flag_reason": item.flag_reason,
            "status": item.status,
            "user_answer": item.user_answer,
            "is_correct": item.is_correct,
            "answered_at": item.answered_at.isoformat() if item.answered_at else None,
            "time_spent_seconds": item.time_spent_seconds,
        })

    # ── сериализуем джоб ─────────────────────────────────────────────
    job = DailyGenerationJob.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()
    job_data = _serialize_job(job) if job else None

    return {
        "status": daily_set.status,
        "daily_set_id": daily_set.id,
        "target_date": daily_set.target_date.isoformat(),
        "reason_summary": daily_set.reason_summary,
        "generated_at": daily_set.generated_at.isoformat() if daily_set.generated_at else None,
        "total_cost_usd": daily_set.total_cost_usd,
        "items": items,
        "job": job_data,
    }


def get_job_status(user_id: int) -> Dict[str, Any]:
    """Получить статус фонового джоба генерации на сегодня."""
    today = date.today()
    job = DailyGenerationJob.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    if not job:
        return {"state": "no_job"}

    return _serialize_job(job)


def submit_answer(
    item_id: int,
    answer: str,
    time_spent: Optional[int] = None,
) -> Dict[str, Any]:
    """Сохранить ответ пользователя на задачу.

    Возвращает
    ----------
    dict
        * ``success`` — bool
        * ``is_correct`` — bool (если ответ проверяем; пока всегда True/False
          на основе точного сравнения с ``correct_answer``)
        * ``correct_answer`` — правильный ответ (чтобы показать)
        * ``message`` — пояснение
    """
    item = DailyTaskItem.query.get(item_id)
    if not item:
        return {"success": False, "message": "Задача не найдена"}

    # ── проверка ответа (точное сравнение) ───────────────────────────
    is_correct = False
    if item.correct_answer:
        # Нормализуем: обрезаем пробелы, приводим к нижнему регистру
        norm_user = answer.strip().lower()
        norm_correct = item.correct_answer.strip().lower()
        is_correct = norm_user == norm_correct

    item.user_answer = answer
    item.is_correct = is_correct
    item.answered_at = datetime.utcnow()
    if time_spent is not None:
        item.time_spent_seconds = time_spent

    db.session.commit()

    return {
        "success": True,
        "is_correct": is_correct,
        "correct_answer": item.correct_answer,
        "message": "Ответ сохранён",
    }


def get_hint(
    item_id: int,
    hint_index: int = 0,
) -> Dict[str, Any]:
    """Получить подсказку для задачи.

    Возвращает
    ----------
    dict
        * ``success`` — bool
        * ``hint`` — текст подсказки (или None, если нет)
        * ``total_hints`` — общее количество подсказок
        * ``hint_index`` — запрошенный индекс
    """
    item = DailyTaskItem.query.get(item_id)
    if not item:
        return {"success": False, "message": "Задача не найдена"}

    hints = _parse_json_field(item.hints, [])
    if not hints:
        return {
            "success": False,
            "message": "Подсказки отсутствуют",
        }

    if hint_index < 0 or hint_index >= len(hints):
        return {
            "success": False,
            "message": f"Неверный индекс подсказки: {hint_index}, всего: {len(hints)}",
        }

    return {
        "success": True,
        "hint": hints[hint_index],
        "total_hints": len(hints),
        "hint_index": hint_index,
    }


# ──────────────────────────────────────────────────────────────────────
# Кэширование пула задач
# ──────────────────────────────────────────────────────────────────────


def _norm_topics(topics: List[Any]) -> List[str]:
    """Нормализовать список тем для детерминированного хэширования.

    * приводит к нижнему регистру
    * обрезает пробелы
    * сортирует
    * пропускает пустые / None
    """
    normalized: List[str] = []
    for t in topics:
        raw = t.get("topic", str(t)) if isinstance(t, dict) else str(t)
        stripped = raw.strip().lower()
        if stripped:
            normalized.append(stripped)
    return sorted(normalized)


def compute_cache_key(profile: Dict[str, Any]) -> str:
    """Детерминированный SHA-256 ключ по профилю пользователя.

    Ученики с одинаковым (class_level, набор тем, class_expected_level)
    получат одинаковый cache_key → один пул задач без повторного AI.

    Регистр и лишние пробелы в названиях тем нормализуются,
    так что ``" Algebra "`` и ``"algebra"`` дадут одинаковый ключ.
    """
    key_data: Dict[str, Any] = {
        "class_level": profile.get("class_level", 0),
        "class_expected_level": profile.get("class_expected_level", 0),
        "weak_topics": _norm_topics(profile.get("weak_topics", [])),
        "strong_topics": _norm_topics(profile.get("strong_topics", [])),
    }
    canonical = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _select_best_task_indices(tasks: List[Dict[str, Any]], n: int = 5) -> List[int]:
    """Вернуть индексы ``n`` лучших задач: сначала без флагов, потом с флагами.

    Это позволяет давать разным пользователям *разные* подмножества
    из одного пула, избегая полного дублирования.
    """
    clean = [i for i, t in enumerate(tasks) if not t.get("is_flagged")]
    flagged = [i for i, t in enumerate(tasks) if t.get("is_flagged")]
    selected = clean[:n]
    if len(selected) < n:
        selected += flagged[: n - len(selected)]
    return selected


def _select_best_tasks(tasks: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    """Вернуть ``n`` лучших task-словарей (сами объекты)."""
    indices = _select_best_task_indices(tasks, n=n)
    return [tasks[i] for i in indices if i < len(tasks)]


def _extract_subject_from_profile(profile: Dict[str, Any]) -> str:
    """Извлечь доминирующий subject из профиля (первая слабая тема)."""
    weak = profile.get("weak_topics", [])
    if weak:
        subj = weak[0].get("subject", "") if isinstance(weak[0], dict) else ""
        if subj:
            return subj
    strong = profile.get("strong_topics", [])
    if strong:
        subj = strong[0].get("subject", "") if isinstance(strong[0], dict) else ""
        if subj:
            return subj
    return "mixed"


# ──────────────────────────────────────────────────────────────────────
# Внутренние функции (фоновый запуск + persist)
# ──────────────────────────────────────────────────────────────────────


def _background_run(
    app: Any,
    user_id: int,
    target_date: date,
    daily_set_id: int,
    job_id: int,
) -> None:
    """Запустить пайплайн в фоновом потоке (синхронная обёртка)."""
    with app.app_context():
        try:
            asyncio.run(_run_pipeline_async(
                user_id=user_id,
                target_date=target_date,
                daily_set_id=daily_set_id,
                job_id=job_id,
            ))
        except Exception as exc:
            logger.exception(
                "Критическая ошибка в фоновой генерации для user=%d: %s",
                user_id,
                exc,
            )
            _fail_job(job_id, str(exc))


async def _run_pipeline_async(
    user_id: int,
    target_date: date,
    daily_set_id: int,
    job_id: int,
) -> None:
    """Асинхронный запуск пайплайна с обновлением прогресса джоба."""
    job = DailyGenerationJob.query.get(job_id)
    if not job:
        logger.error("Job #%s не найден", job_id)
        return

    try:
        # ── Step 1: build_profile ────────────────────────────────────
        _update_job_progress(job, "build_profile", 5)
        logger.info("[user=%d] Step 1: построение профиля", user_id)
        profile = build_profile(user_id)
        logger.info(
            "[user=%d] Профиль: класс=%d, слабых=%d, сильных=%d",
            user_id,
            profile.get("class_level"),
            len(profile.get("weak_topics", [])),
            len(profile.get("strong_topics", [])),
        )

        # ── Step 2–5: пайплайн с live-обновлением прогресса ────────
        # Колбэк обновляет current_step/progress_pct в БД при переходах
        # между внутренними шагами оркестратора, чтобы JS-поллер видел
        # реальный прогресс, а не "застрял на step 2".
        def _progress_cb(step: str, pct: int) -> None:
            try:
                # job уже отвязан от сессии после первого commit'а — берём свежий.
                fresh_job = DailyGenerationJob.query.get(job_id)
                if fresh_job:
                    _update_job_progress(fresh_job, step, pct)
            except Exception as exc:
                logger.warning("[user=%d] progress_cb error: %s", user_id, exc)

        _update_job_progress(job, "gemini_plan", 15)
        result: PipelineResult = await run_daily_generation_pipeline(
            profile, progress_callback=_progress_cb,
        )

        # ── Step 6: persist ──────────────────────────────────────────
        _update_job_progress(job, "persist", 90)
        _persist_pipeline_result(daily_set_id, job_id, result, profile)

        # ── завершение ──────────────────────────────────────────────
        if result.success:
            _complete_job(job_id)
        else:
            _fail_job(job_id, result.error or "Пайплайн завершился с ошибкой")

    except Exception as exc:
        logger.exception(
            "[user=%d] Ошибка в пайплайне: %s",
            user_id,
            exc,
        )
        _fail_job(job_id, str(exc))


def _persist_pipeline_result(
    daily_set_id: int,
    job_id: int,
    result: PipelineResult,
    profile: Dict[str, Any],
) -> None:
    """Записать результат пайплайна в БД (Step 6 по ТЗ).

    * Создаёт / обновляет ``DailyTaskItem`` для каждой из 10 позиций.
    * Устанавливает ``DailyTaskSet.status``, ``generated_at``,
      ``reason_summary``, ``pipeline_log``, ``total_cost_usd``.
    * Обновляет ``DailyGenerationJob.state``.
    """
    daily_set = DailyTaskSet.query.get(daily_set_id)
    if not daily_set:
        logger.error("DailyTaskSet #%s не найден", daily_set_id)
        return

    # ── удаляем старые items (если были) ─────────────────────────────
    DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).delete()

    # ── создаём 10 items ─────────────────────────────────────────────
    for i in range(10):
        spec = result.specs[i] if i < len(result.specs) else {}
        task = result.tasks[i] if i < len(result.tasks) else {}
        audit = (
            result.audit_entries[i]
            if i < len(result.audit_entries) and result.audit_entries[i]
            else {}
        )
        is_flagged = (
            result.is_flagged[i]
            if i < len(result.is_flagged)
            else False
        )
        iteration_count = (
            result.iteration_counts[i]
            if i < len(result.iteration_counts)
            else 0
        )

        # ── флаг-причина (из аудита) ─────────────────────────────────
        flag_reason = None
        if is_flagged and audit:
            issues = audit.get("issues", [])
            if issues:
                flag_reason = "; ".join(
                    f"[{iss.get('code','?')}] {iss.get('description','')}"
                    for iss in issues[:3]  # топ-3 проблемы
                )

        item = DailyTaskItem(
            daily_set_id=daily_set_id,
            position=i + 1,
            # ── мета (из spec) ───────────────────────────────────────
            slot_kind=spec.get("slot_kind"),
            subject=spec.get("subject"),
            topic=spec.get("topic"),
            subtopic=spec.get("subtopic"),
            difficulty_level=spec.get("difficulty_level"),
            weakness_score=spec.get("weakness_score"),
            reason=spec.get("reason"),
            # ── контент (из task) ────────────────────────────────────
            task_text=task.get("task_text", ""),
            correct_answer=task.get("correct_answer"),
            solution=task.get("solution"),
            hints=json.dumps(task.get("hints", []), ensure_ascii=False),
            # ── аудит / итерации ─────────────────────────────────────
            gemini_spec_json=json.dumps(spec, ensure_ascii=False),
            opus_iterations=iteration_count,
            gpt_audit_json=json.dumps(audit, ensure_ascii=False) if audit else None,
            is_flagged=is_flagged,
            flag_reason=flag_reason,
            status="approved" if not is_flagged else "flagged",
        )
        db.session.add(item)

    # ── обновляем DailyTaskSet ───────────────────────────────────────
    status = result.status  # 'ready' | 'partial' | 'failed'
    daily_set.status = status
    daily_set.generated_at = datetime.utcnow()
    daily_set.class_level = profile.get("class_level")
    daily_set.reason_summary = _build_reason_summary(result, profile)
    daily_set.pipeline_log = json.dumps(
        [asdict(s) for s in result.steps],
        ensure_ascii=False,
        default=str,
    )
    daily_set.total_cost_usd = result.total_cost

    db.session.commit()
    logger.info(
        "Персист: сет #%s, статус=%s, cost=$%.4f, items=%d",
        daily_set_id,
        status,
        result.total_cost,
        len(result.tasks),
    )

    # ── сохраняем результат в task_pool (для кэширования) ──────────
    try:
        _save_to_task_pool(result, profile, daily_set_id)
    except Exception as exc:
        logger.warning(
            "Не удалось сохранить в task_pool для сета #%s: %s",
            daily_set_id, exc,
        )


def _save_to_task_pool(
    result: PipelineResult,
    profile: Dict[str, Any],
    daily_set_id: int,
) -> None:
    """Сохранить (или обновить) запись в ``task_pool`` после успешной генерации.

    * Конвертирует ``PipelineResult`` в JSON-строки.
    * Проверяет дубликат по ``cache_key`` (race condition guard).
    * Записывает ``UserTaskAssignment`` для первого пользователя.
    """
    if not result.tasks:
        logger.warning("_save_to_task_pool: нет задач, пропускаем")
        return

    cache_key = compute_cache_key(profile)
    subject = _extract_subject_from_profile(profile)
    grade = profile.get("class_level", 0)

    # ── готовим сериализованные данные ──────────────────────────────
    # Встраиваем audit/is_flagged/iteration_count прямо в task-словари
    # для удобного чтения при cache hit.
    enriched_tasks: List[Dict[str, Any]] = []
    for i, task in enumerate(result.tasks):
        enriched = dict(task)
        if i < len(result.audit_entries):
            enriched["_audit_entry"] = result.audit_entries[i]
        if i < len(result.is_flagged):
            enriched["is_flagged"] = result.is_flagged[i]
        if i < len(result.iteration_counts):
            enriched["_opus_iterations"] = result.iteration_counts[i]
        enriched_tasks.append(enriched)

    tasks_json = json.dumps(enriched_tasks, ensure_ascii=False, default=str)
    specs_json = json.dumps(result.specs, ensure_ascii=False, default=str)
    profile_json = json.dumps(profile, ensure_ascii=False, default=str)

    valid_count = sum(
        1 for f in result.is_flagged if not f
    ) if result.is_flagged else len(result.tasks)

    expires_at = datetime.utcnow() + timedelta(days=30)

    # ── race condition guard: мог уже появиться от параллельного запуска ─
    existing = TaskPool.query.filter_by(cache_key=cache_key).first()
    if existing:
        logger.info(
            "task_pool для ключа %s уже существует (#%d), пропускаем",
            cache_key[:12], existing.id,
        )
        return

    pool_entry = TaskPool(
        cache_key=cache_key,
        subject=subject,
        grade=grade,
        profile_snapshot=profile_json,
        tasks=tasks_json,
        specs=specs_json,
        status=result.status,
        valid_count=valid_count,
        expires_at=expires_at,
    )
    db.session.add(pool_entry)
    db.session.flush()

    # ── записываем привязку для первого пользователя ────────────────
    daily_set = DailyTaskSet.query.get(daily_set_id)
    if daily_set:
        assignment = UserTaskAssignment(
            user_id=daily_set.user_id,
            pool_id=pool_entry.id,
            task_positions=json.dumps(list(range(len(result.tasks)))),
        )
        db.session.add(assignment)

    db.session.commit()
    logger.info(
        "Сохранён task_pool #%s: key=%s, grade=%d, tasks=%d, valid=%d",
        pool_entry.id, cache_key[:12], grade,
        len(result.tasks), valid_count,
    )


# ──────────────────────────────────────────────────────────────────────
# Хелперы
# ──────────────────────────────────────────────────────────────────────


def _update_job_progress(
    job: DailyGenerationJob,
    current_step: str,
    progress_pct: int,
) -> None:
    """Обновить текущий шаг и прогресс джоба."""
    job.current_step = current_step
    job.progress_pct = progress_pct
    db.session.commit()


def _complete_job(job_id: int) -> None:
    """Отметить джоб как завершённый."""
    job = DailyGenerationJob.query.get(job_id)
    if not job:
        return
    job.state = "completed"
    job.finished_at = datetime.utcnow()
    job.progress_pct = 100
    db.session.commit()
    logger.info("Job #%s завершён", job_id)


def _fail_job(job_id: int, error_message: str) -> None:
    """Отметить джоб как завершившийся ошибкой."""
    try:
        job = DailyGenerationJob.query.get(job_id)
        if not job:
            return
        job.state = "failed"
        job.error_message = error_message[:500]  # обрезаем
        job.finished_at = datetime.utcnow()
        db.session.commit()
        logger.error("Job #%s упал: %s", job_id, error_message)
    except Exception as exc:
        logger.exception("Не удалось обновить job #%s: %s", job_id, exc)


def _build_reason_summary(
    result: PipelineResult,
    profile: Dict[str, Any],
) -> str:
    """Сформировать краткое описание (почему эти темы)."""
    weak_topics = profile.get("weak_topics", [])
    strong_topics = profile.get("strong_topics", [])

    weak_names = [t.get("topic_ru", t.get("topic", "?")) for t in weak_topics[:3]]
    strong_names = [t.get("topic_ru", t.get("topic", "?")) for t in strong_topics[:2]]

    parts = []
    if weak_names:
        parts.append(f"Слабые темы: {', '.join(weak_names)}")
    if strong_names:
        parts.append(f"Повторение: {', '.join(strong_names)}")

    # ── добавляем информацию о качестве ──────────────────────────────
    flagged_count = sum(result.is_flagged)
    if flagged_count > 0:
        parts.append(f"({flagged_count} задач помечены на доработку)")

    summary = "; ".join(parts) if parts else "Генерация по профилю"
    return summary[:500]


def _serialize_job(job: DailyGenerationJob) -> Dict[str, Any]:
    """Сериализовать джоб в dict для API."""
    return {
        "id": job.id,
        "state": job.state,
        "current_step": job.current_step,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _parse_json_field(value: Optional[str], fallback: Any = None) -> Any:
    """Безопасно распарсить JSON-поле из БД."""
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Не удалось распарсить JSON: %r", value[:100])
        return fallback
