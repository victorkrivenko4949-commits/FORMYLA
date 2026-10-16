# -*- coding: utf-8 -*-
"""OLYMP_CATALOG_V3.4 — чистка данных каталога при загрузке JSON (без правки файлов).

  * LaTeX: \\( \\) -> $ $, \\[ \\] -> $$ $$, убраны обёртки \\begin{task}/\\begin{solution},
    \\textbf{Ответ:} -> «Ответ: », битые глифы PDF (￿ ⇡ ↵ ⌧) -> нормальные символы;
  * решение, в которое при распознавании PDF попали следующие задачи варианта
    («© МФТИ», «Ответы и решения», «\\n2.\\nа)» …), обрезается на первом таком маркере;
  * если в условии оказалось «Решение.»/«Ответ:», хвост переносится в solution/answer;
  * повтор условия в начале решения (блок \\begin{task}…\\end{task} у Gemini) удаляется;
  * рисунки: остаются только реально существующие файлы, отсутствующие -> fig_missing;
  * задачи с разрушенными формулами (следы PDF: «\\SAB», «6=», «p a2+b2», «BH BC») -> garbled=True.
"""
from __future__ import annotations

import os
import re

STATUS_LABEL = {
    "official_found": "официальное", "official": "официальное", "AI_verified": "проверено ИИ",
    "gemini_solved": "Gemini", "official_variant": "вариант источника", "AI_generated": "сгенерировано",
    "AI_generated_with_hints": "набросок", "unresolved": "не решено", "broken_text": "условие повреждено",
    "figure_only": "только рисунок",
}

_ENV_BLOCK_TASK = re.compile(r"\\begin\{task\*?\}.*?\\end\{task\*?\}", re.S)
_ENV_TAGS = re.compile(r"\\(?:begin|end)\{(?:task|solution|problem|proof|answer)\*?\}")
_ANS_TEXTBF = re.compile(r"\\textbf\{\s*Ответ\s*:?\s*\}\s*:?")
_GLYPHS = {
    "\ufffd": "—", "\uffff": "—",
    "⇡": "π", "↵": "α", "⌧": "τ", "⇧": "П",
    "\u00ad": "", "\u200b": "",
}
_CUT_MARKERS = [
    re.compile(r"©\s*МФТИ"),
    re.compile(r"Олимпиада\s+[“\"«]?Физтех"),
    re.compile(r"Ответы и решения\s"),
    re.compile(r"\n\s*\d{1,2}\.\s*\n\s*[а-г]\)\s"),
    re.compile(r"\n\s*[б-г]\)\s[А-ЯЁ]"),
    re.compile(r"\n\s*(?:Задача|ЗАДАЧА)\s+\d{1,2}[.:]"),
]
_SPLIT_IN_TEXT = re.compile(r"(?:^|\n)\s*(Решение[.:]\s*|Ответ[.:]\s*)", re.M)
_GARBLED_PATTERNS = [
    re.compile(r"\\[A-Z]{2,4}\b(?![a-z])"),
    re.compile(r"\b6=\b"),
    re.compile(r"\bp\s+[a-z0-9]\w*\s*[+\-]"),
    re.compile(r"\b[a-zA-Z]\d\b(?![\w$^{])"),
    re.compile(r"\b(?:sin|cos|tg|ctg)\s+[a-zA-Zα-ω]\s*=\s*[A-Z]{2}\s+[A-Z]{2}\b"),
    re.compile(r"\bC\d\s+\d{1,3}\b"),
    re.compile(r"[\u2300-\u23ff\u2190-\u21ff]"),
]

QA_KEYS = ("tasks", "task_block_removed", "solution_in_text", "text_dup_in_solution",
           "solution_truncated", "text_truncated", "fig_missing", "no_solution", "garbled")


def new_qa() -> dict:
    return {k: 0 for k in QA_KEYS}


def norm_tex(s):
    """Разметка, понятная KaTeX: $…$ / $$…$$, без окружений и битых глифов."""
    if not s or not isinstance(s, str):
        return s or ""
    t = s
    for k, v in _GLYPHS.items():
        if k in t:
            t = t.replace(k, v)
    t = re.sub(r"(?<!\\)\\\(", "$", t)
    t = re.sub(r"(?<!\\)\\\)", "$", t)
    t = re.sub(r"(?<!\\)\\\[", "$$", t)
    t = re.sub(r"(?<!\\)\\\]", "$$", t)
    t = _ANS_TEXTBF.sub("Ответ: ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def cut_tail(s: str, min_keep: int = 120):
    """Обрезка на первом маркере «началась следующая задача». Возвращает (текст, обрезано?)."""
    if not s:
        return s, False
    best = None
    for rx in _CUT_MARKERS:
        m = rx.search(s)
        if m and m.start() >= min_keep and (best is None or m.start() < best):
            best = m.start()
    if best is None:
        return s, False
    return s[:best].rstrip(" \n\t.,;:—-"), True


def garbled_score(s: str) -> int:
    """Число признаков «формулы разрушены при распознавании PDF»."""
    if not s:
        return 0
    return sum(len(rx.findall(s)) for rx in _GARBLED_PATTERNS)


def clean_task(t: dict, qa: dict, fig_dir: str) -> dict:
    text = norm_tex(t.get("text"))
    sol = norm_tex(t.get("solution"))
    ans = norm_tex(t.get("answer"))

    if "\\begin{task" in sol:
        sol = _ENV_BLOCK_TASK.sub("", sol).strip()
        qa["task_block_removed"] += 1
    text = _ENV_TAGS.sub("", text).strip()
    sol = _ENV_TAGS.sub("", sol).strip()
    ans = _ENV_TAGS.sub("", ans).strip()

    m = _SPLIT_IN_TEXT.search(text)
    if m and m.start() >= 40:
        tail = text[m.start():].strip()
        text = text[:m.start()].rstrip()
        qa["solution_in_text"] += 1
        if tail.startswith("Ответ"):
            body = re.sub(r"^Ответ[.:]\s*", "", tail)
            if not ans and len(body) <= 200 and "Решение" not in body:
                ans = body
            elif "Решение" in body:
                a_part, s_part = body.split("Решение", 1)
                if not ans and a_part.strip():
                    ans = a_part.strip()
                if not sol:
                    sol = re.sub(r"^[.:]\s*", "", s_part).strip()
        else:
            body = re.sub(r"^Решение[.:]\s*", "", tail)
            ma = re.search(r"(?:^|\n)\s*Ответ[.:]\s*(.+?)\s*$", body, re.S)
            if ma and not ans and len(ma.group(1)) <= 200:
                ans = ma.group(1).strip()
                body = body[:ma.start()].rstrip()
            if not sol or len(sol) < 40:
                sol = body

    if text and sol and sol.startswith(text):
        sol = sol[len(text):].lstrip(" \n.:—-")
        qa["text_dup_in_solution"] += 1

    sol, cut = cut_tail(sol)
    if cut:
        qa["solution_truncated"] += 1
    text2, cut2 = cut_tail(text, min_keep=60)
    if cut2 and len(text2) >= 60:
        text = text2
        qa["text_truncated"] += 1

    t["garbled"] = (garbled_score(sol) + garbled_score(text)) >= 3
    if t["garbled"]:
        qa["garbled"] += 1

    missing = 0
    for key in ("fig_statement", "fig_solution"):
        keep = []
        for f in t.get(key) or []:
            p = os.path.join(fig_dir, *str(f).replace("\\", "/").split("/"))
            if os.path.exists(p):
                keep.append(f)
            else:
                missing += 1
        t[key] = keep
    qa["fig_missing"] += missing
    t["fig_missing"] = missing

    t["text"], t["solution"], t["answer"] = text, sol, ans
    if not sol:
        qa["no_solution"] += 1
    return t
