# -*- coding: utf-8 -*-
"""
Step 1 пайплайна «Задачи дня» — планировщик (Claude Sonnet 4.6).

Отправляет профиль ученика в планировщика, получает 10 спецификаций задач
(spec'ов) и валидирует их структурно через `validate_gemini_plan()`.

При сбое (HTTP 402 баланс, 429 rate-limit, 5xx, JSON-parse, validation)
**бросает** ``GeminiPlanError`` с классифицированной категорией и человеко-
читаемым сообщением. Это критично: оркестратор и UI получают РЕАЛЬНУЮ
причину сбоя, а не обобщённое "вернул 0 specs".
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any, Dict, List, Optional

from pipeline.openrouter_client import OpenRouterClient, OpenRouterError, TokenUsage
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
_GEMINI_MODEL = "anthropic/claude-sonnet-4.6"


# ──────────────────────────────────────────────────────────────────────
# Классифицированная ошибка планировщика
# ──────────────────────────────────────────────────────────────────────


class GeminiPlanError(Exception):
    """Step 1 PLAN failed with a known, classified reason.

    Оркестратор ловит это исключение и пишет ``str(self)`` в
    ``PipelineResult.error`` и далее в ``DailyGenerationJob.error_message``
    + ``DailyTaskSet.reason_summary``, чтобы UI показал *настоящую* причину
    (HTTP-код, parse-error, validation-issue) — а не обобщённое
    "Gemini вернул 0 specs".
    """

    def __init__(
        self,
        message: str,
        category: str = "unknown",
        status_code: int = 0,
        body_snippet: str = "",
    ):
        super().__init__(message)
        # 'http_402' | 'http_429' | 'http_4xx' | 'http_5xx' |
        # 'network'  | 'parse'    | 'validate' | 'unknown'
        self.category = category
        self.status_code = status_code
        self.body_snippet = body_snippet


def _classify_openrouter_error(exc: OpenRouterError) -> str:
    """Map HTTP status from OpenRouterError to short human category."""
    code = getattr(exc, "status_code", 0) or 0
    if code == 402:
        return "http_402"          # payment required (balance / credit limit)
    if code == 429:
        return "http_429"          # rate limit
    if 400 <= code < 500:
        return f"http_{code}"
    if 500 <= code < 600:
        return f"http_{code}"
    return "network"


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
    slot_alloc = profile.get("slot_allocation") or {
        "measured": 10,
        "calibration": 0,
    }
    completeness = float(profile.get("profile_completeness", 1.0) or 1.0)
    return prompt.format(
        weak_topics=json.dumps(profile["weak_topics"], ensure_ascii=False, indent=2),
        strong_topics=json.dumps(profile["strong_topics"], ensure_ascii=False, indent=2),
        class_level=profile["class_level"],
        class_expected_level=profile["class_expected_level"],
        TOPICS_REFERENCE=json.dumps(topics_ref, ensure_ascii=False, indent=2),
        slot_allocation=json.dumps(slot_alloc, ensure_ascii=False),
        profile_completeness=f"{completeness:.2f}",
    )


# ── основная функция ─────────────────────────────────────────────────────


async def generate_gemini_plan(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Сгенерировать 10 спецификаций задач через планировщика.

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
        ``difficulty_level``, …).

    Raises
    ------
    GeminiPlanError
        При сбое OpenRouter, парсинга JSON или валидации структуры.
        ``str(exc)`` содержит человекочитаемое объяснение (включая HTTP-код).
    """
    class_level = profile["class_level"]
    topics_ref = _build_topics_reference(class_level)
    formatted_prompt = _format_prompt(profile, topics_ref)

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": formatted_prompt},
    ]

    # ── вызов планировщика через OpenRouter ──────────────────────────
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
    except OpenRouterError as exc:
        # Classified HTTP / API error — propagate with status_code & snippet
        category = _classify_openrouter_error(exc)
        body_snippet = (getattr(exc, "body", "") or "")[:300]
        logger.exception(
            "Step 1 PLAN — OpenRouter call to %s failed: status=%s category=%s body=%s",
            _GEMINI_MODEL, exc.status_code, category, body_snippet,
        )
        if category == "http_402":
            human = (
                "Закончился баланс OpenRouter (HTTP 402). "
                "Пополни счёт на openrouter.ai/credits и попробуй снова."
            )
        elif category == "http_429":
            human = (
                "Слишком много запросов к OpenRouter (HTTP 429). "
                "Подожди минуту и повтори."
            )
        elif category.startswith("http_5"):
            human = (
                f"Временный сбой OpenRouter ({exc.status_code}). "
                "Повтори через минуту."
            )
        elif category.startswith("http_4"):
            human = (
                f"Ошибка запроса к OpenRouter ({exc.status_code}). "
                "Проверь конфигурацию."
            )
        else:
            human = f"Сбой связи с OpenRouter: {exc}"
        raise GeminiPlanError(
            human, category=category,
            status_code=exc.status_code, body_snippet=body_snippet,
        ) from exc
    except Exception as exc:
        # Network / timeout / asyncio.CancelledError / etc.
        logger.exception(
            "Step 1 PLAN — call to %s crashed: %s",
            _GEMINI_MODEL, exc,
        )
        raise GeminiPlanError(
            f"Сбой при вызове планировщика: {type(exc).__name__}: {exc}",
            category="network",
        ) from exc

    logger.info(
        "Gemini plan — токены: %d in / %d out, стоимость: $%.6f",
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
    )

    logger.info(
        "Gemini plan — raw response длина: %d символов",
        len(raw_response) if raw_response else 0,
    )

    # DEBUG: dump raw response to file for inspection
    try:
        with open("_gemini_last_response.txt", "w", encoding="utf-8") as _f:
            _f.write(raw_response or "(EMPTY)")
    except Exception:
        pass

    # ── валидация ────────────────────────────────────────────────────
    validation: GeminiPlanValidation = validate_gemini_plan(raw_response)

    if not validation.valid:
        err_summary = "; ".join(validation.all_errors[:5]) or "validation failed"
        logger.error(
            "Gemini plan — ошибки валидации (%d): %s",
            len(validation.all_errors), err_summary,
        )
        tail = raw_response[-800:] if raw_response else "(EMPTY)"
        logger.error("Gemini raw response END (last 800 chars): %s", tail)
        raise GeminiPlanError(
            f"Ответ модели не прошёл валидацию: {err_summary}",
            category="validate",
            body_snippet=tail[:300],
        )

    # ── парсинг JSON ─────────────────────────────────────────────────
    parsed: Optional[Dict[str, Any]] = extract_json_safe(raw_response)
    if parsed is None or "specs" not in parsed:
        raise GeminiPlanError(
            "Не удалось извлечь JSON со spec'ами из ответа модели",
            category="parse",
            body_snippet=(raw_response or "")[-300:],
        )

    specs: List[Dict[str, Any]] = parsed["specs"]
    if not isinstance(specs, list) or len(specs) != 10:
        raise GeminiPlanError(
            f"Модель вернула {len(specs) if isinstance(specs, list) else 'не-list'} spec'ов вместо 10",
            category="validate",
        )

    logger.info(
        "Gemini plan — OK: %d specs, cost=$%.4f",
        len(specs), usage.cost_usd,
    )
    return specs
