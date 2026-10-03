"""Оценка сложности задачи перед запросом к эксперту и сторож первого токена.

1) deepseek-v4-flash (без рассуждений) отвечает одним числом 1..10. По числу
   выбирается модель эксперта: 1..5 — обычная (gpt-6-luna), 6..10 — «тяжёлая»
   (gpt-6-sol). Порог задаётся GEOEXACT_HARD_THRESHOLD (по умолчанию 6).
2) Сторож: если после заголовков ответа за FIRST_TOKEN_LIMIT секунд не пришло
   ни символа текста, ни символа рассуждения, соединение закрывается и тот же
   запрос уходит следующей модели из списка. Именно так выглядит зависание
   роутера: «заголовки через 16 с, текст не пошёл за 100 с (рассуждение 0 симв.)».

Оба этапа не должны становиться новой точкой отказа: любая ошибка оценки даёт
None (порядок моделей как раньше), сторож срабатывает только при полной тишине.
Платный вызов оценки один, без повторов.
"""
from __future__ import annotations

import os
import queue
import re
import threading
import time

import requests

BASE = "https://api.deepseek.com"
RATE_MODEL = (os.environ.get("GEOEXACT_RATE_MODEL") or "").strip() or "deepseek-v4-flash"
HARD_MODEL = (os.environ.get("GEOEXACT_EXPERT_HARD_MODEL") or "").strip() or "gpt-6-sol"
# Оценка >= порога уходит в HARD_MODEL. По умолчанию 6: 1..5 -> Луна, 6..10 -> Sol.
HARD_THRESHOLD = int(os.environ.get("GEOEXACT_HARD_THRESHOLD", "6"))
# Секунд на весь этап оценки. Flash обычно отвечает за 1-3 с.
RATE_TIMEOUT = float(os.environ.get("GEOEXACT_RATE_TIMEOUT", "8"))
# GEOEXACT_DIFFICULTY_ROUTER=0 выключает оценку сложности без деплоя кода.
ENABLED = (os.environ.get("GEOEXACT_DIFFICULTY_ROUTER") or "1").strip().lower() not in ("0", "no", "off")
# Сторож первого токена: секунд тишины после заголовков до смены модели.
# GEOEXACT_FIRST_TOKEN_LIMIT=0 выключает сторож.
FIRST_TOKEN_LIMIT = float(os.environ.get("GEOEXACT_FIRST_TOKEN_LIMIT", "25"))

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
        out = f"сложность не оценена ({err})" if err else "сложность не оценена"
    else:
        target = HARD_MODEL if n >= HARD_THRESHOLD else "обычная модель"
        out = f"сложность {n} -> {target} ({diag.get('rate_seconds', '?')} с)"
    if diag.get("silent"):
        out += "; молчали: " + ", ".join(diag["silent"])
    return out


# --------------------------------------------------------------------------
# Сторож первого токена.
#
# expert_text читает поток через r.iter_lines() и по ходу пишет в diag поля
# first (секунда первого символа текста) и reasoning (символов рассуждения).
# Прокси сессии подменяет ответ: строки читаются во вспомогательном потоке,
# а генератор ждёт их с тайм-аутом. Пока diag не показал ни текста, ни
# рассуждения, а после заголовков прошло больше FIRST_TOKEN_LIMIT секунд,
# соединение закрывается и поднимается ExpertSilent — обёртка expert_text
# ловит её и повторяет запрос следующей моделью.

class ExpertSilent(Exception):
    """Модель прислала заголовки, но за FIRST_TOKEN_LIMIT с не прислала ни символа."""
    code = "EXPERT_SILENT"

    def __init__(self, model: str, seconds: float):
        self.model, self.seconds = model, seconds
        super().__init__(f"{model}: ни текста, ни рассуждения за {seconds:.0f} с после заголовков")


class _ResponseProxy:
    def __init__(self, real, diag: dict, limit: float):
        self._real, self._diag, self._limit = real, diag, limit

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _close(self):
        close = getattr(self._real, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 — соединение уже бесполезно
                pass

    def _started(self) -> bool:
        return self._diag.get("first") is not None or bool(self._diag.get("reasoning"))

    def iter_lines(self, *args, **kwargs):
        q: queue.Queue = queue.Queue()

        def reader():
            try:
                for line in self._real.iter_lines(*args, **kwargs):
                    q.put(("line", line))
                q.put(("end", None))
            except BaseException as e:  # noqa: BLE001 — передаём в основной поток
                q.put(("err", e))

        threading.Thread(target=reader, daemon=True).start()
        t_headers = time.time()
        started = False
        while True:
            try:
                kind, value = q.get(timeout=0.25)
            except queue.Empty:
                kind, value = None, None
            if kind == "line":
                yield value
                # expert_text обработал строку и обновил diag до следующего next()
            elif kind == "end":
                return
            elif kind == "err":
                raise value
            if not started:
                started = self._started()
                if not started and time.time() - t_headers > self._limit:
                    self._close()
                    raise ExpertSilent(str(self._diag.get("model", "")), time.time() - t_headers)


class _SessionProxy:
    def __init__(self, real, diag: dict, limit: float):
        self._real, self._diag, self._limit = real, diag, limit

    def __getattr__(self, name):
        return getattr(self._real, name)

    def post(self, url, **kwargs):
        r = self._real.post(url, **kwargs)
        if kwargs.get("stream"):
            return _ResponseProxy(r, self._diag, self._limit)
        return r


# --------------------------------------------------------------------------
# Подключение к llm.expert_text без правки llm.py.
#
# expert_text строит список моделей из глобальных EXPERT_MODEL / EXPERT_FALLBACKS
# в момент вызова. install() оборачивает функцию: Flash оценивает задачу,
# на время одного вызова глобальные подменяются нужным порядком и
# восстанавливаются в finally; при ExpertSilent запрос повторяется со
# следующей модели списка. Замок нужен, чтобы два параллельных вызова
# (доп. построение и «полное решение» в одном процессе) не путали порядок.
# Вызывается из geoexact/core/__init__.py при импорте пакета.
_lock = threading.Lock()


def install(llm_module) -> bool:
    """Обернуть llm_module.expert_text оценкой сложности и сторожем. Повторный вызов — no-op."""
    original = getattr(llm_module, "expert_text", None)
    if original is None or getattr(original, "_difficulty_routed", False):
        return False

    def expert_text(sess, problem, history=None, max_out=16000, diag=None, messages=None):
        if diag is None:
            diag = {}
        n = rate_difficulty(problem, diag) if ENABLED else None
        models = pick_expert(n, llm_module.EXPERT_MODEL, llm_module.EXPERT_FALLBACKS)
        guarded = _SessionProxy(sess, diag, FIRST_TOKEN_LIMIT) if FIRST_TOKEN_LIMIT > 0 else sess
        last = None
        for i, model in enumerate(models):
            with _lock:
                saved = (llm_module.EXPERT_MODEL, llm_module.EXPERT_FALLBACKS)
                llm_module.EXPERT_MODEL, llm_module.EXPERT_FALLBACKS = model, tuple(models[i + 1:])
                try:
                    return original(guarded, problem, history, max_out=max_out, diag=diag,
                                    messages=messages)
                except ExpertSilent as e:
                    diag.setdefault("silent", []).append(e.model or model)
                    last = e
                finally:
                    llm_module.EXPERT_MODEL, llm_module.EXPERT_FALLBACKS = saved
        raise last if last is not None else RuntimeError("expert_text: нет моделей")

    expert_text._difficulty_routed = True
    expert_text._original = original
    expert_text.__doc__ = original.__doc__
    expert_text.__name__ = "expert_text"
    llm_module.expert_text = expert_text
    return True
