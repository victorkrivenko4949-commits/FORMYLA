# -*- coding: utf-8 -*-
"""Контракты `ScreenResult` / `DeepResult` и заглушки-раннеры `runScreen` / `runDeep`.

Этап 1 ТЗ задаёт контракты типов ScreenResult/DeepResult. Они объявлены здесь
как dataclasses, чтобы вызывающий код (воркер очереди) не зависел от формы
JSON от модели.

runScreen — дешёвый скрининг (effort=low).
runDeep   — дорогой глубокий разбор (effort=max), с проверкой глубины
            рассуждения (reasoning_tokens) и пост-валидацией.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services import insight_prompts
from services.insight_llm_client import get_insight_client, reasoning_too_short

logger = logging.getLogger(__name__)


# ─── Контракты ───────────────────────────────────────────────────────────

@dataclass
class ScreenResult:
    """Результат скрининга (проход 1)."""

    needs_deep_analysis: bool = False
    preliminary_type: Optional[str] = None
    skip_reason: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeepResult:
    """Результат глубокого разбора (проход 2)."""

    has_insight: bool = False
    skip_reason: Optional[str] = None
    insights: List[Dict[str, Any]] = field(default_factory=list)
    valid: bool = False
    validation_reason: Optional[str] = None
    reasoning_short: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    # Gemini-аудит результата DeepSeek.
    audit_approved: bool = False
    audit_issues: List[str] = field(default_factory=list)
    audit_meta: Dict[str, Any] = field(default_factory=dict)
    correction_used: bool = False
    correction_rounds: int = 0


# ─── Вспомогательный рендер промтов ──────────────────────────────────────

def _render(template: str, ctx: Dict[str, Any]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", str(value if value is not None else ""))
    return out


def _fmt_time(sec: Optional[int]) -> str:
    if sec is None:
        return "неизвестно"
    return f"{sec} сек"


# ─── runScreen ───────────────────────────────────────────────────────────

def run_screen(job_ctx: Dict[str, Any]) -> ScreenResult:
    """Дешёвый скрининг решения. Не бросает исключений — возвращает контракт."""
    client = get_insight_client()
    user_prompt = _render(insight_prompts.SCREEN_USER_TEMPLATE, {
        "task_text": job_ctx.get("task_text") or "",
        "correct_answer": job_ctx.get("correct_answer") or "",
        "solution_ref": job_ctx.get("solution_ref") or "",
        "user_solution": job_ctx.get("user_solution") or "",
        "topic": job_ctx.get("topic") or "",
        "difficulty_level": job_ctx.get("difficulty_level") or "",
        "time_spent": _fmt_time(job_ctx.get("time_spent_sec")),
        "etalon_time": _fmt_time(job_ctx.get("etalon_time_sec")),
    })
    try:
        parsed, meta = client.call_json(
            system_prompt=insight_prompts.SCREEN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            effort="low",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[insight] screen call failed")
        return ScreenResult(meta={"error": str(exc)}, raw={})

    needs = bool(parsed.get("needs_deep_analysis", False))
    preliminary = parsed.get("preliminary_type") or None
    skip_reason = parsed.get("skip_reason") or None
    return ScreenResult(
        needs_deep_analysis=needs,
        preliminary_type=preliminary,
        skip_reason=skip_reason,
        raw=parsed,
        meta=meta,
    )


# ─── Аудит Gemini + коррекция DeepSeek ────────────────────────────────────

MAX_AUDIT_CORRECTION_ROUNDS = 2


def _audit_with_gemini(client, job_ctx: Dict[str, Any], deep_json: Dict) -> Dict:
    """Gemini (effort=low) проверяет разбор DeepSeek. Возвращает
    {"approved": bool, "issues": list, "meta": {...}}."""
    import json as _json
    user_prompt = _render(insight_prompts.AUDIT_USER_TEMPLATE, {
        "task_text": job_ctx.get("task_text") or "",
        "correct_answer": job_ctx.get("correct_answer") or "",
        "solution_ref": job_ctx.get("solution_ref") or "",
        "user_solution": job_ctx.get("user_solution") or "",
        "topic": job_ctx.get("topic") or "",
        "difficulty_level": job_ctx.get("difficulty_level") or "",
        "deep_json": _json.dumps(deep_json, ensure_ascii=False),
    })
    try:
        parsed, meta = client.call_json(
            system_prompt=insight_prompts.AUDIT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            effort="low",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[insight] audit call failed")
        # При сбое аудита — пропускаем (не блокируем выдачу DeepSeek).
        return {"approved": True, "issues": [], "meta": {"error": str(exc)}}

    approved = bool(parsed.get("approved", True))
    issues = parsed.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    return {"approved": approved, "issues": issues, "meta": meta}


def _correct_deepseek(client, user_prompt: str, issues: List[str]) -> Dict:
    """Отправить замечания обратно в DeepSeek и получить исправленный JSON."""
    import json as _json
    correction = _render(insight_prompts.CORRECTION_USER_TEMPLATE, {
        "issues": "\n".join(f"- {i}" for i in issues),
    })
    # Тот же диалог: system + исходный user + ответ DeepSeek + замечания.
    messages = [
        {"role": "system", "content": insight_prompts.DEEP_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": _json.dumps(issues, ensure_ascii=False)},
        {"role": "user", "content": correction},
    ]
    try:
        meta = client.call_messages(messages=messages, effort="max")
    except Exception as exc:  # noqa: BLE001
        logger.exception("[insight] correction call failed")
        return {"parsed": {}, "meta": {"error": str(exc)}}

    from services.insight_llm_client import _parse_json
    parsed = _parse_json(meta.get("content") or "")
    return {"parsed": parsed, "meta": meta}


# ─── runDeep ─────────────────────────────────────────────────────────────

def run_deep(job_ctx: Dict[str, Any]) -> DeepResult:
    """Глубокий разбор с Gemini-аудитом, коррекцией и пост-валидацией.

    Схема: DeepSeek (effort=max) -> Gemini-аудит (effort=low).
    Если Gemini отклоняет (approved=false) — отправляем замечания обратно в
    DeepSeek (тот же диалог) и перепроверяем. Цель — устранить возможный
    неправильный отчёт DeepSeek (неверные ответы задач, неконкретные
    формулировки, ложная диагностика).
    """
    from services.insight_llm_client import _parse_json
    from services.insight_validator import filter_valid_insights, validate_deep_result

    client = get_insight_client()
    user_prompt = _render(insight_prompts.DEEP_USER_TEMPLATE, {
        "task_text": job_ctx.get("task_text") or "",
        "correct_answer": job_ctx.get("correct_answer") or "",
        "solution_ref": job_ctx.get("solution_ref") or "",
        "user_solution": job_ctx.get("user_solution") or "",
        "topic": job_ctx.get("topic") or "",
        "difficulty_level": job_ctx.get("difficulty_level") or "",
        "time_spent": _fmt_time(job_ctx.get("time_spent_sec")),
        "etalon_time": _fmt_time(job_ctx.get("etalon_time_sec")),
    })

    # 1) DeepSeek (effort=max).
    try:
        parsed, meta = client.call_json(
            system_prompt=insight_prompts.DEEP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            effort="max",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[insight] deep call failed")
        return DeepResult(meta={"error": str(exc)}, raw={})

    audit_approved = True
    audit_issues: List[str] = []
    audit_meta: Dict[str, Any] = {}
    correction_used = False
    correction_rounds = 0

    # 2) Цикл: Gemini-аудит -> коррекция DeepSeek (до 2 раундов).
    if parsed.get("has_insight"):
        for _round in range(MAX_AUDIT_CORRECTION_ROUNDS):
            audit = _audit_with_gemini(client, job_ctx, parsed)
            audit_approved = audit["approved"]
            audit_issues = audit["issues"]
            audit_meta = audit["meta"]
            if audit_approved:
                break
            correction_rounds += 1
            correction_used = True
            corr = _correct_deepseek(client, user_prompt, audit_issues)
            new_parsed = corr.get("parsed") or {}
            if new_parsed:
                parsed = new_parsed
                meta = corr.get("meta", meta)
            else:
                # Коррекция не вернула валидный JSON — прекращаем, остаёмся на текущем.
                break

    # 3) Пост-валидация.
    short = reasoning_too_short(meta)
    vres = validate_deep_result(parsed)
    valid = vres.ok
    insights = filter_valid_insights(parsed) if not short else []

    return DeepResult(
        has_insight=bool(parsed.get("has_insight", False)),
        skip_reason=parsed.get("skip_reason") or None,
        insights=insights,
        valid=valid and not short,
        validation_reason=("reasoning_short" if short else vres.reason),
        reasoning_short=short,
        raw=parsed,
        meta=meta,
        audit_approved=audit_approved,
        audit_issues=audit_issues,
        audit_meta=audit_meta,
        correction_used=correction_used,
        correction_rounds=correction_rounds,
    )
