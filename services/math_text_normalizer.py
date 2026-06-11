r"""Нормализация математического текста для KaTeX-рендеринга.

Проблема (инцидент 2026-06-10): в разделе «Темы» задачи приходят без LaTeX
разделителей, например `Реши систему: {x^2 + y^2 = 10; x*y = 3}.` — KaTeX
такой текст не рендерит, и x^2 видно сырым ASCII.

Решение — на сервере прогонять текст через :func:`normalize_math_text`
ПЕРЕД отдачей шаблону.

Алгоритм
========
1. Сохраняем уже-LaTeX (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`) и
   HTML-теги в плейсхолдерах — их не трогаем.
2. Двигаемся по тексту слева направо и находим **математические фрагменты**:
   фрагмент состоит из непрерывных math-токенов (буквы латиницы, цифры,
   операторы `+ - * / = ^`, скобки, функции типа `sqrt`/`sin`/`log`, `_` для
   индексов). Граница — кириллица, пробельный знак за пунктуацией или конец
   строки.
3. Фрагмент **считается математическим** только если содержит хотя бы один
   «сильный» маркер: `^`, `*`, `sqrt`, `\sqrt`, `sin/cos/...`, или знак `=`
   между алфанумерик-токенами.
4. Внутри фрагмента причёсываем операторы (sqrt→\sqrt, *→\cdot,
   функции получают `\`-префикс).
5. Системы вида `{x+y=1; x*y=2}` оборачиваем в `$\{...,\;...\}$`.
6. Восстанавливаем плейсхолдеры.

Функция идемпотентна.
"""
from __future__ import annotations

import re

# ── Защищаемые фрагменты ──────────────────────────────────────────────────
_RE_PROTECTED = re.compile(
    r"\$\$[\s\S]+?\$\$"
    r"|\$[^$\n]+?\$"
    r"|\\\([\s\S]+?\\\)"
    r"|\\\[[\s\S]+?\\\]"
    r"|<(?:script|style|code|pre)[\s\S]*?</(?:script|style|code|pre)>"
    r"|<[^>]+>"
)


def _polish_inside(expr: str) -> str:
    """Заменяет ASCII-операторы на LaTeX внутри math-фрагмента."""
    s = expr
    # sqrt(x) → \sqrt{x}  (если не \sqrt уже)
    s = re.sub(r"(?<!\\)\bsqrt\s*\(([^()]+)\)", r"\\sqrt{\1}", s)
    # frac{a}{b} → \frac{a}{b}
    s = re.sub(
        r"(?<!\\)\bfrac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r"\\frac{\1}{\2}",
        s,
    )
    # тригонометрия / логарифмы → \sin etc.
    s = re.sub(
        r"(?<!\\)\b(sin|cos|tan|tg|ctg|cot|log|ln|exp)\s*\(",
        r"\\\1(",
        s,
    )
    # `a * b` → `a \cdot b`  (между алфанумерик токенами)
    s = re.sub(
        r"([0-9A-Za-z\}\)])\s*\*\s*([0-9A-Za-z\{\(\\])",
        r"\1 \\cdot \2",
        s,
    )
    return s


# ── Сегментация: разбиваем текст на чередующиеся куски «обычный текст»
#    и «потенциально математика». Потенциально-математика = непрерывный
#    кусок, состоящий из ASCII-символов math-алфавита.
#
# Math-алфавит:
#   - латинские буквы, цифры
#   - операторы: + - * / = ^ < >
#   - скобки: ( ) { } [ ]
#   - точка, запятая, точка с запятой
#   - подчёркивание (индекс)
#   - бэкслэш, пробел
#
# Граница — что-то, что НЕ из этого набора (кириллица, знаки препинания
# с пробелом после, эмодзи и т.п.).
_RE_NONMATH = re.compile(r"[^A-Za-z0-9_+\-*/=<>^(){}\[\].,;:\s\\]+")


# Регекс для систем `{ ... = ... ; ... = ... }` ВНУТРИ сегмента (не только
# на границах). Используется в `_normalize_segment` ПЕРЕД общим wrap'ом.
_RE_SYSTEM_INLINE = re.compile(r"\{\s*([^{}]*?=[^{}]*?)\s*\}")


def _wrap_system_braces_inline(seg: str) -> str:
    """Находит ВНУТРИ сегмента системы `{ ... }` и заменяет каждую на
    `$\\{...\\}$`. Если систем нет — возвращает исходный сегмент.
    """
    def _repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        parts = []
        for chunk in re.split(r";|,(?!\s*\d)", inner):
            c = chunk.strip()
            if c:
                parts.append(_polish_inside(c))
        if not parts:
            return m.group(0)
        body = r",\; ".join(parts)
        return "$\\{" + body + "\\}$"

    return _RE_SYSTEM_INLINE.sub(_repl, seg)


def _looks_like_math(seg: str) -> bool:
    """True, если сегмент стоит обернуть в `$...$`."""
    # Должен быть хотя бы один «сильный» math-маркер
    has_strong = bool(re.search(
        r"\^"                                 # степень
        r"|(?<!\w)\*(?!\*)"                   # `*` (но не `**`)
        r"|(?<!\\)\bsqrt\s*\("
        r"|\\sqrt\b"
        r"|(?<!\\)\bfrac\s*\{"
        r"|\\frac\b"
        r"|(?<!\\)\b(?:sin|cos|tan|tg|ctg|cot|log|ln|exp)\s*\("
        r"|[A-Za-z][A-Za-z0-9]*\s*=\s*[\d\-+(A-Za-z]"   # x = 5 / xy = ab
        r"|\d+\s*[+\-*/]\s*[A-Za-z]"
        r"|[A-Za-z]\s*[+\-*/]\s*\d",
        seg,
    ))
    if not has_strong:
        return False
    # И минимум 3 значащих символа (не одинокий `=`)
    stripped = seg.strip(" \t.,;:")
    return len(stripped) >= 3


def _normalize_segment(seg: str) -> str:
    """Нормализует один math-сегмент (без $) если он действительно math.

    Стратегия:
        1. Сначала ищем и оборачиваем системы `{ ... }` внутри сегмента —
           они становятся готовыми `$...$` фрагментами.
        2. Если после этого сегмент содержит ASCII-математику и `=`/`^`/`*`,
           оборачиваем непрерывный math-куск (без ведущей/хвостовой
           пунктуации и пробелов).
    """
    # 1) Системы в фигурных скобках — отдельный случай.
    seg = _wrap_system_braces_inline(seg)

    # Если сегмент уже стал полностью обёрнутым (одно `$...$` на весь
    # значащий контент), не трогаем.
    if not _looks_like_math(seg):
        return seg

    # Разбиваем сегмент на «голову» (ведущая пунктуация/пробелы),
    # «ядро» (math), «хвост» (пунктуация/пробелы).
    lead_match = re.match(r"^[\s\:\,\;\.\!\?\-\>]*", seg)
    trail_match = re.search(r"[\s\.\,\;\:\!\?]*$", seg)
    lead = lead_match.group(0) if lead_match else ""
    trail = trail_match.group(0) if trail_match else ""
    core_start = len(lead)
    core_end = len(seg) - len(trail) if trail else len(seg)
    core = seg[core_start:core_end]

    if not core or not _looks_like_math(core):
        return seg

    # Если в ядре уже есть `$` (мы обернули систему на шаге 1), значит
    # ядро состоит из готового LaTeX + хвост — отдаём как есть.
    if "$" in core:
        return seg

    polished = _polish_inside(core)
    return lead + "$" + polished + "$" + trail


def normalize_math_text(text: str) -> str:
    """См. модуль-докстринг."""
    if not text or not isinstance(text, str):
        return text or ""

    # ── Шаг 1: защищаем уже-LaTeX и HTML ──
    placeholders: list[str] = []

    def _save(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00PH{len(placeholders) - 1}\x00"

    safe = _RE_PROTECTED.sub(_save, text)

    # ── Шаг 2: сегментация по нон-math символам ──
    # `_RE_NONMATH` — кириллица, эмодзи, иероглифы (не-math). Разбиваем
    # текст на чередующиеся куски: math-кандидат / nonmath-разделитель.
    result_parts: list[str] = []
    pos = 0
    for m in _RE_NONMATH.finditer(safe):
        # До разделителя — math-кандидат
        candidate = safe[pos:m.start()]
        if candidate:
            result_parts.append(_normalize_segment(candidate))
        # Сам разделитель (русский текст и т.п.) — без изменений
        result_parts.append(m.group(0))
        pos = m.end()
    # Хвост
    tail = safe[pos:]
    if tail:
        result_parts.append(_normalize_segment(tail))

    safe = "".join(result_parts)

    # ── Шаг 3: восстанавливаем плейсхолдеры ──
    def _restore(m: re.Match) -> str:
        idx = int(m.group(1))
        if 0 <= idx < len(placeholders):
            return placeholders[idx]
        return m.group(0)

    return re.sub(r"\x00PH(\d+)\x00", _restore, safe)


def normalize_problem_fields(
    problem: dict,
    fields: tuple = ("text", "solution", "answer", "title"),
) -> dict:
    """Возвращает копию ``problem`` с нормализованными полями.

    Не модифицирует оригинал — кэш OLYMPIADS_DB / PROBLEMS_DB остаётся
    чистым.
    """
    if not isinstance(problem, dict):
        return problem
    out = dict(problem)
    for fld in fields:
        v = out.get(fld)
        if isinstance(v, str) and v:
            try:
                out[fld] = normalize_math_text(v)
            except Exception:
                # Любая ошибка — отдаём исходный текст
                pass
    return out
