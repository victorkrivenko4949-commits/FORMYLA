# -*- coding: utf-8 -*-
r"""daily_tasks/math_normalize.py — единый нормализатор формул для «Задач дня».

Две стадии:
  1. normalize_math_text  — голые \frac/\sqrt/x^2/√5/60°/3/4 вне разделителей
                            оборачиваются в $ ... $ (иначе KaTeX их не рендерит).
  2. beautify_math        — ВНУТРИ $..$ / \(..\) / $$..$$ / \[..\]:
                            √(...) и \sqrt(...)  -> \sqrt{...}   (черта над подкоренным)
                            (a)/(b), a/b         -> \frac{a}{b}  (нормальная дробь вместо слеша)
normalize_math_full = обе стадии. Идемпотентна.
Подключено: models.DailyTaskItem (validates + load-event) и pipeline/step2_opus.py.
"""
import json
import re

# ── стадия 1 ────────────────────────────────────────────────────────────
_PROTECT_RE = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^\n$]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])")
_SUP_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_CMD = r"(?:frac|dfrac|tfrac|sqrt|cdot|times|pm|leq|geq|neq|infty|pi|sum|prod|int|lim|binom|overline|angle|circ|sin|cos|tg|ctg|log|ln|le|ge|ne|div)"
_ARG = r"(?:\{(?:[^{}]|\{[^{}]*\})*\})"
_TOKEN = r"(?:\\" + _CMD + r"(?:\[[^\]]*\])?" + _ARG + r"*|[A-Za-z0-9]+(?:[\^_](?:" + _ARG + r"|-?\d+|[A-Za-z]))+)"
_MATH_RUN_RE = re.compile(r"(?<![\\\w{$])" + _TOKEN + r"(?:\s*(?:[-+=*/·]|\\cdot|\\times|\\pm)?\s*" + _TOKEN + r")*")
_NUM_FRAC_RE = re.compile(r"(?<![\w/.,])(\d{1,4})/(\d{1,4})(?![\w/]|[.,]\d)")
_UNI = {"π": r"\pi", "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "±": r"\pm",
        "∞": r"\infty", "⋅": r"\cdot", "×": r"\times"}


def _pre_unicode(s: str) -> str:
    s = re.sub(r"√\s*\(([^()]+)\)", r"\\sqrt{\1}", s)
    s = re.sub(r"√\s*(\d+(?:[.,]\d+)?|[A-Za-z])", r"\\sqrt{\1}", s)
    s = re.sub(r"([A-Za-z0-9\)])([²³⁴⁵⁶⁷⁸⁹⁰¹]+)",
               lambda m: "%s^{%s}" % (m.group(1), m.group(2).translate(_SUP_MAP)), s)
    s = re.sub(r"(\d)\s*°", r"\1^{\\circ}", s)
    for k, v in _UNI.items():
        s = s.replace(k, v)
    return s


def normalize_math_text(text, numeric_fractions=True):
    """Обернуть «голые» формулы вне разделителей в $...$."""
    if not text:
        return text
    parts = _PROTECT_RE.split(text)
    out = []
    for i, chunk in enumerate(parts):
        if i % 2 == 1 or not chunk:
            out.append(chunk)
            continue
        s = _pre_unicode(chunk)
        if numeric_fractions:
            s = _NUM_FRAC_RE.sub(r"\\frac{\1}{\2}", s)
        s = _MATH_RUN_RE.sub(lambda m: "$" + m.group(0).strip() + "$", s)
        out.append(s)
    return "".join(out)


# ── стадия 2 ────────────────────────────────────────────────────────────
_PAREN = r"\((?:[^()]|\([^()]*\))*\)"
_SQRT_UNI_P = re.compile(r"(?:√|\\surd)\s*(" + _PAREN + r")")
_SQRT_UNI_S = re.compile(r"(?:√|\\surd)\s*([A-Za-z0-9]+(?:\^(?:\{[^{}]*\}|\w))?)")
_SQRT_PAREN = re.compile(r"\\sqrt\s*(" + _PAREN + r")")
_OPERAND = (r"(?:" + _PAREN
            + r"|\\sqrt(?:\[[^\]]*\])?\{(?:[^{}]|\{[^{}]*\})*\}"
            + r"|\\?[A-Za-z0-9]+(?:\^(?:\{[^{}]*\}|\w))?)")
_SLASH_FRAC = re.compile(r"(?<![\w}\\])(" + _OPERAND + r")\s*/\s*(" + _OPERAND + r")")
_SPAN_RE = re.compile(r"(\$\$)([\s\S]+?)(\$\$)|(\$)([^\n$]+?)(\$)|(\\\()([\s\S]+?)(\\\))|(\\\[)([\s\S]+?)(\\\])")


def _balanced(s):
    d = 0
    for c in s:
        d += c == "("
        d -= c == ")"
        if d < 0:
            return False
    return d == 0


def _strip_parens(p):
    p = p.strip()
    if p.startswith("(") and p.endswith(")") and _balanced(p[1:-1]):
        return p[1:-1]
    return p


def beautify_math_inner(m):
    r"""Внутри формулы: √(...)/\sqrt(...) -> \sqrt{...}; a/b -> \frac{a}{b}."""
    s = m
    s = _SQRT_UNI_P.sub(lambda x: r"\sqrt{" + x.group(1)[1:-1] + "}", s)
    s = _SQRT_UNI_S.sub(lambda x: r"\sqrt{" + x.group(1) + "}", s)
    s = _SQRT_PAREN.sub(lambda x: r"\sqrt{" + x.group(1)[1:-1] + "}", s)
    prev = None
    while prev != s:
        prev = s
        s = _SLASH_FRAC.sub(
            lambda x: r"\frac{" + _strip_parens(x.group(1)) + "}{" + _strip_parens(x.group(2)) + "}", s)
    return s


def beautify_math(text):
    r"""Применить beautify_math_inner ко всем $..$, $$..$$, \(..\), \[..\]."""
    if not text:
        return text

    def rep(m):
        g = [x for x in m.groups() if x is not None]
        return g[0] + beautify_math_inner(g[1]) + g[2]
    return _SPAN_RE.sub(rep, text)


def normalize_math_full(text):
    """Полная нормализация: обернуть голые формулы, затем украсить внутри."""
    if not isinstance(text, str) or not text:
        return text
    return beautify_math(normalize_math_text(text))


def normalize_hints_json(value):
    """hints хранится JSON-строкой со списком — нормализуем каждый элемент."""
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return value
    if not isinstance(data, list):
        return value
    return json.dumps([normalize_math_full(h) if isinstance(h, str) else h for h in data],
                      ensure_ascii=False)


def normalize_task_item(item):
    """Нормализовать текстовые поля dict-задачи (pipeline / сериализация)."""
    if not isinstance(item, dict):
        return item
    for key in ("task_text", "solution", "reason"):
        if isinstance(item.get(key), str):
            item[key] = normalize_math_full(item[key])
    hints = item.get("hints")
    if isinstance(hints, list):
        item["hints"] = [normalize_math_full(h) if isinstance(h, str) else h for h in hints]
    elif isinstance(hints, str):
        item["hints"] = normalize_hints_json(hints)
    return item
