# -*- coding: utf-8 -*-
"""
daily_tasks/figure_map.py — карта готовых чертежей для «Задач дня».

Источник чертежей: static/daily_figures/<task_id>_<grade>.svg (2187 файлов).
Маппинг «условие задачи -> файл чертежа» лежит в file2_2187_conditions.jsonl
в корне проекта. Этот модуль индексирует его и позволяет по (grade, условие)
получить путь к готовому SVG.

Используется:
  * daily_task_rotation.py — при создании DailyTaskItem из FORMYLA_BANK.jsonl
  * скриптом бэкфилла — чтобы проставить figure_svg_path уже созданным сетами
  * daily_tasks/services.py — рантайм-фолбэк в _get_item_figure_url
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_MAP_PATH: Path = Path(__file__).resolve().parents[1] / "file2_2187_conditions.jsonl"

_index: Dict[Tuple[int, str], str] = {}
_loaded: bool = False


def _norm(s: str) -> str:
    """Нормализовать условие для сопоставления (свернуть пробелы)."""
    return re.sub(r"\s+", " ", (s or "")).strip()


def load() -> None:
    """Загрузить file2_2187_conditions.jsonl (идемпотентно)."""
    global _loaded, _index
    if _loaded:
        return
    _index = {}
    if not _MAP_PATH.exists():
        logger.warning("figure_map: %s not found", _MAP_PATH)
        _loaded = True
        return

    try:
        with open(_MAP_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                grade = d.get("grade")
                condition = _norm(d.get("condition") or "")
                svg = (d.get("figure_svg_path") or "").strip()
                if grade is None or not condition or not svg:
                    continue
                _index[(int(grade), condition)] = svg
    except Exception as exc:  # pragma: no cover
        logger.warning("figure_map: failed to load %s: %s", _MAP_PATH, exc)

    logger.info("figure_map: loaded %d figure entries", len(_index))
    _loaded = True


def resolve(grade: Optional[int], task_text: str) -> Optional[str]:
    """Вернуть путь к SVG-чертежу для задачи, либо None.

    ``task_text`` — условие задачи (как в FORMYLA_BANK.jsonl / DailyTaskItem).
    ``grade`` — класс ученика (для однозначности сопоставления).
    """
    load()
    if not _index:
        return None
    key = (grade, _norm(task_text))
    return _index.get(key)


def has_figures() -> bool:
    load()
    return bool(_index)
