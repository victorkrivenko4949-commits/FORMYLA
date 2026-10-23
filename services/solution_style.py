# -*- coding: utf-8 -*-
"""services/solution_style.py — детерминированный классификатор стиля решения.

CH19 Step 2.  Классифицирует решение (solution) по ключевым словам без LLM.
Никаких внешних зависимостей, только stdlib re.

Стили:
  * constructive — решение явно строит объекты;
  * coordinate   — вводит координаты / векторы / скалярное произведение;
  * complex      — комплексные числа;
  * trig         — теорема синусов/косинусов, 2R sin, cos значения;
  * angle_chase  — только счёт углов по данной конфигурации;
  * area_ratio   — только отношения площадей и отрезков.

Приоритет (первое совпадение по списку):
  complex > coordinate > constructive > trig > angle_chase > area_ratio > None

classify_solution_style(record) -> str
  record — dict с полями 'solution' и 'statement' (как в JSONL).
  Возвращает один из шести стилей или "unknown" при отсутствии сигнала.
"""
from __future__ import annotations

import re
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────
# Паттерны.  Все — по стемам русских слов, регистронезависимо.
# ──────────────────────────────────────────────────────────────────────────

_COMPLEX_RE = re.compile(
    r"(комплексн|\\mathbb\{?C|\\mathbb\{?Z|модуль комплекс|"
    r"z_1|z_2|z_3|\\bar|сопряжённ|сопряженн|аргумент комплекс|"
    r"\|z\|=|abc\s*=\s*1|единичн(?:ой|ая)\s+окружност(?:и|ь).*комплекс)",
    re.IGNORECASE,
)

_COORDINATE_RE = re.compile(
    r"(координатн|координат|метод координат|вектор|скалярн|"
    r"декартов|введ[ёе]м?\s+систему\s+координат|A\s*\(0\s*,\s*0\)|"
    r"B\s*\(\s*1\s*,\s*0\)|ось\s+абсцисс|ось\s+ординат|\$\s*[A-Z]\s*\([^)]*\d)",
    re.IGNORECASE,
)

_CONSTRUCTIVE_RE = re.compile(
    r"(провед|провед[ёе]м|соедин|соедин[яи]м|продл|продлим|постро|построим|"
    r"опуст|опустим|впишем|вписываем|опишем|описываем|"
    r"отметим\s+точк|обозначим\s+через|обозначим\s+точк|"
    r"точк[уа]\s+пересечения|пересечени[яе]\s+обознач|"
    r"касательн(?:ую|ой).*провед|через\s+точк.*провед)",
    re.IGNORECASE,
)

_TRIG_RE = re.compile(
    r"(теорем[ау]\s+синусов|теорем[ау]\s+косинусов|2R\s*\\?sin|2R\s*sin|"
    r"\\sin|\\cos|\\tan|\\ctg|sin\s*\(|cos\s*\(|"
    r"тригонометр|формул[ау]\s+косинусов|формул[ау]\s+синусов)",
    re.IGNORECASE,
)

_ANGLE_CHASE_RE = re.compile(
    r"(угол\s+[A-Z]{1,3}\s*=|\\angle\s*[A-Z]{1,3}|сумм[ау]\s+углов|"
    r"вписанн(?:ый|ого)\s+угл|центральн(?:ый|ого)\s+угл|"
    r"равн(?:ы|ых)\s+угл|угл[а-я]*\s+равен|величин[ау]\s+угл)",
    re.IGNORECASE,
)

_AREA_RATIO_RE = re.compile(
    r"(площад|S_\{|\\frac\{\s*S|S\s*=\s*|отношени[ея]\s+площадей|"
    r"площад[еи]й|S\^|S_\w|высот[а-я]*\s*=\s*|отношени[ея]\s+отрезков|"
    r"медиан[а-я]*\s+дел)",
    re.IGNORECASE,
)


def classify_solution_style(record) -> str:
    """Детерминированная классификация стиля решения.

    record: dict с ключами solution / statement (как в JSONL).
    Возвращает один из шести стилей или 'unknown'.
    """
    if not isinstance(record, dict):
        return "unknown"

    solution = str(record.get("solution") or "")
    statement = str(record.get("statement") or "")
    text = solution if solution.strip() else statement
    if not text.strip():
        return "unknown"

    # Порядок приоритета: complex > coordinate > constructive > trig >
    # angle_chase > area_ratio.
    if _COMPLEX_RE.search(text):
        return "complex"
    if _COORDINATE_RE.search(text):
        return "coordinate"
    if _CONSTRUCTIVE_RE.search(text):
        return "constructive"
    if _TRIG_RE.search(text):
        return "trig"
    if _ANGLE_CHASE_RE.search(text):
        return "angle_chase"
    if _AREA_RATIO_RE.search(text):
        return "area_ratio"
    return "unknown"


def expected_has_aux(style: str) -> Optional[bool]:
    """Ожидание has_aux по стилю.

    constructive -> True;  coordinate/complex/trig -> False;
    angle_chase/area_ratio/unknown -> None (любое).
    """
    if style == "constructive":
        return True
    if style in ("coordinate", "complex", "trig"):
        return False
    return None
