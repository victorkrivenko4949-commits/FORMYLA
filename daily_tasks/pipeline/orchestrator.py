# -*- coding: utf-8 -*-
"""
Оркестратор пайплайна «Задачи дня».

Реализует Step 1–5 по ТЗ:
  Step 2: Gemini → specs
  Step 3: Opus → tasks
  Step 4: GPT audit → verdict + issues
  Step 5: Fix‑loop (Opus fix → GPT re‑audit, max 3 итерации)
  Rescue‑pass: если ≥ 3 задач всё ещё ``is_flagged`` после 3 итераций
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .step1_gemini import generate_gemini_plan, GeminiPlanError
from .step2_opus import generate_opus_tasks
from .step3_gpt_audit import audit_tasks
from .step4_opus_fix import fix_single_task

logger = logging.getLogger(__name__)

# ── константы ────────────────────────────────────────────────────────────
MAX_FIX_ITERATIONS = 5
"""Максимальное число итераций Opus‑fix → GPT‑audit для одной задачи."""

MIN_VALID_TASKS = 7
"""Минимальное количество валидных задач для статуса ``ready``."""

FLAGGED_THRESHOLD = 3
"""При ≥ этого числа ``is_flagged`` задач запускается rescue‑проход."""


def _safe_progress(callback, step: str, pct: int) -> None:
    """Безопасно дёргает progress-callback (если передан).
    Любые исключения подавляются и логируются, чтобы не сломать пайплайн
    из-за побочного UI-эффекта."""
    if callback is None:
        return
    try:
        callback(step, pct)
    except Exception as exc:
        logger.warning("Progress callback failed: %s", exc)


# ── структуры данных ────────────────────────────────────────────────────


@dataclass
class PipelineStepLog:
    """Запись одного шага пайплайна для ``pipeline_log``."""
    step: str
    duration_sec: float
    cost_usd: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Результат работы полного пайплайна генерации."""

    success: bool
    status: str  # 'ready' | 'partial' | 'failed'
    specs: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    audit_entries: List[Dict[str, Any]] = field(default_factory=list)
    iteration_counts: List[int] = field(default_factory=list)
    is_flagged: List[bool] = field(default_factory=list)
    steps: List[PipelineStepLog] = field(default_factory=list)
    total_cost: float = 0.0
    error: Optional[str] = None


# ── helpers ──────────────────────────────────────────────────────────────


def _make_step_log(
    step: str,
    start: float,
    cost: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    error: Optional[str] = None,
) -> PipelineStepLog:
    return PipelineStepLog(
        step=step,
        duration_sec=round(time.monotonic() - start, 3),
        cost_usd=cost,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error=error,
    )


# ── rescue‑проход ────────────────────────────────────────────────────────


async def _rescue_pass(
    flagged_specs: List[Dict[str, Any]],
    flagged_positions: List[int],
) -> Tuple[List[Dict[str, Any]], List[PipelineStepLog], float]:
    """Rescue‑проход для задач, не прошедших 3 итерации фикса.

    Генерирует НОВЫЕ задачи через Opus (с пометкой «проще/clean‑archetype»)
    и проводит один раунд аудита (без дополнительных итераций фикса).
    """
    rescue_steps: List[PipelineStepLog] = []
    rescue_cost = 0.0

    # ── Opus generate для flagged позиций ─────────────────────────────
    logger.warning(
        "Rescue: запуск Opus generate для %d flagged задач (позиции %s)",
        len(flagged_specs),
        flagged_positions,
    )
    t0 = time.monotonic()
    rescue_tasks = await generate_opus_tasks(flagged_specs)
    rescue_steps.append(_make_step_log("rescue_opus_generate", t0))
    rescue_cost += rescue_steps[-1].cost_usd

    if not rescue_tasks or len(rescue_tasks) != len(flagged_specs):
        logger.error("Rescue: Opus generate вернул пустой результат")
        rescue_steps[-1].error = "Opus generate вернул пустой результат"
        return [], rescue_steps, rescue_cost

    # ── один раунд GPT audit (без fix‑loop) ───────────────────────────
    t0 = time.monotonic()
    rescue_audit = await audit_tasks(flagged_specs, rescue_tasks)
    rescue_steps.append(_make_step_log("rescue_gpt_audit", t0))
    rescue_cost += rescue_steps[-1].cost_usd

    if not rescue_audit or len(rescue_audit) != len(flagged_specs):
        logger.error("Rescue: GPT audit вернул пустой результат")
        rescue_steps[-1].error = "GPT audit вернул пустой результат"
        return [], rescue_steps, rescue_cost

    # Принимаем все approved задачи из rescue; остальные — flagged
    final_rescue_tasks: List[Dict[str, Any]] = []
    for i, (spec, task, audit_entry) in enumerate(
        zip(flagged_specs, rescue_tasks, rescue_audit)
    ):
        if audit_entry.get("verdict") == "approved":
            # Пересохраняем спеки rescue (они должны быть проще)
            # audit_entry["position"] перезаписываем на оригинальную позицию
            audit_entry["position"] = flagged_positions[i]
            final_rescue_tasks.append(task)
        else:
            # Даже rescue не прошёл — оставляем flagged
            final_rescue_tasks.append(task)

    logger.info(
        "Rescue: %d/%d задач approved после rescue-прохода",
        sum(1 for a in rescue_audit if a.get("verdict") == "approved"),
        len(rescue_audit),
    )
    return final_rescue_tasks, rescue_steps, rescue_cost


# ── основной пайплайн ────────────────────────────────────────────────────


async def run_daily_generation_pipeline(
    profile: Dict[str, Any],
    progress_callback: callable = None,
) -> PipelineResult:
    """Запустить полный пайплайн генерации «Задачи дня».

    Параметры
    ---------
    profile : dict
        Профиль пользователя от ``build_profile()``. Ожидаемые ключи:
        ``user_id``, ``class_level``, ``weak_topics``, ``strong_topics``,
        ``class_expected_level``, ``adaptive_summary``.

    Возвращает
    ----------
    PipelineResult
        Структурированный результат со списками ``specs``, ``tasks``,
        ``audit_entries``, ``iteration_counts``, ``is_flagged``,
        ``steps`` (лог шагов) и ``total_cost``.
    """
    result = PipelineResult(success=False, status="failed")
    all_steps: List[PipelineStepLog] = []
    total_cost = 0.0

    # ═══════════════════════════════════════════════════════════════════
    # Step 2: Gemini → specs
    # ═══════════════════════════════════════════════════════════════════
    logger.info("Pipeline: Step 2 — Gemini plan")
    _safe_progress(progress_callback, "gemini_plan", 15)
    t0 = time.monotonic()
    try:
        specs = await generate_gemini_plan(profile)
        all_steps.append(_make_step_log("gemini_plan", t0))
        total_cost += all_steps[-1].cost_usd

        if not specs or len(specs) != 10:
            msg = (
                f"Планировщик вернул {len(specs) if specs else 0} "
                "задач вместо 10"
            )
            logger.error("Pipeline: %s", msg)
            result.error = msg
            result.steps = all_steps
            return result
    except GeminiPlanError as exc:
        # Классифицированная ошибка от step1 — уже содержит понятный текст.
        # Пробрасываем КОНКРЕТНУЮ причину (HTTP-402 / parse / validate / etc.)
        # вместо обобщённого "Gemini вернул 0 specs".
        msg = str(exc)
        logger.error(
            "Pipeline: Step 1 PLAN failed: category=%s status=%s msg=%s",
            getattr(exc, "category", "?"),
            getattr(exc, "status_code", 0),
            msg,
        )
        all_steps.append(_make_step_log("gemini_plan", t0, error=msg))
        result.error = msg
        result.steps = all_steps
        return result
    except Exception as exc:
        msg = f"Сбой планировщика: {type(exc).__name__}: {exc}"
        logger.exception("Pipeline: %s", msg)
        all_steps.append(_make_step_log("gemini_plan", t0, error=str(exc)))
        result.error = msg
        result.steps = all_steps
        return result

    result.specs = specs

    # ═══════════════════════════════════════════════════════════════════
    # Step 3: Opus → tasks
    # ═══════════════════════════════════════════════════════════════════
    logger.info("Pipeline: Step 3 — Opus generate")
    _safe_progress(progress_callback, "opus_generate", 35)
    t0 = time.monotonic()
    try:
        opus_tasks = await generate_opus_tasks(specs)
        all_steps.append(_make_step_log("opus_generate", t0))
        total_cost += all_steps[-1].cost_usd

        if not opus_tasks or len(opus_tasks) != 10:
            msg = (
                f"Генератор задач вернул "
                f"{len(opus_tasks) if opus_tasks else 0} задач вместо 10. "
                "Возможные причины: HTTP-ошибка OpenRouter (см. логи), "
                "таймаут, баланс."
            )
            logger.error("Pipeline: %s", msg)
            result.error = msg
            result.steps = all_steps
            return result
    except Exception as exc:
        msg = f"Сбой генератора задач: {type(exc).__name__}: {exc}"
        logger.exception("Pipeline: %s", msg)
        all_steps.append(_make_step_log("opus_generate", t0, error=str(exc)))
        result.error = msg
        result.steps = all_steps
        return result

    # ═══════════════════════════════════════════════════════════════════
    # Step 4 + Step 5: GPT audit + fix‑loop (max 3 итерации)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("Pipeline: Step 4+5 — GPT audit + fix-loop (max %d it)", MAX_FIX_ITERATIONS)
    _safe_progress(progress_callback, "gpt_audit", 60)

    approved: List[Tuple[int, Dict, Dict, Dict, int]] = []  # (position, spec, task, audit, iterations)
    queue: List[Tuple[Dict, Dict, int]] = [
        (spec, task, 1) for spec, task in zip(specs, opus_tasks)
    ]
    fix_iteration_count = 0

    while queue:
        fix_iteration_count += 1
        pending_specs = [s for s, _, _ in queue]
        pending_tasks = [t for _, t, _ in queue]

        # ── GPT audit ────────────────────────────────────────────────
        t0 = time.monotonic()
        try:
            audit_entries = await audit_tasks(pending_specs, pending_tasks)
            all_steps.append(
                _make_step_log(f"gpt_audit_iter_{fix_iteration_count}", t0)
            )
            total_cost += all_steps[-1].cost_usd
        except Exception as exc:
            logger.exception("GPT audit crashed on iteration %d", fix_iteration_count)
            all_steps.append(
                _make_step_log(
                    f"gpt_audit_iter_{fix_iteration_count}",
                    t0,
                    error=str(exc),
                )
            )
            # В случае ошибки аудита — флагаем все задачи в очереди
            for spec, task, it in queue:
                approved.append((None, spec, task, {"verdict": "needs_fix", "issues": [], "flagged": True}, it))
            break

        if not audit_entries or len(audit_entries) != len(queue):
            logger.error("Audit вернул %d entries (ожидалось %d)", len(audit_entries or []), len(queue))
            for spec, task, it in queue:
                approved.append((None, spec, task, {"verdict": "needs_fix", "issues": [], "flagged": True}, it))
            break

        # ── распределяем approved / needs_fix ────────────────────────
        next_queue: List[Tuple[Dict, Dict, int]] = []

        for (spec, task, it), audit_entry in zip(queue, audit_entries):
            position = spec.get("position", "?")

            if audit_entry.get("verdict") == "approved":
                approved.append((position, spec, task, audit_entry, it))
                logger.debug("Position %s — approved (ит: %d)", position, it)
            else:
                if it >= MAX_FIX_ITERATIONS:
                    # Исчерпали лимит итераций — флагаем
                    approved.append(
                        (position, spec, task, {**audit_entry, "flagged": True}, it)
                    )
                    logger.warning("Position %s — flagged (ит: %d, лимит)", position, it)
                else:
                    # Opus fix
                    t_fix = time.monotonic()
                    try:
                        fixed_task = await fix_single_task(spec, task, audit_entry)
                        all_steps.append(
                            _make_step_log(f"opus_fix_{position}_it_{it}", t_fix)
                        )
                        total_cost += all_steps[-1].cost_usd
                    except Exception as exc:
                        logger.exception(
                            "Opus fix crashed на position=%s, итерация %d", position, it
                        )
                        all_steps.append(
                            _make_step_log(
                                f"opus_fix_{position}_it_{it}",
                                t_fix,
                                error=str(exc),
                            )
                        )
                        # Если fix упал — отправляем задачу обратно в очередь как есть
                        # (она пойдёт на ещё один audit, а потом будет flagged)
                        next_queue.append((spec, task, it + 1))
                        continue

                    if fixed_task is not None:
                        next_queue.append((spec, fixed_task, it + 1))
                        logger.debug(
                            "Position %s — fix OK (ит: %d → %d)",
                            position, it, it + 1,
                        )
                    else:
                        # Opus fix вернул None — оставляем старую задачу, +1 итерация
                        logger.warning(
                            "Position %s — fix вернул None, повтор на итерации %d",
                            position, it,
                        )
                        next_queue.append((spec, task, it + 1))

        queue = next_queue

    # ── сортируем approved по position ─────────────────────────────────
    # approved: list of (position, spec, task, audit_entry, iterations)
    approved.sort(key=lambda x: x[0] if x[0] is not None else 999)

    final_specs: List[Dict] = []
    final_tasks: List[Dict] = []
    final_audit: List[Dict] = []
    iteration_counts: List[int] = []
    is_flagged: List[bool] = []

    for position, spec, task, audit_entry, it in approved:
        final_specs.append(spec)
        final_tasks.append(task)
        final_audit.append(audit_entry)
        iteration_counts.append(it)
        is_flagged.append(audit_entry.get("flagged", False))

    result.specs = final_specs
    result.tasks = final_tasks
    result.audit_entries = final_audit
    result.iteration_counts = iteration_counts
    result.is_flagged = is_flagged

    # ═══════════════════════════════════════════════════════════════════
    # Rescue‑проход (если ≥ FLAGGED_THRESHOLD задач flagged)
    # ═══════════════════════════════════════════════════════════════════
    flagged_count = sum(is_flagged)
    if flagged_count >= FLAGGED_THRESHOLD:
        logger.warning(
            "Pipeline: %d задач is_flagged=true — запуск rescue-прохода",
            flagged_count,
        )
        _safe_progress(progress_callback, "rescue_pass", 80)
        flagged_indices = [i for i, f in enumerate(is_flagged) if f]
        flagged_specs_for_rescue = [final_specs[i] for i in flagged_indices]
        flagged_positions = [i + 1 for i in flagged_indices]  # 1-based

        rescue_tasks, rescue_steps, rescue_cost = await _rescue_pass(
            flagged_specs_for_rescue, flagged_positions,
        )
        all_steps.extend(rescue_steps)
        total_cost += rescue_cost

        if rescue_tasks and len(rescue_tasks) == len(flagged_indices):
            for idx_in_rescue, original_idx in enumerate(flagged_indices):
                final_tasks[original_idx] = rescue_tasks[idx_in_rescue]
                # Снимаем флаг, если rescue-задача прошла audit
                audit_entry = final_audit[original_idx]
                if audit_entry.get("verdict") == "approved":
                    is_flagged[original_idx] = False

            result.tasks = final_tasks
            result.is_flagged = is_flagged

    # ═══════════════════════════════════════════════════════════════════
    # Финальный статус
    # ═══════════════════════════════════════════════════════════════════
    valid_count = len(final_tasks) - sum(is_flagged)
    if valid_count >= MIN_VALID_TASKS:
        result.status = "ready"
        result.success = True
    elif valid_count > 0:
        result.status = "partial"
        result.success = True  # partial — всё равно успех, но с пометкой
    else:
        result.status = "failed"
        result.success = False
        result.error = "Нет ни одной валидной задачи после полного пайплайна"

    result.steps = all_steps
    result.total_cost = round(total_cost, 6)

    logger.info(
        "Pipeline завершён: status=%s, valid=%d/%d, cost=$%.4f, шагов=%d",
        result.status,
        valid_count,
        len(final_tasks),
        total_cost,
        len(all_steps),
    )
    return result
