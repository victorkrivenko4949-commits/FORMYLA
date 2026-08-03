# -*- coding: utf-8 -*-
"""
Regression tests for /api/tutor/hint and /api/tutor/solution.

Background
----------
Before the fix the endpoints looked at TWO sources:

    problem = next((p for p in PROBLEMS_DB if p.get("id") == pid), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == pid), None)

`_RAW_DB` is the **probniks/combos** table — its top-level items have
`id`, `olympiad`, `year`, `grade`, `round`, `problems` (a nested list of
tasks).  They DO NOT carry a `text`/`answer` themselves.  So whenever a
caller asked for a problem whose id happened to coincide with a combo id
(very common), the endpoint returned 200 with an empty prompt and the AI
hallucinated something like «в условии не указана задача».

This file pins down the correct behaviour:

  * `_find_problem_for_tutor(pid)` returns a problem only if its `id`
    matches in `PROBLEMS_DB` AND `text` is non-empty.
  * `/api/tutor/hint/<id>` and `/api/tutor/solution/<id>` pass the real
    `text`/`answer` to the DeepSeek client (no empty strings).
  * Unknown id -> 404.
  * Probnik (combo) id -> 404 (regression test for the bug).
  * Empty-text problem -> 404 (defensive).
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_problems(monkeypatch):
    """Import the real Flask app and replace PROBLEMS_DB / _RAW_DB with a
    minimal, deterministic dataset that mirrors the production schema."""
    import app as appmod

    # Real "темы" entries — must have id + text + answer + difficulty.
    fake_problems = [
        {"id": 1001, "subject": "algebra", "subtopic": "linear",
         "grade": 6, "difficulty": 2,
         "text": "Реши уравнение: 3x = 12.",
         "answer": "4"},
        {"id": 1002, "subject": "geometry", "subtopic": "areas",
         "grade": 6, "difficulty": 3,
         "text": "Площадь квадрата со стороной 5?",
         "answer": "25"},
        # Defensive: an entry with empty text. The endpoint must NOT feed
        # this to the AI.
        {"id": 1003, "subject": "logic", "subtopic": "?",
         "grade": 6, "difficulty": 1,
         "text": "",
         "answer": "?"},
    ]

    # Combos table — top-level objects whose `id` may collide with the
    # problem ids the client uses. They MUST be ignored by the tutor.
    fake_combos = [
        {"id": 1001,                              # <- clashes on purpose!
         "olympiad": "vsosh-9-2027",
         "olympiad_title": "ВсОШ 9",
         "year": 2024, "grade": 9, "round": 1,
         "round_title": "Школьный",
         "problems": [
             {"num": 1, "text": "Combo problem 1 text",
              "answer": "X", "solution": "Y"},
         ],
         "source_url": "", "source_name": ""},
    ]

    monkeypatch.setattr(appmod, "PROBLEMS_DB", fake_problems)
    monkeypatch.setattr(appmod, "_RAW_DB", fake_combos)
    monkeypatch.setattr(appmod, "DEEPSEEK_AVAILABLE", True)

    appmod.app.testing = True
    appmod.app.config["WTF_CSRF_ENABLED"] = False
    appmod.app.config["LOGIN_DISABLED"] = True  # bypass @login_required
    return appmod


@pytest.fixture
def client(app_with_problems):
    return app_with_problems.app.test_client()


# ─── Helper unit tests ──────────────────────────────────────────────────────


class TestFindProblemForTutor:
    def test_finds_existing(self, app_with_problems):
        p = app_with_problems._find_problem_for_tutor(1001)
        assert p is not None
        assert p["text"].startswith("Реши уравнение")
        assert p["answer"] == "4"

    def test_unknown_id_returns_none(self, app_with_problems):
        assert app_with_problems._find_problem_for_tutor(999999) is None

    def test_empty_text_returns_none(self, app_with_problems):
        # Regression: even if id matches, an empty `text` must be rejected.
        assert app_with_problems._find_problem_for_tutor(1003) is None

    def test_combo_id_is_NOT_matched(self, app_with_problems):
        """Regression for the «не генерится решение в темах» bug.

        Combo id=1001 exists in _RAW_DB but the helper must still find the
        PROBLEMS_DB entry (real task), not the combo. We assert by checking
        we got the problem text, not the combo's first sub-problem text."""
        p = app_with_problems._find_problem_for_tutor(1001)
        assert p is not None
        assert "Combo problem" not in (p.get("text") or "")
        assert "Реши уравнение" in p["text"]


# ─── HTTP-level endpoint tests ──────────────────────────────────────────────


class TestSolutionEndpoint:
    def test_known_problem_calls_deepseek_with_real_text(
        self, app_with_problems, client
    ):
        with patch.object(app_with_problems, "DeepSeekClient") as Mock:
            instance = Mock.return_value
            instance.generate_solution.return_value = "FAKE SOLUTION"

            r = client.post("/api/tutor/solution/1001",
                            json={}, content_type="application/json")
            assert r.status_code == 200
            data = r.get_json()
            assert data["solution"] == "FAKE SOLUTION"
            assert data["answer"] == "4"
            assert data["problem_id"] == 1001

            # The crucial assertion: a non-empty `problem_text` reached
            # the AI client. Before the fix this was "" for combo ids.
            kwargs = instance.generate_solution.call_args.kwargs
            assert kwargs["problem_text"].startswith("Реши уравнение")
            assert kwargs["problem_answer"] == "4"
            assert kwargs["difficulty"] == 2

    def test_unknown_problem_returns_404(self, client):
        r = client.post("/api/tutor/solution/999999",
                        json={}, content_type="application/json")
        assert r.status_code == 404
        assert "не найдена" in r.get_json()["error"].lower()

    def test_empty_text_problem_returns_404(self, client):
        # Defensive: PROBLEMS_DB has id=1003 with empty text. Endpoint
        # must NOT call AI on this — otherwise we get the «в условии не
        # указана задача» hallucination again.
        r = client.post("/api/tutor/solution/1003",
                        json={}, content_type="application/json")
        assert r.status_code == 404

    def test_combo_id_returns_404_not_AI_hallucination(
        self, app_with_problems, client
    ):
        """Regression: probnik id (1001 in _RAW_DB) must NOT short-circuit
        the lookup — id 1001 also exists in PROBLEMS_DB so we expect a real
        AI call with the PROBLEMS_DB text, never with the combo's empty
        top-level fields."""
        with patch.object(app_with_problems, "DeepSeekClient") as Mock:
            instance = Mock.return_value
            instance.generate_solution.return_value = "FAKE"
            r = client.post("/api/tutor/solution/1001",
                            json={}, content_type="application/json")
            assert r.status_code == 200
            text_sent = instance.generate_solution.call_args.kwargs["problem_text"]
            # [ERROR] The pre-fix behaviour gave AI text="" — now it has content.
            assert text_sent.strip() != ""
            assert "Combo problem" not in text_sent  # came from PROBLEMS_DB

    def test_ai_unavailable_503(self, app_with_problems, client, monkeypatch):
        monkeypatch.setattr(app_with_problems, "DEEPSEEK_AVAILABLE", False)
        r = client.post("/api/tutor/solution/1001",
                        json={}, content_type="application/json")
        assert r.status_code == 503

    def test_ai_exception_returns_500(self, app_with_problems, client):
        with patch.object(app_with_problems, "DeepSeekClient") as Mock:
            Mock.return_value.generate_solution.side_effect = RuntimeError("boom")
            r = client.post("/api/tutor/solution/1001",
                            json={}, content_type="application/json")
            assert r.status_code == 500
            assert "Ошибка" in r.get_json()["error"]


class TestHintEndpoint:
    def test_known_problem_calls_deepseek(self, app_with_problems, client):
        with patch.object(app_with_problems, "DeepSeekClient") as Mock:
            Mock.return_value.generate_hint.return_value = "Подумай о…"
            r = client.post("/api/tutor/hint/1002",
                            json={}, content_type="application/json")
            assert r.status_code == 200
            data = r.get_json()
            assert data["hint"] == "Подумай о…"
            assert data["problem_id"] == 1002
            kw = Mock.return_value.generate_hint.call_args.kwargs
            assert "квадрат" in kw["problem_text"].lower()
            assert kw["problem_answer"] == "25"

    def test_unknown_problem_404(self, client):
        r = client.post("/api/tutor/hint/424242",
                        json={}, content_type="application/json")
        assert r.status_code == 404

    def test_empty_text_problem_404(self, client):
        r = client.post("/api/tutor/hint/1003",
                        json={}, content_type="application/json")
        assert r.status_code == 404
