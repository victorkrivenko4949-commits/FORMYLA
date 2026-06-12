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
from sqlalchemy import insert as sql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError:
    pg_insert = None  # PostgreSQL driver not installed (e.g., SQLite-only env)

from models import db

from .models import DailyTaskSet, DailyTaskItem, DailyGenerationJob, TaskPool, UserTaskAssignment
from .pipeline.orchestrator import (
    PipelineResult,
    run_daily_generation_pipeline,
)
from .profile import build_profile, ProfileBuildError

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Часовой пояс пользователя (МСК, UTC+3)
# ──────────────────────────────────────────────────────────────────────
# Render работает в UTC. Если использовать today_in_user_tz() напрямую, то в
# 21:00-23:59 МСК пользователь видит «сет на завтра», но БД содержит сет
# на «сегодня UTC» = вчера МСК → 404 «no_set» и фейковая ошибка генерации.
# Решение: единая утилита, считающая дату по МСК для всех мест, где сет
# создаётся / ищется по target_date.

DAILY_TASKS_TZ = timezone(timedelta(hours=3))  # МСК = UTC+3

# ──────────────────────────────────────────────────────────────────────
# Zombie-job watchdog
# ──────────────────────────────────────────────────────────────────────
# Нормальная генерация занимает ~60-120 секунд (3 AI-шага + аудит + фикс-луп).
# Если фоновый поток умер (gunicorn worker restart, OOM, deploy, SIGKILL),
# job/sеt застывает в `running`/`generating` навсегда → UI бесконечно крутит
# таймер «прошло X:XX», а guard в enqueue_daily_generation() видит
# существующий generating-сет и НЕ запускает новую генерацию.
#
# Чтобы избежать необходимости в отдельном cron-watchdog'е, мы делаем
# **lazy cleanup** прямо в hot path: при каждом GET /job_status и
# POST /regenerate проверяем, нет ли «зомби» (state='running' старше
# STALE_JOB_TIMEOUT), и помечаем их как failed. Это идемпотентно,
# не требует доп. процессов и работает на любом плане Render.
STALE_JOB_TIMEOUT = timedelta(minutes=10)
"""Если job 'running' старше этого порога — считаем поток мёртвым."""


def today_in_user_tz() -> date:
    """Текущая дата в часовом поясе пользователя (МСК, UTC+3).

    На Render серверное время — UTC. Чтобы пользователь, открывающий
    /daily_tasks в 22:30 МСК (= 19:30 UTC), видел сет на «сегодня МСК»,
    а не на вчерашнюю UTC-дату, используем явный TZ.
    """
    return datetime.now(DAILY_TASKS_TZ).date()


def _reap_stale_jobs(user_id: Optional[int] = None) -> int:
    """Lazy-watchdog: помечает зомби-jobs как failed и освобождает сеты.

    Условие зомби: ``DailyGenerationJob.state == 'running'`` и
    ``started_at`` старше :data:`STALE_JOB_TIMEOUT`. Такое случается,
    когда фоновый ``threading.Thread(daemon=True)`` умер до завершения
    (рестарт gunicorn, OOM, deploy). Без этой проверки сет навсегда
    остаётся в ``generating`` и блокирует новую генерацию.

    Вызывается из ``get_job_status()`` и ``enqueue_daily_generation()``
    перед основной логикой — поэтому пользователь, увидевший «висит»,
    автоматически разморозит сет, просто обновив страницу.

    Параметры
    ---------
    user_id : int | None
        Если задан — чистим только jobs данного пользователя
        (минимизирует contention в hot path). ``None`` — чистим всех
        (используется только в startup-хуке, если будет добавлен).

    Возвращает
    ----------
    int : сколько зомби помечено как failed.
    """
    try:
        threshold = datetime.utcnow() - STALE_JOB_TIMEOUT
        q = DailyGenerationJob.query.filter(
            DailyGenerationJob.state == "running",
            DailyGenerationJob.started_at != None,  # noqa: E711
            DailyGenerationJob.started_at < threshold,
        )
        if user_id is not None:
            q = q.filter(DailyGenerationJob.user_id == user_id)
        stale_jobs = q.all()
        if not stale_jobs:
            return 0

        reaped = 0
        for job in stale_jobs:
            job.state = "failed"
            job.error_message = (
                "Генерация прервана (поток умер до завершения, "
                "вероятно рестарт сервера). Попробуйте ещё раз."
            )[:500]
            job.finished_at = datetime.utcnow()

            # связанный DailyTaskSet тоже размораживаем, иначе guard
            # в enqueue_daily_generation() будет видеть status='generating'
            # и отказывать в новой генерации.
            if job.daily_set_id:
                related_set = DailyTaskSet.query.get(job.daily_set_id)
                if related_set and related_set.status == "generating":
                    related_set.status = "failed"
                    related_set.reason_summary = (
                        "❌ Генерация прервана — попробуйте ещё раз"
                    )
                    related_set.generated_at = datetime.utcnow()
            reaped += 1
            logger.warning(
                "Reaped zombie job #%s (user=%s, started_at=%s, step=%s)",
                job.id, job.user_id, job.started_at, job.current_step,
            )

        db.session.commit()
        return reaped
    except Exception:
        logger.exception("Не удалось почистить зомби-jobs")
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


def _reap_stale_pools() -> int:
    """Lazy-watchdog для ``TaskPool``: чистит зависшие пулы предгенерации.

    Аналогично :func:`_reap_stale_jobs`, но для записей в ``task_pool``
    со ``status='generating'`` и ``expires_at < now`` (по умолчанию
    prewarm-пулы создаются с TTL=1h в :func:`trigger_daily_prewarm`).
    Зомби-пул блокирует cache_hit для всех пользователей с тем же
    профилем — поэтому чистим его при каждом обращении.

    Возвращает количество помеченных failed-пулов.
    """
    try:
        now = datetime.utcnow()
        # Берём слегка щедрый порог — 15 минут для пулов:
        # generating-пул должен жить максимум TTL (1h), но если он
        # старше expires_at — он гарантированно мёртв.
        stale_pools = TaskPool.query.filter(
            TaskPool.status == "generating",
            TaskPool.expires_at.isnot(None),
            TaskPool.expires_at < now,
        ).all()
        if not stale_pools:
            return 0
        for pool in stale_pools:
            pool.status = "failed"
            pool.expires_at = now - timedelta(seconds=1)
            logger.warning(
                "Reaped zombie task_pool #%s (cache_key=%s, was generating, expired)",
                pool.id, (pool.cache_key or "")[:12],
            )
        db.session.commit()
        return len(stale_pools)
    except Exception:
        logger.exception("Не удалось почистить зомби-пулы")
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


# ──────────────────────────────────────────────────────────────────────
# Публичные функции
# ──────────────────────────────────────────────────────────────────────


def enqueue_daily_generation(
    user_id: int,
    triggered_by: str = "manual",
    profile: Optional[Dict[str, Any]] = None,
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
    today = today_in_user_tz()

    # ── lazy zombie-cleanup: размораживаем зависшие jobs пользователя ──
    # Если предыдущий фоновый поток умер (рестарт gunicorn, OOM), сет
    # навсегда остаётся в 'generating' и блокирует новую генерацию.
    # Чистим перед проверкой guard'а ниже, чтобы тот же запрос смог
    # запустить новую генерацию.
    _reap_stale_jobs(user_id=user_id)

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
    if profile is not None:
        cache_key = compute_cache_key(profile)

        now = datetime.utcnow()

        # ── Fix 5: пул ещё генерируется (предгенерация после адаптивного теста) ──
        # ВАЖНО: сначала чистим зомби-пулы (status='generating' с истёкшим
        # expires_at — поток заполнения умер). Иначе пользователь навсегда
        # застрянет на «Пул ещё генерируется».
        _reap_stale_pools()
        generating_pool: Optional[TaskPool] = TaskPool.query.filter(
            TaskPool.cache_key == cache_key,
            TaskPool.status == "generating",
        ).first()
        if generating_pool:
            logger.info(
                "Пул для key=%s ещё генерируется (#%d) — возвращаем generating",
                cache_key[:12], generating_pool.id,
            )
            return {
                "daily_set_id": None,
                "job_id": generating_pool.id,
                "status": "generating",
                "message": "Пул задач ещё генерируется",
            }

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
            selected_indices = _select_best_task_indices(
                tasks_data, n=10, rotation=pool.used_count or 0,
            )

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

            # темы, считаемые калибровочными в этом профиле, — нужны для
            # is_calibration на items (PR percent_to_level + calibration)
            cal_topic_set = {
                (t or "").strip().lower()
                for t in (profile.get("calibration_topics") or [])
                if isinstance(t, str)
            }

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

                spec_topic = (spec.get("topic") or "").strip().lower()
                is_calibration = spec_topic in cal_topic_set

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
                    is_calibration=is_calibration,
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
                "Cache HIT для user=%d key=%s pool=%d → сет #%d (10 задач)",
                user_id, cache_key[:12], pool.id, daily_set.id,
            )

            return {
                "daily_set_id": daily_set.id,
                "job_id": None,
                "status": "ready",
                "message": "Задачи взяты из общего пула (кэш)",
            }

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
    # lazy zombie-cleanup: если job умер — размораживаем сет, чтобы
    # пользователь увидел failed-state + кнопку Retry, а не пустоту.
    _reap_stale_jobs(user_id=user_id)

    today = today_in_user_tz()
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
    all_items: List[Dict[str, Any]] = []
    for item in daily_set.items.order_by(DailyTaskItem.position).all():
        # is_calibration появилось в новой миграции — берём безопасно
        # на случай если БД ещё не пересоздана.
        is_calibration = bool(getattr(item, "is_calibration", False) or False)
        all_items.append({
            "id": item.id,
            "position": item.position,
            "slot_kind": item.slot_kind,
            "subject": item.subject,
            "topic": item.topic,
            "subtopic": item.subtopic,
            "difficulty": item.difficulty_level,
            "weakness_score": item.weakness_score,
            "reason": item.reason,
            "is_calibration": is_calibration,
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

    # ── отбираем 10 лучших (чистые сначала, флагованные только если чистых < 10) ──
    best_indices = _select_best_task_indices(all_items, n=10)
    items = [all_items[i] for i in best_indices]

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
    """Получить статус фонового джоба генерации на сегодня.

    Перед возвратом статуса вызывает :func:`_reap_stale_jobs` — если
    фоновый поток умер (рестарт worker'а, OOM), job автоматически
    помечается failed, и пользователь увидит «Попробовать снова»
    вместо вечного таймера «прошло X:XX».
    """
    # lazy zombie-cleanup: пользователь, открывший /daily_tasks и
    # увидевший зависший таймер, обновит страницу — и этот же запрос
    # разморозит сет (если job старше STALE_JOB_TIMEOUT).
    _reap_stale_jobs(user_id=user_id)

    today = today_in_user_tz()
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


def _norm_topics(topics: Optional[List[Any]]) -> List[str]:
    """Нормализовать список тем для детерминированного хэширования.

    * приводит к нижнему регистру
    * обрезает пробелы
    * удаляет дубликаты
    * сортирует
    * пропускает пустые / None
    * возвращает [] для None
    """
    if topics is None:
        return []
    normalized: List[str] = []
    for t in topics:
        raw = t.get("topic", str(t)) if isinstance(t, dict) else str(t)
        stripped = raw.strip().lower()
        if stripped:
            normalized.append(stripped)
    # Deduplicate preserving first occurrence, then sort
    seen: set = set()
    deduped = [x for x in normalized if not (x in seen or seen.add(x))]
    return sorted(deduped)


def compute_cache_key(profile: Dict[str, Any]) -> str:
    """Детерминированный SHA-256 ключ по профилю пользователя.

    Ученики с одинаковым (class_level, набор тем, class_expected_level,
    набор калибровочных тем дня, profile_completeness) получают
    одинаковый cache_key → один пул задач без повторного AI.

    PR percent_to_level + calibration:
    * добавлены ``profile_completeness`` и ``calibration_topics`` —
      иначе ученик с 1/7 тестов и ученик с 7/7 тестов получили бы
      ОДИН пул, что неверно (для них набор задач должен отличаться).

    Регистр и лишние пробелы в названиях тем нормализуются.
    """
    # квантуем completeness до 0.10, чтобы мелкие колебания
    # (например 0.142 vs 0.143) не множили пулы
    completeness_q = round(float(profile.get("profile_completeness", 0.0)), 1)
    key_data: Dict[str, Any] = {
        "subject": profile.get("subject", "unknown"),
        "class_level": profile.get("class_level", 0),
        "class_expected_level": profile.get("class_expected_level", 0),
        "weak_topics": _norm_topics(profile.get("weak_topics", [])),
        "strong_topics": _norm_topics(profile.get("strong_topics", [])),
        "calibration_topics": sorted(
            (t or "").strip().lower()
            for t in (profile.get("calibration_topics") or [])
            if isinstance(t, str) and t.strip()
        ),
        "completeness_q": completeness_q,
    }
    canonical = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _select_best_task_indices(
    tasks: List[Dict[str, Any]],
    n: int = 5,
    rotation: int = 0,
) -> List[int]:
    """Вернуть индексы ``n`` лучших задач с ротацией.

    * Сначала чистые (без флагов), потом флагнутые.
    * Если ``rotation > 0`` — сдвигает порядок, чтобы разные пользователи
      получали **разные** подмножества из одного пула.

    Параметры
    ---------
    tasks : list[dict]
        Список задач (словарей) с ключом ``is_flagged``.
    n : int
        Сколько задач выбрать.
    rotation : int
        Сдвиг для ротации (``pool.used_count`` или ``hash(user_id)``).
    """
    clean = [i for i, t in enumerate(tasks) if not t.get("is_flagged")]
    flagged = [i for i, t in enumerate(tasks) if t.get("is_flagged")]
    ordered = clean + flagged

    if len(ordered) > n and rotation:
        offset = rotation % len(ordered)
        ordered = ordered[offset:] + ordered[:offset]

    return ordered[:n]


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
        logger.info("[user=%d] Step 1: построение профиля", user_id)
        try:
            profile = build_profile(user_id)
        except ProfileBuildError as exc:
            # Бизнес-ошибка (нет grade, нет каталога) — не баг.
            # Помечаем сет failed с понятной причиной, выходим без traceback.
            logger.warning(
                "[user=%d] ProfileBuildError: %s", user_id, exc,
            )
            _mark_set_failed(daily_set_id, str(exc))
            _fail_job(job_id, f"Профиль: {exc}")
            return
        logger.info(
            "[user=%d] Профиль: класс=%s completeness=%.2f слабых=%d сильных=%d калибровочных=%d",
            user_id,
            profile.get("class_level"),
            profile.get("profile_completeness", 0.0),
            len(profile.get("weak_topics", [])),
            len(profile.get("strong_topics", [])),
            len(profile.get("calibration_topics", [])),
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
    """Записать результат пайплайна в БД (Step 6 по ТЗ).

    Поведение зависит от ``result.status``:

    * ``'ready'`` / ``'partial'`` — создаём ``DailyTaskItem`` для **каждой
      реальной задачи** в ``result.tasks`` (1 … N, N ≤ 10).
    * ``'failed'`` — **НЕ создаём** «zombie»-items с ``task_text=''``;
      сохраняем сет со статусом ``failed`` и причиной в ``reason_summary``,
      чтобы UI мог показать понятное сообщение об ошибке, а не пустые
      карточки. ``error_message`` джоба содержит технические детали.
    """
    daily_set = DailyTaskSet.query.get(daily_set_id)
    if not daily_set:
        logger.error("DailyTaskSet #%s не найден", daily_set_id)
        return

    # ── удаляем старые items (если были) ─────────────────────────────
    DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).delete()

    status = result.status  # 'ready' | 'partial' | 'failed'
    is_failed = (status == "failed") or (not result.tasks)

    # ── ВАЖНО: при failed НЕ создаём пустые items ──────────────────
    # Раньше создавали 10 «zombie»-items с task_text='' — фронт рендерил
    # пустые карточки, пользователь видел «пустой блок без ошибки».
    items_created = 0
    # Множество калибровочных тем — нужно для is_calibration на items.
    cal_topic_set = {
        (t or "").strip().lower()
        for t in (profile.get("calibration_topics") or [])
        if isinstance(t, str)
    }
    if not is_failed:
        n_real = min(10, len(result.tasks))
        for i in range(n_real):
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

            # Пропускаем «битые» задачи без текста — они бы создали zombie-item
            task_text = (task.get("task_text") or "").strip()
            if not task_text:
                logger.warning(
                    "Persist: пропускаю позицию %d — task_text пуст (spec=%s)",
                    i + 1, spec.get("topic", "?"),
                )
                continue

            # ── флаг-причина (из аудита) ─────────────────────────────
            flag_reason = None
            if is_flagged and audit:
                issues = audit.get("issues", [])
                if issues:
                    flag_reason = "; ".join(
                        f"[{iss.get('code','?')}] {iss.get('description','')}"
                        for iss in issues[:3]  # топ-3 проблемы
                    )

            spec_topic = (spec.get("topic") or "").strip().lower()
            is_calibration = spec_topic in cal_topic_set

            item = DailyTaskItem(
                daily_set_id=daily_set_id,
                position=i + 1,
                # ── мета (из spec) ───────────────────────────────────
                slot_kind=spec.get("slot_kind"),
                subject=spec.get("subject"),
                topic=spec.get("topic"),
                subtopic=spec.get("subtopic"),
                difficulty_level=spec.get("difficulty_level"),
                weakness_score=spec.get("weakness_score"),
                reason=spec.get("reason"),
                is_calibration=is_calibration,
                # ── контент (из task) ────────────────────────────────
                task_text=task_text,
                correct_answer=task.get("correct_answer"),
                solution=task.get("solution"),
                hints=json.dumps(task.get("hints", []), ensure_ascii=False),
                # ── аудит / итерации ─────────────────────────────────
                gemini_spec_json=json.dumps(spec, ensure_ascii=False),
                opus_iterations=iteration_count,
                gpt_audit_json=(
                    json.dumps(audit, ensure_ascii=False) if audit else None
                ),
                is_flagged=is_flagged,
                flag_reason=flag_reason,
                status="approved" if not is_flagged else "flagged",
            )
            db.session.add(item)
            items_created += 1

            if is_flagged:
                logger.warning(
                    "FLAG: position=%d, flag_reason=%s, audit_preview=%s",
                    i + 1, flag_reason,
                    json.dumps(audit, ensure_ascii=False, default=str)[:500],
                )

    # ── обновляем DailyTaskSet ───────────────────────────────────────
    daily_set.status = "failed" if is_failed else status
    daily_set.generated_at = datetime.utcnow()
    daily_set.class_level = profile.get("class_level")

    if is_failed:
        # Сохраняем реальную причину для UI: она видна и в шапке сета,
        # и в DailyGenerationJob.error_message (через _fail_job).
        err = result.error or "Неизвестная ошибка генерации"
        daily_set.reason_summary = f"❌ {err[:400]}"
    else:
        daily_set.reason_summary = _build_reason_summary(result, profile)

    daily_set.pipeline_log = json.dumps(
        [asdict(s) for s in result.steps],
        ensure_ascii=False,
        default=str,
    )
    daily_set.total_cost_usd = result.total_cost

    db.session.commit()
    logger.info(
        "Персист: сет #%s, статус=%s, cost=$%.4f, items_created=%d, error=%r",
        daily_set_id, daily_set.status, result.total_cost,
        items_created, result.error,
    )

    # ── PER-TOPIC DIFFICULTY MATCHING: лог-сводка соответствия ────────
    # Печатаем «тема → window vs реальные уровни задач», чтобы было
    # видно, что 1/8 алгебра дала задачи L1-L3, а 8/8 геометрия — L7-L8.
    try:
        _log_topic_difficulty_match(profile, result)
    except Exception:
        logger.exception("Не удалось напечатать topic-difficulty summary")

    # ── сохраняем результат в task_pool (только если успех) ─────────
    if not is_failed:
        try:
            _save_to_task_pool(result, profile, daily_set_id)
        except Exception:
            # ИСПРАВЛЕНО: было warning без exception, теперь полный stacktrace
            logger.exception(
                "Не удалось сохранить в task_pool для сета #%s", daily_set_id,
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

    # TTL: частичный пул живёт 7 дней, готовый — 30 дней
    ttl_days = 7 if result.status == "partial" else 30
    expires_at = datetime.utcnow() + timedelta(days=ttl_days)

    # ── race condition guard: мог уже появиться от параллельного запуска ─
    existing = TaskPool.query.filter_by(cache_key=cache_key).first()
    if existing:
        if existing.status == "generating":
            # Fix 1: предгенерация — обновляем пул вместо создания нового
            logger.info(
                "task_pool для key=%s уже есть (#%d, status=%s) — обновляем",
                cache_key[:12], existing.id, existing.status,
            )
            existing.tasks = tasks_json
            existing.specs = specs_json
            existing.status = result.status  # 'ready' или 'partial'
            existing.valid_count = valid_count
            existing.expires_at = expires_at
            existing.profile_snapshot = profile_json
            db.session.flush()

            # ── записываем привязку для первого пользователя ────────
            daily_set = DailyTaskSet.query.get(daily_set_id)
            if daily_set:
                assignment = UserTaskAssignment(
                    user_id=daily_set.user_id,
                    pool_id=existing.id,
                    task_positions=json.dumps(list(range(len(result.tasks)))),
                )
                db.session.add(assignment)

            db.session.commit()
            logger.info(
                "Обновлён task_pool #%s: key=%s, status=%s, tasks=%d, valid=%d",
                existing.id, cache_key[:12], existing.status,
                len(result.tasks), valid_count,
            )
            return
        else:
            logger.info(
                "task_pool для ключа %s уже существует (#%d, status=%s), пропускаем",
                cache_key[:12], existing.id, existing.status,
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


def _mark_set_failed(daily_set_id: int, reason: str) -> None:
    """Пометить DailyTaskSet как failed с понятной причиной.

    Используется при ProfileBuildError (пустой grade и т.п.) — чтобы UI
    показал юзеру конкретное сообщение, а не «общая ошибка».
    """
    try:
        s = DailyTaskSet.query.get(daily_set_id)
        if not s:
            return
        s.status = "failed"
        s.reason_summary = f"❌ {reason[:400]}"
        s.generated_at = datetime.utcnow()
        db.session.commit()
        logger.warning("DailyTaskSet #%s marked failed: %s", daily_set_id, reason)
    except Exception:
        logger.exception("Не удалось пометить DailyTaskSet #%s как failed", daily_set_id)
        db.session.rollback()


def _build_reason_summary(
    result: "PipelineResult",
    profile: Dict[str, Any],
) -> str:
    """Сформировать краткое описание (почему эти темы).

    PR percent_to_level + calibration:
    * добавлен префикс с completeness ("Пройдено N/7 тестов")
    * сообщение про калибровочные темы — UI рисует баннер и бейджи
    """
    weak_topics = profile.get("weak_topics", [])
    strong_topics = profile.get("strong_topics", [])

    weak_names = [t.get("topic_ru", t.get("topic", "?")) for t in weak_topics[:3]]
    strong_names = [t.get("topic_ru", t.get("topic", "?")) for t in strong_topics[:2]]

    parts: List[str] = []

    # ── completeness: «Пройдено N/7 тестов» ─────────────────────────
    measured = int(profile.get("measured_topics_count", 0) or 0)
    completeness = float(profile.get("profile_completeness", 0.0) or 0.0)
    # total = 7 для 7+ кл; для 5-6 может отличаться, но в reason нам важна
    # дробь measured/total — берём из topics_full если есть
    total_topics = len(profile.get("topics_full") or []) or 7
    if completeness < 1.0:
        parts.append(
            f"Пройдено {measured} из {total_topics} тестов — "
            f"задачи по непройденным темам ориентировочные"
        )

    if weak_names:
        parts.append(f"Слабые темы: {', '.join(weak_names)}")
    if strong_names:
        parts.append(f"Повторение: {', '.join(strong_names)}")

    cal_topics = profile.get("calibration_topics") or []
    if cal_topics:
        parts.append(f"Калибровка: {', '.join(cal_topics[:2])}")

    # ── информация о качестве ────────────────────────────────────────
    flagged_count = sum(result.is_flagged)
    if flagged_count > 0:
        parts.append(f"({flagged_count} задач помечены на доработку)")

    summary = "; ".join(parts) if parts else "Генерация по профилю"
    return summary[:500]


def _serialize_job(job: DailyGenerationJob) -> Dict[str, Any]:
    """Сериализовать джоб в dict для API.

    Все ``*_at`` поля в БД хранятся как naive UTC (``datetime.utcnow()``).
    Чтобы фронт корректно интерпретировал их (в частности — для подсчёта
    «прошло X:XX» от ``started_at``), отдаём ISO-строку с явным
    суффиксом ``Z``. Дополнительно отдаём ``elapsed_seconds`` —
    серверно посчитанное прошедшее время в секундах, чтобы JS не
    зависел от расхождения часов клиент/сервер.
    """
    elapsed_seconds = None
    if job.started_at:
        elapsed_seconds = max(
            0, int((datetime.utcnow() - job.started_at).total_seconds())
        )
    return {
        "id": job.id,
        "state": job.state,
        "current_step": job.current_step,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "started_at": (job.started_at.isoformat() + "Z") if job.started_at else None,
        "finished_at": (job.finished_at.isoformat() + "Z") if job.finished_at else None,
        "created_at": (job.created_at.isoformat() + "Z") if job.created_at else None,
        "elapsed_seconds": elapsed_seconds,
    }


def _log_topic_difficulty_match(
    profile: Dict[str, Any],
    result: "PipelineResult",
) -> None:
    """Печать сводки «тема → запланированное окно vs реальные уровни задач».

    PR per-topic difficulty matching: критерий готовности по ТЗ — на
    тестовом профиле «алгебра 1/8, геометрия 8/8» в логах виден чистый
    матчинг topic→difficulty. Эта функция выводит ровно такой блок.
    """
    # Собираем target_level/level_window per topic из профиля
    topic_meta: Dict[str, Dict[str, Any]] = {}
    for t in (profile.get("topics_full") or []):
        topic = (t.get("topic") or "").strip()
        if not topic:
            continue
        topic_meta[topic] = {
            "target_level": t.get("target_level"),
            "level_window": t.get("level_window") or [
                t.get("level_low"), t.get("level_high"),
            ],
            "test_correct": t.get("test_correct"),
            "test_total": t.get("test_total"),
            "calibration": bool(t.get("calibration")),
            "final_level": t.get("final_level"),
        }

    # Группируем сгенерированные задачи по теме
    levels_by_topic: Dict[str, List[int]] = {}
    mismatches: List[str] = []
    for spec, is_flagged in zip(result.specs or [], result.is_flagged or []):
        topic = (spec.get("topic") or "?").strip()
        lvl = spec.get("difficulty_level")
        levels_by_topic.setdefault(topic, []).append(lvl)
        meta = topic_meta.get(topic, {})
        win = meta.get("level_window") or [1, 8]
        if isinstance(lvl, int) and isinstance(win, (list, tuple)) and len(win) == 2:
            lo, hi = win[0], win[1]
            if lo is not None and hi is not None and not (lo <= lvl <= hi):
                mismatches.append(
                    f"pos={spec.get('position')} topic={topic} L{lvl} OUTSIDE window {win}"
                )

    logger.info("=" * 60)
    logger.info("PER-TOPIC DIFFICULTY MATCHING SUMMARY")
    logger.info("=" * 60)
    for topic, levels in levels_by_topic.items():
        meta = topic_meta.get(topic, {})
        score = "N/A"
        if meta.get("test_total"):
            score = f"{meta.get('test_correct')}/{meta.get('test_total')}"
        cal = " (CAL)" if meta.get("calibration") else ""
        logger.info(
            "  %s%s — тест %s, target=L%s, окно %s → задачи: %s",
            topic, cal, score,
            meta.get("target_level"), meta.get("level_window"),
            levels,
        )
    if mismatches:
        logger.warning("MISMATCHES (%d):", len(mismatches))
        for m in mismatches:
            logger.warning("  %s", m)
    else:
        logger.info("MATCH OK: все задачи попали в окно своих тем.")
    logger.info("=" * 60)


def _parse_json_field(value: Any, fallback: Any = None) -> Any:
    """Безопасно распарсить JSON-поле из БД.

    Поддерживает оба диалекта:
    - SQLite: хранит JSON как TEXT → парсим через json.loads()
    - PostgreSQL: JSON-колонки возвращают уже разобранный list/dict → возвращаем как есть
    """
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        preview = str(value)[:100] if value else "None"
        logger.warning("Не удалось распарсить JSON: %r", preview)
        return fallback


# ══════════════════════════════════════════════════════════════════════
# Fix 2–3: Проактивная предгенерация (prewarm) после адаптивного теста
# ══════════════════════════════════════════════════════════════════════


def _dialect_insert(model):
    """Return dialect-appropriate sqlalchemy Insert builder with ON CONFLICT support.

    ``sqlalchemy.sql.base.Insert`` does **not** have ``on_conflict_do_nothing``;
    only dialect-specific subclasses (sqlite / postgresql) provide it.
    """
    name = db.engine.dialect.name if db.engine else 'sqlite'
    if name.startswith('postgresql') and pg_insert is not None:
        return pg_insert(model)
    return sqlite_insert(model)


def trigger_daily_prewarm(user_id: int) -> Dict[str, Any]:
    """Проактивная предгенерация пула задач после адаптивного теста.

    Атомарно создаёт запись в ``task_pool`` со статусом ``'generating'``.
    Если такой ключ уже есть — проверяет статус:

    * ``generating`` → ``already_running``
    * ``ready`` / ``partial`` → ``cache_hit``

    Возвращает словарь с ``status``, ``pool_id``, ``message``.
    """
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
        _future = _executor.submit(build_profile, user_id)
        try:
            profile = _future.result(timeout=20)
        except _cf.TimeoutError:
            logger.warning("trigger_daily_prewarm: build_profile timed out after 20s")
            return {"status": "error", "message": "Ошибка построения профиля"}
    cache_key = compute_cache_key(profile)
    subject = _extract_subject_from_profile(profile)
    grade = profile.get("class_level", 0)
    profile_json = json.dumps(profile, ensure_ascii=False, default=str)

    # ── Атомарный захват: INSERT … ON CONFLICT DO NOTHING RETURNING id ──
    stmt = _dialect_insert(TaskPool).values(
        cache_key=cache_key,
        subject=subject,
        grade=grade,
        profile_snapshot=profile_json,
        tasks="[]",
        specs="[]",
        status="generating",
        valid_count=0,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    ).on_conflict_do_nothing(index_elements=['cache_key'])

    try:
        result = db.session.execute(stmt.returning(TaskPool.id))
        row = result.fetchone()
        db.session.commit()
    except Exception:
        logger.exception("ON CONFLICT insert failed for cache_key=%s", cache_key)
        db.session.rollback()
        row = None

    if row:
        # Наш INSERT прошёл — запускаем генерацию в фоне
        pool_id = row[0]
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_and_fill_pool,
            args=(app, pool_id, profile),
            daemon=True,
        )
        thread.start()
        return {"status": "started", "pool_id": pool_id, "message": "Генерация запущена"}

    # Ключ уже существует — проверяем статус
    pool: Optional[TaskPool] = TaskPool.query.filter_by(cache_key=cache_key).first()
    if not pool:
        return {"status": "error", "message": "Гонка: пул не найден"}
    if pool.status == "generating":
        return {"status": "already_running", "pool_id": pool.id, "message": "Уже генерируется"}
    return {"status": "cache_hit", "pool_id": pool.id, "message": "Пул уже готов"}


def _run_and_fill_pool(app, pool_id: int, profile: Dict[str, Any]) -> None:
    """Фоновый worker: запускает пайплайн и заполняет пул.

    Обязательно создаёт свой ``app.app_context()`` — НЕ использовать
    сессию из запроса! При ошибке переводит пул в ``failed``.
    """
    with app.app_context():
        try:
            import asyncio
            result = asyncio.run(run_daily_generation_pipeline(profile))

            pool = db.session.get(TaskPool, pool_id)
            if not pool:
                logger.error("Пул #%s не найден в _run_and_fill_pool", pool_id)
                return

            # Сериализуем результат
            enriched_tasks = []
            for i, task in enumerate(result.tasks):
                enriched = dict(task)
                if i < len(result.audit_entries):
                    enriched["_audit_entry"] = result.audit_entries[i]
                if i < len(result.is_flagged):
                    enriched["is_flagged"] = result.is_flagged[i]
                if i < len(result.iteration_counts):
                    enriched["_opus_iterations"] = result.iteration_counts[i]
                enriched_tasks.append(enriched)

            pool.tasks = json.dumps(enriched_tasks, ensure_ascii=False, default=str)
            pool.specs = json.dumps(result.specs, ensure_ascii=False, default=str)
            pool.status = result.status  # 'ready' или 'partial'
            pool.valid_count = (
                sum(1 for f in result.is_flagged if not f)
                if result.is_flagged else len(result.tasks)
            )
            ttl_days = 7 if result.status == "partial" else 30
            pool.expires_at = datetime.utcnow() + timedelta(days=ttl_days)
            db.session.commit()
            logger.info("Пул #%s заполнен: статус=%s", pool_id, pool.status)

        except Exception as exc:
            logger.exception("Ошибка заполнения пула #%s: %s", pool_id, exc)
            try:
                pool = db.session.get(TaskPool, pool_id)
                if pool:
                    pool.status = "failed"
                    pool.expires_at = datetime.utcnow() - timedelta(days=1)
                    db.session.commit()
            except Exception:
                logger.exception("Не удалось отметить пул #%s как failed", pool_id)
                db.session.rollback()
