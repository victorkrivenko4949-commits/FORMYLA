# -*- coding: utf-8 -*-
"""
daily_tasks/running_pct.py — достройка профиля по решённым калибровочным задачам.

PR percent_to_level + calibration (ТЗ от 2026-06-08, п.4).

Идея
----
Когда у ученика **нет** ``AdaptiveTestResult`` по теме, мы не знаем точный %.
Но он решает калибровочные задачи в «Задачах дня» — со временем накапливается
история ``TaskSolution`` по этой теме. Эту историю мы можем превратить в
«скользящий процент знания темы» (running_pct), и тогда тема постепенно
переходит из ``measured=False`` в ``measured=True``.

Формула (вариант B из ТЗ — выбран пользователем):
    weight_difficulty = difficulty_level / MAX_LEVEL    # тяжёлая задача весит больше
    weight_recency    = HALF_LIFE_DECAY ** age_in_days  # «забывание» старых ответов
    contribution      = is_correct * weight_difficulty * weight_recency
    denominator       = weight_difficulty * weight_recency  (только за рассмотренные ответы)
    running_pct       = 100 * Σ(contribution) / Σ(denominator)

Минимальный порог `MIN_ANSWERS_FOR_MEASURED` (N=8) — пока ответов меньше,
тема считается «всё ещё калибровочной» (measured=False), но running_pct
уже виден в профиле для логов/UI.

API
---
* :func:`compute_running_pct(answers)` — чистая функция (для тестов),
  принимает список dicts с полями ``is_correct``, ``difficulty_level``,
  ``answered_at`` (datetime) и возвращает (pct, n_answers, measured_flag).
* :func:`compute_topic_running_pct(user_id, db_topic)` — версия,
  ходящая в БД (TaskSolution + AdaptiveTask) и считающая то же самое.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Параметры — все в одном месте для тюнинга ────────────────────────
HALF_LIFE_DAYS: float = 30.0      # за 30 дней вес ответа падает в 2 раза
MAX_DIFFICULTY: int = 4           # шкала задач 1..4 в нашей системе
MIN_ANSWERS_FOR_MEASURED: int = 8 # сколько ответов нужно, чтобы measured=True
MAX_LOOKBACK_DAYS: int = 180      # ответы старше 180 дней не учитываем
MAX_ANSWERS_CONSIDERED: int = 50  # верхняя граница (производительность)


def _decay_weight(answered_at: Optional[datetime], now: datetime) -> float:
    """Экспоненциальное затухание: half-life = HALF_LIFE_DAYS."""
    if answered_at is None:
        return 1.0
    age_days = max(0.0, (now - answered_at).total_seconds() / 86400.0)
    # 0.5 ** (age / half_life)
    return 0.5 ** (age_days / HALF_LIFE_DAYS) if HALF_LIFE_DAYS > 0 else 1.0


def _difficulty_weight(difficulty: Optional[int]) -> float:
    """Вес сложности: lvl 4 весит в 4× больше lvl 1."""
    if difficulty is None:
        # неизвестная сложность -> нейтральный вес = середина шкалы
        return (MAX_DIFFICULTY / 2.0) / MAX_DIFFICULTY
    try:
        d = int(difficulty)
    except (TypeError, ValueError):
        return 0.5
    d = max(1, min(MAX_DIFFICULTY, d))
    return d / MAX_DIFFICULTY


def compute_running_pct(
    answers: Iterable[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Tuple[Optional[float], int, bool]:
    """Посчитать running_pct по списку ответов.

    Параметры
    ---------
    answers : iterable[dict]
        Каждый элемент содержит ключи:
          - ``is_correct`` (bool)
          - ``difficulty_level`` (int 1..4 или 1..8) — опционально
          - ``answered_at`` (datetime) — опционально
    now : datetime
        Текущий момент (для тестов можно подставить фиксированный).

    Возвращает
    ----------
    tuple (running_pct, n_answers_used, measured)

    * ``running_pct`` — float 0..100 или ``None`` если 0 ответов.
    * ``n_answers_used`` — сколько ответов реально учтены (после фильтров).
    * ``measured`` — bool, True если ответов хватило для «уверенного» процента.
    """
    if now is None:
        now = datetime.utcnow()

    cutoff = now - timedelta(days=MAX_LOOKBACK_DAYS)

    # Сортируем answers по answered_at desc (самые свежие первые) и режем
    # до MAX_ANSWERS_CONSIDERED, чтобы не считать на огромных историях.
    def _sort_key(a: Dict[str, Any]):
        ts = a.get("answered_at")
        if isinstance(ts, datetime):
            return ts
        return datetime.min

    sorted_ans = sorted(answers, key=_sort_key, reverse=True)[
        :MAX_ANSWERS_CONSIDERED
    ]

    numerator = 0.0
    denominator = 0.0
    n = 0
    for ans in sorted_ans:
        ts = ans.get("answered_at")
        if isinstance(ts, datetime) and ts < cutoff:
            continue
        wd = _difficulty_weight(ans.get("difficulty_level"))
        wr = _decay_weight(ts if isinstance(ts, datetime) else None, now)
        w = wd * wr
        if w <= 0:
            continue
        # is_correct: трактуем None как False (нет ответа = не зачёт)
        is_correct = 1.0 if bool(ans.get("is_correct")) else 0.0
        numerator += is_correct * w
        denominator += w
        n += 1

    if n == 0 or denominator <= 0:
        return (None, 0, False)

    pct = round(100.0 * numerator / denominator, 2)
    pct = max(0.0, min(100.0, pct))
    measured = n >= MIN_ANSWERS_FOR_MEASURED
    return (pct, n, measured)


# ──────────────────────────────────────────────────────────────────────
# БД-версия (используется из profile.build_profile в будущей версии)
# ──────────────────────────────────────────────────────────────────────


def compute_topic_running_pct(
    user_id: int,
    db_topic: str,
    now: Optional[datetime] = None,
) -> Tuple[Optional[float], int, bool]:
    """Прочитать историю ответов из БД и посчитать running_pct.

    Импорты db/моделей внутри функции — чтобы модуль грузился даже без
    Flask-окружения (нужно для модульных тестов чистой логики).
    """
    try:
        from models import db, TaskSolution, AdaptiveTask  # noqa: WPS433
    except Exception:
        logger.exception(
            "compute_topic_running_pct: не удалось импортировать модели"
        )
        return (None, 0, False)

    rows = (
        db.session.query(
            TaskSolution.is_correct,
            TaskSolution.created_at,
            AdaptiveTask.difficulty_level,
        )
        .join(AdaptiveTask, TaskSolution.task_id == AdaptiveTask.id)
        .filter(
            TaskSolution.user_id == user_id,
            AdaptiveTask.topic == db_topic,
        )
        .order_by(TaskSolution.created_at.desc())
        .limit(MAX_ANSWERS_CONSIDERED)
        .all()
    )

    answers: List[Dict[str, Any]] = [
        {
            "is_correct": row[0],
            "answered_at": row[1],
            "difficulty_level": row[2],
        }
        for row in rows
    ]
    return compute_running_pct(answers, now=now)
