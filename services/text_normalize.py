# -*- coding: utf-8 -*-
"""services/text_normalize.py — нормализация LaTeX-условия задачи в плоский текст.

Приводит обёртки и команды LaTeX к юникодному/ASCII виду, чтобы регексы
разборщиков (условие → точки/углы/длины) могли их матчить.

Порядок важен: сначала снимаем обёртки, затем команды, затем юникод,
в конце сворачиваем пробелы.  Идемпотентна.
"""

from __future__ import annotations

import re
from typing import Tuple

# ──────────────────────────────────────────────────────────────────────────
# Обёртки (снимаются первыми): \( ... \)  \[ ... \]  $$ ... $$  $ ... $
# ──────────────────────────────────────────────────────────────────────────
_WRAPPERS = [
    (re.compile(r"\\\(\s*(.*?)\s*\\\)"), r"\1"),
    (re.compile(r"\\\[\s*(.*?)\s*\\\]"), r"\1"),
    (re.compile(r"\$\$\s*(.*?)\s*\$\$"), r"\1"),
    (re.compile(r"\$\s*(.*?)\s*\$"), r"\1"),
]

# ──────────────────────────────────────────────────────────────────────────
# Команды LaTeX -> текст.  Порядок важен (более длинные/специфичные первыми).
# ──────────────────────────────────────────────────────────────────────────
_COMMANDS = [
    (r"\operatorname", ""),
    (r"\mathrm", ""),
    (r"\text", ""),
    (r"\overline", ""),
    (r"\vec", ""),
    (r"\mathbf", ""),
    (r"\mathit", ""),
    (r"\left", ""),
    (r"\right", ""),
    (r"\triangle", "треугольник "),
    (r"\angle", "∠"),
    (r"\parallel", "∥"),
    (r"\perp", "⊥"),
    (r"\cdot", "·"),
    (r"\times", "×"),
    (r"\ldots", "…"),
    (r"\dots", "…"),
    (r"\alpha", "α"),
    (r"\beta", "β"),
    (r"\gamma", "γ"),
    (r"\degree", "°"),
    # Суперскрипт градуса: 45^\circ / 45^{\circ} -> 45°
    (r"^{\circ}", "°"),
    (r"^\circ", "°"),
    (r"^{\degree}", "°"),
    (r"^\degree", "°"),
    (r"\circ", "°"),
    (r"\,", " "),
    (r"\;", " "),
    (r"\:", " "),
    (r"\!", " "),
    (r"\ ", " "),
    (r"\~", " "),
]

# \frac{a}{b} -> a/b
_FRAC_RE = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
# \sqrt{x} -> sqrt(x)
_SQRT_RE = re.compile(r"\\sqrt\{([^{}]*)\}")

# Символы юникода (в самом конце).
_UNICODE = [
    (re.compile(r"[−–—]"), "-"),
    (re.compile(r"[’′]"), "'"),
]

_MULTI_SPACE_RE = re.compile(r"\s+")

# Склеивание латиницы с кириллицей после снятия обёртки («угол\(A\)» → «уголA»).
_CYR_LAT_RE = re.compile(r"([А-Яа-яЁё])([A-Za-z])")
_LAT_CYR_RE = re.compile(r"([A-Za-z])([А-Яа-яЁё])")


def normalize_condition(text: str) -> str:
    """Нормализовать условие: снять LaTeX-обёртки/команды, привести символы.

    Идемпотентна: normalize_condition(normalize_condition(x)) == normalize_condition(x).
    """
    if not text:
        return ""
    s = str(text)

    # 1. Обёртки.
    for rx, repl in _WRAPPERS:
        s = rx.sub(repl, s)

    # 2. \frac и \sqrt (до общих команд, т.к. содержат фигурные скобки).
    s = _FRAC_RE.sub(r"\1/\2", s)
    s = _SQRT_RE.sub(r"sqrt(\1)", s)

    # 3. Команды.
    for cmd, repl in _COMMANDS:
        s = s.replace(cmd, repl)

    # 4. Юникод.
    for rx, repl in _UNICODE:
        s = rx.sub(repl, s)

    # 5. Свернуть пробелы.
    s = _MULTI_SPACE_RE.sub(" ", s)

    # 6. Убрать повторы градуса: «45°°» -> «45°».
    s = re.sub(r"°+", "°", s)

    # 7. Склеить знак угла с именем: «∠ BAC» -> «∠BAC».
    s = re.sub(r"∠\s+", "∠", s)

    # 8. Склеивание латиницы с кириллицей: «уголA» -> «угол A».
    s = _CYR_LAT_RE.sub(r"\1 \2", s)
    s = _LAT_CYR_RE.sub(r"\1 \2", s)

    s = _MULTI_SPACE_RE.sub(" ", s)
    return s.strip()


def normalized_or_original(text: str) -> Tuple[str, str]:
    """Вернуть (нормализованный, оригинал).

    Оригинал НЕ мутируется — нужен для показа пользователю.
    """
    return normalize_condition(text), (text or "")
