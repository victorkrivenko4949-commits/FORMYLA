# -*- coding: utf-8 -*-
"""services/daily_bank_keys.py — единый ключ темы для основного банка (шаг 8, вариант Б).

Решение: ключ темы в daily_task_bank.subtopic — theme_id вида G9_T16, тот же,
что в monthly_cycle, data/theme_to_section.json и data/theme_titles.json.
Класс зашит в префикс, поэтому отдельная колонка grade не требуется, а
задачи одного класса не могут утечь другому: grade_of_theme() сверяется
с классом ученика при выборке.

Чистые функции без Flask/БД — используются загрузчиком, выдачей и тестами.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

THEME_RE = re.compile(r"^G(?P<grade>\d{1,2})_T(?P<num>\d{2})$")
CANONICAL_SECTIONS = ("algebra", "number_theory", "geometry", "combinatorics", "logic")
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def parse_theme_id(theme_id: Optional[str]) -> Optional[Tuple[int, int]]:
    """'G9_T16' -> (9, 16); иначе None. Регистр НЕ нормализуется: ключи в
    справочниках в верхнем регистре, и строка 'g9_t16' считается невалидной."""
    if not theme_id:
        return None
    m = THEME_RE.match(theme_id.strip())
    if not m:
        return None
    grade, num = int(m.group("grade")), int(m.group("num"))
    if not (5 <= grade <= 11):
        return None
    return grade, num


def grade_of_theme(theme_id: Optional[str]) -> Optional[int]:
    parsed = parse_theme_id(theme_id)
    return parsed[0] if parsed else None


@lru_cache(maxsize=1)
def _theme_to_section() -> Dict[str, str]:
    path = os.path.join(_DATA_DIR, "theme_to_section.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _theme_titles() -> Dict[str, str]:
    path = os.path.join(_DATA_DIR, "theme_titles.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def section_of_theme(theme_id: Optional[str]) -> Optional[str]:
    """Раздел по theme_id из data/theme_to_section.json, регистр ключа сохраняется."""
    if not theme_id:
        return None
    sec = _theme_to_section().get(theme_id.strip())
    return sec if sec in CANONICAL_SECTIONS else None


def title_of_theme(theme_id: Optional[str]) -> Optional[str]:
    if not theme_id:
        return None
    return _theme_titles().get(theme_id.strip())


def is_known_theme(theme_id: Optional[str]) -> bool:
    return parse_theme_id(theme_id) is not None and theme_id.strip() in _theme_to_section()


def title_section_map() -> Dict[str, str]:
    """Русское название темы -> канонический раздел (по theme_titles + theme_to_section).

    Нужно для записи ответов в движок уровня: у задач дня item.topic — это название
    темы, а не раздел (дефект U6 этапа 4). Названия, которые в разных классах
    относятся к разным разделам, НЕ включаются (неоднозначность -> пусть решает
    вызывающий код), поэтому карта безопасна для подмешивания в SECTION_RU_TO_SLUG.
    """
    sections = _theme_to_section()
    out: Dict[str, str] = {}
    conflict: set = set()
    for tid, title in _theme_titles().items():
        sec = sections.get(tid)
        t = (title or "").strip()
        if not t or sec not in CANONICAL_SECTIONS:
            continue
        if t in out and out[t] != sec:
            conflict.add(t)
        out.setdefault(t, sec)
    for t in conflict:
        out.pop(t, None)
    return out


def section_of_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    return title_section_map().get(title.strip())
