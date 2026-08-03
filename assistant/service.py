# -*- coding: utf-8 -*-
"""High-level orchestration for the FORMYLA Site Assistant.

Pipeline (TZ section 3):

    user message
        v
    topic filter (assistant.safety.classify_topic)
        v  on off-topic / solve-task -> polite refusal (no LLM call)
        v
    KB search   (assistant.knowledge.search)
        v
    build prompt with FORMYLA_CONTEXT block (only relevant rows)
        v
    DeepSeek call (assistant.deepseek_client.chat)
        v
    sanitize (assistant.safety.sanitize_answer) — hedge / external URL filter
        v
    pick suggested_actions by category
        v
    log_event -> return final dict
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .deepseek_client import chat as deepseek_chat
from .deepseek_client import is_enabled as deepseek_is_enabled
from .kb import all_active, log_event, search
from .prompts import FORMYLA_ASSISTANT_SYSTEM_PROMPT
from .safety import (
    REFUSAL_OFF_TOPIC,
    REFUSAL_SOLVE_TASK,
    SAFE_FALLBACK,
    classify_topic,
    sanitize_answer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Suggested-actions catalogue (TZ section 13)
# ---------------------------------------------------------------------------
_DEFAULT_ACTIONS: List[Dict[str, str]] = [
    {"label": "Начать с диагностики", "url": "/adaptive-test"},
    {"label": "Открыть пробники",      "url": "/probniki"},
]

_ACTIONS_BY_CATEGORY: Dict[str, List[Dict[str, str]]] = {
    "getting_started": [
        {"label": "Пройти адаптивный тест", "url": "/adaptive-test"},
        {"label": "Открыть профиль",        "url": "/profile"},
    ],
    "adaptive_test": [
        {"label": "Пройти адаптивный тест", "url": "/adaptive-test"},
        {"label": "Посмотреть прогресс",    "url": "/profile"},
    ],
    "progress": [
        {"label": "Открыть личный кабинет", "url": "/profile"},
        {"label": "Начать тренировку",      "url": "/probniki"},
    ],
    "problems": [
        {"label": "Перейти к задачам",  "url": "/problems"},
        {"label": "Открыть пробники",   "url": "/probniki"},
    ],
    "methods": [
        {"label": "Открыть методы",     "url": "/methods"},
    ],
    "probniki": [
        {"label": "Открыть пробники",   "url": "/probniki"},
    ],
    "olympiads": [
        {"label": "Подготовка к ВсОШ",  "url": "/vsosh"},
        {"label": "Открыть пробники",   "url": "/probniki"},
    ],
    "tariffs": [
        {"label": "Посмотреть тарифы",  "url": "/pricing"},
    ],
    "errors": [
        {"label": "Написать в поддержку", "url": "/support"},
    ],
}


def _pick_actions(category: Optional[str]) -> List[Dict[str, str]]:
    if not category:
        return list(_DEFAULT_ACTIONS)
    return list(_ACTIONS_BY_CATEGORY.get(category, _DEFAULT_ACTIONS))


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
_MAX_CONTEXT_ROWS = 5
_MAX_ANSWER_CHARS = 400  # truncate per-row to keep prompt lean


def _truncate(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _build_user_prompt(message: str, rows: List[dict]) -> str:
    """Inject the KB context the model is allowed to use."""
    if not rows:
        context_block = "(контекст пуст — отвечай фразой-отказом из системного промпта)"
    else:
        parts = []
        for r in rows:
            block = (
                f"— Категория: {r.get('category') or '—'}\n"
                f"  Заголовок: {r.get('title') or '—'}\n"
                f"  Вопрос:    {r.get('question') or '—'}\n"
                f"  Ответ:     {_truncate(r.get('answer') or '', _MAX_ANSWER_CHARS)}\n"
                f"  Ссылка:    {r.get('page_url') or '—'}"
            )
            parts.append(block)
        context_block = "\n\n".join(parts)

    return (
        "FORMYLA_CONTEXT (используй ТОЛЬКО эти факты):\n"
        f"{context_block}\n\n"
        "Вопрос пользователя:\n"
        f"{message.strip()}\n\n"
        "Ответ:"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def answer(message: str) -> Dict[str, object]:
    """Main entry. Returns the public response dict (TZ section 5)::

        {
            "ok": bool,
            "answer": str,
            "suggested_actions": [{"label": str, "url": str}, ...],
            "category": Optional[str],   # debug / analytics
        }
    """
    msg = (message or "").strip()

    # 1. Topic filter — refuse without LLM call.
    topic, reason = classify_topic(msg)
    if topic == "solve_task":
        log_event(
            user_message=msg,
            assistant_answer=REFUSAL_SOLVE_TASK,
            category="refused_solve_task",
            is_refused=True,
        )
        return {
            "ok": True,
            "answer": REFUSAL_SOLVE_TASK,
            "suggested_actions": _pick_actions("problems"),
            "category": "refused_solve_task",
        }
    if topic == "off_topic":
        log_event(
            user_message=msg,
            assistant_answer=REFUSAL_OFF_TOPIC,
            category="refused_off_topic",
            is_refused=True,
        )
        return {
            "ok": True,
            "answer": REFUSAL_OFF_TOPIC,
            "suggested_actions": _pick_actions(None),
            "category": "refused_off_topic",
        }

    # 2. Knowledge-base lookup.
    rows = search(msg, limit=_MAX_CONTEXT_ROWS)

    # If nothing matched, give the model EVERY active row — still capped to
    # the limit — so it can pick the closest one or honestly say it doesn't
    # know (the system prompt forces that fallback phrase).
    if not rows:
        rows = all_active()[:_MAX_CONTEXT_ROWS]

    top_category = rows[0].get("category") if rows else None
    used_ids = [int(r["id"]) for r in rows if r.get("id") is not None]

    # 3. LLM call.
    llm_text: Optional[str] = None
    if deepseek_is_enabled():
        try:
            llm_text = deepseek_chat(
                user_message=_build_user_prompt(msg, rows),
                system_prompt=FORMYLA_ASSISTANT_SYSTEM_PROMPT,
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("assistant.service: deepseek_chat raised: %s", e)
            llm_text = None
    else:
        logger.info("assistant.service: DeepSeek disabled — using deterministic fallback")

    # 4. Sanitize / fallback.
    if llm_text:
        final_answer, replaced = sanitize_answer(llm_text)
    else:
        # No LLM available — use the top KB answer verbatim if we have one.
        if rows:
            final_answer = (rows[0].get("answer") or SAFE_FALLBACK).strip()
            replaced = False
        else:
            final_answer = SAFE_FALLBACK
            replaced = True

    # 5. Actions.
    actions = _pick_actions(top_category)

    # 6. Log + return.
    log_event(
        user_message=msg,
        assistant_answer=final_answer,
        category=top_category,
        used_context_ids=used_ids,
        is_refused=replaced,
    )
    return {
        "ok": True,
        "answer": final_answer,
        "suggested_actions": actions,
        "category": top_category,
    }


__all__ = ["answer"]
