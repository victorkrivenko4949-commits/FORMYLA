# -*- coding: utf-8 -*-
"""
daily_tasks/pipeline/slot_planner.py - deterministic 10-slot planner.

THEMATIC DAY MODE (DETERMINISTIC CALENDAR, 2026-06-22):
    Each day ALL 10 tasks belong to ONE topic. The topic of the day is
    chosen by a DETERMINISTIC CALENDAR (no randomness): the full topic
    catalog of the user is sorted stably, and the day index
    (today - ANCHOR_DATE) % len(topics) selects exactly one topic. Thus
    every topic appears exactly once per cycle (cycle length == number of
    topics), and when the cycle restarts the topics repeat in the same
    order. The same calendar date always maps to the same topic.
    Difficulty per slot is still picked inside that topic's level window and
    spread out via _enforce_spread, so the 10 tasks share one topic but vary
    in difficulty.

The LLM (Step 1) only fills in topic content (archetype, must_use_concepts,
reason_for_student, ...) for spec objects whose topic + difficulty_level
are already locked in by us.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from itertools import zip_longest

logger = logging.getLogger(__name__)

TOTAL_SLOTS = 10
MIN_LEVEL = 1
MAX_LEVEL = 8

# Grade-aware minimum difficulty floor (2026-06-26).
# For older grades the calibration/low end of (1,8) produced tasks that were
# far too easy (e.g. L1-L2 for a 9th grader prepping municipal/regional). We
# raise the floor of the level window per grade so the same topic window still
# varies in difficulty but never drops below a grade-appropriate baseline.
_GRADE_LEVEL_FLOOR = {
    5: 1,
    6: 1,
    7: 2,
    8: 3,
    9: 4,
    10: 4,
    11: 5,
}


def _grade_floor(profile: Dict[str, Any]) -> int:
    """Minimum difficulty_level allowed for this user's grade."""
    try:
        grade = int(profile.get("class_level") or 0)
    except (TypeError, ValueError):
        grade = 0
    return _GRADE_LEVEL_FLOOR.get(grade, MIN_LEVEL)

# Anchor date for the deterministic topic calendar. Day index is computed as
# (today - ANCHOR_DATE).days, so this fixes the phase of the cycle. Do not
# change after launch unless you intend to shift everyone's calendar.
ANCHOR_DATE = date(2026, 1, 1)


@dataclass
class PlannedSlot:
    """One pre-planned slot for the daily set."""
    position: int
    slot_kind: str
    subject: str
    topic: str
    topic_key: str
    difficulty_level: int
    target_level: int
    level_window: Tuple[int, int]
    is_calibration: bool
    measured: bool
    pct: Optional[float]
    test_correct: Optional[int]
    test_total: Optional[int]
    final_level: Optional[int]
    subtopic_hints: List[str] = field(default_factory=list)
    reason_hint: str = ""
    theme_subtopic: str = ""

    def to_spec_seed(self) -> Dict[str, Any]:
        """Convert to a dict that Step 1 (LLM) can extend."""
        return {
            "position": self.position,
            "slot_kind": self.slot_kind,
            "subject": self.subject,
            "theme": (self.topic + " — " + self.theme_subtopic) if self.theme_subtopic else self.topic,
            "topic": self.topic,
            "topic_key": self.topic_key,
            "theme_subtopic": self.theme_subtopic,
            "difficulty_level": self.difficulty_level,
            "target_level": self.target_level,
            "level_window": list(self.level_window),
            "is_calibration": self.is_calibration,
            "measured": self.measured,
            "pct": self.pct,
            "test_correct": self.test_correct,
            "test_total": self.test_total,
            "final_level": self.final_level,
            "subtopic_hints": list(self.subtopic_hints),
            "reason_hint": self.reason_hint,
        }


def _clamp(x: int, lo: int = MIN_LEVEL, hi: int = MAX_LEVEL) -> int:
    return max(lo, min(hi, int(x)))


def _topic_window(topic: Dict[str, Any]) -> Tuple[int, int]:
    """Pull (low, high) window from a topic dict."""
    measured = bool(topic.get("measured", False)) and not topic.get("calibration")
    _t = topic.get("target_level")
    if measured and _t is not None:
        return (_clamp(_t), _clamp(_t))
    win = topic.get("level_window")
    if isinstance(win, (list, tuple)) and len(win) == 2:
        return (_clamp(win[0]), _clamp(win[1]))
    lo = topic.get("level_low")
    hi = topic.get("level_high")
    if lo is not None and hi is not None:
        return (_clamp(lo), _clamp(hi))
    t = topic.get("target_level")
    if t is not None:
        return (_clamp(t), _clamp(t))
    return (MIN_LEVEL, MAX_LEVEL)


def _slot_kind_for(topic: Dict[str, Any], slot_difficulty: int) -> str:
    """Classify a slot kind given the topic state + chosen difficulty."""
    if topic.get("calibration") or not topic.get("measured", True):
        return "calibration"
    lo, hi = _topic_window(topic)
    is_strong = (topic.get("target_level") or 0) >= 6 or (topic.get("pct") or 0) >= 75
    if slot_difficulty >= hi:
        return "strong_challenge" if is_strong else "weak_challenge"
    if slot_difficulty <= lo:
        return "weak_base" if not is_strong else "strong_review"
    return "strong_review" if is_strong else "weak_main"


def _pick_difficulty_for_topic(
    topic: Dict[str, Any],
    slot_index_in_topic: int,
    total_slots_for_topic: int,
) -> int:
    """Pick a concrete difficulty inside topic's level_window."""
    lo, hi = _topic_window(topic)
    if lo == hi:
        return lo
    target = _clamp(topic.get("target_level") or lo, lo, hi)
    width = hi - lo + 1
    n = max(1, total_slots_for_topic)
    measured = bool(topic.get("measured", False))
    is_calibration = bool(topic.get("calibration")) or not measured
    if is_calibration:
        if n == 1:
            return _clamp(lo + (hi - lo) // 2, lo, hi)
        if n >= 2:
            step = (hi - lo) / float(n - 1)
            level = int(round(lo + slot_index_in_topic * step))
            return _clamp(level, lo, hi)
        return target
    pct = float(topic.get("pct") or 0)
    is_strong = target >= 6 or pct >= 75
    is_weak = target <= 3
    if is_strong:
        if slot_index_in_topic == 0:
            return hi
        return max(lo, hi - 1) if slot_index_in_topic % 2 == 1 else hi
    if is_weak:
        step = slot_index_in_topic % width
        return _clamp(lo + step, lo, hi)
    if n == 1:
        return target
    if n >= 2:
        s = (hi - lo) / float(n - 1)
        return _clamp(int(round(lo + slot_index_in_topic * s)), lo, hi)
    return _clamp(lo + (slot_index_in_topic % width), lo, hi)


def _topic_sort_key(topic: Dict[str, Any]) -> str:
    """Stable, deterministic sort key for a topic dict.

    Order priority: topic_key -> db_topic -> topic. Falling back through
    these keeps the cycle order stable even if some fields are missing,
    so the same catalog always yields the same calendar order.
    """
    return str(
        topic.get("topic_key")
        or topic.get("db_topic")
        or topic.get("topic")
        or ""
    )


def _day_index(today: date, cycle_len: int) -> int:
    """Deterministic day index into the topic cycle.

    Uses a fixed ANCHOR_DATE so a given calendar date always maps to the
    same position in the cycle. cycle_len == number of topics, therefore
    each topic is visited exactly once per cycle and the cycle repeats in
    the same order on the next pass.
    """
    if cycle_len <= 0:
        return 0
    return (today - ANCHOR_DATE).days % cycle_len


def _pick_day_topic(
    all_topics: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> Tuple[Dict[str, Any], int, int]:
    """Pick the topic of the day via the DETERMINISTIC CALENDAR.

    Returns (day_topic, day_index, cycle_len). No randomness: topics are
    sorted stably and indexed by the calendar day, so every topic shows up
    exactly once per full cycle before any repeats.
    """
    today = today or date.today()
    topics_sorted = sorted(all_topics, key=_topic_sort_key)
    cycle_len = len(topics_sorted)
    idx = _day_index(today, cycle_len)
    return topics_sorted[idx], idx, cycle_len


def plan_slots(
profile: Dict[str, Any],
total_slots: int = TOTAL_SLOTS,
today: Optional[date] = None,
) -> List[PlannedSlot]:
"""Build the deterministic list of 10 PlannedSlot objects.

THEMATIC DAY (DETERMINISTIC CALENDAR): all slots belong to ONE topic
from the user's full topic catalog (profile['topics_full']). The topic
is chosen by a fixed calendar (see _pick_day_topic), NOT randomly, so
every topic is used exactly once per cycle and cycles repeat in the
same order. ``today`` may be passed for testing / backfill; defaults to
date.today().
"""
all_topics = list(profile.get("topics_full") or [])
if not all_topics:
logger.warning("plan_slots: empty topics_full, cannot build thematic day")
return []
day_topic, day_index, cycle_len = _pick_day_topic(all_topics, today)
# Apply grade-aware difficulty floor so the same topic window never drops
# below a grade-appropriate baseline (e.g. no L1-L2 tasks for a 9th grader).
_floor = _grade_floor(profile)
if _floor > MIN_LEVEL:
_lo, _hi = _topic_window(day_topic)
_new_lo = _clamp(max(_lo, _floor))
_new_hi = _clamp(max(_hi, _new_lo))
day_topic = dict(day_topic)
day_topic["level_window"] = [_new_lo, _new_hi]
if day_topic.get("target_level") is not None:
day_topic["target_level"] = _clamp(max(int(day_topic["target_level"]), _new_lo))
logger.info(
"plan_slots: grade floor applied grade_floor=%d window->[%d,%d]",
_floor, _new_lo, _new_hi,
)
logger.info(
"plan_slots THEMATIC DAY (calendar): topic=%s subject=%s measured=%s "
"day_index=%d/%d cycle_len=%d",
day_topic.get("topic"), day_topic.get("subject"),
day_topic.get("measured"), day_index, cycle_len, cycle_len,
)
slots: List[PlannedSlot] = []
for k in range(total_slots):
difficulty = _pick_difficulty_for_topic(day_topic, k, total_slots)
lo, hi = _topic_window(day_topic)
slot_kind = _slot_kind_for(day_topic, difficulty)
reason_bits: List[str] = []
corr, tot = day_topic.get("test_correct"), day_topic.get("test_total")
if day_topic.get("calibration"):
reason_bits.append("Тест по этой теме не пройден - калибровочная задача")
elif corr is not None and tot:
reason_bits.append(f"Результат теста по теме: {corr}/{tot}")
reason_bits.append(f"уровень {difficulty} из окна [{lo}, {hi}]")
slots.append(PlannedSlot(
position=k + 1,
slot_kind=slot_kind,
subject=day_topic.get("subject", "unknown"),
topic=day_topic.get("topic", ""),
topic_key=day_topic.get("topic_key", day_topic.get("topic", "")),
difficulty_level=difficulty,
target_level=int(day_topic.get("target_level") or difficulty),
level_window=(lo, hi),
is_calibration=bool(day_topic.get("calibration") or not day_topic.get("measured", True)),
measured=bool(day_topic.get("measured", False)),
pct=day_topic.get("pct"),
test_correct=day_topic.get("test_correct"),
test_total=day_topic.get("test_total"),
final_level=day_topic.get("final_level"),
subtopic_hints=list(day_topic.get("subtopic_hints") or []),
reason_hint="; ".join(reason_bits),
))
slots = slots[:total_slots]
_enforce_spread(slots, max_same_level=2)
_assign_diverse_themes(slots)
_log_plan(slots)
return slots


def _enforce_spread(slots: List[PlannedSlot], max_same_level: int = 2) -> None:
    """In-place: spread difficulty_level so one level repeats <= max_same_level."""
    if len(slots) <= max_same_level:
        return
    from collections import Counter
    while True:
        counts = Counter(s.difficulty_level for s in slots)
        over = [lvl for lvl, c in counts.items() if c > max_same_level]
        if not over:
            return
        moved_anything = False
        for lvl in over:
            movable = [
                s for s in slots
                if s.difficulty_level == lvl and (s.is_calibration or not s.measured)
            ]
            if not movable:
                continue
            movable.sort(key=lambda s: s.position)
            to_move = max(0, counts[lvl] - max_same_level)
            extras = movable[-to_move:] if to_move else []
            for slot in extras:
                lo, hi = slot.level_window
                candidates: List[int] = []
                for d in range(1, max(hi - lvl, lvl - lo) + 1):
                    if lvl + d <= hi:
                        candidates.append(lvl + d)
                    if lvl - d >= lo:
                        candidates.append(lvl - d)
                placed = False
                for new_lvl in candidates:
                    if counts.get(new_lvl, 0) < max_same_level:
                        slot.difficulty_level = new_lvl
                        counts[lvl] -= 1
                        counts[new_lvl] = counts.get(new_lvl, 0) + 1
                        placed = True
                        moved_anything = True
                        break
        if not moved_anything:
            return


def topic_to_window_summary(slots: List[PlannedSlot]) -> Dict[str, Dict[str, Any]]:
    """Return {topic: {window: [lo,hi], levels: [...]}} summary."""
    out: Dict[str, Dict[str, Any]] = {}
    for s in slots:
        rec = out.setdefault(s.topic, {
            "window": list(s.level_window),
            "target_level": s.target_level,
            "is_calibration": s.is_calibration,
            "test_correct": s.test_correct,
            "test_total": s.test_total,
            "levels": [],
        })
        rec["levels"].append(s.difficulty_level)
    return out


def _log_plan(slots: List[PlannedSlot]) -> None:
    """Emit per-slot info lines + a summary line for diagnostics."""
    if not slots:
        logger.warning("slot_planner: empty plan")
        return
    from collections import Counter
    for s in slots:
        logger.info(
            "SLOT_PLAN pos=%d topic=%s measured=%s window=[%d..%d] "
            "target=L%d -> level=%d (slot_kind=%s)",
            s.position, s.topic, s.measured,
            s.level_window[0], s.level_window[1],
            s.target_level, s.difficulty_level, s.slot_kind,
        )
    levels = [s.difficulty_level for s in slots]
    counts = Counter(levels)
    dups = [f"L{lvl}x{c}" for lvl, c in sorted(counts.items()) if c > 2]
    logger.info(
        "slot_planner summary: levels=%s distribution=%s%s",
        levels, dict(sorted(counts.items())),
        (" duplicates>2: " + ", ".join(dups)) if dups else "",
    )


def check_slots_match_windows(
    specs: List[Dict[str, Any]],
    planned_slots: List[PlannedSlot],
) -> List[Dict[str, Any]]:
    """Validate that LLM-produced specs keep difficulty inside topic window."""
    by_pos = {s.position: s for s in planned_slots}
    mismatches: List[Dict[str, Any]] = []
    for spec in specs or []:
        pos = spec.get("position")
        planned = by_pos.get(pos)
        if not planned:
            continue
        got = spec.get("difficulty_level")
        lo, hi = planned.level_window
        if not isinstance(got, int) or got < lo or got > hi:
            mismatches.append({
                "position": pos,
                "topic": planned.topic,
                "expected_window": [lo, hi],
                "got_difficulty": got,
                "planned_difficulty": planned.difficulty_level,
            })
    return mismatches


def _assign_diverse_themes(slots: List[PlannedSlot]) -> None:
    by_topic: Dict[str, List[PlannedSlot]] = {}
    for s in slots:
        by_topic.setdefault(s.topic, []).append(s)
    for topic, group in by_topic.items():
        if len(group) <= 1:
            continue
        hints: List[str] = []
        for s in group:
            for h in s.subtopic_hints:
                if h and h not in hints:
                    hints.append(h)
        if not hints:
            continue
        for i, s in enumerate(group):
            s.theme_subtopic = hints[i % len(hints)]
