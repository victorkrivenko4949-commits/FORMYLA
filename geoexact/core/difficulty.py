"""Оценка сложности задачи перед запросом к эксперту.

deepseek-v4-flash (без рассуждений) отвечает одним числом 1..10. По числу
выбирается модель эксперта: 1..5 — обычная (gpt-6-luna), 6..10 — «тяжёлая»
(gpt-6-sol). Порог задаётся GEOEXACT_HARD_THRESHOLD (по умолчанию 6).

Этап не должен становиться новой точкой отказа: любая ошибка (сеть, тайм-аут,
не число в ответе, нет ключа) даёт None, и выбор модели идёт как раньше.
Платный вызов один, без повторов.
"""
from __future__ import annotations

import os
import re
import time

import requests

BASE = "https://api.deepseek.com"
RATE_MODEL = (os.environ.get("GEOEXACT_RATE_MODEL") or "").strip() or "deepseek-v4-flash"
HARD_MODEL = (os.environ.get("GEOEXACT_EXPERT_HARD_MODEL") or "").strip() or "gpt-6-sol"
# Оценка >= порога уходит в HARD_MODEL. По умолчанию 6: 1..5 -> Луна, 6..10 -> Sol.
HARD_THRESHOLD = int(os.environ.get("GEOEXACT_HARD_THRESHOLD", "6"))
# Секунд на весь этап. Flash обычно отвечает за 1-3 с.
RATE_TIMEOUT = float(os.environ.get("GEOEXACT_RATE_TIMEOUT", "8"))

RATE_PROMPT = (
    "Оцени сложность геометрической задачи по шкале от 1 до 10, "
    "где 1 — одно очевидное действие по определению или формуле, "
    "5 — обычная школьная задача на 2–3 шага, "
    "8 — задача с нестандартным дополнительным построением, "
    "10 — олимпиадная задача с неочевидным построением и длинным доказательством.\n"
    "Ответь только одним целым числом от 1 до 10, без слов, знаков и пояснений.\n\n"
    "Задача:\n{problem}"
)

_NUM = re.compile(r"\d+")


def parse_rating(text: str | None) -> int | None:
    """Первое целое в ответе, если оно в 1..10; иначе None."""
    m = _NUM.search(text or "")
    if not m:
        return None
    n = int(m.group())
    return n if 1 <= n <= 10 else None


def rate_difficulty(problem: str, diag: dict | None = None, *, session=None,
                    timeout: float | None = None) -> int | None:
    """Одно число 1..10 от Flash или None, если оценка не получена.

    В diag пишутся difficulty, rate_model, rate_seconds (и rate_error при сбое),
    чтобы _diag_text мог показать «сложность 7 -> gpt-6-sol».
    """
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key or not (problem or "").strip():
        return None
    t0 = time.time()
    tmo = RATE_TIMEOUT if timeout is None else timeout
    payload = {
        "model": RATE_MODEL,
        "messages": [{"role": "user", "content": RATE_PROMPT.format(problem=problem.strip())}],
        "max_tokens": 4,
        "temperature": 0,
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    post = (session or requests).post
    try:
        r = post(f"{BASE}/v1/chat/completions", headers=headers, json=payload,
                 timeout=(min(5.0, tmo), tmo))
        if r.status_code == 400 and "thinking" in (r.text or ""):
            payload.pop("thinking", None)
            r = post(f"{BASE}/v1/chat/completions", headers=headers, json=payload,
                     timeout=(min(5.0, tmo), tmo))
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        n = parse_rating(text)
        if diag is not None:
            diag.update(difficulty=n, rate_model=RATE_MODEL,
                        rate_seconds=round(time.time() - t0, 1))
            if n is None:
                diag["rate_error"] = f"не число: {str(text)[:40]!r}"
        return n
    except Exception as e:  # noqa: BLE001 — любой сбой этапа не должен ронять запрос
        if diag is not None:
            diag.update(difficulty=None, rate_model=RATE_MODEL,
                        rate_seconds=round(time.time() - t0, 1),
                        rate_error=f"{type(e).__name__}: {str(e)[:80]}")
        return None


def pick_expert(difficulty: int | None, default: str, fallbacks=()) -> list[str]:
    """Порядок моделей эксперта с учётом оценки.

    None или ниже порога: [default, *fallbacks]. От порога: [HARD_MODEL, default, *fallbacks]
    без дубликатов — если Sol молчит, Луна остаётся запасной.
    """
    order = [default, *fallbacks]
    if difficulty is not None and difficulty >= HARD_THRESHOLD:
        order = [HARD_MODEL, *order]
    seen: list[str] = []
    for m in order:
        if m and m not in seen:
            seen.append(m)
    return seen


def diag_text(diag: dict | None) -> str:
    """Короткая строка для сообщения пользователю: «сложность 7 -> gpt-6-sol»."""
    if not diag or "difficulty" not in diag:
        return ""
    n = diag.get("difficulty")
    if n is None:
        err = diag.get("rate_error", "")
        return f"сложность не оценена ({err})" if err else "сложность не оценена"
    target = HARD_MODEL if n >= HARD_THRESHOLD else "обычная модель"
    return f"сложность {n} -> {target} ({diag.get('rate_seconds', '?')} с)"
