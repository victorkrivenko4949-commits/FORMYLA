# -*- coding: utf-8 -*-
"""services/solution_generator.py — вызов solver'а и разбор ответа.

CH-aux: разделяем «решить задачу текстом» (v4-pro, thinking) и «извлечь
построения» (v4-flash).  Этот модуль отвечает за первый шаг.

Использует services.llm_router.call_llm с ролью "solver" (прямой DeepSeek
первым в цепочке).  Возвращает распарсенный dict контракта SolverResult.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from services.llm_router import (
    call_llm,
    LLMError,
    logical_model_for_role,
    max_tokens_for_role,
)

from services.figure_plan_schemas import parse_solver_result

# REC-5 Part 6: shadow-режим — параллельный прогон solver'а на Gemini (OdiRouter)
# для сравнения качества.  Результат shadow НЕ влияет на pipeline (только лог).
# По умолчанию выключен, включается FIGURE_SOLVER_GEMINI_SHADOW=true.
FIGURE_SOLVER_GEMINI_SHADOW = (
    os.environ.get("FIGURE_SOLVER_GEMINI_SHADOW", "false").strip().lower()
    in ("1", "true", "yes", "on")
)


class SolverError(Exception):
    """Неустранимая ошибка решателя (валидный JSON не получен)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class SolverEmptyResponse(SolverError):
    """Модель вернула пустой content (не тихий None)."""

    def __init__(self, message: str = "модель вернула пустой ответ"):
        super().__init__("SOLVER_EMPTY_RESPONSE", message)


# Версия промпта (входит в ключ solver-кэша).
SOLVER_PROMPT_VERSION = "solver-v3"

_SOLVER_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "figures", "solver_task.txt"
)


def _load_solver_prompt() -> str:
    try:
        with open(_SOLVER_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _run_shadow_solver(messages, logger) -> Optional[Dict[str, Any]]:
    """Shadow-прогон solver'а на Gemini (OdiRouter) для сравнения качества.

    Никогда не кидает исключений наружу и не влияет на основной pipeline —
    только пишет в лог итог сравнения (aux_needed / answer).
    """
    try:
        shadow_resp = call_llm(
            logical_model_for_role("solver_shadow"),
            messages,
            max_tokens=max_tokens_for_role("solver_shadow"),
            role="solver_shadow",
            timeout=(15, int(os.environ.get("FIGURE_SOLVER_TIMEOUT", "35"))),
            logger=logger,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        if logger:
            logger.info("[solver_shadow] failed: %s", e)
        return None

    shadow_content = (shadow_resp.get("content") or "").strip()
    if not shadow_content:
        if logger:
            logger.info("[solver_shadow] empty content provider=%s model=%s",
                        shadow_resp.get("provider"), shadow_resp.get("model_id"))
        return None

    shadow = parse_solver_result(shadow_content)
    if shadow is None:
        if logger:
            logger.info("[solver_shadow] bad json provider=%s model=%s",
                        shadow_resp.get("provider"), shadow_resp.get("model_id"))
        return None

    shadow["_provider"] = shadow_resp.get("provider", "")
    shadow["_model"] = shadow_resp.get("model_id", "")
    return shadow


def solve_problem(condition_text: str, *, logger=None) -> Dict[str, Any]:
    """Решить геометрическую задачу через роль solver.

    Args:
        condition_text: текст условия.
        logger: опциональный логгер.

    Returns:
        распарсенный dict контракта SolverResult.

    Raises:
        SolverError при невалидном JSON / пустом ответе / ошибке транспорта.
    """
    from services.text_normalize import normalize_condition
    prompt = _load_solver_prompt()
    if not prompt:
        raise SolverError("SOLVER_PROMPT_MISSING", "системный промпт решателя не загружен")

    model = logical_model_for_role("solver")
    norm_condition = normalize_condition(condition_text)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"ЗАДАЧА:\n{norm_condition}\n\nВерни СТРОГО JSON."},
    ]

    try:
        # REC-8: принудительный JSON + явный max_tokens по роли solver.
        resp = call_llm(
            model,
            messages,
            max_tokens=max_tokens_for_role("solver"),
            role="solver",
            timeout=(15, int(os.environ.get("FIGURE_SOLVER_TIMEOUT", "180"))),
            logger=logger,
            response_format={"type": "json_object"},
        )
    except LLMError as e:
        code = getattr(e, "code", "LLM_ERROR")
        # REC-5 / §2.3: пустой content — явная ошибка SolverEmptyResponse.
        if code == "LLM_EMPTY_CONTENT":
            raise SolverEmptyResponse(str(e))
        raise SolverError(code, str(e))

    content = (resp.get("content") or "").strip()
    if not content:
        # REC-5 / §2.3: пустой content — явная ошибка, не тихий None.
        if logger:
            logger.warning("[solver] empty content provider=%s model=%s",
                           resp.get("provider"), resp.get("model_id"))
        raise SolverEmptyResponse()

    result = parse_solver_result(content)
    if result is None:
        raise SolverError("SOLVER_BAD_JSON", "модель вернула невалидный JSON")

    # Проложим служебные поля для телеметрии.
    result["_provider"] = resp.get("provider", "")
    result["_model"] = resp.get("model_id", "")
    usage = dict(resp.get("usage", {}) or {})
    # reasoning-токены роутер уже извлёк на верхний уровень — продублируем в usage,
    # чтобы _record_stage мог их прочитать единообразно.
    if "reasoning_tokens" not in usage and resp.get("reasoning_tokens") is not None:
        usage["reasoning_tokens"] = resp.get("reasoning_tokens")
    result["_usage"] = usage
    result["_cost_usd"] = resp.get("cost_usd", 0.0)

    # REC-5 Part 6: shadow-сравнение с Gemini (не влияет на pipeline).
    if FIGURE_SOLVER_GEMINI_SHADOW:
        shadow = _run_shadow_solver(messages, logger)
        if logger and shadow is not None:
            main_ans = ((result.get("answer") or {}).get("value"))
            shadow_ans = ((shadow.get("answer") or {}).get("value"))
            logger.info(
                "[solver_shadow] main(provider=%s,aux=%s,answer=%s) vs "
                "gemini(provider=%s,aux=%s,answer=%s)",
                result.get("_provider"), result.get("aux_needed"), main_ans,
                shadow.get("_provider"), shadow.get("aux_needed"), shadow_ans,
            )
        result["_shadow"] = shadow

    return result
