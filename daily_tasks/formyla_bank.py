# -*- coding: utf-8 -*-
"""Bank of daily tasks from FORMYLA_BANK.jsonl, indexed by grade, topic and level."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)
_BANK_PATH: Path = Path(__file__).resolve().parents[1] / "FORMYLA_BANK.jsonl"
_index: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}
_loaded = False


def load() -> None:
    """Load and index the JSONL bank once per process."""
    global _loaded, _index
    if _loaded:
        return
    if not _BANK_PATH.exists():
        logger.warning("formyla_bank: %s not found", _BANK_PATH)
        return
    index: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}
    with open(_BANK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    continue
                topic = (d.get("topic") or "").strip()
                if not topic:
                    continue
                key = (int(d["grade"]), topic, int(d["level"]))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            index.setdefault(key, []).append(d)
    _index = index
    _loaded = True
    logger.info("formyla_bank: loaded %d tasks for %d keys",
                sum(map(len, _index.values())), len(_index))


def has_rows() -> bool:
    load()
    return bool(_index)


def _student_grade(user_id: Optional[int], supplied_grade: int) -> int:
    """Prefer the completed intake class over an outdated caller default."""
    if user_id is None:
        return supplied_grade
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if not cs:
            return supplied_grade
        prep = cs.prep_state
        if isinstance(prep, str):
            prep = json.loads(prep)
        if not isinstance(prep, dict):
            return supplied_grade
        intake = prep.get("intake") or prep.get("onboarding") or {}
        if not isinstance(intake, dict) or not intake.get("completed"):
            return supplied_grade
        class_level = intake.get("class_level") or intake.get("grade")
        if class_level is None:
            return supplied_grade
        grade = int(class_level)
        if 5 <= grade <= 11:
            if grade != supplied_grade:
                logger.warning("formyla_bank: correcting caller grade %s -> %s for user %s",
                               supplied_grade, grade, user_id)
            return grade
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    except Exception:
        logger.exception("formyla_bank: could not read intake grade for user %s", user_id)
    return supplied_grade


def get_tasks(grade: int, topic: str, level: int,
              count: int = 5, user_id: Optional[int] = None,
              exclude_positions: Optional[Set[int]] = None,
              exclude_texts: Optional[Set[str]] = None,
              day_seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Pick same-grade, same-topic tasks, preferring the requested level."""
    load()
    if count <= 0:
        return []
    grade = _student_grade(user_id, grade)
    topic = (topic or "").strip()
    if not topic:
        return []
    if topic.startswith(f"G{grade}_T"):
        try:
            from services.theme_registry import theme_title
            topic = theme_title(topic)
        except ImportError:
            pass
    levels = [level] + [lv for lv in (level - 1, level + 1, level - 2, level + 2)
                        if 1 <= lv <= 4 and lv != level]
    tasks = []
    for lv in levels:
        tasks.extend(_index.get((grade, topic, lv), ()))
    seen_positions: Set[Tuple[int, int]] = set()
    seen_texts: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for task in tasks:
        text = (task.get("task_text") or task.get("statement") or "").strip()
        if not text or text in seen_texts:
            continue
        try:
            position = int(task.get("position"))
            task_level = int(task.get("level", level))
        except (ValueError, TypeError):
            position = None
            task_level = level
        if exclude_positions and position in exclude_positions:
            continue
        position_key = (task_level, position) if position is not None else None
        if position_key is not None and position_key in seen_positions:
            continue
        if position_key is not None:
            seen_positions.add(position_key)
        seen_texts.add(text)
        unique.append(task)
    excluded = exclude_texts or set()
    fresh = [t for t in unique if (t.get("task_text") or t.get("statement") or "").strip() not in excluded]
    repeats = [t for t in unique if (t.get("task_text") or t.get("statement") or "").strip() in excluded]
    if user_id is not None:
        day_part = int(day_seed) if day_seed else 0
        def sort_key(t: Dict[str, Any]) -> str:
            value = f"{user_id}:{day_part}:{t.get('level', level)}:{t.get('position')}"
            return hashlib.md5(value.encode("utf-8")).hexdigest()
        fresh.sort(key=sort_key)
        repeats.sort(key=sort_key)
    result = (fresh + repeats)[:count]
    if not result:
        logger.warning("formyla_bank: no tasks for grade=%s topic=%r level=%s", grade, topic, level)
    return result


def available_topics(grade: int) -> List[str]:
    load()
    return sorted({topic for (g, topic, _), rows in _index.items() if g == grade and rows})


def task_count(grade: int, topic: str, level: int) -> int:
    load()
    return len(_index.get((grade, (topic or "").strip(), level), ()))
