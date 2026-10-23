# -*- coding: utf-8 -*-
"""
topic_analyzer.py — Анализ успеваемости ученика по темам.

Предоставляет функцию analyze_topics(user_id), которая:
  - Группирует попытки (CuratorTaskAttempt) по topic
  - Вычисляет метрики: solve_rate, avg_attempts, avg_difficulty_solved, hint_dependency
  - Классифицирует тему: СИЛЬНАЯ / СРЕДНЯЯ / СЛАБАЯ / НЕТ ДАННЫХ
  - Возвращает структурированный dict для API-ответа.
"""

import logging
from typing import Dict, List, Optional, Tuple

from curator.config import (
    TOPIC_STRONG_THRESHOLD,
    TOPIC_MEDIUM_THRESHOLD,
    MIN_ATTEMPTS_FOR_ANALYSIS,
    TOPIC_LABELS_RU,
    DIAG_TOPICS,
)
from models import db
from curator.models import CuratorTaskAttempt

logger = logging.getLogger(__name__)


def analyze_topics(user_id: int) -> dict:
    """Анализировать успеваемость ученика по всем темам.

    Args:
        user_id: ID пользователя.

    Returns:
        dict с ключами:
          - topics: список per-topic метрик
          - summary: общая сводка
    """
    if not user_id:
        return {"topics": [], "summary": _empty_summary()}

    try:
        attempts = (
            CuratorTaskAttempt.query
            .filter_by(user_id=user_id)
            .filter(CuratorTaskAttempt.topic.isnot(None))
            .all()
        )
    except Exception as e:
        logger.error(f"[topic_analyzer] DB error for user {user_id}: {e}")
        return {"topics": [], "summary": _empty_summary()}

    if not attempts:
        return {
            "topics": [_topic_result_no_data(t) for t in DIAG_TOPICS],
            "summary": _empty_summary(),
        }

    # Группируем попытки по темам
    by_topic: Dict[str, List[CuratorTaskAttempt]] = {}
    for a in attempts:
        topic = (a.topic or "").strip().lower()
        if not topic:
            continue
        by_topic.setdefault(topic, []).append(a)

    # Вычисляем метрики для каждой темы
    topics_result = []
    total_attempts = 0
    total_correct = 0

    # Сортируем в порядке DIAG_TOPICS + добавляем любые другие темы
    sorted_topics = _sort_topics(list(by_topic.keys()))

    for topic in sorted_topics:
        topic_attempts = by_topic[topic]
        metrics = _compute_topic_metrics(topic, topic_attempts)
        topics_result.append(metrics)
        total_attempts += metrics["total_attempts"]
        total_correct += metrics["correct_attempts"]

    # Добавляем темы из DIAG_TOPICS, по которым нет данных
    existing = {t["topic"] for t in topics_result}
    for topic in DIAG_TOPICS:
        if topic not in existing:
            topics_result.append(_topic_result_no_data(topic))

    overall_solve_rate = _safe_pct(total_correct, total_attempts)

    # Сортируем финальный результат: СЛАБЫЕ -> СРЕДНИЕ -> СИЛЬНЫЕ -> НЕТ ДАННЫХ
    _sort_key = {
        "СЛАБАЯ": 0,
        "СРЕДНЯЯ": 1,
        "СИЛЬНАЯ": 2,
        "НЕТ ДАННЫХ": 3,
    }
    topics_result.sort(key=lambda t: (_sort_key.get(t["classification"], 99), t["topic"]))

    weak_topics = [t for t in topics_result if t["classification"] == "СЛАБАЯ"]
    medium_topics = [t for t in topics_result if t["classification"] == "СРЕДНЯЯ"]
    strong_topics = [t for t in topics_result if t["classification"] == "СИЛЬНАЯ"]
    no_data_topics = [t for t in topics_result if t["classification"] == "НЕТ ДАННЫХ"]

    return {
        "topics": topics_result,
        "summary": {
            "total_attempts": total_attempts,
            "total_correct": total_correct,
            "overall_solve_rate": round(overall_solve_rate, 1),
            "weak_count": len(weak_topics),
            "medium_count": len(medium_topics),
            "strong_count": len(strong_topics),
            "no_data_count": len(no_data_topics),
            "weak_topics": [t["topic"] for t in weak_topics],
            "medium_topics": [t["topic"] for t in medium_topics],
            "strong_topics": [t["topic"] for t in strong_topics],
            "no_data_topics": [t["topic"] for t in no_data_topics],
        },
    }


# ─── Внутренние функции ────────────────────────────────────────────────────


def _compute_topic_metrics(topic: str, attempts: List[CuratorTaskAttempt]) -> dict:
    """Вычислить метрики для одной темы."""
    total = len(attempts)
    correct = sum(1 for a in attempts if a.is_correct is True)
    incorrect = sum(1 for a in attempts if a.is_correct is False)
    skipped = total - correct - incorrect

    solve_rate = _safe_pct(correct, total)
    avg_attempts = _safe_avg([a.attempts_count for a in attempts])

    # Средняя сложность решённых задач
    solved_difficulties = [
        a.difficulty for a in attempts if a.is_correct is True and a.difficulty is not None
    ]
    avg_difficulty_solved = _safe_avg(solved_difficulties) if solved_difficulties else 0.0

    # Процент попыток, в которых использовались подсказки (hints_used > 0)
    hint_dependency = _safe_pct(
        sum(1 for a in attempts if (a.hints_used or 0) > 0),
        total,
    )

    # Среднее количество использованных подсказок
    avg_hints_used = _safe_avg([a.hints_used or 0 for a in attempts])

    classification = _classify_topic(solve_rate, total)

    return {
        "topic": topic,
        "label": TOPIC_LABELS_RU.get(topic, topic.capitalize()),
        "total_attempts": total,
        "correct_attempts": correct,
        "incorrect_attempts": incorrect,
        "skipped_attempts": skipped,
        "solve_rate": round(solve_rate, 1),
        "avg_attempts": round(avg_attempts, 1),
        "avg_difficulty_solved": round(avg_difficulty_solved, 1),
        "hint_dependency": round(hint_dependency, 1),
        "avg_hints_used": round(avg_hints_used, 1),
        "classification": classification,
    }


def _classify_topic(solve_rate: float, total_attempts: int) -> str:
    """Классифицировать тему по проценту решённых задач.

    Пороги (из config.py):
      - СИЛЬНАЯ:   solve_rate >= TOPIC_STRONG_THRESHOLD (70%)
      - СРЕДНЯЯ:   TOPIC_MEDIUM_THRESHOLD (40%) <= solve_rate < TOPIC_STRONG_THRESHOLD (70%)
      - СЛАБАЯ:    solve_rate < TOPIC_MEDIUM_THRESHOLD (40%)
      - НЕТ ДАННЫХ: total_attempts < MIN_ATTEMPTS_FOR_ANALYSIS (3)
    """
    if total_attempts < MIN_ATTEMPTS_FOR_ANALYSIS:
        return "НЕТ ДАННЫХ"
    if solve_rate >= TOPIC_STRONG_THRESHOLD:
        return "СИЛЬНАЯ"
    if solve_rate >= TOPIC_MEDIUM_THRESHOLD:
        return "СРЕДНЯЯ"
    return "СЛАБАЯ"


def _topic_result_no_data(topic: str) -> dict:
    """Сформировать результат для темы без данных."""
    return {
        "topic": topic,
        "label": TOPIC_LABELS_RU.get(topic, topic.capitalize()),
        "total_attempts": 0,
        "correct_attempts": 0,
        "incorrect_attempts": 0,
        "skipped_attempts": 0,
        "solve_rate": 0.0,
        "avg_attempts": 0.0,
        "avg_difficulty_solved": 0.0,
        "hint_dependency": 0.0,
        "avg_hints_used": 0.0,
        "classification": "НЕТ ДАННЫХ",
    }


def _empty_summary() -> dict:
    """Сформировать пустую сводку."""
    return {
        "total_attempts": 0,
        "total_correct": 0,
        "overall_solve_rate": 0.0,
        "weak_count": 0,
        "medium_count": 0,
        "strong_count": 0,
        "no_data_count": len(DIAG_TOPICS),
        "weak_topics": [],
        "medium_topics": [],
        "strong_topics": [],
        "no_data_topics": list(DIAG_TOPICS),
    }


def _safe_pct(part: int, total: int) -> float:
    """Безопасное вычисление процента."""
    if total <= 0:
        return 0.0
    return part / total * 100.0


def _safe_avg(values: List[float]) -> float:
    """Безопасное вычисление среднего."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _sort_topics(topics: List[str]) -> List[str]:
    """Сортировка тем: сначала DIAG_TOPICS в заданном порядке, потом остальные."""
    ordered = [t for t in DIAG_TOPICS if t in topics]
    others = sorted(t for t in topics if t not in DIAG_TOPICS)
    return ordered + others
