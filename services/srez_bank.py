# -*- coding: utf-8 -*-
"""
services/srez_bank.py — Банк задач утреннего среза из файла FORMYLA_SREZ.jsonl.

Читает FORMYLA_SREZ.jsonl из корня проекта и индексирует задачи по
(grade, theme_id, level). Используется services/theme_probe.py как
ПРИОРИТЕТНЫЙ источник задач утреннего среза (когда AdaptiveTask пуст).

Формат одной строки (JSONL):
    {
      "grade": 7,                # класс 5..11
      "theme_id": "G7_T01",      # id подтемы (как в цикле куратора)
      "theme": "Многочлены...",  # человеческое название (опционально)
      "level": 1,                # уровень сложности 1..4
      "text": "...",             # условие задачи
      "answer": "...",           # ответ
      "solution": "...",         # решение (опционально)
      "method": "..."            # метод (опционально)
    }

Ключ подбора: (grade, theme_id, level).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_BANK_PATH: Path = Path(__file__).resolve().parents[1] / "FORMYLA_SREZ.jsonl"

_index: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}
_loaded: bool = False


def load() -> None:
    """Загрузить FORMYLA_SREZ.jsonl в память (идемпотентно)."""
    global _loaded, _index
    if _loaded:
        return
    _index = {}
    if not _BANK_PATH.exists():
        logger.warning("srez_bank: %s not found", _BANK_PATH)
        _loaded = True
        return

    with open(_BANK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            grade = d.get("grade")
            theme_id = (d.get("theme_id") or "").strip()
            level = d.get("level")
            if grade is None or not theme_id or level is None:
                continue
            key = (int(grade), theme_id, int(level))
            _index.setdefault(key, []).append(d)

    total = sum(len(v) for v in _index.values())
    logger.info("srez_bank: loaded %d tasks for %d keys", total, len(_index))
    _loaded = True


def has_rows() -> bool:
    load()
    return bool(_index)


def get_tasks(grade: int, theme_id: str, level: int,
              count: int = 5,
              exclude_texts: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Вернуть до ``count`` задач по (grade, theme_id, level).

    При нехватке доливает задачи соседних уровней той же подтемы.
    exclude_texts — уже показанные условия (для исключения повторов).
    """
    load()
    key = (grade, (theme_id or "").strip(), level)
    tasks = list(_index.get(key, []))

    if len(tasks) < count:
        for lv in (level - 1, level + 1, level - 2, level + 2):
            for extra in _index.get((grade, (theme_id or "").strip(), lv), []):
                tasks.append(extra)
                if len(tasks) >= count:
                    break
            if len(tasks) >= count:
                break

    # Уникализируем по тексту условия
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for t in tasks:
        text = (t.get("text") or t.get("statement") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(t)

    if exclude_texts:
        unique = [t for t in unique if (t.get("text") or t.get("statement") or "").strip() not in exclude_texts]

    return unique[:count]


_FIGURE_DIR = Path(__file__).resolve().parents[1] / "static" / "srez_figures"
_figure_cache: Dict[str, str] = {}


def load_figure_svg(uid: str) -> Optional[str]:
    """Вернуть содержимое SVG-чертежа для задачи среза по task_uid.

    Чертежи лежат в static/srez_figures/<uid>.svg (распакованы из архива
    «Итоговый набор чертежей — 362 SVG»).  Возвращает SVG-строку или None.
    Кэшируется в памяти процесса.
    """
    uid = (uid or "").strip()
    if not uid:
        return None
    if uid in _figure_cache:
        return _figure_cache[uid]
    p = _FIGURE_DIR / f"{uid}.svg"
    if not p.exists():
        _figure_cache[uid] = None
        return None
    try:
        svg = p.read_text(encoding="utf-8")
    except Exception:
        _figure_cache[uid] = None
        return None
    _figure_cache[uid] = svg
    return svg


def has_figure(uid: str) -> bool:
    """Есть ли готовый чертёж для task_uid."""
    return load_figure_svg(uid) is not None
