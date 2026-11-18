# -*- coding: utf-8 -*-
"""Read-only индекс FORMYLA_BANK.jsonl для конструктора листка.

Читает тот же файл, что и daily_tasks/formyla_bank.py (``_BANK_PATH``), ничего
не пишет. Словари: by_id, by_grade_level[(grade, level)], by_topic[topic],
by_grade_topic_level[(grade, topic, level)]. Загружается один раз (lazy),
сброс — reset() (для тестов).
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from daily_tasks.formyla_bank import _BANK_PATH as BANK_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded = False
by_id: Dict[int, Dict[str, Any]] = {}
by_grade_level: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
by_topic: Dict[str, List[Dict[str, Any]]] = {}
by_grade_topic_level: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}

ID_FIELD = "position"


def _to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def reset() -> None:
    global _loaded
    with _lock:
        _loaded = False
        by_id.clear(); by_grade_level.clear(); by_topic.clear(); by_grade_topic_level.clear()


def load(path=None) -> None:
    global _loaded
    with _lock:
        if _loaded:
            return
        p = path or BANK_PATH
        if not p.exists():
            logger.warning("worksheets.bank_index: %s not found", p)
            _loaded = True
            return
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tid = _to_int(d.get(ID_FIELD))
                grade = _to_int(d.get("grade"))
                level = _to_int(d.get("level"))
                topic = (d.get("topic") or "").strip()
                if tid is None or grade is None or level is None or not topic:
                    continue
                if tid in by_id:
                    logger.warning("worksheets.bank_index: duplicate %s=%s", ID_FIELD, tid)
                    continue
                by_id[tid] = d
                by_grade_level.setdefault((grade, level), []).append(d)
                by_topic.setdefault(topic, []).append(d)
                by_grade_topic_level.setdefault((grade, topic, level), []).append(d)
        _loaded = True
        logger.info("worksheets.bank_index: %d tasks, %d (grade,level) keys, %d topics",
                    len(by_id), len(by_grade_level), len(by_topic))


def get(task_id: int) -> Optional[Dict[str, Any]]:
    load()
    return by_id.get(int(task_id))


def candidates(grade: int, level: int, topics=None) -> List[Dict[str, Any]]:
    load()
    if not topics:
        return list(by_grade_level.get((grade, level), []))
    out: List[Dict[str, Any]] = []
    for t in topics:
        out.extend(by_grade_topic_level.get((grade, t, level), []))
    return out


def topics_for_grade(grade: int) -> List[str]:
    load()
    return sorted({t for (g, t, _l) in by_grade_topic_level if g == grade})
