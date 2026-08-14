# -*- coding: utf-8 -*-
"""
daily_tasks/pipeline/slot_planner.py - daily slot planner driven by onboarding + level_engine.

NEW LOGIC (2026-07-28):
    - COUNT  = daily_tasks from onboarding (default 5). Hardcoded 10 removed.
    - LEVEL  = level_engine.allowed_difficulty by current mu,
               capped by route_ceiling = min(5, target_level + 1).
    - SECTIONS = priority to sections with lowest mu in level_by_section;
                 section without data is priority (needs measurement).
                 No more than 2 consecutive slots from same section.
    - THEMATIC DAY = FALLBACK only: when level_by_section is empty
                     AND onboarding is not done (no анкета).
    - Task generation inside slots is NOT touched — AI pipeline stays as-is.

The LLM (Step 1) only fills in topic content (archetype, must_use_concepts,
reason_for_student, ...) for spec objects whose topic + difficulty_level
are already locked in by us.
"""
from __future__ import annotations

import logging
from collections import Counter as _CounterCol
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from itertools import zip_longest

from daily_tasks.pipeline.diversity_catalog import DIVERSITY_CATALOG

logger = logging.getLogger(__name__)

TOTAL_SLOTS = 10  # kept for backwards compat; new logic ignores this
MIN_LEVEL = 1
MAX_LEVEL = 5

# Fallback-список универсальных методов, если в каталоге нет данных
SOLUTION_METHODS: List[str] = [
    "разбор случаев",
    "от противного",
    "оценка и границы",
    "подбор и проверка",
    "обратный ход",
    "систематический перебор",
    "построение схемы или таблицы",
    "индукция и рекурсия",
    "сравнение и аналогия",
    "графическая интерпретация",
]

# Grade-aware minimum difficulty floor (2026-06-26).
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


def _profile_grade(profile: Dict[str, Any]) -> Optional[int]:
    """Best-effort integer grade from profile, or None."""
    try:
        g = int(profile.get("class_level") or 0)
    except (TypeError, ValueError):
        return None
    return g or None


# Anchor date for the deterministic topic calendar.
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
    is_strong = (topic.get("target_level") or 0) >= 4 or (topic.get("pct") or 0) >= 75
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
    is_strong = target >= 4 or pct >= 75
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
    """Stable, deterministic sort key for a topic dict."""
    return str(
        topic.get("topic_key")
        or topic.get("db_topic")
        or topic.get("topic")
        or ""
    )


def _day_index(today: date, cycle_len: int) -> int:
    """Deterministic day index into the topic cycle."""
    if cycle_len <= 0:
        return 0
    return (today - ANCHOR_DATE).days % cycle_len


def _pick_day_topic(
    all_topics: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> Tuple[Dict[str, Any], int, int]:
    """Pick the topic of the day via the DETERMINISTIC CALENDAR."""
    today = today or date.today()
    topics_sorted = sorted(all_topics, key=_topic_sort_key)
    cycle_len = len(topics_sorted)
    idx = _day_index(today, cycle_len)
    return topics_sorted[idx], idx, cycle_len


def _normalize_key(s: str) -> str:
    """Normalize a topic string for fuzzy matching against the catalog."""
    return "".join(ch.lower() for ch in str(s or "") if ch.isalnum())


def _catalog_node(grade: Optional[int], topic_key: str, topic: str) -> Dict[str, Any]:
    """Look up a DIVERSITY_CATALOG node for this grade + topic.

    Tries exact match on topic_key/topic first, then a normalized match
    (case/punctuation/space-insensitive). Returns {} if nothing fits.
    """
    if grade is None:
        return {}
    grade_node = DIVERSITY_CATALOG.get(grade) or DIVERSITY_CATALOG.get(str(grade)) or {}
    if not grade_node:
        return {}
    for cand in (topic_key, topic):
        if cand and cand in grade_node:
            return grade_node[cand]
    wanted = {_normalize_key(topic_key), _normalize_key(topic)}
    wanted.discard("")
    for cat_topic, node in grade_node.items():
        if _normalize_key(cat_topic) in wanted:
            return node
    return {}


def _catalog_subtopics(grade: Optional[int], topic_key: str, topic: str) -> List[str]:
    """Return the list of subtopics for a topic from the catalog (may be empty)."""
    node = _catalog_node(grade, topic_key, topic)
    subs = node.get("subtopics") if isinstance(node, dict) else None
    return list(subs) if subs else []


def plan_slots(
    profile: Dict[str, Any],
    total_slots: int = TOTAL_SLOTS,
    today: Optional[date] = None,
) -> List[PlannedSlot]:
    """Build a list of PlannedSlot objects driven by onboarding + level_engine.

    NEW LOGIC (2026-07-28):
      1. COUNT  — daily_tasks from onboarding (default 5).  total_slots
         param is ONLY used if onboarding is absent.
      2. LEVEL  — level_engine.allowed_difficulty by current mu,
         capped above by route_ceiling = min(5, target_level + 1).
      3. SECTIONS — priority to sections with lowest mu in level_by_section;
         section without data counts as priority (mu=1.0, needs measurement).
         No more than 2 consecutive slots from the same section.
      4. THEMATIC DAY — FALLBACK only: when level_by_section is empty
         AND onboarding is not done (анкета не пройдена).

    Task generation inside each slot (AI pipeline) is NOT touched.
    """
    user_id = profile.get("user_id")
    if not user_id:
        # No user_id -> try thematic fallback with whatever we have
        logger.warning("plan_slots: no user_id in profile — using thematic fallback")
        return _plan_thematic_fallback(profile, max(total_slots, 5), today)

    # ── 1. Check if we should use the new engine-based logic ──────────
    from services.level_engine import get_state, allowed_difficulty
    from services.daily_task_rotation import (
        _get_onboarding, get_daily_task_count, _section_priorities,
    )

    onboard = _get_onboarding(user_id)
    state = get_state(user_id)
    by_section = state.get("by_section", {})

    # Determine if onboarding is done
    onboarding_done = bool(onboard) if onboard else False

    # ── FALLBACK: thematic day when level_by_section is empty AND
    #    onboarding not done (no анкета). ───────────────────────────────
    if not by_section and not onboarding_done:
        logger.info(
            "plan_slots: level_by_section empty + no onboarding -> "
            "thematic day fallback for user=%d", user_id,
        )
        return _plan_thematic_fallback(profile, max(total_slots, 5), today)

    # ── 2. Count: ВСЕГДА 10 задач (TOTAL_SLOTS) ──────────────────────
    count = max(total_slots, TOTAL_SLOTS)

    # ── 3. Level: allowed_difficulty by current mu, capped by route_ceiling ─
    mu = state.get("mu", 3.0)
    rounded_level = max(1, min(5, int(round(mu))))

    # route_ceiling = min(5, target_level + 1)
    target_level = 5
    if onboard:
        tl = onboard.get("target_level")
        if isinstance(tl, (int, float)):
            target_level = int(tl)
    route_ceiling = min(5, target_level + 1)
    logger.info(
        "plan_slots: user=%d target_level=%d route_ceiling=%d",
        user_id, target_level, route_ceiling,
    )

    allowed_levels = allowed_difficulty(rounded_level, "formyla_L1_L5_TOP5")
    allowed_levels = [l for l in allowed_levels if l <= route_ceiling]
    if not allowed_levels:
        allowed_levels = [route_ceiling]

    # ── 4. Section priorities (lowest mu first) ───────────────────────
    sections_ordered = _section_priorities(by_section)

    # ── 5. Build slots ───────────────────────────────────────────────
    grade = _profile_grade(profile)

    slots: List[PlannedSlot] = []
    section_counts: Dict[str, int] = {s: 0 for s, _ in sections_ordered}
    last_section = ""

    for pos in range(count):
        # Pick next section: priority to lowest counts, max 2 consecutive
        chosen_sec = ""
        for sec, _ in sections_ordered:
            if sec == last_section and section_counts.get(sec, 0) >= 2:
                continue
            chosen_sec = sec
            break
        if not chosen_sec:
            # All blocked -> pick any
            for sec, _ in sections_ordered:
                chosen_sec = sec
                break
        if not chosen_sec:
            break

        # Pick difficulty: spread evenly across allowed_levels
        diff_idx = pos % len(allowed_levels)
        difficulty = allowed_levels[diff_idx]

        section_counts[chosen_sec] = section_counts.get(chosen_sec, 0) + 1
        last_section = chosen_sec

        # Determine if this section has measurements
        sec_data = by_section.get(chosen_sec, {}) if isinstance(by_section, dict) else {}
        measured = isinstance(sec_data, dict) and sec_data.get("n", 0) > 0
        sec_mu = float(sec_data.get("mu", 1.0)) if isinstance(sec_data, dict) else 1.0

        slot_kind = "weak_main" if sec_mu < 3.0 else "strong_review"

        reason_bits: List[str] = []
        reason_bits.append(f"Раздел: {chosen_sec} (mu={sec_mu:.1f})")
        reason_bits.append(f"уровень {difficulty} из [{min(allowed_levels)}, {max(allowed_levels)}]")

        slots.append(PlannedSlot(
            position=pos + 1,
            slot_kind=slot_kind,
            subject="math",
            topic=chosen_sec,
            topic_key=chosen_sec,
            difficulty_level=difficulty,
            target_level=difficulty,
            level_window=(min(allowed_levels), max(allowed_levels)),
            is_calibration=not measured,
            measured=measured,
            pct=None,
            test_correct=None,
            test_total=None,
            final_level=None,
            subtopic_hints=[],
            reason_hint="; ".join(reason_bits),
        ))

    # Enforce spread and log
    _enforce_spread(slots, max_same_level=2)
    _log_plan(slots)
    return slots


def _plan_thematic_fallback(
    profile: Dict[str, Any],
    total_slots: int,
    today: Optional[date] = None,
) -> List[PlannedSlot]:
    """Original thematic-day logic preserved as fallback.

    Used when level_by_section is empty AND onboarding is not done.
    All slots belong to ONE topic chosen by deterministic calendar.
    """
    all_topics = list(profile.get("topics_full") or [])
    if not all_topics:
        logger.warning("plan_slots: empty topics_full, cannot build thematic day")
        return []

    day_topic, day_index, cycle_len = _pick_day_topic(all_topics, today)
    grade = _profile_grade(profile)

    # Apply grade-aware difficulty floor.
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

    _existing_hints = list(day_topic.get("subtopic_hints") or [])
    _catalog_subs = _catalog_subtopics(
        grade,
        day_topic.get("topic_key", day_topic.get("topic", "")),
        day_topic.get("topic", ""),
    )
    _day_hints = _existing_hints or _catalog_subs

    logger.info(
        "plan_slots THEMATIC DAY FALLBACK: topic=%s subject=%s measured=%s "
        "day_index=%d/%d cycle_len=%d",
        day_topic.get("topic"), day_topic.get("subject"), day_topic.get("measured"),
        day_index, cycle_len, cycle_len,
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
            subtopic_hints=list(_day_hints),
            reason_hint="; ".join(reason_bits),
        ))

    slots = slots[:total_slots]
    _enforce_spread(slots, max_same_level=2)
    _assign_diverse_themes(slots, day_index=day_index)
    _log_plan(slots)
    return slots


def assign_diversity(
    slots: List[PlannedSlot],
    subtopics: List[str],
    day_index: int = 0,
    grade: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Assign unique subtopic + method to each slot for diversity."""
    if not slots:
        return []
    day_topic = slots[0].topic_key
    day_topic_name = slots[0].topic
    node: Dict[str, Any] = _catalog_node(grade, day_topic, day_topic_name)
    subs: List[str] = node.get("subtopics") or (subtopics or [])
    methods: List[str] = node.get("methods") or SOLUTION_METHODS
    level_notes: Dict = node.get("level_notes", {})
    if not subs:
        subs = [f"подтема {i}" for i in range(1, 11)]
    if not methods:
        methods = SOLUTION_METHODS
    rot = day_index % len(subs) if subs else 0
    rotated_subs = subs[rot:] + subs[:rot]
    used: List[Dict[str, Any]] = []
    for i, slot in enumerate(slots):
        sub = rotated_subs[i % len(rotated_subs)] if rotated_subs else ""
        method = methods[(i + day_index) % len(methods)] if methods else ""
        lvl = slot.difficulty_level
        note = level_notes.get(lvl) or level_notes.get(str(lvl), "")
        slot.subtopic_hints = [sub]
        slot.theme_subtopic = sub
        slot.reason_hint = (
            f"класс {grade}; уровень {lvl} ({note}); подтема: {sub}; метод: {method}"
        )
        used.append({
            "position": slot.position,
            "topic": slot.topic,
            "subtopic": sub,
            "method": method,
            "level": lvl,
            "note": note,
        })
    return used


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
                for new_lvl in candidates:
                    if counts.get(new_lvl, 0) < max_same_level:
                        slot.difficulty_level = new_lvl
                        counts[lvl] -= 1
                        counts[new_lvl] = counts.get(new_lvl, 0) + 1
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
            "SLOT_PLAN pos=%d topic=%s subtopic=%s measured=%s window=[%d..%d] "
            "target=L%d -> level=%d (slot_kind=%s)",
            s.position, s.topic, s.theme_subtopic, s.measured,
            s.level_window[0], s.level_window[1],
            s.target_level, s.difficulty_level, s.slot_kind,
        )
    levels = [s.difficulty_level for s in slots]
    counts = Counter(levels)
    dups = [f"L{lvl}x{c}" for lvl, c in sorted(counts.items()) if c > 2]
    subs = [s.theme_subtopic for s in slots]
    logger.info(
        "slot_planner summary: levels=%s distribution=%s%s subtopics=%s",
        levels, dict(sorted(counts.items())),
        (" duplicates>2: " + ", ".join(dups)) if dups else "",
        subs,
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


def _assign_diverse_themes(slots: List[PlannedSlot], day_index: int = 0) -> None:
    """Assign a DISTINCT theme_subtopic to each slot from its subtopic_hints.

    The hints list is rotated by day_index so the same topic gets a
    different ordering of subtopics on different days. Each slot in a topic
    group gets a different subtopic (cycling only if there are fewer hints
    than slots), guaranteeing the 10 daily tasks cover varied facets
    (e.g. quadratics: Vieta, parameters, root placement, ...).
    """
    by_topic: Dict[str, List[PlannedSlot]] = {}
    for s in slots:
        by_topic.setdefault(s.topic, []).append(s)
    for topic, group in by_topic.items():
        hints: List[str] = []
        for s in group:
            for h in s.subtopic_hints:
                if h and h not in hints:
                    hints.append(h)
        if not hints:
            continue
        rot = day_index % len(hints)
        rotated = hints[rot:] + hints[:rot]
        for i, s in enumerate(group):
            sub = rotated[i % len(rotated)]
            s.theme_subtopic = sub
            s.subtopic_hints = [sub]


# === NEW (curator monthly plan): per-SUBTOPIC daily generation ===
def plan_slots_for_subtopic(profile, day_topic, subtopic_slug, subtopic_name, day_index=0, total_slots=TOTAL_SLOTS):
    """Build total_slots PlannedSlot objects all locked to ONE subtopic of the day."""
    grade = _profile_grade(profile)
    topic = dict(day_topic or {})
    lo, hi = _topic_window(topic)
    _floor = _grade_floor(profile)
    if _floor > MIN_LEVEL:
        lo = _clamp(max(lo, _floor))
        hi = _clamp(max(hi, lo))
    topic["level_window"] = [lo, hi]
    if topic.get("target_level") is not None:
        topic["target_level"] = _clamp(max(int(topic["target_level"]), lo))
    title = subtopic_name or subtopic_slug or topic.get("topic", "")
    logger.info(
        "plan_slots_for_subtopic: subtopic=%s parent_topic=%s grade=%s window=[%d,%d]",
        subtopic_slug, topic.get("topic"), grade, lo, hi,
    )
    slots = []
    for k in range(total_slots):
        difficulty = _pick_difficulty_for_topic(topic, k, total_slots)
        slot_kind = _slot_kind_for(topic, difficulty)
        method = SOLUTION_METHODS[(k + day_index) % len(SOLUTION_METHODS)]
        reason_bits = []
        corr, tot = topic.get("test_correct"), topic.get("test_total")
        if topic.get("calibration"):
            reason_bits.append("Тест по теме не пройден - калибровочная задача")
        elif corr is not None and tot:
            reason_bits.append(f"Результат теста по теме: {corr}/{tot}")
        reason_bits.append(f"подтема: {title}; метод: {method}; уровень {difficulty} из [{lo}, {hi}]")
        slots.append(PlannedSlot(
            position=k + 1,
            slot_kind=slot_kind,
            subject=topic.get("subject", "math"),
            topic=topic.get("topic", ""),
            topic_key=topic.get("topic_key", topic.get("topic", "")),
            difficulty_level=difficulty,
            target_level=int(topic.get("target_level") or difficulty),
            level_window=(lo, hi),
            is_calibration=bool(topic.get("calibration") or not topic.get("measured", True)),
            measured=bool(topic.get("measured", False)),
            pct=topic.get("pct"),
            test_correct=topic.get("test_correct"),
            test_total=topic.get("test_total"),
            final_level=topic.get("final_level"),
            subtopic_hints=[title],
            reason_hint="; ".join(reason_bits),
            theme_subtopic=title,
        ))
    slots = slots[:total_slots]
    _enforce_spread(slots, max_same_level=2)
    _log_plan(slots)
    return slots
