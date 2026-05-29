# -*- coding: utf-8 -*-
"""
Step 2 пайплайна «Задачи дня» — Gemini 3.1 Pro (параллельный генератор задач).

Принимает 10 спецификаций от Step 1, для КАЖДОЙ независимо вызывает LLM
в 5 параллельных потоках через ``asyncio.Semaphore(5)``. Каждый воркер
обрабатывает свою спеку независимо: упавший воркер не валит остальных,
а возвращает «синтетическую» заглушку с правильной position — на Step 3
её пометят ``needs_fix``, на Step 4 — попытаются восстановить.

Зачем переехали с Opus 4.8 на Gemini 3.1 Pro:
* Раньше один batch-запрос на 10 задач шёл ~120-180 сек и иногда обрывался
  по 90s-таймауту, обнуляя ВСЕ 10 позиций.
* Параллельный режим 5×2 даёт ~25-40 сек wall-time и устойчивость к
  частичным сбоям (упавшие позиции лечит Step 4).
* Gemini 3.1 Pro быстрее Opus в 3-4 раза и в проде уже подтверждён рабочим
  (см. services/drawing_service.py:60 — MODEL_CRITIC).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any, Dict, List, Optional, Tuple

from pipeline.openrouter_client import OpenRouterClient, TokenUsage

from .validators import (
    OpusGenerationValidation,
    extract_json_safe,
    validate_opus_generation,
)

logger = logging.getLogger(__name__)

# ── модель ────────────────────────────────────────────────────────────────
# Step 2 GENERATE: Claude Sonnet 4.5 — base, без reasoning. Раньше пробовали
# gemini-3.1-pro-preview (45s × 10 = 450s суммарно) и opus-4.8-fast (batch-180s),
# обе нестабильны на медленном интернете. Sonnet 4.5 точно следует JSON-схеме
# и кладёт одну задачу за ~5-10s; в проде используется в daily_pool/generator.py.
_OPUS_MODEL = "anthropic/claude-sonnet-4.5"

# 5 параллельных потоков: 10 specs распределяются по 5 воркерам (~2 spec
# на воркер при чистом распараллеливании). Семафор ограничивает число
# одновременных HTTP-запросов к OpenRouter, чтобы не словить 429.
_PARALLEL_WORKERS = 5


# ── helpers ───────────────────────────────────────────────────────────────


def _load_prompt() -> str:
    """Загрузить содержимое `prompts/opus_generate.md`."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "opus_generate.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_prompt_for_single_spec(spec: Dict[str, Any]) -> str:
    """Подставить ОДНУ спецификацию в prompt-шаблон.

    Промпт ожидает ``{"specs": [...]}`` на входе и ``{"tasks": [...]}``
    на выходе. Здесь подсовываем массив длины 1.
    """
    prompt = _load_prompt()
    specs_json = json.dumps(
        {"specs": [spec]},
        ensure_ascii=False,
        indent=2,
    )
    return prompt.replace('{ "specs": [...] }', specs_json)


def _synthesize_fallback_task(spec: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Сформировать пустую задачу-заглушку с правильной позицией.

    Это нужно, чтобы общий выход Step 2 всегда содержал ровно 10 элементов
    (требование ``validate_opus_generation``). Step 3 пометит её
    ``needs_fix``, Step 4 попробует регенерировать.
    """
    pos = spec.get("position")
    return {
        "position": pos,
        "task_text": (
            f"[GEN_FAILED] Не удалось сгенерировать задачу для позиции {pos}. "
            f"Причина: {reason}"
        ),
        "correct_answer": "—",
        "solution": "—",
        "hints": ["Будет сгенерировано на шаге исправления."],
        "_generation_failed": True,
        "_failure_reason": reason,
    }


async def _generate_one_spec(
    client: OpenRouterClient,
    semaphore: asyncio.Semaphore,
    spec: Dict[str, Any],
) -> Tuple[Dict[str, Any], float]:
    """Сгенерировать одну задачу под одну спеку.

    Возвращает кортеж (task_dict, cost_usd). При ЛЮБОЙ ошибке (HTTP timeout,
    невалидный JSON, отсутствие нужных полей) — возвращает синтетическую
    заглушку с ``_generation_failed=True`` и cost=0. Это позволяет
    остальным 4 воркерам спокойно доработать.
    """
    import time as _time_mod
    pos = spec.get("position")
    formatted = _format_prompt_for_single_spec(spec)
    messages = [{"role": "user", "content": formatted}]
    topic_short = (spec.get("topic") or "?")[:30]
    subtopic_short = (spec.get("subtopic") or "?")[:30]

    async with semaphore:
        _t0 = _time_mod.time()
        logger.info(
            "Step 2 GENERATE [pos=%s] START — topic=%r subtopic=%r difficulty=L%s",
            pos, topic_short, subtopic_short, spec.get("difficulty_level"),
        )
        try:
            raw, usage = await client.chat(
                model=_OPUS_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
            )
        except Exception as exc:
            _dt = _time_mod.time() - _t0
            logger.exception(
                "Step 2 GENERATE [pos=%s] FAIL after %.1fs — HTTP/network error: %s",
                pos, _dt, exc,
            )
            return _synthesize_fallback_task(spec, f"http_error: {exc}"), 0.0
        _dt = _time_mod.time() - _t0
        logger.info(
            "Step 2 GENERATE [pos=%s] HTTP-OK in %.1fs — in=%d out=%d cost=$%.4f",
            pos, _dt, usage.input_tokens, usage.output_tokens, usage.cost_usd,
        )

    # Парсим ответ — ожидаем {"tasks": [ОДНА задача]}
    parsed = extract_json_safe(raw)
    if parsed is None or not isinstance(parsed, dict):
        logger.error("Step 2 GENERATE — pos=%s — не смогли распарсить JSON", pos)
        return _synthesize_fallback_task(spec, "invalid_json"), usage.cost_usd

    tasks_list = parsed.get("tasks")
    if not isinstance(tasks_list, list) or len(tasks_list) == 0:
        logger.error(
            "Step 2 GENERATE — pos=%s — отсутствует/пустой 'tasks' в ответе",
            pos,
        )
        return _synthesize_fallback_task(spec, "no_tasks_key"), usage.cost_usd

    task = tasks_list[0]
    if not isinstance(task, dict):
        logger.error("Step 2 GENERATE — pos=%s — task не словарь", pos)
        return _synthesize_fallback_task(spec, "task_not_dict"), usage.cost_usd

    # Принудительно фиксируем position на ту, что в спеке (модель иногда
    # ставит position=1 для одиночной задачи независимо от исходной)
    task["position"] = pos

    text_preview = (task.get("task_text") or "")[:120].replace("\n", " ")
    answer_preview = str(task.get("correct_answer") or "")[:60]
    logger.info(
        "Step 2 GENERATE [pos=%s] OK — text=%r  answer=%r",
        pos, text_preview, answer_preview,
    )
    return task, usage.cost_usd


# ── основная функция ─────────────────────────────────────────────────────


async def generate_opus_tasks(specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Сгенерировать 10 задач параллельно через Gemini 3.1 Pro (5 потоков).

    Параметры
    ---------
    specs : list[dict]
        10 спецификаций от Step 1 (каждая содержит ``position``, ``slot_kind``,
        ``subject``, ``topic``, ``subtopic``, ``difficulty_level``, …).

    Возвращает
    ----------
    list[dict]
        10 задач (по одной на каждую спеку, отсортированы по ``position``).
        Сбойные позиции возвращаются как fallback-заглушки с флагом
        ``_generation_failed=True`` — общий список всё равно длины 10, чтобы
        ``validate_opus_generation`` (требует ровно 10) не валился целиком.
        Пустой список — только если на входе не 10 спек или ВСЕ воркеры
        выбросили нерекаверебельную ошибку.
    """
    if not specs:
        logger.error("Step 2 GENERATE — пустой список спек, нечего генерировать")
        return []

    if len(specs) != 10:
        logger.warning(
            "Step 2 GENERATE — получено %d спек вместо ожидаемых 10, всё равно "
            "продолжаем (валидатор может развернуть результат позже)",
            len(specs),
        )

    semaphore = asyncio.Semaphore(_PARALLEL_WORKERS)

    logger.info(
        "Step 2 GENERATE — запуск %d параллельных воркеров (semaphore=%d), "
        "модель=%s",
        len(specs), _PARALLEL_WORKERS, _OPUS_MODEL,
    )

    async with OpenRouterClient() as client:
        coros = [_generate_one_spec(client, semaphore, spec) for spec in specs]
        results = await asyncio.gather(*coros, return_exceptions=False)

    # Разворачиваем результаты
    tasks: List[Dict[str, Any]] = []
    total_cost = 0.0
    failed_positions: List[Any] = []
    for task, cost in results:
        tasks.append(task)
        total_cost += cost
        if task.get("_generation_failed"):
            failed_positions.append(task.get("position"))

    # Сортируем по position для стабильности
    tasks.sort(key=lambda t: t.get("position") or 0)

    logger.info(
        "Step 2 GENERATE — DONE: %d задач (failed=%d at positions %s), "
        "total_cost=$%.4f (5 parallel workers)",
        len(tasks), len(failed_positions), failed_positions, total_cost,
    )

    # ── валидация ─────────────────────────────────────────────────────
    # Формируем единый ответ для совместимости с существующим валидатором,
    # который ожидает строку с JSON {"tasks": [10 элементов]}.
    pseudo_raw = json.dumps({"tasks": tasks}, ensure_ascii=False)
    validation: OpusGenerationValidation = validate_opus_generation(pseudo_raw)

    if not validation.valid:
        # Если упало мало позиций — продолжаем, Step 3/4 их подлечит.
        # Если упало всё — пробрасываем []. Граница — >= 5 валидных задач.
        valid_entries = sum(1 for e in validation.entries if e.valid)
        if valid_entries >= 5:
            logger.warning(
                "Step 2 GENERATE — частичная валидация: %d/10 ok, %d ошибок. "
                "Пропускаем дальше — Step 3 пометит сбойные, Step 4 исправит.",
                valid_entries, len(validation.all_errors),
            )
        else:
            logger.error(
                "Step 2 GENERATE — критическая ошибка: только %d/10 задач "
                "прошли валидацию. Ошибки: %s",
                valid_entries,
                "; ".join(validation.all_errors[:5]),
            )
            return []

    return tasks
