# -*- coding: utf-8 -*-
"""
daily_tasks/formyla_bank.py — Банк «Задачи дня» из файла FORMYLA_BANK.jsonl.

Читает FORMYLA_BANK.jsonl из корня проекта и индексирует задачи по
(grade, topic, level). Это ПРИОРИТЕТНЫЙ источник «Задач дня»: когда вы
зальёте сюда всю базу, pick_daily_set возьмёт задачи именно отсюда.

Формат одной строки (JSONL):
    {
      "grade": 5,               # класс 5..11
      "topic": "Числа...",      # тема/подтема (любая строка-ключ)
      "level": 1,               # уровень сложности 1..4
      "position": 1,            # порядковый номер внутри (grade, topic, level)
      "task_text": "...",       # условие задачи
      "correct_answer": "...",  # ответ
      "solution": "...",        # решение (опционально)
      "methods": ["..."],       # методы (опционально)
      "tags": ["..."]           # теги (опционально)
    }

Ключ подбора: (grade, topic, level). Дополнительно поддерживает
детерминированную перемешку под пользователя (md5(user_id:position)),
чтобы разные ученики получали задачи в разном порядке.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Файл лежит в корне проекта (на один уровень выше daily_tasks/).
_BANK_PATH: Path = Path(__file__).resolve().parents[1] / "FORMYLA_BANK.jsonl"

_index: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}
_loaded: bool = False


def load() -> None:
    """Загрузить FORMYLA_BANK.jsonl в память (идемпотентно)."""
    global _loaded, _index
    if _loaded:
        return
    _index = {}
    if not _BANK_PATH.exists():
        logger.warning("formyla_bank: %s not found", _BANK_PATH)
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
            topic = (d.get("topic") or "").strip()
            level = d.get("level")
            if grade is None or not topic or level is None:
                continue
            key = (int(grade), topic, int(level))
            _index.setdefault(key, []).append(d)

    total = sum(len(v) for v in _index.values())
    logger.info("formyla_bank: loaded %d tasks for %d keys", total, len(_index))
    _loaded = True


def has_rows() -> bool:
    """True, если в FORMYLA_BANK.jsonl есть хотя бы одна задача."""
    load()
    return bool(_index)


def get_tasks(grade: int, topic: str, level: int,
              count: int = 5, user_id: Optional[int] = None,
              exclude_positions: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
    """Вернуть до ``count`` задач по (grade, topic, level).

    Порядок детерминированно перемешан по пользователю (если передан
    user_id) через md5(user_id:position). Уже выданные позиции можно
    исключить через exclude_positions.
    """
    load()
    key = (grade, (topic or "").strip(), level)
    tasks = list(_index.get(key, []))

    # Сначала пробуем точный уровень; при нехватке доливаем соседние уровни.
    if len(tasks) < count:
        for lv in (level - 1, level + 1, level - 2, level + 2):
            for extra in _index.get((grade, (topic or "").strip(), lv), []):
                tasks.append(extra)
                if len(tasks) >= count:
                    break
            if len(tasks) >= count:
                break

    # Уникализируем по position
    seen: Set[int] = set()
    unique: List[Dict[str, Any]] = []
    for t in tasks:
        pos = t.get("position")
        if pos is None or int(pos) in seen:
            continue
        seen.add(int(pos))
        unique.append(t)

    if exclude_positions:
        unique = [t for t in unique if int(t.get("position", -1)) not in exclude_positions]

    if user_id is not None:
        def _sort_key(t: Dict[str, Any]) -> str:
            return hashlib.md5(
                f"{user_id}:{t.get('position')}".encode("utf-8")
            ).hexdigest()
        unique.sort(key=_sort_key)

    return unique[:count]


def available_topics(grade: int) -> List[str]:
    """Список тем (topic) для класса, для которых есть задачи."""
    load()
    topics = sorted({t for (g, t, _), v in _index.items() if g == grade and v})
    return topics


def task_count(grade: int, topic: str, level: int) -> int:
    load()
    return len(_index.get((grade, (topic or "").strip(), level), []))
