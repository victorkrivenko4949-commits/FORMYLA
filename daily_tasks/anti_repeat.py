# -*- coding: utf-8 -*-
"""daily_tasks/anti_repeat.py - anti-repeat of daily tasks across topic cycles.

WHY: the topic calendar (slot_planner) repeats the SAME topic once per cycle.
On the 2nd+ pass the same topic (e.g. number theory) must NOT yield tasks that
are 1-to-1 with what the student already saw. This module:

  1. collects the student's recent task history grouped by topic
     (get_recent_tasks_history) - archetype + subtopic + a normalized hash of
     the statement text;
  2. exposes a stable statement hash (statement_hash) that ignores concrete
     numbers, so "same template, different numbers" still counts as a repeat;
  3. flags freshly generated tasks whose statement matches the history
     (check_repeats_against_history) so the orchestrator can re-roll them via
     the existing is_flagged / rescue-pass mechanism.

This file is self-contained: it only reads models and is imported by
profile.py (history), step1_gemini.py (prompt context) and the orchestrator
(dedup). It has no side effects on import.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# How many recent daily sets to look back over when building history.
DEFAULT_LOOKBACK_SETS = 60
# Cap how many history entries per topic we feed into the prompt.
MAX_HISTORY_PER_TOPIC = 30


def normalize_statement(text: str) -> str:
    """Normalize a task statement for a stable, number-insensitive hash.

    Lowercase, collapse whitespace and replace every run of digits with '#'.
    This way "Find gcd(12, 18)" and "Find gcd(20, 35)" map to the same key,
    so re-using the same template with new numbers is detected as a repeat.
    """
    t = (text or "").lower()
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def statement_hash(text: str) -> str:
    """Short stable hash of a normalized statement."""
    norm = normalize_statement(text)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _archetype_from_spec(spec_json: str) -> str:
    """Pull task_archetype out of the stored gemini_spec_json blob."""
    if not spec_json:
        return ""
    try:
        data = json.loads(spec_json) or {}
    except Exception:
        return ""
    return str(data.get("task_archetype") or "")


def get_recent_tasks_history(
    user_id: int,
    lookback_sets: int = DEFAULT_LOOKBACK_SETS,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return recent task history for a user, grouped by topic.

    Output: {topic: [{subtopic, archetype, difficulty, stmt_hash}, ...]}
    Ordered newest-first within each topic.
    """
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    history: Dict[str, List[Dict[str, Any]]] = {}
    try:
        rows = (
            DailyTaskItem.query
            .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
            .filter(DailyTaskSet.user_id == user_id)
            .order_by(DailyTaskSet.target_date.desc())
            .limit(lookback_sets * 10)
            .all()
        )
    except Exception as exc:
        logger.warning("get_recent_tasks_history failed for user %s: %s", user_id, exc)
        return history

    for it in rows:
        topic = it.topic or "?"
        history.setdefault(topic, []).append({
            "subtopic": it.subtopic or "",
            "archetype": _archetype_from_spec(it.gemini_spec_json),
            "difficulty": it.difficulty_level,
            "stmt_hash": statement_hash(it.task_text),
        })
    return history


def format_history_for_prompt(
    history: Dict[str, List[Dict[str, Any]]],
    topic: str,
) -> str:
    """Human-readable block for the planner prompt, for ONE topic (the day topic)."""
    prev = (history or {}).get(topic) or []
    if not prev:
        return "(po etoy teme ranee zadach ne bylo - pervyy prohod tsikla)"
    lines: List[str] = []
    for p in prev[:MAX_HISTORY_PER_TOPIC]:
        lines.append(
            f" - arhetip <<{p['archetype']}>>, subtopic <<{p['subtopic']}>>, L{p['difficulty']}"
        )
    return "\n".join(lines)


def check_repeats_against_history(
    tasks: List[Dict[str, Any]],
    history_for_topic: List[Dict[str, Any]],
) -> List[int]:
    """Return positions of tasks whose statement repeats the history."""
    seen = {h.get("stmt_hash") for h in (history_for_topic or [])}
    dups: List[int] = []
    for t in tasks or []:
        if statement_hash(t.get("task_text", "")) in seen:
            pos = t.get("position")
            if pos is not None:
                dups.append(pos)
    if dups:
        logger.info("anti_repeat: %d task(s) repeat history, flagging: %s", len(dups), dups)
    return dups
