# -*- coding: utf-8 -*-
"""
Meta Reviewer service: reviews complete 5-problem variant for coherence.
Called ONCE after all 5 problems are generated and individually approved.
"""
import json
import logging

from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

from config.models import META_REVIEWER_MODEL as MODEL, META_REVIEWER_TEMPERATURE as TEMPERATURE
MAX_META_RETRIES = 2

SYSTEM_MSG = (
    'Ты — главный редактор олимпиадного сборника. '
    'Проверь ВАРИАНТ ЦЕЛИКОМ (5 задач) на внутреннюю согласованность.'
)


def review_variant(problems: list, analysis: dict, variant_date: str) -> dict:
    """
    Review a complete variant (5 problems) for internal consistency.

    Args:
        problems: list of 5 dicts with statement, answer, topic, difficulty
        analysis: analysis profile dict
        variant_date: date string

    Returns dict with verdict, checks, issues, reject_positions, suggestions.
    """
    prompt = _build_prompt(problems, analysis, variant_date)

    result = openrouter.chat(
        model=MODEL,
        messages=[
            dict(role="system", content=SYSTEM_MSG),
            dict(role="user", content=prompt)
        ],
        temperature=TEMPERATURE,
        max_tokens=2048,
    )

    content = result["content"]
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.error(f"[MetaReview] JSON parse error: {content[:200]}")
        raise ValueError("MetaReview returned invalid JSON")

    # Ensure all expected keys exist
    for key in ["theme_diversity", "difficulty_progression", "style_consistency",
               "no_overlaps", "balance_ok"]:
        if key not in data:
            data[key] = True

    data.setdefault("issues", [])
    data.setdefault("reject_positions", [])
    data.setdefault("suggestions", [])

    # Override verdict based on checks
    all_ok = all(data.get(k, True) for k in [
        "theme_diversity", "difficulty_progression",
        "style_consistency", "no_overlaps", "balance_ok"
    ])
    if all_ok and not data.get("reject_positions"):
        data["verdict"] = "approve"
    else:
        data["verdict"] = "reject"

    data["_usage"] = result["usage"]
    data["_cost"] = result["cost_usd"]

    openrouter.log_cost_to_db('meta_review', MODEL, result['usage'], result['cost_usd'])
    logger.info(
        f"[MetaReview] verdict={data['verdict']} "
        f"reject_pos={data['reject_positions']} "
        f"${{result['cost_usd']:.4f}}"
    )
    return data


def _build_prompt(problems: list, analysis: dict, variant_date: str) -> str:
    """Build the meta review prompt with all 5 problems."""
    sep = chr(9552) * 51
    olympiad = analysis.get("olympiad", "")
    grade = analysis.get("grade", "")
    round_name = analysis.get("round", "")
    style_notes = json.dumps(analysis.get("style_notes", dict()), ensure_ascii=False)
    themes_dist = json.dumps(analysis.get("themes_distribution", dict()), ensure_ascii=False)
    predicted = analysis.get("predicted_variant", [])
    expected_diffs = ", ".join(str(p.get("difficulty", "?")) for p in predicted)

    header = (
        f"ОЛИМПИАДА: {olympiad}, {grade} класс, {round_name}\n"
        f"ДАТА ВАРИАНТА: {variant_date}"
    )

    problems_text = ""
    for i, p in enumerate(problems, 1):
        topic = p.get("topic", "?")
        diff = p.get("difficulty", "?")
        stmt = p.get("statement", "")
        ans = p.get("answer", "")
        problems_text += (
            f"\nЗАДАЧА {i} (тема: {topic}, сложность: {diff}/10):\n"
            f"{stmt}\n"
            f"Ответ: {ans}\n"
        )

    checks = "\n".join([
        "1. ТЕМЫ НЕ ДУБЛИРУЮТСЯ: все 5 задач на разные темы/подтемы",
        "2. СЛОЖНОСТЬ РАСТЁТ: задача 1 легче задачи 5 (допустимо: +-1 уровень)",
        "3. СТИЛЬ ЕДИНЫЙ: все задачи выглядят как один вариант одной олимпиады",
        "4. НЕТ ПЕРЕСЕЧЕНИЙ: задачи не используют одинаковые числа/конструкции",
        "5. БАЛАНС: есть и вычислительные, и доказательные задачи",
    ])

    return (
        f"{header}\n\n"
        f"{sep}\n"
        "ВАРИАНТ (5 задач):\n"
        f"{sep}\n"
        f"{problems_text}\n\n"
        f"{sep}\n"
        "ПРОФИЛЬ ОЛИМПИАДЫ:\n"
        f"{style_notes}\n"
        f"Ожидаемое распределение тем: {themes_dist}\n"
        f"Ожидаемый рост сложности: {expected_diffs}\n\n"
        f"{sep}\n"
        "ПРОВЕРЬ:\n"
        f"{checks}\n\n"
        "Верни ТОЛЬКО валидный JSON с полями: verdict, theme_diversity, "
        "difficulty_progression, style_consistency, no_overlaps, balance_ok, "
        "issues, reject_positions, suggestions"
    )

