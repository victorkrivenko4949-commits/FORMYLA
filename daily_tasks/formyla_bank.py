# -*- coding: utf-8 -*-
"""Bank of daily tasks from FORMYLA_BANK.jsonl, indexed by grade, topic and level.

Подбор: get_tasks(grade, topic, level) берёт задачи ТОЛЬКО запрошенного уровня,
пока их хватает. Если задач точного уровня не хватает (дырка в банке), добор идёт
смесью соседних уровней: LOWER_SHARE (70%) из level-1 и остальное (30%) из level+1.
Если одного из соседних уровней нет (level=1 или 4) или в нём тоже нехватка —
недостающее берётся из другого соседа, затем из level±2, и только потом —
уже выданные задачи (wrap-around). Перемешка md5(user_id:day_seed:level:position)
действует только ВНУТРИ уровня.
"""

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

# Доля добора из уровня ниже при нехватке точного уровня (остальное — из уровня выше).
LOWER_SHARE = 0.7


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


def _task_text(task: Dict[str, Any]) -> str:
    return (task.get("task_text") or task.get("statement") or "").strip()


def _collect(grade: int, topic: str, levels: List[int],
             exclude_positions: Optional[Set[int]]) -> Dict[int, List[Dict[str, Any]]]:
    """Уникальные (по тексту и (уровень, position)) задачи по уровням."""
    seen_positions: Set[Tuple[int, int]] = set()
    seen_texts: Set[str] = set()
    out: Dict[int, List[Dict[str, Any]]] = {lv: [] for lv in levels}
    for lv in levels:
        for task in _index.get((grade, topic, lv), ()):
            text = _task_text(task)
            if not text or text in seen_texts:
                continue
            try:
                position = int(task.get("position"))
            except (ValueError, TypeError):
                position = None
            if exclude_positions and position in exclude_positions:
                continue
            key = (lv, position) if position is not None else None
            if key is not None and key in seen_positions:
                continue
            if key is not None:
                seen_positions.add(key)
            seen_texts.add(text)
            out[lv].append(task)
    return out


def _shuffle(tasks: List[Dict[str, Any]], lv: int, user_id: Optional[int], day_part: int) -> List[Dict[str, Any]]:
    if user_id is None:
        return sorted(tasks, key=lambda t: int(t.get("position") or 0))
    return sorted(tasks, key=lambda t: hashlib.md5(
        f"{user_id}:{day_part}:{lv}:{t.get('position')}".encode("utf-8")).hexdigest())


def _take(pool: Dict[int, List[Dict[str, Any]]], lv: int, n: int) -> List[Dict[str, Any]]:
    if n <= 0 or lv not in pool:
        return []
    picked, pool[lv] = pool[lv][:n], pool[lv][n:]
    return picked


def get_tasks(grade: int, topic: str, level: int,
              count: int = 5, user_id: Optional[int] = None,
              exclude_positions: Optional[Set[int]] = None,
              exclude_texts: Optional[Set[str]] = None,
              day_seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Pick same-grade, same-topic tasks of the requested level.

    Порядок:
      1. свежие задачи точного уровня — сколько есть;
      2. если не хватает: добор смесью LOWER_SHARE из level-1 и остатка из level+1
         (свежие); недобор одной стороны компенсируется другой;
      3. свежие из level-2 / level+2;
      4. уже выданные (exclude_texts) — в том же порядке уровней.
    """
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
    day_part = int(day_seed) if day_seed else 0
    excluded = exclude_texts or set()

    by_level = _collect(grade, topic, levels, exclude_positions)
    fresh: Dict[int, List[Dict[str, Any]]] = {}
    repeats: Dict[int, List[Dict[str, Any]]] = {}
    for lv in levels:
        f = [t for t in by_level[lv] if _task_text(t) not in excluded]
        r = [t for t in by_level[lv] if _task_text(t) in excluded]
        fresh[lv] = _shuffle(f, lv, user_id, day_part)
        repeats[lv] = _shuffle(r, lv, user_id, day_part)

    picked: List[Tuple[int, Dict[str, Any]]] = []

    def add(lv: int, items: List[Dict[str, Any]]) -> None:
        picked.extend((lv, t) for t in items)

    # 1. точный уровень
    add(level, _take(fresh, level, count))

    # 2. смесь соседей 70/30
    need = count - len(picked)
    if need > 0:
        lower, upper = level - 1, level + 1
        # округление чередуется по дням, чтобы в среднем держать LOWER_SHARE (3.5 -> 4/3/4/3)
        rnd = 0.5 if day_part % 2 == 0 else 0.0
        want_lower = int(need * LOWER_SHARE + rnd) if upper in fresh else need
        want_upper = need - want_lower if upper in fresh else 0
        if lower not in fresh:
            want_lower, want_upper = 0, need
        got_lower = _take(fresh, lower, want_lower)
        got_upper = _take(fresh, upper, want_upper)
        # компенсация недобора одной стороны другой
        short = need - len(got_lower) - len(got_upper)
        if short > 0:
            got_lower += _take(fresh, lower, short)
            short = need - len(got_lower) - len(got_upper)
        if short > 0:
            got_upper += _take(fresh, upper, short)
        add(lower, got_lower)
        add(upper, got_upper)

    # 3. level±2 свежие
    for lv in (level - 2, level + 2):
        need = count - len(picked)
        if need <= 0:
            break
        add(lv, _take(fresh, lv, need))

    # 4. повторы в порядке уровней
    for lv in levels:
        need = count - len(picked)
        if need <= 0:
            break
        add(lv, _take(repeats, lv, need))

    result = [t for _, t in picked]
    if not result:
        logger.warning("formyla_bank: no tasks for grade=%s topic=%r level=%s", grade, topic, level)
    else:
        off = [lv for lv, _ in picked if lv != level]
        if off:
            logger.warning(
                "formyla_bank: level shortage grade=%s topic=%r level=%s: exact=%d, mix=%s",
                grade, topic, level, len(picked) - len(off),
                {lv: off.count(lv) for lv in sorted(set(off))},
            )
    return result


def available_topics(grade: int) -> List[str]:
    load()
    return sorted({topic for (g, topic, _), rows in _index.items() if g == grade and rows})


def task_count(grade: int, topic: str, level: int) -> int:
    load()
    return len(_index.get((grade, (topic or "").strip(), level), ()))
