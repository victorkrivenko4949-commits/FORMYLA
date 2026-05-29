# -*- coding: utf-8 -*-
"""
Step 1 пайплайна «Задачи дня» — Gemini 2.5 Pro (планировщик).

Отправляет профиль ученика в Gemini, получает 10 спецификаций задач (spec'ов)
и валидирует их структурно через `validate_gemini_plan()`.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from pipeline.openrouter_client import OpenRouterClient, TokenUsage
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE
from services.taxonomy_grade6 import get_all_subtopics as get_grade6_subtopics
from services.topic_taxonomy import get_all_subtopics_for_grade

from .validators import (
    GeminiPlanValidation,
    extract_json_safe,
    validate_gemini_plan,
)

logger = logging.getLogger(__name__)

# ── модель ────────────────────────────────────────────────────────────────
# Step 1 PLAN: Claude Sonnet 4.5 — base-модель без reasoning. Reasoning-
# флагманы (gpt-5.5-pro, gemini-3.1-pro) на стриминге 4-5 минут регулярно
# роняют соединение через нестабильный интернет. Sonnet 4.5 уже в проде
# в config/models.py:21 (ANALYZER_MODEL), стабильно отдаёт JSON за 5-15s.
_GEMINI_MODEL = "anthropic/claude-sonnet-4.5"

# ── helpers ───────────────────────────────────────────────────────────────


def _build_topics_reference(class_level: int) -> Dict[str, Any]:
    """Построить `TOPICS_REFERENCE` — словарь «тема → подтемы» для класса.

    Используемые источники в зависимости от класса:

    *   5 класс — `services/topic_taxonomy.py` (фильтр по grade=5)
    *   6 класс — `services/taxonomy_grade6.py` (специализированный справочник)
    *   7–11    — `services/adaptive_topics_registry.py` (7 тем на класс)
    """
    if class_level == 6:
        raw = get_grade6_subtopics()  # [(topic, key, label), ...]
        ref: Dict[str, Any] = {}
        for topic, key, label in raw:
            ref.setdefault(topic, []).append({"key": key, "label": label})
        return ref

    if class_level <= 5:
        raw = get_all_subtopics_for_grade(class_level)  # [(topic, subtopic), ...]
        ref: Dict[str, Any] = {}
        for topic, subtopic in raw:
            ref.setdefault(topic, []).append(subtopic)
        return ref

    # 7–11 классы — ADAPTIVE_TOPICS_BY_GRADE
    topics = ADAPTIVE_TOPICS_BY_GRADE.get(class_level, [])
    return {t["db_topic"]: [] for t in topics}


def _load_prompt() -> str:
    """Загрузить содержимое `prompts/gemini_plan.md`."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "gemini_plan.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_prompt(
    profile: Dict[str, Any],
    topics_ref: Dict[str, Any],
) -> str:
    """Подставить переменные в prompt-шаблон."""
    prompt = _load_prompt()
    return prompt.format(
        weak_topics=json.dumps(profile["weak_topics"], ensure_ascii=False, indent=2),
        strong_topics=json.dumps(profile["strong_topics"], ensure_ascii=False, indent=2),
        class_level=profile["class_level"],
        class_expected_level=profile["class_expected_level"],
        TOPICS_REFERENCE=json.dumps(topics_ref, ensure_ascii=False, indent=2),
    )


# ── основная функция ─────────────────────────────────────────────────────


async def generate_gemini_plan(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Сгенерировать 10 спецификаций задач через Gemini 2.5 Pro.

    Параметры
    ---------
    profile : dict
        Результат `build_profile(user_id)` — содержит ``weak_topics``,
        ``strong_topics``, ``class_level``, ``class_expected_level`` и пр.

    Возвращает
    ----------
    list[dict]
        10 валидированных spec'ов (каждый — словарь с ключами ``position``,
        ``slot_kind``, ``subject``, ``topic``, ``subtopic``,
        ``difficulty_level``, …)  либо пустой список в случае ошибки.
    """
    class_level = profile["class_level"]
    topics_ref = _build_topics_reference(class_level)
    formatted_prompt = _format_prompt(profile, topics_ref)

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": formatted_prompt},
    ]

    # ── вызов планировщика через OpenRouter ──────────────────────────
    # Любые исключения (httpx timeout, 4xx/5xx, network, asyncio.CancelledError)
    # ловим здесь и возвращаем []. Это критично: фоновый тред job-а раньше
    # падал молча и оставлял state='running' навсегда.
    raw_response: str
    usage: TokenUsage

    try:
        async with OpenRouterClient() as client:
            raw_response, usage = await client.chat(
                model=_GEMINI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=16384,
            )
    except Exception as exc:
        logger.exception(
            "Step 1 PLAN — call to %s failed: %s. Returning [] so the "
            "orchestrator can mark the job as failed instead of hanging "
            "in state='running' forever.",
            _GEMINI_MODEL,
            exc,
        )
        return []

    logger.info(
        "Gemini plan — токены: %d in / %d out, стоимость: $%.6f",
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
    )

    logger.info("Gemini plan — raw response длина: %d символов", len(raw_response) if raw_response else 0)

    # DEBUG: dump raw response to file for inspection
    try:
        with open("_gemini_last_response.txt", "w", encoding="utf-8") as _f:
            _f.write(raw_response or "(EMPTY)")
    except Exception:
        pass

    # ── валидация ────────────────────────────────────────────────────
    validation: GeminiPlanValidation = validate_gemini_plan(raw_response)

    if not validation.valid:
        logger.error(
            "Gemini plan — ошибки валидации (%d): %s",
            len(validation.all_errors),
            "; ".join(validation.all_errors),
        )
        logger.error("Gemini raw response END (last 800 chars): %s", raw_response[-800:] if raw_response else "(EMPTY)")
        return []

    # ── парсинг JSON ─────────────────────────────────────────────────
    parsed: Optional[Dict[str, Any]] = extract_json_safe(raw_response)
    if parsed is None or "specs" not in parsed:
        logger.error("Gemini plan — не найден ключ 'specs' после успешной валидации")
        return []

    specs: List[Dict[str, Any]] = parsed["specs"]
    logger.info(
        "Gemini plan — OK: %d specs, cost=$%.4f",
        len(specs),
        usage.cost_usd,
    )
    return specs
