# -*- coding: utf-8 -*-
"""Pre- and post-processing safety checks for the FORMYLA Site Assistant.

Two layers:

1. :func:`classify_topic` runs BEFORE the LLM call. It refuses obvious
   off-topic questions (math homework, weather, politics, etc.) so we
   never burn DeepSeek tokens on them and never accidentally answer.

2. :func:`sanitize_answer` runs AFTER the LLM call. It catches hedging
   phrases, hallucinated links and over-long replies; in those cases it
   replaces the model output with a safe fallback phrase.
"""
from __future__ import annotations

import re
from typing import Tuple

# ---------------------------------------------------------------------------
# Pre-LLM topic filter (TZ section 11)
# ---------------------------------------------------------------------------
ALLOWED_KEYWORDS = (
    "formyla", "формула", "формулаи", "формулы", "сайт", "платформа",
    "адаптивный", "тест", "диагностика", "прогресс", "личный кабинет",
    "задачи", "задача", "пробник", "пробники", "метод", "методы",
    "олимпиада", "олимпиады", "всош", "матпраздник", "турнир",
    "подготовка", "тариф", "тарифы", "оплата", "подписка", "ошибка",
    "не работает", "аккаунт", "регистрация", "войти", "вход",
    "класс", "тема", "уровень", "помощник", "поддержка",
    "результат", "результаты", "сложность", "профиль",
    "стрик", "балл", "баллы", "рейтинг",
)

# Indirect/UX-style phrases that DO belong to FORMYLA even without
# the obvious keyword. Anything matching is whitelisted as on-topic.
_ALLOWED_PATTERNS = (
    r"\bкак\s+(пройти|сдать|начать|следить|смотреть|открыть|найти|готовиться)\b",
    r"\bгде\s+(мои|посмотреть|найти|увидеть|искать)\b",
    r"\bчто\s+(дальше|решать|выбрать)\b",
    r"\bне\s+могу\s+(войти|зайти|открыть|зарегистрироваться)\b",
    r"\bкак\s+пользоваться\b",
)

# Clear off-topic markers (refuse instantly).
_BLOCK_PATTERNS = (
    r"\bреши(?:те)?\s+(?:мне\s+)?задач",
    r"\bнапиши(?:те)?\s+сочинени",
    r"\bкто\s+президент\b",
    r"\bкак\s+заработать\b",
    r"\bкак\s+похудеть\b",
    r"\bкакая\s+погода\b",
    r"\bкурс\s+(доллара|евро|валют)\b",
    r"\bновост(и|ей)\b",
    r"\bполитик(а|и|у)\b",
    r"\b(коронавирус|covid|вакцин)\b",
    r"\bрецепт\b",
)

_re_allowed = [re.compile(p, re.IGNORECASE) for p in _ALLOWED_PATTERNS]
_re_blocked = [re.compile(p, re.IGNORECASE) for p in _BLOCK_PATTERNS]


def classify_topic(message: str) -> Tuple[str, str]:
    """Decide whether a message is on-topic.

    Returns one of:
        ("ok",           "")          — proceed to the LLM
        ("off_topic",    reason_text) — refuse politely
        ("solve_task",   reason_text) — math homework attempt; refuse
    """
    if not message or not message.strip():
        return "off_topic", "empty"

    text = message.lower().strip()

    # 1. Hard blocklist — refuse immediately, no LLM call.
    for rx in _re_blocked:
        m = rx.search(text)
        if m:
            if m.re.pattern.startswith(r"\bреши") or "сочинени" in m.re.pattern:
                return "solve_task", m.group(0)
            return "off_topic", m.group(0)

    # 2. Whitelist by keyword or pattern.
    for kw in ALLOWED_KEYWORDS:
        if kw in text:
            return "ok", kw
    for rx in _re_allowed:
        m = rx.search(text)
        if m:
            return "ok", m.group(0)

    # 3. No signal either way — treat as off-topic.
    return "off_topic", "no_keyword"


# ---------------------------------------------------------------------------
# Post-LLM sanity check (TZ section 12)
# ---------------------------------------------------------------------------
_HEDGE_PATTERNS = (
    r"\bя\s+думаю\b",
    r"\bвозможно\b",
    r"\bскорее\s+всего\b",
    r"\bнаверное\b",
    r"\bесли\s+на\s+сайте\s+есть\b",
    r"\bдолжно\s+быть\b",
    r"\bпо-моему\b",
    r"\bкажется\b",
)
_re_hedge = [re.compile(p, re.IGNORECASE) for p in _HEDGE_PATTERNS]

# Reject URLs that aren't relative to FORMYLA.
_re_external_url = re.compile(r"https?://(?!(?:www\.)?formyla\.)[^\s)]+", re.IGNORECASE)

_MAX_ANSWER_LEN = 1200

SAFE_FALLBACK = (
    "Пока у меня нет точной информации по этому вопросу. "
    "Лучше уточнить у поддержки FORMYLA."
)


def sanitize_answer(answer: str) -> Tuple[str, bool]:
    """Return ``(clean_answer, was_replaced)``.

    If the model output looks unsafe (hedging, external URLs, too long, or
    drifted into generic talk), replace it with :data:`SAFE_FALLBACK`.
    """
    if not answer or not answer.strip():
        return SAFE_FALLBACK, True

    text = answer.strip()

    if len(text) > _MAX_ANSWER_LEN:
        return SAFE_FALLBACK, True

    if _re_external_url.search(text):
        return SAFE_FALLBACK, True

    for rx in _re_hedge:
        if rx.search(text):
            return SAFE_FALLBACK, True

    return text, False


# Canonical refusal phrases (matched in service to short-circuit).
REFUSAL_OFF_TOPIC = (
    "Я помощник по сайту FORMYLA и могу отвечать только на вопросы о "
    "платформе: адаптивный тест, прогресс, задачи, методы, тарифы и "
    "подготовка."
)
REFUSAL_SOLVE_TASK = (
    "Я не решаю школьные и олимпиадные задачи за тебя. Я помогаю "
    "разобраться, как пользоваться сайтом FORMYLA: где найти задачи, как "
    "пройти адаптивный тест, как отслеживать прогресс."
)


__all__ = [
    "ALLOWED_KEYWORDS",
    "classify_topic",
    "sanitize_answer",
    "SAFE_FALLBACK",
    "REFUSAL_OFF_TOPIC",
    "REFUSAL_SOLVE_TASK",
]
