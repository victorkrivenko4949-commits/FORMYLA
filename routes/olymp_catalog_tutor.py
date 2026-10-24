# -*- coding: utf-8 -*-
"""OLYMP_CATALOG_V3.4 — ИИ-тьютор каталога (deepseek-v4-pro, thinking) и LaTeX-нормализация ответов."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time

from routes.olymp_catalog_clean import STATUS_LABEL

logger = logging.getLogger(__name__)

TUTOR_MODEL = os.environ.get("OLYMP_TUTOR_MODEL", "deepseek-v4-pro").strip()
TUTOR_MAX_TOKENS = int(os.environ.get("OLYMP_TUTOR_MAX_TOKENS", "8000"))
TUTOR_THINKING = os.environ.get("OLYMP_TUTOR_THINKING", "1").strip() not in ("0", "false", "no")
TUTOR_HISTORY = int(os.environ.get("OLYMP_TUTOR_HISTORY", "24"))
PREP_TTL = int(os.environ.get("OLYMP_TUTOR_PREP_TTL", str(12 * 3600)))

PREP_CACHE: dict = {}          # uid -> {"brief": str, "ts": float, "usage": dict, "secs": float}
_PREP_LOCKS: dict = {}
_PREP_LOCKS_GUARD = threading.Lock()

SYSTEM_PROMPT = (
    "Ты — ИИ-тьютор FORMYLA по олимпиадной математике (модель deepseek-v4-pro). "
    "Ты уже ЗАРАНЕЕ, до первого вопроса ученика, полностью проанализировал задачу: разобрал условие, "
    "понял эталонное решение по шагам, нашёл ключевую идею, проверил ответ, продумал типичные ошибки и "
    "вероятные вопросы. Ниже даны задача и твой конспект подготовки. Отвечай как преподаватель, который "
    "уже всё знает про эту задачу: без «дайте подумать», сразу по существу.\n\n"
    "ПРАВИЛА:\n"
    "1. Отвечай по-русски, кратко и структурно; Markdown допустим (### заголовки, списки, **жирный**).\n"
    "2. ВСЕ формулы, переменные, числа с операциями — ТОЛЬКО в LaTeX: строчные $...$, выключные $$...$$. "
    "Запрещены \\( \\), \\[ \\], формулы без долларов и юникод-математика (×, ², √, ≤, °) — "
    "используй \\cdot, ^{2}, \\sqrt{}, \\le, ^{\\circ}.\n"
    "3. Если ученик просит подсказку — веди по шагам (сократовский метод), не раскрывай всё сразу. "
    "Если явно просит полное решение — дай полностью и аккуратно.\n"
    "4. Если ученик присылает своё решение — проверь по шагам, укажи первую ошибку и почему это ошибка.\n"
    "5. Если эталонное решение содержит пробел или ошибку — честно скажи и дай исправленную версию.\n"
    "6. Не выдумывай условий, которых нет в задаче. Если чего-то не хватает (например, рисунка) — скажи об этом."
)

PREPARE_PROMPT = (
    "ЖЁСТКАЯ ИНСТРУКЦИЯ: сейчас ученика ещё нет. Проанализируй задачу, ПОЛНОСТЬЮ пойми эталонное решение "
    "(проверь каждый переход и итоговый ответ) и подготовься к вопросам. Результат — твой рабочий конспект, "
    "который ты будешь держать перед глазами во время диалога. Формат — Markdown, формулы только в $...$ / $$...$$:\n\n"
    "### Суть задачи\n1–2 предложения: что дано, что требуется.\n"
    "### Ключевая идея\nГлавный приём/наблюдение, без которого задача не решается.\n"
    "### Решение по шагам\nНумерованный список; для каждого шага — почему он верен.\n"
    "### Проверка ответа\nСверка с эталонным ответом; если есть расхождение — разбор.\n"
    "### Где ученики ошибаются\n3 типичные ошибки.\n"
    "### Вероятные вопросы ученика и заготовки ответов\n5 пунктов «вопрос → короткий ответ».\n"
    "### Подсказки по уровням\nТри подсказки: лёгкая (направление), средняя (ключевой факт), сильная (почти решение).\n"
    "### Замечания к эталону\nЕсли эталон неполон/ошибочен — опиши и исправь; иначе напиши «Эталон корректен»."
)

RESTORE_SECTION = (
    "\n### Восстановленное решение\nПолное, аккуратное решение задачи в правильной LaTeX-разметке "
    "($...$ / $$...$$), которым следует заменить повреждённый или отсутствующий эталон."
)

GARBLED_NOTE = (
    "ВНИМАНИЕ: эталон распознан из PDF с искажениями формул (потеряны дроби, корни, индексы, знаки \\angle и ≠; "
    "«p a2+b2» означает корень из a²+b², «BH BC» — дробь BH/BC, «\\SAB» — угол SAB). Восстанови математический "
    "смысл по контексту и опирайся на восстановленную версию, а не на буквальный текст."
)

FIG_MISSING_NOTE = (
    "ВНИМАНИЕ: условие ссылается на рисунок, но рисунок к задаче в каталоге ОТСУТСТВУЕТ. Не придумывай, что на нём "
    "изображено. В начале подготовки честно отметь это, восстанови конфигурацию из текста условия и эталонного решения "
    "настолько, насколько это возможно, и явно перечисли, какие детали рисунка остаются неизвестными. "
    "Если ученик спросит про рисунок — предложи открыть первоисточник (ИСТОЧНИК ниже)."
)

_UNICODE_MATH = {
    "×": r"\cdot", "·": r"\cdot", "÷": ":", "−": "-", "≤": r"\le", "≥": r"\ge", "≠": r"\ne",
    "±": r"\pm", "∞": r"\infty", "√": r"\sqrt", "°": r"^{\circ}", "∠": r"\angle", "∈": r"\in",
    "∉": r"\notin", "⊂": r"\subset", "∪": r"\cup", "∩": r"\cap", "→": r"\to", "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow", "∑": r"\sum", "∏": r"\prod", "≡": r"\equiv", "≈": r"\approx",
    "²": "^{2}", "³": "^{3}", "π": r"\pi", "α": r"\alpha", "β": r"\beta", "γ": r"\gamma",
}


def latex_fallback(text: str) -> str:
    """\\( \\) -> $ $, \\[ \\] -> $$ $$, юникод-математика внутри $…$ -> LaTeX."""
    if not text:
        return text
    t = text.replace(r"\(", "$").replace(r"\)", "$").replace(r"\[", "$$").replace(r"\]", "$$")

    def fix_math(m):
        inner = m.group(0)
        for k, v in _UNICODE_MATH.items():
            inner = inner.replace(k, v + " " if v.startswith("\\") and not v.endswith("}") else v)
        return inner

    t = re.sub(r"\$\$.*?\$\$|\$[^$\n]+?\$", fix_math, t, flags=re.S)
    t = re.sub(r"\$\$\s*\n?\s*\$\$", "", t)
    return t


def normalize_tutor_latex(text: str) -> str:
    try:
        from method_week.latex import normalize_latex  # type: ignore
        text = normalize_latex(text)
    except Exception:  # noqa: BLE001
        pass
    return latex_fallback(text)


def task_context(t: dict) -> str:
    head = "%s, %s, %s" % (t.get("olymp", ""), t.get("year", ""), t.get("round", ""))
    if t.get("day"):
        head += ", день %s" % t["day"]
    head += ", %s класс, задача %s" % (t.get("grade", ""), t.get("num", ""))
    parts = ["ЗАДАЧА: " + head, "УСЛОВИЕ:\n" + (t.get("text") or "").strip()]
    if t.get("fig_statement"):
        note = "К условию прилагается рисунок (%d шт.), в текстовом виде он недоступен — опирайся на условие." % len(t["fig_statement"])
        if t.get("fig_anchor") == "block_snapshot":
            note += " Рисунок — снимок фрагмента страницы первоисточника с текстом задачи."
        parts.append(note)
    elif t.get("fig_not_linked"):
        parts.append(FIG_MISSING_NOTE)
    if t.get("answer"):
        parts.append("ЭТАЛОННЫЙ ОТВЕТ:\n" + str(t["answer"]).strip())
    sol = (t.get("solution") or "").strip()
    if sol:
        parts.append("ЭТАЛОННОЕ РЕШЕНИЕ (статус: %s):\n%s" % (STATUS_LABEL.get(t.get("status"), t.get("status")), sol))
        if t.get("garbled"):
            parts.append(GARBLED_NOTE)
    else:
        parts.append("ЭТАЛОННОЕ РЕШЕНИЕ: отсутствует — реши задачу самостоятельно и будь особенно внимателен.")
    if t.get("source"):
        parts.append("ИСТОЧНИК: " + str(t["source"]))
    return "\n\n".join(parts)


async def _ds_chat(messages, thinking: bool, max_tokens: int, temperature: float):
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient
    async with DeepSeekClient() as client:
        client._model = TUTOR_MODEL  # принудительно v4-pro
        text, usage = await client.async_chat(TUTOR_MODEL, messages, temperature=temperature,
                                              max_tokens=max_tokens, thinking=thinking)
        return text, {"in": usage.input_tokens, "out": usage.output_tokens, "cost_usd": round(usage.cost_usd, 6)}


def call_model(messages, thinking: bool = True, max_tokens: int = TUTOR_MAX_TOKENS, temperature: float = 0.3):
    return asyncio.run(_ds_chat(messages, thinking, max_tokens, temperature))


def _prep_lock(uid: str) -> threading.Lock:
    with _PREP_LOCKS_GUARD:
        lock = _PREP_LOCKS.get(uid)
        if lock is None:
            lock = _PREP_LOCKS[uid] = threading.Lock()
        return lock


def get_or_prepare(t: dict, force: bool = False) -> dict:
    uid = t["uid"]
    hit = PREP_CACHE.get(uid)
    if hit and not force and time.time() - hit["ts"] < PREP_TTL:
        return {**hit, "cached": True}
    with _prep_lock(uid):
        hit = PREP_CACHE.get(uid)
        if hit and not force and time.time() - hit["ts"] < PREP_TTL:
            return {**hit, "cached": True}
        prompt = PREPARE_PROMPT
        if t.get("garbled") or not (t.get("solution") or "").strip():
            prompt += RESTORE_SECTION
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_context(t) + "\n\n" + prompt},
        ]
        t0 = time.time()
        text, usage = call_model(messages, thinking=TUTOR_THINKING, temperature=0.2)
        brief = normalize_tutor_latex(text).strip()
        entry = {"brief": brief, "ts": time.time(), "usage": usage, "secs": round(time.time() - t0, 1)}
        PREP_CACHE[uid] = entry
        logger.info("[olymp_tutor] prepared uid=%s in %.1fs usage=%s", uid[:12], entry["secs"], usage)
        return {**entry, "cached": False}
