# -*- coding: utf-8 -*-
"""
Step 4 пайплайна «Задачи дня» — фикс одной задачи.

Получает (spec, previous_task, audit_report) для ОДНОЙ задачи, которая
получила verdict="needs_fix", и перегенерирует её исправленной версией.

2026-06-25: добавлен JSON-retry loop + эскалация на сильную модель +
level-scaled max_tokens, чтобы fix никогда не возвращал None из-за markdown/обрезки JSON.
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

from services.openrouter_client import OpenRouterClient, TokenUsage, make_token_usage
from .validators import (
    OpusFixValidation,
    extract_json_safe,
    validate_opus_fix,
)

logger = logging.getLogger(__name__)

# ── модели ────────────────────────────────────────────
# All models now use DeepSeek API directly (no OpenRouter).
# DeepSeek Chat v3.1 is fast (3-4s), supports json_object response_format,
# and costs significantly less than Claude Sonnet via OpenRouter.
_FIX_MODEL_EASY = "deepseek/deepseek-chat-v3.1"
_FIX_MODEL_HARD = "deepseek/deepseek-chat-v3.1"
_FIX_MODEL_ESCALATION = "deepseek/deepseek-chat-v3.1"
_FIX_HARD_THRESHOLD = 4
_OPUS_FIX_MODEL = _FIX_MODEL_HARD  # алиас для совместимости

# JSON-mode: заставляем модель вернуть чистый JSON без markdown.
_JSON_RESPONSE_FORMAT = {"type": "json_object"}
_MAX_JSON_RETRIES = 3


def _max_tokens_for_level(difficulty_level: Any) -> int:
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    if lvl >= 6:
        return 8192
    if lvl >= 4:
        return 6144
    return 4096


def _pick_model(difficulty_level: Any) -> str:
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    return _FIX_MODEL_HARD if lvl >= _FIX_HARD_THRESHOLD else _FIX_MODEL_EASY


# ── helpers ───────────────────────────────────────────
def _load_prompt() -> str:
    prompt_path = os.path.join(
        os.path.dirname(__file__), "prompts", "opus_fix.md",
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_fix_prompt(
    spec: Dict[str, Any],
    previous_task: Dict[str, Any],
    audit_report: Dict[str, Any],
) -> str:
    prompt = _load_prompt()
    input_data = {
        "spec": spec,
        "previous_task": previous_task,
        "audit_report": audit_report,
    }
    input_json = json.dumps(input_data, ensure_ascii=False, indent=2)
    return prompt.replace(
        '{ "spec": {...}, "previous_task": {...}, "audit_report": {...} }',
        input_json,
    )


def _coerce_fixed_task(parsed: Any) -> Optional[Dict[str, Any]]:
    """Извлечь исправленную задачу из разных форм ответа модели."""
    if not isinstance(parsed, dict):
        return None
    task = parsed.get("task")
    if isinstance(task, dict) and task:
        return task
    # Модель иногда кладёт поля задачи прямо в корень.
    if parsed.get("task_text") or parsed.get("correct_answer"):
        return parsed
    for _alt in ("fixed_task", "result", "data"):
        _v = parsed.get(_alt)
        if isinstance(_v, dict) and _v:
            return _v
    return None


# ── основная функция ────────────────────────────────
async def _call_fix_model(
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
) -> tuple[Optional[Dict[str, Any]], Any]:
    """Один вызов модели + валидация. Возвращает (task|None, usage)."""
    async with OpenRouterClient() as client:
        raw_response, usage = await client.async_chat(
            model=model,
            messages=messages,
            temperature=0.4,
            max_tokens=max_tokens,
            response_format=_JSON_RESPONSE_FORMAT,
        )
    validation: OpusFixValidation = validate_opus_fix(raw_response)
    if not validation.valid:
        logger.warning(
            "fix(%s) — валидация не прошла: %s",
            model, "; ".join(validation.errors)[:300],
        )
        return None, usage
    parsed = extract_json_safe(raw_response)
    fixed = _coerce_fixed_task(parsed)
    if fixed is None:
        logger.warning("fix(%s) — не найден 'task' в ответе", model)
    return fixed, usage


async def fix_single_task(
    spec: Dict[str, Any],
    previous_task: Dict[str, Any],
    audit_report: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Исправить ОДНУ задачу с retry + эскалацией на сильную модель.

    Никогда не сдаётся с первого раза: делает до _MAX_JSON_RETRIES попыток,
    последняя из которых — на самой сильной модели (escalation).
    """
    formatted_prompt = _format_fix_prompt(spec, previous_task, audit_report)
    difficulty = spec.get("difficulty_level")
    max_tokens = _max_tokens_for_level(difficulty)
    base_model = _pick_model(difficulty)
    position = audit_report.get("position", "?")

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": formatted_prompt},
    ]

    for attempt in range(1, _MAX_JSON_RETRIES + 1):
        # На последней попытке эскалируем на сильную модель.
        model = _FIX_MODEL_ESCALATION if attempt == _MAX_JSON_RETRIES else base_model
        try:
            fixed, usage = await _call_fix_model(model, messages, max_tokens)
        except Exception as exc:
            logger.warning(
                "fix — position=%s, попытка %d/%d, ошибка вызова (%s): %s",
                position, attempt, _MAX_JSON_RETRIES, model, exc,
            )
            continue
        if fixed is not None:
            logger.info(
                "fix — OK: position=%s, попытка %d, model=%s, cost=$%.4f",
                position, attempt, model, getattr(usage, "cost_usd", 0.0),
            )
            return fixed
        # Добавляем корректирующую инструкцию и повторяем.
        messages.append({
            "role": "user",
            "content": (
                "Предыдущий ответ был невалидным. Верни СТРОГО один чистый JSON-объект "
                "вида {\"task\": {\"task_text\": ..., \"correct_answer\": ..., "
                "\"solution\": ..., \"hints\": [...]}} без markdown, комментариев и обрезки."
            ),
        })
        logger.warning(
            "fix — position=%s, попытка %d/%d неудачна, повтор",
            position, attempt, _MAX_JSON_RETRIES,
        )

    logger.error("fix — position=%s: все %d попыток провалились", position, _MAX_JSON_RETRIES)
    return None
