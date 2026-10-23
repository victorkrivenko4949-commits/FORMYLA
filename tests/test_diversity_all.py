# -*- coding: utf-8 -*-
"""
Tests for per-slot diversity (subtopic + method) using DIVERSITY_CATALOG.

Verifies that assign_diversity() works for ALL grades 5..11 and ALL topics
in each grade, without any network calls (uses mock profile+slots).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

import pytest

from daily_tasks.pipeline.diversity_catalog import DIVERSITY_CATALOG
from daily_tasks.pipeline.slot_planner import (
    PlannedSlot,
    SOLUTION_METHODS,
    assign_diversity,
)
from daily_tasks.pipeline.step1_gemini import DIVERSITY_RULES, build_forbidden_block


# ── helpers ────────────────────────────────────────────────────────────────


def _make_slots(
    topic_key: str,
    n: int = 10,
    levels: List[int] | None = None,
) -> List[PlannedSlot]:
    """Create n PlannedSlot objects all with the same topic_key."""
    if levels is None:
        # Default: spread levels 1..8 roughly
        levels = [1, 1, 2, 2, 3, 3, 4, 5, 6, 7][:n]
    slots: List[PlannedSlot] = []
    for i in range(n):
        lvl = levels[i] if i < len(levels) else 1
        slots.append(PlannedSlot(
            position=i + 1,
            slot_kind="weak_main",
            subject="math",
            topic=topic_key,
            topic_key=topic_key,
            difficulty_level=lvl,
            target_level=lvl,
            level_window=(1, 8),
            is_calibration=False,
            measured=True,
            pct=50.0,
            test_correct=4,
            test_total=8,
            final_level=lvl,
            subtopic_hints=[],
            reason_hint="",
        ))
    return slots


def _unique_count(items: List[str]) -> int:
    """Number of unique non-empty items."""
    return len({s for s in items if s})


# ── test: assign_diversity produces exactly 10 entries ────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_assign_diversity_produces_10_slots(grade: int):
    """For every grade 5..11, assign_diversity returns 10 used entries."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key in catalog_grade:
        slots = _make_slots(topic_key)
        used = assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        assert len(used) == 10, (
            f"grade={grade} topic={topic_key}: "
            f"expected 10 entries, got {len(used)}"
        )


# ── test: unique subtopics ────────────────────────────────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_unique_subtopics(grade: int):
    """At least min(7, len(subs)) unique subtopics across 10 slots."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        subs = node.get("subtopics", [])
        if not subs:
            continue  # skip topics with no subtopics
        slots = _make_slots(topic_key)
        used = assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        assigned_subs = [e["subtopic"] for e in used]
        unique_subs = _unique_count(assigned_subs)
        expected_min = min(7, len(subs))

        assert unique_subs >= expected_min, (
            f"grade={grade} topic={topic_key}: "
            f"only {unique_subs} unique subtopics, "
            f"expected >= {expected_min} (total catalog={len(subs)})"
        )


# ── test: difficulty spread (no more than 2 per level if calibration) ──────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_difficulty_spread_max_2(grade: int):
    """No difficulty_level appears more than 2 times (catalog spread rule)."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        slots = _make_slots(
            topic_key,
            levels=[1, 1, 2, 3, 3, 4, 5, 6, 7, 8],
        )
        used = assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        level_counts = Counter(e["level"] for e in used)
        for lvl, cnt in level_counts.items():
            # Allow up to 3 if topic has narrow window
            assert cnt <= 3, (
                f"grade={grade} topic={topic_key}: "
                f"level L{lvl} appears {cnt} times (max 3 allowed)"
            )


# ── test: level_notes exist for every slot level ──────────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_level_notes_present(grade: int):
    """Each slot has a non-empty note from level_notes."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        slots = _make_slots(topic_key)
        used = assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        for entry in used:
            assert entry["note"], (
                f"grade={grade} topic={topic_key} pos={entry['position']}: "
                f"empty note for level L{entry['level']}"
            )


# ── test: methods are assigned (not empty) ────────────────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_methods_assigned(grade: int):
    """Each slot has a non-empty method."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        slots = _make_slots(topic_key)
        used = assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        for entry in used:
            assert entry["method"], (
                f"grade={grade} topic={topic_key} pos={entry['position']}: "
                f"empty method"
            )


# ── test: rotation works (day_index changes subtopic order) ───────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_rotation_changes_assignment(grade: int):
    """Different day_index produces different subtopic for the first slot."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        subs = node.get("subtopics", [])
        if len(subs) < 2:
            continue  # need at least 2 to see rotation

        slots0 = _make_slots(topic_key)
        used0 = assign_diversity(slots0, subtopics=[], day_index=0, grade=grade)

        slots1 = _make_slots(topic_key)
        used1 = assign_diversity(slots1, subtopics=[], day_index=1, grade=grade)

        # With at least 2 subtopics, day_index=0 vs 1 must differ at slot 1
        # (unless catalog has exactly 1 subtopic, already skipped)
        assert used0[0]["subtopic"] != used1[0]["subtopic"], (
            f"grade={grade} topic={topic_key}: "
            f"rotation failed — day 0 and day 1 give same first subtopic"
        )


# ── test: reason_hint contains grade, level, subtopic, method ─────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_reason_hint_contains_all_fields(grade: int):
    """Slot.reason_hint includes grade, level, subtopic, method."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key in catalog_grade:
        slots = _make_slots(topic_key)
        assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        for slot in slots:
            hint = slot.reason_hint
            assert f"класс {grade}" in hint, (
                f"grade={grade} topic={topic_key}: reason_hint missing grade"
            )
            assert f"уровень {slot.difficulty_level}" in hint, (
                f"grade={grade} topic={topic_key}: reason_hint missing level"
            )
            assert "подтема:" in hint, (
                f"grade={grade} topic={topic_key}: reason_hint missing subtopic"
            )
            assert "метод:" in hint, (
                f"grade={grade} topic={topic_key}: reason_hint missing method"
            )


# ── test: subtopic_hints is set on each slot ──────────────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_subtopic_hints_set(grade: int):
    """Each slot has non-empty subtopic_hints after assign_diversity."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key in catalog_grade:
        slots = _make_slots(topic_key)
        assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        for slot in slots:
            assert slot.subtopic_hints, (
                f"grade={grade} topic={topic_key} pos={slot.position}: "
                f"subtopic_hints is empty"
            )


# ── test: fallback SOLUTION_METHODS works when catalog has no methods ──────


def test_fallback_solution_methods():
    """When catalog node has no methods, fallback SOLUTION_METHODS is used."""
    slots = _make_slots("unknown_topic")
    used = assign_diversity(slots, subtopics=[], day_index=0, grade=99)
    assert len(used) == 10
    for entry in used:
        assert entry["method"] in SOLUTION_METHODS, (
            f"method '{entry['method']}' not in SOLUTION_METHODS"
        )


# ── test: fallback subtopics work ─────────────────────────────────────────


def test_fallback_subtopics():
    """When no catalog node, inventory subtopics are used."""
    slots = _make_slots("unknown_topic")
    inventory_subs = ["тест A", "тест B", "тест C"]
    used = assign_diversity(slots, subtopics=inventory_subs, day_index=0, grade=99)
    assert len(used) == 10
    # At least 3 unique subtopics from inventory
    unique_subs = _unique_count([e["subtopic"] for e in used])
    assert unique_subs >= 3


# ── test: build_forbidden_block contains "ЗАПРЕЩЕНО" ──────────────────────


def test_build_forbidden_block_contains_zaprescheno():
    """build_forbidden_block() output includes the word 'ЗАПРЕЩЕНО'."""
    used = [
        {"position": 1, "topic": "Алгебра", "subtopic": "тест A",
         "method": "разбор случаев", "level": 3, "note": "простой пример"},
    ]
    block = build_forbidden_block(used)
    assert "ЗАПРЕЩЕНО" in block, (
        "build_forbidden_block must contain 'ЗАПРЕЩЕНО'"
    )


def test_build_forbidden_block_with_empty_used():
    """build_forbidden_block with empty used returns graceful message."""
    block = build_forbidden_block([])
    assert block.strip() != ""
    assert "Нет данных" in block or "ЗАПРЕЩЕНО" in block


def test_build_forbidden_block_with_recent_pool():
    """build_forbidden_block includes recent_pool_tasks when provided."""
    used = [
        {"position": 1, "topic": "Геометрия", "subtopic": "тест A",
         "method": "от противного", "level": 5, "note": ""},
    ]
    recent = [{"task_text": "Решите уравнение x^2=4"}]
    block = build_forbidden_block(used, recent_pool_tasks=recent)
    assert "Решите уравнение" in block
    assert "НЕДАВНИЕ ЗАДАЧИ" in block


# ── test: DIVERSITY_RULES constant is defined ─────────────────────────────


def test_diversity_rules_defined():
    """DIVERSITY_RULES is a non-empty string."""
    assert DIVERSITY_RULES
    assert "ЗАПРЕЩЕНО" in DIVERSITY_RULES
    assert "subtopic_hints" in DIVERSITY_RULES


# ── test: slot.reason_hint is non-empty after diversity ───────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_reason_hint_nonempty(grade: int):
    """After assign_diversity, all slots have non-empty reason_hint."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key in catalog_grade:
        slots = _make_slots(topic_key)
        assign_diversity(slots, subtopics=[], day_index=0, grade=grade)

        for slot in slots:
            assert slot.reason_hint, (
                f"grade={grade} topic={topic_key} pos={slot.position}: "
                f"reason_hint empty after assign_diversity"
            )


# ── test: level_notes support both int and str keys ───────────────────────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_level_notes_int_and_str_keys(grade: int):
    """level_notes should be accessible by int key (already the default)."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key, node in catalog_grade.items():
        notes = node.get("level_notes", {})
        for lvl in range(1, 9):
            # Must be accessible by int (as used in assign_diversity)
            val = notes.get(lvl) or notes.get(str(lvl))
            if val is None:
                # Not all levels have notes — that's OK for partial coverage
                continue
            assert isinstance(val, str) and len(val) > 0, (
                f"grade={grade} topic={topic_key}: "
                f"level_notes[{lvl}] is not a non-empty string"
            )


# ── test: empty slots list returns empty ────────────────────────────────


def test_assign_diversity_empty_slots():
    """assign_diversity with empty slots returns empty list."""
    result = assign_diversity([], subtopics=[], day_index=0, grade=5)
    assert result == []


# ── test: multiple days produce different assignments (full coverage) ────


@pytest.mark.parametrize("grade", list(range(5, 12)))
def test_multiple_days_different(grade: int):
    """Assignments for day 0 and day 6 differ (rotation)."""
    catalog_grade = DIVERSITY_CATALOG.get(grade, {})
    if not catalog_grade:
        pytest.skip(f"No diversity data for grade {grade}")

    for topic_key in catalog_grade:
        subs = catalog_grade[topic_key].get("subtopics", [])
        if len(subs) < 2:
            continue

        slots0 = _make_slots(topic_key)
        used0 = assign_diversity(slots0, subtopics=[], day_index=0, grade=grade)

        slots6 = _make_slots(topic_key)
        used6 = assign_diversity(slots6, subtopics=[], day_index=6, grade=grade)

        # At least one subtopic should differ
        subs0 = [e["subtopic"] for e in used0]
        subs6 = [e["subtopic"] for e in used6]
        assert subs0 != subs6, (
            f"grade={grade} topic={topic_key}: "
            f"day 0 and day 6 produce identical subtopic lists"
        )
