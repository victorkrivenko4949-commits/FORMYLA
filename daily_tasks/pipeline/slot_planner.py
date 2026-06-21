# -*- coding: utf-8 -*-
"""
daily_tasks/pipeline/slot_planner.py - deterministic 10-slot planner.

PR per-topic difficulty matching (2026-06-10).

Before this fix the LLM (Step 1) decided the difficulty_level for each of
the 10 daily-task slots. That created two bugs:

1. The old percent_to_level mapped everything into L1..L5, so even 8/8 on
   geometry could not produce L8.
2. Even when the upper range was available, the LLM sometimes mixed
   difficulties across topics (gave L3 algebra when the student tested 8/8).

This module fixes both issues deterministically, BEFORE calling the LLM:

* split 10 slots between weak topics, strong topics and calibration topics
  proportionally to weakness priority;
* for each slot, pick a concrete difficulty_level INSIDE the per-topic
  window [level_low, level_high] of the chosen topic.

The LLM then only fills in topic content (archetype, must_use_concepts,
reason_for_student, ...) for spec objects whose topic + difficulty_level
are already locked in by us.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


TOTAL_SLOTS = 10
MIN_LEVEL = 1
MAX_LEVEL = 8


# ---------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------


@dataclass
class PlannedSlot:
    """One pre-planned slot for the daily set.

    Step 1 (LLM) receives a list of such slots and just enriches them
    with text fields (task_archetype, must_use_concepts, ...). The
    LLM MUST NOT change topic / subject / difficulty_level.
    """

    position: int
    slot_kind: str          # weak_base / weak_main / weak_challenge / strong_review / strong_challenge / calibration
    subject: str
    topic: str              # db_topic value
    topic_key: str
    difficulty_level: int   # 1..8, picked inside the topic window
    target_level: int       # per-topic target from adaptive test
    level_window: Tuple[int, int]  # (low, high) for this topic
    is_calibration: bool
    measured: bool
    pct: Optional[float]
    test_correct: Optional[int]
    test_total: Optional[int]
    final_level: Optional[int]
    subtopic_hints: List[str] = field(default_factory=list)
    reason_hint: str = ""
   theme_subtopic: str = ""  # diversified subtopic for unique themes

    def to_spec_seed(self) -> Dict[str, Any]:
        """Convert to a dict that Step 1 (LLM) can extend."""
        return {
            "position": self.position,
            "slot_kind": self.slot_kind,
            "subject": self.subject,
            "theme": (self.topic + " — " + self.theme_subtopic) if self.theme_subtopic else self.topic, "topic": self.topic,
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


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _clamp(x: int, lo: int = MIN_LEVEL, hi: int = MAX_LEVEL) -> int:
    return max(lo, min(hi, int(x)))


def _topic_window(topic: Dict[str, Any]) -> Tuple[int, int]:
    """Pull (low, high) window from a topic dict.

    Profile fills 'level_window' / 'level_low' / 'level_high'. Falls back
    to (target_level, target_level) or full range as a last resort.
    """
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
    """Classify a slot kind given the topic state + chosen difficulty.

    Calibration topics always get 'calibration'. For measured topics:
    * top of window  -> *_challenge
    * bottom of window -> *_base
    * middle       -> *_main / *_review
    Strong topics get strong_review / strong_challenge prefix.
    """
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
    """Pick a concrete difficulty inside topic's level_window.

    Distribution policy depends on whether the topic was MEASURED
    (we have real adaptive-test data) and on the student's level.

    * NOT measured / calibration: ученик ещё не проходил тест по теме.
      Стартуем от СЕРЕДИНЫ окна (чтобы не пугать максимумом) и при
      нескольких слотах — равномерно разносим уровни по окну.
      Окно [3..8], 2 слота → [5, 7] вместо прежних [8, 8].
    * MEASURED strong (target >= 6, pct >= 75): bias to the TOP, но
      два слота всегда РАЗНЫЕ (hi и hi-1), а не два одинаковых hi.
    * MEASURED weak (target <= 3): bias to the BOTTOM, последний слот
      на step up для роста.
    * MEASURED medium: ровное распределение по окну.

    Детерминированно: distribution зависит только от slot_index_in_topic
    и total_slots_for_topic, никакого random.
    """
    lo, hi = _topic_window(topic)
    if lo == hi:
        return lo

    target = _clamp(topic.get("target_level") or lo, lo, hi)
    width = hi - lo + 1
    n = max(1, total_slots_for_topic)

    # ── 1) НЕ ИЗМЕРЕННАЯ / калибровочная тема ─────────────────────────
    # Главный фикс ТЗ: пока уровень неизвестен — НЕ ставить верх окна
    # и при нескольких слотах разнести равномерно.
    measured = bool(topic.get("measured", False))
    is_calibration = bool(topic.get("calibration")) or not measured
    if is_calibration:
        if n == 1:
            # Один слот по неизвестной теме — даём середину окна, а не верх.
            # Это «калибровочная» задача: посмотреть, тянет ли ученик середину.
            return _clamp(lo + (hi - lo) // 2, lo, hi)
        # Несколько слотов: равномерно по окну от lo до hi (включительно).
        # Формула: позиция k из n даёт level = lo + round(k*(hi-lo)/(n-1)).
        if n >= 2:
            step = (hi - lo) / float(n - 1)
            level = int(round(lo + slot_index_in_topic * step))
            return _clamp(level, lo, hi)
        return target

    # ── 2) ИЗМЕРЕННАЯ сильная тема ────────────────────────────────────
    pct = float(topic.get("pct") or 0)
    is_strong = target >= 6 or pct >= 75
    is_weak = target <= 3

    if is_strong:
        # Top-biased, но без дубликата: 2 слота → [hi, hi-1].
        # 3 слота → [hi, hi-1, hi] (если hi-1==lo, держим hi).
        if slot_index_in_topic == 0:
            return hi
        return max(lo, hi - 1) if slot_index_in_topic % 2 == 1 else hi

    if is_weak:
        # Bottom-biased: lo, lo+1, lo+2, …
        step = slot_index_in_topic % width
        return _clamp(lo + step, lo, hi)

    # Medium: ровно по окну.
    if n == 1:
        return target
    if n >= 2:
        s = (hi - lo) / float(n - 1)
        return _clamp(int(round(lo + slot_index_in_topic * s)), lo, hi)
    return _clamp(lo + (slot_index_in_topic % width), lo, hi)


# ---------------------------------------------------------------------
# Slot allocation (how many of 10 slots each topic gets)
# ---------------------------------------------------------------------


def _allocate_topic_slots(
    weak_topics: List[Dict[str, Any]],
    strong_topics: List[Dict[str, Any]],
    calibration_topics: List[Dict[str, Any]],
    total_slots: int = TOTAL_SLOTS,
) -> List[Tuple[Dict[str, Any], int]]:
    """Allocate total_slots between topics.

    Strategy:
    * Reserve up to 3 slots for strong_topics (review of strengths).
    * Reserve up to 2 slots for calibration topics.
    * Remaining slots go to weak_topics, distributed by priority.

    Returns: list of (topic_dict, n_slots) ordered as we want positions
    to appear in the daily set.
    """
    if total_slots <= 0:
        return []

    weak = [t for t in (weak_topics or []) if not t.get("calibration")]
    strong = list(strong_topics or [])
    calibration = list(calibration_topics or [])

    # Sort weak by priority desc (low pct -> top), strong by pct desc.
    weak.sort(key=lambda t: -(t.get("priority") or 0))
    strong.sort(key=lambda t: -(t.get("pct") or 0))

    # Decide caps depending on what we have.
    # PR per-topic difficulty matching: каждая сильная тема получает
    # минимум 2 слота — иначе 8/8 даёт всего 1 задачу L8, что выглядит
    # как ошибка. Слабые темы тоже могут получать несколько слотов:
    # с 1 weak topic → до 4 слотов, чтобы не уперлись все 8 в одну тему.
    if strong:
        # минимум 2 слота на каждую сильную тему, но не больше 5 в сумме
        max_strong = min(len(strong) * 3, 5)
        max_strong = max(2, max_strong)
    else:
        max_strong = 0
    max_cal = min(2, len(calibration)) if calibration else 0

    # weak gets the rest — minimum 1 slot per weak topic if any
    weak_slots_total = max(0, total_slots - max_strong - max_cal)

    # If we have weak topics but no strong/cal, give them everything.
    if not strong and not calibration and weak:
        weak_slots_total = total_slots
        max_strong = 0
        max_cal = 0
    elif not weak:
        # No measured weak topics: split between strong and calibration.
        if strong and calibration:
            max_strong = max(1, min(len(strong), total_slots - max_cal))
            max_cal = total_slots - max_strong
        elif strong:
            max_strong = min(len(strong), total_slots)
        elif calibration:
            max_cal = min(len(calibration), total_slots)

    # If sum is less than total_slots (e.g. only 1 weak + 1 strong + 1 cal
    # but total=10), top up weak (it can repeat the same topic with
    # different difficulties).
    used = weak_slots_total + max_strong + max_cal
    if used < total_slots:
        if weak:
            weak_slots_total += (total_slots - used)
        elif strong:
            max_strong += (total_slots - used)
        elif calibration:
            max_cal += (total_slots - used)

    # Distribute weak_slots_total across weak topics (proportional to priority)
    allocated: List[Tuple[Dict[str, Any], int]] = []

    if weak and weak_slots_total > 0:
        total_priority = sum((t.get("priority") or 1) for t in weak) or 1
        weak_alloc: List[int] = []
        running = 0
        for i, t in enumerate(weak):
            share = (t.get("priority") or 1) / total_priority
            n = int(round(share * weak_slots_total))
            n = max(1, n)  # every weak topic gets at least 1 slot
            weak_alloc.append(n)
            running += n
        # Fix rounding: ensure sum == weak_slots_total
        delta = weak_slots_total - sum(weak_alloc)
        i = 0
        while delta != 0 and weak_alloc:
            idx = i % len(weak_alloc)
            if delta > 0:
                weak_alloc[idx] += 1
                delta -= 1
            else:
                if weak_alloc[idx] > 1:
                    weak_alloc[idx] -= 1
                    delta += 1
            i += 1
            if i > 1000:  # safety
                break
        # Cap: a single topic shouldn't dominate (max 4 of 10)
        for idx in range(len(weak_alloc)):
            if weak_alloc[idx] > 4:
                overflow = weak_alloc[idx] - 4
                weak_alloc[idx] = 4
                # redistribute overflow to topics with <4
                j = 0
                while overflow > 0 and any(x < 4 for x in weak_alloc):
                    k = (idx + 1 + j) % len(weak_alloc)
                    if weak_alloc[k] < 4:
                        weak_alloc[k] += 1
                        overflow -= 1
                    j += 1
                    if j > 1000:
                        break
        for t, n in zip(weak, weak_alloc):
            if n > 0:
                allocated.append((t, n))

    # strong topics: распределяем max_strong слотов между сильными темами.
    # Каждая получает минимум 1 слот, остаток — самым сильным (по pct).
    if strong and max_strong > 0:
        n_s = min(len(strong), max_strong)
        per = max_strong // n_s
        rem = max_strong % n_s
        for i in range(n_s):
            extra = 1 if i < rem else 0
            allocated.append((strong[i], per + extra))

    # calibration topics: split max_cal across calibration_topics evenly
    if calibration and max_cal > 0:
        n_topics = min(len(calibration), max_cal)
        per = max_cal // n_topics
        rem = max_cal % n_topics
        for i in range(n_topics):
            extra = 1 if i < rem else 0
            allocated.append((calibration[i], per + extra))

    # Safety: total must equal total_slots. If we under-allocated, push the
    # remainder to the strongest weak (or strong) bucket.
    cur_total = sum(n for _, n in allocated)
    if cur_total < total_slots and allocated:
        # find best donor — prefer weak (those with priority), else strong[0]
        donor_idx = 0
        for i, (t, _) in enumerate(allocated):
            if not t.get("calibration"):
                donor_idx = i
                break
        topic, n = allocated[donor_idx]
        allocated[donor_idx] = (topic, n + (total_slots - cur_total))

    return allocated


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------


def plan_slots(
    profile: Dict[str, Any],
    total_slots: int = TOTAL_SLOTS,
) -> List[PlannedSlot]:
    """Build the deterministic list of 10 PlannedSlot objects.

    Each slot already has topic + difficulty_level locked in. Step 1 only
    enriches the text fields.
    """
    weak_topics = list(profile.get("weak_topics") or [])
    strong_topics = list(profile.get("strong_topics") or [])
    calibration_topic_names = list(profile.get("calibration_topics") or [])

    # Lookup full topic dicts for calibration_topics (they are by name).
    topics_full = list(profile.get("topics_full") or [])
    cal_name_set = {str(n).strip().lower() for n in calibration_topic_names if n}
    calibration_topic_dicts: List[Dict[str, Any]] = []
    for t in topics_full:
        if (t.get("topic") or "").strip().lower() in cal_name_set:
            calibration_topic_dicts.append(t)
    # If something went missing, fall back to entries in weak_topics with
    # calibration=True (legacy path).
    if not calibration_topic_dicts:
        calibration_topic_dicts = [t for t in weak_topics if t.get("calibration")]

    # Remove calibration topics from weak_topics list (they have their own
    # allocation bucket).
    weak_topics = [t for t in weak_topics if not t.get("calibration")]

    allocation = _allocate_topic_slots(
        weak_topics=weak_topics,
        strong_topics=strong_topics,
        calibration_topics=calibration_topic_dicts,
        total_slots=total_slots,
    )

    # Build slots
    slots: List[PlannedSlot] = []
    position = 1
    for topic, n_slots in allocation:
        for k in range(n_slots):
            difficulty = _pick_difficulty_for_topic(topic, k, n_slots)
            lo, hi = _topic_window(topic)
            slot_kind = _slot_kind_for(topic, difficulty)
            reason_bits = []
            corr, tot = topic.get("test_correct"), topic.get("test_total")
            if topic.get("calibration"):
                reason_bits.append(
                    "Тест по этой теме не пройден - калибровочная задача"
                )
            elif corr is not None and tot:
                reason_bits.append(
                    f"Результат теста по теме: {corr}/{tot}"
                )
            reason_bits.append(f"уровень {difficulty} из окна [{lo}, {hi}]")
            slot = PlannedSlot(
                position=position,
                slot_kind=slot_kind,
                subject=topic.get("subject", "unknown"),
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
                subtopic_hints=list(topic.get("subtopic_hints") or []),
                reason_hint="; ".join(reason_bits),
            )
            slots.append(slot)
            position += 1
            if position > total_slots:
                break
        if position > total_slots:
            break

    # If we still have <10 slots (very sparse profile), pad with the top
    # weak/calibration topic at its target level. This keeps the contract:
    # exactly TOTAL_SLOTS slots.
    while len(slots) < total_slots:
        donor_pool = weak_topics or calibration_topic_dicts or strong_topics
        if not donor_pool:
            break
        donor = donor_pool[len(slots) % len(donor_pool)]
        lo, hi = _topic_window(donor)
        difficulty = _clamp(donor.get("target_level") or lo, lo, hi)
        slots.append(PlannedSlot(
            position=len(slots) + 1,
            slot_kind=_slot_kind_for(donor, difficulty),
            subject=donor.get("subject", "unknown"),
            topic=donor.get("topic", ""),
            topic_key=donor.get("topic_key", donor.get("topic", "")),
            difficulty_level=difficulty,
            target_level=int(donor.get("target_level") or difficulty),
            level_window=(lo, hi),
            is_calibration=bool(donor.get("calibration") or not donor.get("measured", True)),
            measured=bool(donor.get("measured", False)),
            pct=donor.get("pct"),
            test_correct=donor.get("test_correct"),
            test_total=donor.get("test_total"),
            final_level=donor.get("final_level"),
            subtopic_hints=list(donor.get("subtopic_hints") or []),
            reason_hint="filler slot at target level",
        ))

    # Truncate if somehow we over-shot.
    slots = slots[:total_slots]

    # ── Глобальное правило разброса: не более 2 задач с одним уровнем ───
    # Применяется ТОЛЬКО к не-измеренным/калибровочным слотам — у измеренных
    # уровень = закон (по результатам теста). Если у нас 3+ слотов с
    # одинаковым difficulty_level и среди них есть calibration-слот —
    # сдвигаем такие слоты по их level_window, пока распределение не станет
    # ≤2 одинаковых уровней (или пока двигать больше некуда).
    _enforce_spread(slots, max_same_level=2)
    _assign_diverse_themes(slots)

    _log_plan(slots)
    return slots


def _enforce_spread(slots: List[PlannedSlot], max_same_level: int = 2) -> None:
    """In-place: разносим difficulty_level так, чтобы один и тот же
    уровень встречался не более ``max_same_level`` раз.

    Двигаем ТОЛЬКО калибровочные/не-измеренные слоты (их уровень не закон).
    Для каждого «лишнего» слота пробуем сдвинуть его уровень внутри окна
    туда, где счётчик ещё не упёрся в потолок. Детерминированно: сначала
    идём вверх по окну, потом вниз.
    """
    if len(slots) <= max_same_level:
        return
    # Count occurrences
    from collections import Counter
    while True:
        counts = Counter(s.difficulty_level for s in slots)
        over = [lvl for lvl, c in counts.items() if c > max_same_level]
        if not over:
            return
        moved_anything = False
        for lvl in over:
            # Кандидаты на сдвиг: только калибровочные/не-измеренные слоты
            # с этим уровнем; среди них сначала пробуем те, у кого окно
            # шире (есть куда двигать).
            movable = [
                s for s in slots
                if s.difficulty_level == lvl and (s.is_calibration or not s.measured)
            ]
            if not movable:
                # Все слоты с этим уровнем — измеренные. Двигать нельзя.
                # Логируем и выходим из внешнего while, чтобы не зацикливаться.
                logger.info(
                    "slot_planner: level=%d встречается %d раз, но все слоты "
                    "измеренные (target locked) — оставляем как есть",
                    lvl, counts[lvl],
                )
                continue
            # Сколько слотов на этом уровне нужно подвинуть, чтобы счётчик
            # упал до max_same_level: c − max_same_level (но не больше,
            # чем калибровочных слотов на этом уровне).
            movable.sort(key=lambda s: s.position)
            to_move = max(0, counts[lvl] - max_same_level)
            # Двигаем сначала самые «последние по порядку» калибровочные
            # слоты — они менее заметны как нарушители порядка отображения.
            extras = movable[-to_move:] if to_move else []
            for slot in extras:
                lo, hi = slot.level_window
                # Кандидаты: сначала вверх (lvl+1, lvl+2, …, hi),
                # потом вниз (lvl-1, …, lo).
                candidates: List[int] = []
                for d in range(1, max(hi - lvl, lvl - lo) + 1):
                    if lvl + d <= hi:
                        candidates.append(lvl + d)
                    if lvl - d >= lo:
                        candidates.append(lvl - d)
                placed = False
                for new_lvl in candidates:
                    if counts.get(new_lvl, 0) < max_same_level:
                        logger.info(
                            "slot_planner spread: pos=%d topic=%s "
                            "level %d→%d (counter[%d]=%d, window=[%d,%d])",
                            slot.position, slot.topic, lvl, new_lvl,
                            lvl, counts[lvl], lo, hi,
                        )
                        slot.difficulty_level = new_lvl
                        counts[lvl] -= 1
                        counts[new_lvl] = counts.get(new_lvl, 0) + 1
                        placed = True
                        moved_anything = True
                        break
                if not placed:
                    # Окно слота не позволяет сдвинуться без перекоса
                    # — оставляем как есть, логируем.
                    logger.info(
                        "slot_planner spread: pos=%d topic=%s "
                        "не удалось подвинуть с L%d (окно=[%d,%d] узкое)",
                        slot.position, slot.topic, lvl, lo, hi,
                    )
        if not moved_anything:
            return


# ---------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------


def topic_to_window_summary(slots: List[PlannedSlot]) -> Dict[str, Dict[str, Any]]:
    """Return {topic: {window: [lo,hi], levels: [...]} } summary."""
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
    """Emit per-slot info lines + a summary line for diagnostics.

    Per-slot формат (требование ТЗ — чтобы было видно распределение в проде):
        SLOT_PLAN pos=N topic=<...> measured=<bool> window=[a..b] -> level=<n>

    Плюс одна суммарная строка с распределением уровней по комплекту:
        slot_planner summary: levels_count={L1:..,L2:..,…} duplicates=[L4×3, …]
    """
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
        levels,
        dict(sorted(counts.items())),
        (" duplicates>2: " + ", ".join(dups)) if dups else "",
    )


def check_slots_match_windows(
    specs: List[Dict[str, Any]],
    planned_slots: List[PlannedSlot],
) -> List[Dict[str, Any]]:
    """Validate that LLM-produced specs keep difficulty inside topic window.

    Returns a list of mismatches (empty if everything is OK). Each entry:
    {position, topic, expected_window, got_difficulty, planned_difficulty}.
    """
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
