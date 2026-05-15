# -*- coding: utf-8 -*-
"""
Calibrator — калибровка уровня сложности через openai/gpt-4o.

Анти-self-bias: Generator (deepseek) ≠ Calibrator (gpt-4o).
НЕ решает задачу до конца — оценивает по идеям.
"""
from __future__ import annotations

import logging

from pipeline.config import (
    CALIBRATOR_MODEL,
    CALIBRATOR_TEMPERATURE,
    CALIBRATOR_MAX_TOKENS,
    CALIBRATOR_CONFIDENCE_MIN,
    LEVEL_DESCRIPTIONS,
)
from pipeline.openrouter_client import OpenRouterClient, TokenUsage
from pipeline.schemas import GeneratorOutput, CalibratorOutput

logger = logging.getLogger("pipeline.calibrator")

# ─── Шкала уровней для промпта ────────────────────────────────────────────────
_LEVEL_SCALE_TEXT = "\n".join(
    f"  {k} — {v}" for k, v in LEVEL_DESCRIPTIONS.items()
)

SYSTEM_PROMPT = f"""\
Ты — эксперт по олимпиадной сложности. НЕ решай задачу до конца — оцени по идеям.

ШКАЛА УРОВНЕЙ:
{_LEVEL_SCALE_TEXT}

МЕТОД: перечисли минимум идей, необходимых для решения. Оцени — школьные или олимпиадные.
- 0 нетривиальных идей ≈ уровень 1–3
- 1 нетривиальная идея ≈ уровень 4
- 2 идеи ≈ уровень 5–6
- творческий ход ≈ уровень 7

ВЫХОД — строго JSON (без markdown-обёртки):
{{
  "predicted_level": 1..7,
  "confidence": 0.0..1.0,
  "reasoning": "...",
  "ideas_required": ["..."],
  "verdict": "PASS если predicted_level == claimed_level, иначе FAIL",
  "suggested_level": predicted_level,
  "fix_hint": "..."
}}

Если confidence < {CALIBRATOR_CONFIDENCE_MIN:.2f} → FAIL даже при совпадении уровней.
"""


def _build_user_prompt(task: GeneratorOutput, claimed_level: int) -> str:
    """Формирует user-промпт для Calibrator."""
    task_json = task.model_dump_json(indent=2, ensure_ascii=False)
    return (
        f"Заявленный уровень: {claimed_level}\n\n"
        f"JSON задачи:\n{task_json}"
    )


async def calibrate_task(
    client: OpenRouterClient,
    task: GeneratorOutput,
    claimed_level: int,
) -> tuple[CalibratorOutput, TokenUsage]:
    """
    Калибрует уровень сложности задачи.

    Returns:
        (CalibratorOutput, TokenUsage)
    """
    user_msg = _build_user_prompt(task, claimed_level)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    data, usage = await client.chat_json(
        model=CALIBRATOR_MODEL,
        messages=messages,
        temperature=CALIBRATOR_TEMPERATURE,
        max_tokens=CALIBRATOR_MAX_TOKENS,
    )

    result = CalibratorOutput.model_validate(data)

    # F-2: confidence < CALIBRATOR_CONFIDENCE_MIN -> FAIL
    if result.confidence < CALIBRATOR_CONFIDENCE_MIN and result.verdict == "PASS":
        logger.warning(
            "Calibrator said PASS but confidence=%.2f < %.2f — overriding to FAIL",
            result.confidence, CALIBRATOR_CONFIDENCE_MIN,
        )
        result.verdict = "FAIL"
        if not result.fix_hint:
            result.fix_hint = (
                f"Низкая уверенность ({result.confidence:.2f}). "
                f"Сделай задачу более однозначной по уровню."
            )

    # Если predicted_level != claimed_level → FAIL
    if result.predicted_level != claimed_level and result.verdict == "PASS":
        logger.warning(
            "Calibrator said PASS but predicted=%d != claimed=%d — overriding to FAIL",
            result.predicted_level, claimed_level,
        )
        result.verdict = "FAIL"

    logger.info(
        "Calibration: predicted=%d, claimed=%d, confidence=%.2f, verdict=%s",
        result.predicted_level, claimed_level, result.confidence, result.verdict,
    )
    return result, usage
