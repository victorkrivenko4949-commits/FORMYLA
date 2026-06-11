# -*- coding: utf-8 -*-
r"""Канонизация LaTeX-корней \sqrt[n]{...} и \sqrt{...}.

Инцидент 2026-06-11: на странице задачи (например /olympiads/task/12100,
метод G6, задача G6.17) кубический корень рендерился как болтающаяся
маленькая «³» без знака радикала:

    (a²+b²+c²)/3 ≥ ³ a²b²c² = ³ 1 = 1      ← \sqrt потерян

Причина — повреждённый LaTeX в данных. Команда \sqrt[3]{...} в разных
местах была испорчена одним из способов:

  * \sqrt[3] X            — потеряны фигурные скобки вокруг аргумента
  * \sqrt [3]{...}        — пробел между \sqrt и [n]
  * ∛(...) / ³√(...)      — юникод-корень вместо LaTeX
  * ^{3}\sqrt{...}        — «³» отдельным символом превратилась в степень
                            (классический баг замены '³'->'^{3}' ДО '√')

Этот модуль приводит такие формы к каноничному KaTeX-виду
\sqrt[n]{...} / \sqrt{...}. Функция идемпотентна.

БЕЗОПАСНОСТЬ — главное требование. НЕ трогаем конструкции, которые
неотличимы от легитимной математики:
  * a^2\sqrt{2}   («a в квадрате умножить на √2») — НЕ корень, оставляем.
  * голый [n]{..} без \sqrt — НЕ трогаем (риск сломать интервалы/индексы).
Битые кубкорни приходят как юникод (∛ / ³√) — это однозначный сигнал.
"""
from __future__ import annotations

import re

# ── Юникод-корни ───────────────────────────────────────────────────────────
# ∛ (U+221B) — единый кубический радикал.
# «³√» — суперскрипт-3 (U+00B3) + радикал. Обрабатываем cbrt ДО обычного √,
# иначе одиночный √ съест корень и «³» останется висеть.
_RE_UNICODE_CBRT_PAREN = re.compile(r"(?:∛|³\s*√)\s*\(([^()]*)\)")
_RE_UNICODE_CBRT_TOKEN = re.compile(r"(?:∛|³\s*√)\s*([A-Za-z0-9]+)")
# Обычный квадратный радикал √ (без предшествующего ³ и без \).
_RE_UNICODE_SQRT_PAREN = re.compile(r"(?<![³\\])√\s*\(([^()]*)\)")
_RE_UNICODE_SQRT_TOKEN = re.compile(r"(?<![³\\])√\s*([A-Za-z0-9]+)")

# ── \sqrt с лишним пробелом перед [n] ───────────────────────────────────────
_RE_SQRT_SPACE_BRACKET = re.compile(r"\\sqrt\s+\[")

# ── \sqrt[n] БЕЗ { вокруг аргумента ─────────────────────────────────────────
# \sqrt[3]{X} оставляем как есть; чиним только формы без скобок.
#   \sqrt[3](X)        -> \sqrt[3]{X}
#   \sqrt[3]\frac{}{}  -> \sqrt[3]{\frac{}{}}
#   \sqrt[3] X         -> \sqrt[3]{X}   (только пробел + ОДИН символ)
_RE_SQRT_N_PAREN = re.compile(r"\\sqrt\s*\[(\d+)\]\s*\(([^()]*)\)")
_RE_SQRT_N_CMD = re.compile(r"\\sqrt\s*\[(\d+)\]\s*(\\[A-Za-z]+(?:\{[^{}]*\})*)")
# С пробелом: \sqrt[3] X -> \sqrt[3]{X} (ОДИН символ).
_RE_SQRT_N_BARE = re.compile(r"\\sqrt\s*\[(\d+)\]\s+([A-Za-z0-9])(?![A-Za-z0-9])")
# Без пробела: \sqrt[3]abc -> \sqrt[3]{abc}. KaTeX без {} возьмёт только
# первый символ — то есть это явно битый корень. Оборачиваем весь
# примыкающий алфанум-токен (включая ^/_ и {} в степенях).
_RE_SQRT_N_NOSPACE = re.compile(
    r"\\sqrt\s*\[(\d+)\]([A-Za-z0-9]+(?:[\^_]\{?[A-Za-z0-9]+\}?)*)"
)

# ── \sqrt (без [n]) БЕЗ { ───────────────────────────────────────────────────
_RE_SQRT_PAREN = re.compile(r"\\sqrt\s*\(([^()]*)\)")
# bare «\sqrt 2» -> «\sqrt{2}»: ТОЛЬКО пробел + ОДИН символ, дальше не алфанум.
_RE_SQRT_BARE = re.compile(r"\\sqrt\s+([A-Za-z0-9])(?![A-Za-z0-9{\[])")


def _convert_unicode_balanced(s: str) -> str:
    r"""Юникод-корень над сбалансированной скобочной группой: √((a)(b)) -> \sqrt{(a)(b)}.

    Regex [^()]* не покрывает вложенные скобки, поэтому такие подкоренные
    выражения сканируем вручную со счётчиком скобок. Триггер однозначен:
    √ / ∛ / ³√ непосредственно перед «(». Один проход; повторный вызов
    ничего не меняет (после конвертации перед группой стоит «{», не корень).
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        # Определяем тип корня и длину префикса.
        deg = None
        plen = 0
        if ch == "∛":
            deg, plen = "3", 1
        elif ch == "³":
            j = i + 1
            while j < n and s[j].isspace():
                j += 1
            if j < n and s[j] == "√":
                deg, plen = "3", (j - i + 1)
        elif ch == "√" and (i == 0 or s[i - 1] not in "³\\"):
            deg, plen = "", 1
        if deg is None:
            out.append(ch)
            i += 1
            continue
        # Пропускаем пробелы между корнем и «(».
        k = i + plen
        while k < n and s[k].isspace():
            k += 1
        if k >= n or s[k] != "(":
            out.append(s[i:i + plen])
            i += plen
            continue
        # Сканируем сбалансированную группу.
        depth = 0
        m = k
        while m < n:
            if s[m] == "(":
                depth += 1
            elif s[m] == ")":
                depth -= 1
                if depth == 0:
                    break
            m += 1
        if depth != 0:  # несбалансировано — не трогаем
            out.append(s[i:i + plen])
            i += plen
            continue
        inner = s[k + 1:m]  # содержимое внешних скобок
        idx = ("[" + deg + "]") if deg else ""
        out.append(r"\sqrt" + idx + "{" + inner + "}")
        i = m + 1
    return "".join(out)


def normalize_roots(text: str) -> str:
    r"""Приводит корни в строке к каноничному \sqrt[n]{...} / \sqrt{...}.

    Идемпотентна и безопасна для корректных формул (см. докстринг модуля).
    """
    if not text or not isinstance(text, str):
        return text or ""

    s = text

    # Вложенные юникод-корни (√(x+√(x+11))) требуют нескольких проходов: regex
    # с [^()] чинит внутренний корень первым, внешний — только на следующем
    # проходе. Поэтому крутим блок подстановок до стабилизации (cap 10).
    for _ in range(10):
        prev = s

        # 0) Юникод-корень над сбалансированной скобочной группой √((a)(b)).
        #    Regex ниже ([^()]*) такие случаи не покрывает.
        s = _convert_unicode_balanced(s)

        # 1) Юникод-корни -> LaTeX. Сначала cbrt (³√/∛), потом обычный √.
        s = _RE_UNICODE_CBRT_PAREN.sub(lambda m: r"\sqrt[3]{" + m.group(1) + "}", s)
        s = _RE_UNICODE_CBRT_TOKEN.sub(lambda m: r"\sqrt[3]{" + m.group(1) + "}", s)
        s = _RE_UNICODE_SQRT_PAREN.sub(lambda m: r"\sqrt{" + m.group(1) + "}", s)
        s = _RE_UNICODE_SQRT_TOKEN.sub(lambda m: r"\sqrt{" + m.group(1) + "}", s)

        # 2) Лишний пробел перед [n]: \sqrt [3]{...} -> \sqrt[3]{...}
        s = _RE_SQRT_SPACE_BRACKET.sub(r"\\sqrt[", s)

        # 3) \sqrt[n] без фигурных скобок -> добавить {}.
        s = _RE_SQRT_N_PAREN.sub(lambda m: r"\sqrt[" + m.group(1) + "]{" + m.group(2) + "}", s)
        s = _RE_SQRT_N_CMD.sub(lambda m: r"\sqrt[" + m.group(1) + "]{" + m.group(2) + "}", s)
        s = _RE_SQRT_N_BARE.sub(lambda m: r"\sqrt[" + m.group(1) + "]{" + m.group(2) + "}", s)
        s = _RE_SQRT_N_NOSPACE.sub(lambda m: r"\sqrt[" + m.group(1) + "]{" + m.group(2) + "}", s)

        # 4) \sqrt (без индекса) без скобок.
        s = _RE_SQRT_PAREN.sub(lambda m: r"\sqrt{" + m.group(1) + "}", s)
        s = _RE_SQRT_BARE.sub(lambda m: r"\sqrt{" + m.group(1) + "}", s)

        if s == prev:
            break

    return s


def normalize_root_fields(item: dict, fields=None) -> tuple[dict, list[str]]:
    """Нормализует корни в указанных полях словаря (копия, не мутирует вход).

    Возвращает (новый_словарь, список_изменённых_полей).
    """
    if fields is None:
        fields = ("text", "solution", "idea", "answer", "task_text",
                  "solution_idea", "condition_md", "solution_md", "idea_md")
    if not isinstance(item, dict):
        return item, []
    out = dict(item)
    changed = []
    for fld in fields:
        v = out.get(fld)
        if isinstance(v, str) and v:
            nv = normalize_roots(v)
            if nv != v:
                out[fld] = nv
                changed.append(fld)
    return out, changed


__all__ = ["normalize_roots", "normalize_root_fields"]
