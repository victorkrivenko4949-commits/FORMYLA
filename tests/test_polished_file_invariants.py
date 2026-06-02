# -*- coding: utf-8 -*-
"""Tests that lock-in critical invariants of the polished 8389-task file.
(Was 8394; 5 broken tasks were removed in the 2026-05 final cleanup.)

These tests guarantee that the downstream site code does NOT need to
parse subject/level/grade from the task id - every task carries them
explicitly as fields. If this test ever fails, the import is unsafe.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

POLISHED = os.path.join(
    ROOT,
    "adaptive_data",
    "final",
    "formyla_adaptive_final_polished.json",
)

VALID_SUBJECTS = set([
    "algebra", "geometry", "combinatorics",
    "number_theory", "logic", "set_theory",
])


@pytest.fixture(scope="module")
def tasks():
    if not os.path.isfile(POLISHED):
        pytest.skip("polished file not present: " + POLISHED)
    with open(POLISHED, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, list):
        return doc
    return doc.get("tasks") or doc.get("items") or doc.get("data") or []


class TestPolishedFileInvariants:
    def test_total_count(self, tasks):
        # Was 8394 before 2026-05 final cleanup; 5 broken tasks were removed.
        assert len(tasks) == 8389

    def test_all_ids_unique(self, tasks):
        ids = [t.get("id") for t in tasks]
        assert len(set(ids)) == len(ids)
        assert all(ids)

    def test_subject_always_present_and_canonical(self, tasks):
        for t in tasks:
            sj = t.get("subject")
            assert sj in VALID_SUBJECTS, (
                "task " + str(t.get("id"))
                + " has subject=" + repr(sj)
            )

    def test_grade_int_in_5_11(self, tasks):
        for t in tasks:
            g = t.get("grade")
            assert isinstance(g, int), (
                "task " + str(t.get("id"))
                + " has non-int grade=" + repr(g)
            )
            assert 5 <= g <= 11, (
                "task " + str(t.get("id"))
                + " has grade out of range: " + str(g)
            )

    def test_level_int_in_1_8(self, tasks):
        for t in tasks:
            lv = t.get("level")
            assert isinstance(lv, int)
            assert 1 <= lv <= 8, (
                "task " + str(t.get("id"))
                + " has level out of range: " + str(lv)
            )

    def test_topic_and_diagnostic_section_present(self, tasks):
        for t in tasks:
            tp = t.get("topic") or ""
            ds = t.get("diagnostic_section") or ""
            assert tp or ds, "task " + str(t.get("id")) + " has no topic"

    def test_topic_equals_diagnostic_section(self, tasks):
        """Import script's strict validator requires this equality."""
        for t in tasks:
            tp = t.get("topic")
            ds = t.get("diagnostic_section")
            if tp and ds:
                assert tp == ds, (
                    "task " + str(t.get("id"))
                    + " has topic != diagnostic_section"
                )

    def test_domain_equals_subject_or_absent(self, tasks):
        """Import script's strict validator requires this equality."""
        for t in tasks:
            dom = t.get("domain")
            sj = t.get("subject")
            if dom:
                assert dom == sj, (
                    "task " + str(t.get("id"))
                    + " has domain != subject"
                )

    def test_statement_answer_solution_non_empty(self, tasks):
        for t in tasks:
            for k in ("statement", "answer", "solution"):
                v = t.get(k)
                assert isinstance(v, str) and v.strip(), (
                    "task " + str(t.get("id"))
                    + " has empty " + k
                )

    def test_id_parsing_NOT_required_for_subject_or_level(self, tasks):
        """For every single task, subject and level must be obtainable
        from explicit fields, NEVER by parsing the id string."""
        # We assert: if we delete the id from a task dict and ask the
        # classifier, it still returns the correct subject.
        from services.subject_classifier import classify_subject
        for t in tasks:
            copy_no_id = dict(t)
            copy_no_id.pop("id", None)
            classified = classify_subject(copy_no_id)
            assert classified == t.get("subject"), (
                "task " + str(t.get("id"))
                + ": classify_subject(without id) returned "
                + repr(classified)
                + " but subject field is "
                + repr(t.get("subject"))
            )

    def test_id_is_opaque_string(self, tasks):
        """id is an opaque, stable lookup key. It must be a non-empty
        string. Code MUST NOT depend on its substring structure."""
        for t in tasks:
            tid = t.get("id")
            assert isinstance(tid, str) and tid