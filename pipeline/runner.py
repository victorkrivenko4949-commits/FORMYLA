# -*- coding: utf-8 -*-
"""
Runner — управляющий цикл пайплайна.

    Generator → Validator → Calibrator
        ↓ FAIL          ↓ FAIL
        feedback ────────┘
        max 4 итерации
    если не сошлось → manual_review_queue
"""
from __future__ import annotations

import logging
from typing import List, Optional

from pipeline.config import MAX_ITERATIONS
from pipeline.openrouter_client import OpenRouterClient, OpenRouterError, TokenUsage
from pipeline.generator import generate_task
from pipeline.validator import validate_task
from pipeline.calibrator import calibrate_task
from pipeline.schemas import PipelineResult

logger = logging.getLogger("pipeline.runner")


class IterationLog:
    """Лог одной итерации (для записи в task_generation_log)."""

    __slots__ = (
        "iteration", "stage", "verdict", "fix_hint",
        "model", "input_tokens", "output_tokens", "cost_usd", "latency_s",
    )

    def __init__(
        self,
        iteration: int,
        stage: str,
        verdict: Optional[str] = None,
        fix_hint: str = "",
        usage: Optional[TokenUsage] = None,
    ):
        self.iteration = iteration
        self.stage = stage  # "generator" | "validator" | "calibrator"
        self.verdict = verdict
        self.fix_hint = fix_hint
        if usage:
            self.model = usage.model
            self.input_tokens = usage.input_tokens
            self.output_tokens = usage.output_tokens
            self.cost_usd = usage.cost_usd
            self.latency_s = usage.latency_s
        else:
            self.model = ""
            self.input_tokens = 0
            self.output_tokens = 0
            self.cost_usd = 0.0
            self.latency_s = 0.0


async def run_pipeline(
    subject: str,
    grade: int,
    level: int,
    topic_hint: Optional[str] = None,
    avoid_patterns: Optional[List[str]] = None,
    client: Optional[OpenRouterClient] = None,
) -> tuple[PipelineResult, List[IterationLog]]:
    """
    Запускает один полный прогон пайплайна.

    Args:
        subject: алгебра, геометрия, и т.д.
        grade: класс (7..13)
        level: целевой уровень сложности (1..7)
        topic_hint: подсказка по теме (например "квадратичные функции")
        avoid_patterns: паттерны, которых надо избегать
        client: опциональный OpenRouterClient (для переиспользования соединения)

    Returns:
        (PipelineResult, list[IterationLog])
    """
    iter_logs: List[IterationLog] = []
    feedback: Optional[str] = None
    last_task = None
    last_validator = None
    last_calibrator = None

    total_in = 0
    total_out = 0
    total_cost = 0.0

    # Управление контекстом клиента
    owns_client = client is None
    if owns_client:
        client = OpenRouterClient()
        await client.__aenter__()

    try:
        for i in range(1, MAX_ITERATIONS + 1):
            logger.info("─── Iteration %d/%d ───", i, MAX_ITERATIONS)

            # ─── 1. Generator ────────────────────────────────────────────────
            try:
                task, gen_usage = await generate_task(
                    client=client,
                    subject=subject, grade=grade, level=level,
                    topic_hint=topic_hint,
                    avoid_patterns=avoid_patterns,
                    feedback=feedback,
                )
            except Exception as e:
                logger.exception("Generator failed at iteration %d", i)
                iter_logs.append(IterationLog(i, "generator", verdict="ERROR", fix_hint=str(e)))
                feedback = f"GENERATOR ERROR: {e}. Сгенерируй заново."
                continue

            iter_logs.append(IterationLog(i, "generator", verdict="OK", usage=gen_usage))
            total_in += gen_usage.input_tokens
            total_out += gen_usage.output_tokens
            total_cost += gen_usage.cost_usd
            last_task = task

            # ─── 2. Validator ────────────────────────────────────────────────
            try:
                v_result, v_usage = await validate_task(
                    client=client,
                    task=task, subject=subject, grade=grade, level=level,
                )
            except Exception as e:
                logger.exception("Validator failed at iteration %d", i)
                iter_logs.append(IterationLog(i, "validator", verdict="ERROR", fix_hint=str(e)))
                feedback = f"VALIDATOR ERROR: {e}. Сгенерируй заново."
                continue

            iter_logs.append(IterationLog(
                i, "validator",
                verdict=v_result.verdict,
                fix_hint=v_result.fix_hint,
                usage=v_usage,
            ))
            total_in += v_usage.input_tokens
            total_out += v_usage.output_tokens
            total_cost += v_usage.cost_usd
            last_validator = v_result

            if v_result.verdict == "FAIL":
                feedback = f"VALIDATOR: {v_result.fix_hint}"
                logger.info("Validator FAIL → restart with feedback")
                continue

            # ─── 3. Calibrator ───────────────────────────────────────────────
            try:
                c_result, c_usage = await calibrate_task(
                    client=client, task=task, claimed_level=level,
                )
            except Exception as e:
                logger.exception("Calibrator failed at iteration %d", i)
                iter_logs.append(IterationLog(i, "calibrator", verdict="ERROR", fix_hint=str(e)))
                feedback = f"CALIBRATOR ERROR: {e}. Сгенерируй заново."
                continue

            iter_logs.append(IterationLog(
                i, "calibrator",
                verdict=c_result.verdict,
                fix_hint=c_result.fix_hint,
                usage=c_usage,
            ))
            total_in += c_usage.input_tokens
            total_out += c_usage.output_tokens
            total_cost += c_usage.cost_usd
            last_calibrator = c_result

            if c_result.verdict == "FAIL":
                feedback = (
                    f"CALIBRATOR: реальный уровень {c_result.suggested_level}, "
                    f"а должен быть {level}. {c_result.fix_hint}"
                )
                logger.info("Calibrator FAIL → restart with feedback")
                continue

            # ─── SUCCESS ─────────────────────────────────────────────────────
            logger.info("✓ Pipeline SUCCESS at iteration %d", i)
            return (
                PipelineResult(
                    success=True,
                    task=task,
                    validator_result=v_result,
                    calibrator_result=c_result,
                    iterations=i,
                    total_tokens_input=total_in,
                    total_tokens_output=total_out,
                    total_cost_usd=total_cost,
                ),
                iter_logs,
            )

        # ─── FAILED after MAX_ITERATIONS ─────────────────────────────────────
        logger.warning("Pipeline FAILED after %d iterations → manual_review_queue", MAX_ITERATIONS)
        return (
            PipelineResult(
                success=False,
                task=last_task,
                validator_result=last_validator,
                calibrator_result=last_calibrator,
                iterations=MAX_ITERATIONS,
                total_tokens_input=total_in,
                total_tokens_output=total_out,
                total_cost_usd=total_cost,
                error=f"Failed after {MAX_ITERATIONS} iterations",
                sent_to_review=True,
            ),
            iter_logs,
        )

    finally:
        if owns_client and client is not None:
            await client.__aexit__(None, None, None)
