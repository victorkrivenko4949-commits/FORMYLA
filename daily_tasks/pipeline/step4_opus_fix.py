# -*- coding: utf-8 -*-
"""
Step 4 пайплайна «Задачи дня» — Claude Opus 4 (фикс одной задачи).

Получает (spec, previous_task, audit_report) для ОДНОЙ задачи, которая
получила verdict="needs_fix", и перегенерирует её исправленной версией,
после чего валидирует результат через `validate_opus_fix()`.
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

from pipeline.openrouter_client import OpenRouterClient, TokenUsage

from .validators import (
    OpusFixValidation,
    extract_json_safe,
    validate_opus_fix,
)

logger = logging.getLogger(__name__)

# ── модель ────────────────────────────────────────────────────────────────
# Step 4 FIX LOOP: Opus 4.8 fast (как и шаг 2 — для быстрой починки)
# Fix cost-routing: лёгкие (L<6) чиним Sonnet 4.6, олимпиадные (L>=6) -> Opus 4.8-fast.
_FIX_MODEL_EASY = "deepseek/deepseek-chat-v3.1"
_FIX_MODEL_HARD = "deepseek/deepseek-chat-v3.1"
_FIX_HARD_THRESHOLD = 6
_OPUS_FIX_MODEL = _FIX_MODEL_HARD  # алиас для совместимости

# ── helpers ───────────────────────────────────────────────────────────────


def _load_prompt() -> str:
    """Загрузить содержимое `prompts/opus_fix.md`."""
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
    """Подставить spec, previous_task и audit_report в prompt-шаблон.

    Внимание: шаблон содержит литеральную JSON-вставку
    ``{ "spec": {...}, "previous_task": {...}, "audit_report": {...} }``,
    поэтому используется ``str.replace()``, а не ``str.format()`` (иначе
    фигурные скобки JSON вызовут ``KeyError``).
    """
    prompt = _load_prompt()
    input_data = {
        "spec": spec,
        "previous_task": previous_task,
        "audit_report": audit_report,
    }
    input_json = json.dumps(
        input_data,
        ensure_ascii=False,
        indent=2,
    )
    # Заменяем литеральный JSON-заполнитель на реальные данные
    return prompt.replace(
        '{ "spec": {...}, "previous_task": {...}, "audit_report": {...} }',
        input_json,
    )


# ── основная функция ─────────────────────────────────────────────────────


async def fix_single_task(
    spec: Dict[str, Any],
    previous_task: Dict[str, Any],
    audit_report: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Исправить ОДНУ задачу через Claude Opus 4 по отчёту аудита.

    Параметры
    ---------
    spec : dict
        Спекуляция (спека) задачи — ``topic``, ``subtopic``,
        ``difficulty_level`` и пр.
    previous_task : dict
        Предыдущая (бракованная) версия задачи с ключами ``task_text``,
        ``correct_answer``, ``solution``, ``hints``.
    audit_report : dict
        Отчёт аудита для этой задачи — ``position``, ``verdict``,
        ``issues`` (список замечаний).

    Возвращает
    ----------
    dict or None
        Исправленная задача (словарь с ключами ``task_text``,
        ``correct_answer``, ``solution``, ``hints``) либо ``None``
        в случае ошибки валидации.
    """
    formatted_prompt = _format_fix_prompt(spec, previous_task, audit_report)

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": formatted_prompt},
    ]

    # ── вызов Opus через OpenRouter ───────────────────────────────────
    raw_response: str
    usage: TokenUsage

    async with OpenRouterClient() as client:
        raw_response, usage = await client.chat(
            model=(_FIX_MODEL_HARD if (int(spec.get("difficulty_level") or 1) >= _FIX_HARD_THRESHOLD) else _FIX_MODEL_EASY),
            messages=messages,
            temperature=0.5,
            max_tokens=4096,
        )

    logger.info(
        "Opus fix — токены: %d in / %d out, стоимость: $%.6f",
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
    )

    # ── валидация ─────────────────────────────────────────────────────
    validation: OpusFixValidation = validate_opus_fix(raw_response)

    if not validation.valid:
        logger.error(
            "Opus fix — ошибки валидации (%d): %s",
            len(validation.errors),
            "; ".join(validation.errors),
        )
        return None

    # ── парсинг JSON ──────────────────────────────────────────────────
    parsed: Optional[Dict[str, Any]] = extract_json_safe(raw_response)
    if parsed is None or "task" not in parsed:
        logger.error("Opus fix — не найден ключ 'task' после успешной валидации")
        return None

    fixed_task: Dict[str, Any] = parsed["task"]
    logger.info(
        "Opus fix — OK: position=%s, cost=$%.4f",
        audit_report.get("position", "?"),
        usage.cost_usd,
    )
    return fixed_task
