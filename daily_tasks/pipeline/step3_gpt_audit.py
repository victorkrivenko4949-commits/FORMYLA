# -*- coding: utf-8 -*-
# Step 3: ChatGPT-5.5 Pro auditor, 5 parallel workers.
# Splits 10 (spec, task) pairs into 5 batches of 2, runs asyncio.gather.

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
    GPTAuditValidation,
    extract_json_safe,
    validate_gpt_audit,
)

logger = logging.getLogger(__name__)

# AUDIT model: Claude Opus 4.8 Fast — быстрая и стабильная.
# ВАЖНО: раньше тут пробовали разные модели (Sonnet 4.5, GPT-5.5 Pro),
# и все возвращали `{"audit": []}` — НО это было из-за бага в
# _format_audit_prompt(): placeholder "position: 1" не совпадал с "position: N"
# в gpt_audit.md, поэтому модель получала пустой шаблон. Баг исправлен.
_GPT_AUDIT_MODEL = "anthropic/claude-opus-4.8-fast"

# Parallel workers (10 tasks split into 5 batches of 2)
_AUDIT_PARALLEL_WORKERS = 5


def _load_prompt() -> str:
    prompt_path = os.path.join(
        os.path.dirname(__file__), "prompts", "gpt_audit.md",
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_audit_prompt(items: List[Dict[str, Any]]) -> str:
    prompt = _load_prompt()
    items_json = json.dumps(
        {"items": items},
        ensure_ascii=False,
        indent=2,
    )
    # КРИТИЧЕСКИ ВАЖНО: placeholder в prompts/gpt_audit.md использует букву N,
    # а не цифру. Раньше тут был literal с "position": 1 — replace() никогда
    # не срабатывал, и модель получала пустой шаблон вместо реальных задач,
    # из-за чего возвращала `{"audit": []}`.
    placeholder = '{ "items": [{"position": N, "spec": {...}, "task": {...}}, ...] }'
    if placeholder not in prompt:
        # Fallback: просто аппендим items_json в конец, если placeholder не найден.
        logger.warning(
            "AUDIT prompt placeholder not found — appending items_json to prompt"
        )
        return prompt + "\n\nВходные данные (items):\n" + items_json
    return prompt.replace(placeholder, items_json)


def _split_into_batches(
    items: List[Dict[str, Any]],
    n_batches: int,
) -> List[List[Dict[str, Any]]]:
    n = len(items)
    if n_batches <= 0 or n == 0:
        return [items] if items else []
    base = n // n_batches
    rem = n % n_batches
    out: List[List[Dict[str, Any]]] = []
    idx = 0
    for i in range(n_batches):
        size = base + (1 if i < rem else 0)
        if size == 0:
            continue
        out.append(items[idx:idx + size])
        idx += size
    return out


async def _audit_batch(
    client: OpenRouterClient,
    batch_id: int,
    items: List[Dict[str, Any]],
) -> Tuple[int, List[Dict[str, Any]], float]:
    """Audit one batch. Returns (batch_id, audit_entries, cost_usd).
    On error returns synthetic 'needs_fix' entries so pipeline continues."""
    import time as _time_mod
    formatted = _format_audit_prompt(items)
    messages = [
        {
            "role": "system",
            "content": (
                "You output ONLY a single valid JSON object — nothing else. "
                "No markdown code fences, no commentary before or after, no "
                "explanations. Just the JSON, beginning with '{' and ending "
                "with '}'. The 'audit' array length MUST equal the input "
                "'items' array length. Each entry MUST contain position, "
                "verdict, and issues."
            ),
        },
        {"role": "user", "content": formatted},
    ]
    positions_in_batch = [it.get("position") for it in items]
    _t0 = _time_mod.time()
    logger.info(
        "Step 3 AUDIT [batch=%d] START — positions=%s (%d items)",
        batch_id, positions_in_batch, len(items),
    )

    try:
        raw, usage = await client.chat(
            model=_GPT_AUDIT_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
        )
        _dt = _time_mod.time() - _t0
        logger.info(
            "Step 3 AUDIT [batch=%d] HTTP-OK in %.1fs — in=%d out=%d cost=$%.4f",
            batch_id, _dt, usage.input_tokens, usage.output_tokens, usage.cost_usd,
        )
    except Exception as exc:
        logger.error("AUDIT batch %d — HTTP/timeout error: %s", batch_id, exc)
        # synthesize needs_fix for each item so pipeline keeps going
        fallback = [
            {
                "position": it.get("position"),
                "verdict": "needs_fix",
                "issues": [
                    {"severity": "minor",
                     "kind": "audit_error",
                     "message": f"audit batch failed: {exc}"}
                ],
            }
            for it in items
        ]
        return batch_id, fallback, 0.0

    validation: GPTAuditValidation = validate_gpt_audit(raw)
    if not validation.valid:
        # Dump raw response — короткий ответ часто говорит САМ что не так
        # (markdown, refusal, обрезка). Видеть это критически важно.
        raw_preview = (raw or "")[:600].replace("\n", "\\n")
        logger.error(
            "AUDIT batch %d — validation errors (%d): %s | RAW(600 chars)=%r",
            batch_id,
            len(validation.all_errors),
            "; ".join(validation.all_errors),
            raw_preview,
        )
        fallback = [
            {
                "position": it.get("position"),
                "verdict": "needs_fix",
                "issues": [
                    {"severity": "minor",
                     "kind": "audit_invalid_json",
                     "message": "audit returned invalid format"}
                ],
            }
            for it in items
        ]
        return batch_id, fallback, usage.cost_usd

    parsed = extract_json_safe(raw)
    if parsed is None or "audit" not in parsed:
        logger.error("AUDIT batch %d — no 'audit' key in parsed JSON", batch_id)
        fallback = [
            {
                "position": it.get("position"),
                "verdict": "needs_fix",
                "issues": [
                    {"severity": "minor",
                     "kind": "audit_no_audit_key",
                     "message": "audit response missing 'audit' key"}
                ],
            }
            for it in items
        ]
        return batch_id, fallback, usage.cost_usd

    audit_entries: List[Dict[str, Any]] = parsed["audit"]
    verdicts = {}
    for e in audit_entries:
        v = e.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
    detail = ", ".join(f"{v}={n}" for v, n in sorted(verdicts.items()))
    logger.info(
        "Step 3 AUDIT [batch=%d] OK — %d entries (%s) cost=$%.4f",
        batch_id, len(audit_entries), detail, usage.cost_usd,
    )
    return batch_id, audit_entries, usage.cost_usd


async def audit_tasks(
    specs: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Audit 10 tasks via ChatGPT-5.5 Pro using 5 parallel workers.

    Splits 10 (spec, task) pairs into 5 batches of 2, then runs
    asyncio.gather to query OpenRouter in parallel.

    Parameters
    ----------
    specs : list of 10 dicts (from Gemini/GPT plan)
    tasks : list of 10 dicts (from Opus generation)

    Returns
    -------
    list of 10 audit entries, sorted by position. Empty list only if
    counts are mismatched (then orchestrator handles fallback).
    """
    if len(specs) != len(tasks):
        logger.error(
            "AUDIT — mismatch: %d specs vs %d tasks",
            len(specs), len(tasks),
        )
        return []

    items = [
        {"position": i + 1, "spec": spec, "task": task}
        for i, (spec, task) in enumerate(zip(specs, tasks))
    ]

    batches = _split_into_batches(items, _AUDIT_PARALLEL_WORKERS)
    logger.info(
        "AUDIT — launching %d parallel workers for %d items (batches: %s)",
        len(batches), len(items), [len(b) for b in batches],
    )

    async with OpenRouterClient() as client:
        coros = [
            _audit_batch(client, idx, batch)
            for idx, batch in enumerate(batches)
        ]
        results = await asyncio.gather(*coros, return_exceptions=False)

    # merge all entries and sort by position
    all_entries: List[Dict[str, Any]] = []
    total_cost = 0.0
    for _batch_id, entries, cost in results:
        all_entries.extend(entries)
        total_cost += cost

    all_entries.sort(key=lambda e: e.get("position", 0))

    logger.info(
        "AUDIT — DONE: %d entries, total_cost=$%.4f (5 parallel workers)",
        len(all_entries),
        total_cost,
    )
    return all_entries
