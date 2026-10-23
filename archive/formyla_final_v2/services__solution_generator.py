# -*- coding: utf-8 -*-
"""services/solution_generator.py — вызов solver'а и разбор ответа.

CH-aux: разделяем «решить задачу текстом» (v4-pro, thinking) и «извлечь
построения» (v4-flash).  Этот модуль отвечает за первый шаг.

CH-fidelity: здесь же — repair-прогон решателя, когда компилятор потерял
часть объявленных построений (aux_repair).  Модель получает список потерянных
операций и переписывает только aux_constructions, чтобы итоговый чертёж
выводился ТОЧЬ-В-ТОЧЬ как сказано в решении.

Использует services.llm_router.call_llm с ролью "solver" (прямой DeepSeek
первым в цепочке).  Возвращает распарсенный dict контракта SolverResult.
"""

from __future__ import annotations

import json
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
SOLVER_PROMPT_VERSION = "solver-v4"

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


_REPAIR_PROMPT = (
    "Ты ранее решал геометрическую задачу и вернул aux_constructions, но "
    "часть построений была ПОТЕРЯНА компилятором и не попала на чертёж. "
    "Перепиши ТОЛЬКО aux_constructions (и при необходимости steps), чтобы "
    "каждое построение из решения было построено.\n"
    "Правила:\n"
    "1. op — только из разрешённого списка; пиши дословные op из списка.\n"
    "2. quote — ДОСЛОВНАЯ подстрока из соответствующего steps[].text.\n"
    "3. Все точки в points либо из условия, либо созданы ранее через foot_id/id.\n"
    "4. Не пропускай построения: каждое действие решения должно стать отдельной "
    "aux_construction.\n"
    "Верни СТРОГО один JSON (тот же формат, что и раньше), без markdown.\n"
)


def repair_solver_aux(
    condition_text: str,
    *,
    fidelity: Dict[str, Any],
    previous: Optional[Dict[str, Any]] = None,
    base_plan: Optional[Dict[str, Any]] = None,
    logger=None,
) -> Optional[Dict[str, Any]]:
    """CH-fidelity: переписать aux_constructions после потерь компилятора.

    Вызывается, когда fidelity_report показал dropped > 0.  Передаём модели
    список потерянных операций И доступные id точек base-плана (чтобы она
    не ссылалась на несуществующие точки и реально починила UNRESOLVED_POINT).
    Возвращает новый распарсенный SolverResult или None при неудаче.
    """
    from services.text_normalize import normalize_condition

    model = logical_model_for_role("solver")
    norm_condition = normalize_condition(condition_text)

    lost = (fidelity or {}).get("issues", []) or []
    lost_text = "\n".join(f"- {i}" for i in lost[:20]) or "(нет)"
    prev_aux = ""
    if isinstance(previous, dict):
        try:
            prev_aux = json.dumps(
                (previous.get("aux_constructions") or []), ensure_ascii=False
            )
        except Exception:
            prev_aux = ""

    # Доступные точки base-плана — чтобы модель не выдумывала новые имена
    # и могла исправить UNRESOLVED_POINT.
    base_ids_text = "(неизвестно)"
    if isinstance(base_plan, dict):
        cs = base_plan.get("constructions", []) or []
        ids = [c.get("id") for c in cs if isinstance(c, dict) and c.get("id")]
        if ids:
            base_ids_text = ", ".join(str(i) for i in ids)

    system_prompt = _REPAIR_PROMPT
    user_prompt = (
        f"ЗАДАЧА:\n{norm_condition}\n\n"
        f"Доступные точки base-чертежа: {base_ids_text}\n"
        f"Потерянные построения (не попали на чертёж):\n{lost_text}\n\n"
        f"Твои предыдущие aux_constructions:\n{prev_aux}\n\n"
        "Верни СТРОГО JSON со всеми aux_constructions, без потерь."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
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
        if logger:
            logger.warning("[solver_repair] LLM error: %s", e)
        return None
    except Exception as e:  # pragma: no cover - защита от транспорта
        if logger:
            logger.warning("[solver_repair] error: %s", e)
        return None

    content = (resp.get("content") or "").strip()
    if not content:
        return None

    result = parse_solver_result(content)
    if result is None:
        return None

    result["_provider"] = resp.get("provider", "")
    result["_model"] = resp.get("model_id", "")
    result["_usage"] = resp.get("usage", {}) or {}
    result["_cost_usd"] = resp.get("cost_usd", 0.0)
    return result


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

    # CH-fidelity: до 3 попыток при невалидном JSON / пустом ответе.
    result = None
    last_error = None
    for attempt in range(3):
        try:
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
            if code == "LLM_EMPTY_CONTENT":
                last_error = SolverEmptyResponse(str(e))
            else:
                last_error = SolverError(code, str(e))
            if attempt < 2:
                continue
            raise last_error

        content = (resp.get("content") or "").strip()
        if not content:
            if logger:
                logger.warning("[solver] empty content provider=%s model=%s",
                               resp.get("provider"), resp.get("model_id"))
            last_error = SolverEmptyResponse()
            if attempt < 2:
                continue
            raise last_error

        result = parse_solver_result(content)
        if result is not None:
            break
        if logger:
            logger.warning("[solver] bad json attempt=%d provider=%s",
                           attempt + 1, resp.get("provider"))
        last_error = SolverError("SOLVER_BAD_JSON", "модель вернула невалидный JSON")

    if result is None:
        raise last_error or SolverError("SOLVER_BAD_JSON", "модель вернула невалидный JSON")

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
