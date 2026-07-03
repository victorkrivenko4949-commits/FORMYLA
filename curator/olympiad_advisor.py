# -*- coding: utf-8 -*-
"""
olympiad_advisor.py — Олимпиадный советник.

Предоставляет функцию recommend_olympiads(user_id), которая:
  - Определяет класс ученика (preferred_grade из User)
  - Запускает анализ тем (Topic Analyzer) для выявления слабых/сильных сторон
  - Сопоставляет слабые темы с subtopic_keys из базы знаний олимпиад
  - Подбирает релевантные олимпиады через services.olympiads_knowledge
  - Генерирует AI-персонализированные рекомендации через DeepSeek
  - Возвращает структурированный dict для API-ответа
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from models import User
from curator.config import (
    OLYMPIAD_MAX_RECOMMENDATIONS,
    TOPIC_LABELS_RU,
    DIAG_TOPICS,
)
from curator.topic_analyzer import analyze_topics
from services.olympiads_knowledge import (
    OLYMPIAD_KNOWLEDGE,
    recommend_olympiads_for,
)
from ai.deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)


# ─── Маппинг тем Куратора → subtopic_keys базы знаний олимпиад ─────────────
# DIAG_TOPICS из config.py: algebra, geometry, combinatorics, number_theory, logic
# OLYMPIAD_KNOWLEDGE использует более дробные subtopic_keys.

TOPIC_TO_SUBTOPIC_KEYS = {
    "algebra": [
        "quadratic_vieta",
        "quadratic_parameters",
        "systems_modules_radicals",
        "systems_parameters_inequalities",
        "trigonometry",
        "trigonometry_mixed",
        "exp_log",
        "functions_graphs_parameters",
        "inequalities_estimates",
        "polynomials_sequences_fe",
    ],
    "geometry": [
        "geometry_similarity_circle",
        "geometry_triangle_circle",
        "stereometry_vectors",
        "stereometry_coordinates_vectors",
    ],
    "combinatorics": [
        "combinatorics_graphs",
        "combinatorics_logic_invariants",
        "combinatorics_graphs_probability",
        "combinatorics_graphs_logic",
    ],
    "number_theory": [
        "divisibility_remainders",
        "number_theory_diophantine",
        "number_theory",
        "number_theory_advanced",
    ],
    "logic": [
        "logic_invariants",
        "logic_invariants_strategies",
        "logic_sets_functions",
        "combinatorics_logic_invariants",
    ],
}

# Обратный маппинг: subtopic_key → curator topic
_SUBTOPIC_TO_TOPIC: Dict[str, str] = {}
for _topic, _keys in TOPIC_TO_SUBTOPIC_KEYS.items():
    for _k in _keys:
        _SUBTOPIC_TO_TOPIC[_k] = _topic


def recommend_olympiads(user_id: int, grade: Optional[int] = None) -> dict:
    """Подобрать олимпиады для ученика на основе анализа тем.

    Args:
        user_id: ID пользователя.
        grade: Класс (5-11). Если None — берётся из User.preferred_grade.

    Returns:
        dict с ключами:
          - user_id: int
          - grade: int (класс)
          - olympiad_knowledge: dict (slug -> info) для всех подходящих олимпиад
          - recommendations: список рекомендаций (до OLYMPIAD_MAX_RECOMMENDATIONS)
          - topic_analysis: результаты анализа тем
          - ai_advice: str — AI-персонализированный совет (или None)
    """
    if not user_id:
        return _empty_response("user_id is required")

    # ── 1. Определяем класс ──────────────────────────────────────────────────
    try:
        user = User.query.get(user_id)
    except Exception as e:
        logger.error(f"[olympiad_advisor] DB error fetching user {user_id}: {e}")
        return _empty_response("User not found")

    if not user:
        return _empty_response("User not found")

    if grade is None:
        grade = user.preferred_grade

    if not grade:
        return {
            "user_id": user_id,
            "grade": None,
            "error": "grade_not_set",
            "message": "Укажите класс в профиле (preferred_grade), чтобы получить рекомендации.",
            "recommendations": [],
            "topic_analysis": None,
            "ai_advice": None,
        }

    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return _empty_response(f"Invalid grade: {grade}")

    if grade_int < 5 or grade_int > 11:
        return _empty_response(f"Grade {grade_int} is out of range (5-11)")

    # ── 2. Анализ тем ────────────────────────────────────────────────────────
    topic_analysis = analyze_topics(user_id)
    weak_topics = topic_analysis.get("summary", {}).get("weak_topics", [])
    medium_topics = topic_analysis.get("summary", {}).get("medium_topics", [])
    strong_topics = topic_analysis.get("summary", {}).get("strong_topics", [])

    # ── 3. Маппинг слабых/средних тем → subtopic_keys ────────────────────────
    weak_subtopic_keys: List[str] = []
    for topic_name in weak_topics + medium_topics:
        keys = TOPIC_TO_SUBTOPIC_KEYS.get(topic_name, [])
        weak_subtopic_keys.extend(keys)

    # ── 4. Подбор олимпиад ────────────────────────────────────────────────────
    recommended_slugs = recommend_olympiads_for(
        grade=grade_int,
        weak_subtopic_keys=weak_subtopic_keys,
        limit=OLYMPIAD_MAX_RECOMMENDATIONS,
    )

    # ── 5. Собираем детальную информацию по каждой рекомендованной олимпиаде ───
    recommendations = []
    olympiad_knowledge = {}

    for slug in recommended_slugs:
        kb = OLYMPIAD_KNOWLEDGE.get(slug)
        if not kb:
            continue

        grade_info = kb.get("by_grade", {}).get(grade_int)
        if not grade_info:
            continue

        # Определяем, какие из curator-слабых тем покрывает эта олимпиада
        covered_weak_topics = []
        for sub_key in grade_info.get("subtopic_keys", []):
            curator_topic = _SUBTOPIC_TO_TOPIC.get(sub_key)
            if curator_topic and curator_topic in set(weak_topics + medium_topics):
                if curator_topic not in covered_weak_topics:
                    covered_weak_topics.append(curator_topic)

        entry = {
            "slug": slug,
            "name": kb.get("name", slug),
            "level": kb.get("level", "unknown"),
            "profile": kb.get("profile", ""),
            "perk": kb.get("perk", ""),
            "format": kb.get("format", ""),
            "grade_focus": grade_info.get("focus", []),
            "must_know": grade_info.get("must_know", []),
            "covered_weak_topics": covered_weak_topics,
            "relevance_score": len(covered_weak_topics),
        }
        recommendations.append(entry)

        olympiad_knowledge[slug] = entry

    # Сортируем по relevance_score (убывание)
    recommendations.sort(key=lambda r: (-r["relevance_score"], r["slug"]))

    # ── 6. AI-персонализированный совет ──────────────────────────────────────
    ai_advice = _generate_ai_advice(
        grade=grade_int,
        weak_topics=weak_topics,
        medium_topics=medium_topics,
        strong_topics=strong_topics,
        recommendations=recommendations,
        topic_analysis=topic_analysis,
    )

    return {
        "user_id": user_id,
        "grade": grade_int,
        "recommendations": recommendations[:OLYMPIAD_MAX_RECOMMENDATIONS],
        "topic_analysis": topic_analysis,
        "ai_advice": ai_advice,
    }


# ─── AI-генерация персонализированного совета ──────────────────────────────


def _generate_ai_advice(
    grade: int,
    weak_topics: List[str],
    medium_topics: List[str],
    strong_topics: List[str],
    recommendations: List[dict],
    topic_analysis: dict,
) -> Optional[str]:
    """Сгенерировать персонализированный совет через DeepSeek."""
    if not recommendations:
        return "Пока нет подходящих рекомендаций. Пройдите диагностику, чтобы получить персональные советы."

    try:
        # Строим контекст для AI
        weak_labels = [TOPIC_LABELS_RU.get(t, t) for t in weak_topics]
        medium_labels = [TOPIC_LABELS_RU.get(t, t) for t in medium_topics]
        strong_labels = [TOPIC_LABELS_RU.get(t, t) for t in strong_topics]

        rec_lines = []
        for r in recommendations:
            focus_str = "; ".join(r.get("grade_focus", []))
            must_str = "; ".join(r.get("must_know", []))
            rec_lines.append(
                f"- {r['name']} ({r['level']}): фокус — {focus_str}. "
                f"Надо уметь: {must_str}. Льгота: {r['perk']}."
            )

        system_prompt = (
            "Ты — опытный олимпиадный тренер по математике. "
            "Дай ученику персонализированный совет: какие олимпиады выбрать, "
            "на какие темы сделать упор, как распределить подготовку. "
            "Ответ напиши на русском языке, дружелюбно, но по делу, 3-5 предложений. "
            "Не используй markdown, просто текст."
        )

        user_prompt = (
            f"Ученик {grade} класса.\n"
            f"Сильные темы: {', '.join(strong_labels) if strong_labels else 'пока не определены'}.\n"
            f"Средние темы: {', '.join(medium_labels) if medium_labels else 'нет'}.\n"
            f"Слабые темы: {', '.join(weak_labels) if weak_labels else 'нет данных'}.\n\n"
            f"Подходящие олимпиады:\n"
            + "\n".join(rec_lines)
            + "\n\nДай краткий персональный совет."
        )

        client = DeepSeekClient()
        advice = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=500,
        )

        if advice and advice.strip():
            return advice.strip()

    except Exception as e:
        logger.warning(f"[olympiad_advisor] AI advice generation failed: {e}")

    return None


# ─── Вспомогательные функции ───────────────────────────────────────────────


def _empty_response(message: str) -> dict:
    """Сформировать пустой ответ с сообщением об ошибке."""
    return {
        "user_id": None,
        "grade": None,
        "error": message,
        "recommendations": [],
        "topic_analysis": None,
        "ai_advice": None,
    }
