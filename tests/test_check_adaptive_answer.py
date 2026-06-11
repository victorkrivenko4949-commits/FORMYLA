# -*- coding: utf-8 -*-
"""Tests for app.check_adaptive_answer() — scoring, difficulty, streak logic."""

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Helper ──────────────────────────────────────────────────────────────

def _call_check_answer(client, user_answer, mock_review_return,
                       user_solution="", slot=0, task_id=1,
                       difficulty=1, streak=0):
    """Simulate a POST to /api/check_adaptive_answer with given patches.

    Also patches the local answer checker (check_answer) so it returns
    (False, "parse_error") — forcing the AI review path to be exercised.

    Parameters
    ----------
    client : Flask test client
    user_answer : str
    mock_review_return : dict
        The return value for the mocked review_attempt.
    user_solution : str
    slot : int
    task_id : int
    difficulty : int
        Initial adaptive_current_difficulty (default 1).
    streak : int
        Initial partial_correct_streak (default 0).
    """
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.answer = "5"
    mock_task.difficulty = 1
    mock_task.difficulty_level = 1
    mock_task.topic = "algebra"
    mock_task.solution = "x = 5"
    mock_task.task_text = "Solve for x: 2x + 3 = 13"

    mock_review = MagicMock(return_value=mock_review_return)
    mock_checker = MagicMock(return_value=(False, "parse_error"))

    # ── Initialise adaptive test session ────────────────────────────
    # The check_adaptive_answer endpoint requires these session keys.
    with client.session_transaction() as sess:
        sess["adaptive_filtered_tasks"] = [task_id]
        sess["adaptive_current_difficulty"] = difficulty
        sess["partial_correct_streak"] = streak
        # adaptive_slots will be lazy-initialised by _adaptive_get_slots()

    # ── Apply patches ───────────────────────────────────────────────
    # Also patch the local answer checker so it falls through to AI
    with patch(
        "services.ai_tutor_review.review_attempt", mock_review
    ), patch(
        "models.AdaptiveTask",
    ) as MockAdaptiveTask, patch(
        "services.answer_checker.check_answer", mock_checker
    ):
        MockAdaptiveTask.query.get.return_value = mock_task

        resp = client.post(
            "/api/check_adaptive_answer",
            json={
                "task_id": task_id,
                "user_answer": user_answer,
                "user_solution": user_solution,
                "slot": slot,
            },
        )

    return resp


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Return a Flask test client for the main app.

    Creates a test user (id=999) in the DB if not present, and sets up the
    Flask-Login session so that require_registration() passes.
    """
    from app import app as flask_app
    from models import db, User

    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        # Ensure a non-guest test user exists for Flask-Login
        user = db.session.get(User, 999)
        if not user:
            user = User(
                id=999,
                email="test_check_adaptive@formyla.local",
                nickname="test_adaptive_user",
                is_guest=False,
            )
            db.session.add(user)
            db.session.commit()

    with flask_app.test_client() as c:
        with c.session_transaction() as sess:
            # Flask-Login reads _user_id from session to load current_user
            sess["_user_id"] = "999"
            sess["_fresh"] = True
            sess["user_id"] = 999
            sess["_id"] = "test-session-999"
            sess["device_id"] = "test-device-999"
        yield c


# ═══════════════════════════════════════════════════════════════════════════

# ── Tests ─────────────────────────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════════
# FORMYLA v2 scale (since commit "scoring v2"):
#   answer_correct=True,  method_correct=True/None      → score=+1, level+1
#   answer_correct=True,  method_correct=False (с реш.) → score= 0, level=ст.
#   answer_correct=False, method_correct=True  (с реш.) → score= 0, level=ст.
#   answer_correct=False, method_correct=False/None    → score=-1, level-1
#   answer_correct=None (AI failure / суждение неясно)  → score= 0, level=ст.
# Уровень clamped to [1, 8] (FORMYLA v2, fix/adaptive-progress).
# ═════════════════════════════════════════════════════════════════════════


def test_correct_answer_level_up(client):
    """ТЗ FORMYLA v2: верный ответ + верный метод → +1 балл, уровень +1."""
    mock_return = {
        "score": 1.0,
        "feedback": "✅ Всё верно!",
        "category": "correct",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1  # +1 балл
    assert data["new_level"] == 2  # было 1 → стало 2


def test_correct_answer_wrong_method_neutral(client):
    """ТЗ FORMYLA v2: верный ответ + неверный метод → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.5,
        "feedback": "🟡 Ответ верный, но метод не тот.",
        "category": "correct_no_justification",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "5", mock_return, user_solution="неверное решение")
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0  # ответ верен, но метод неверный — нейтрально
    assert data["new_level"] == 1


def test_wrong_answer_full_negative(client):
    """ТЗ FORMYLA v2: неверный ответ + неверный метод → -1 балл, уровень -1.

    На level=1 уровень clamp'ится снизу — остаётся 1.
    """
    mock_return = {
        "score": -1.0,
        "feedback": "❌ Ответ не принят.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
        "answer_correct": False,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "42", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == -1
    # current=1, delta=-1, clamp → max(1, 0) = 1
    assert data["new_level"] == 1


def test_wrong_answer_level_down_from_5(client):
    """ТЗ FORMYLA v2: неверный ответ на уровне 5 → score=-1, уровень 5→4."""
    mock_return = {
        "score": -1.0,
        "feedback": "❌ Неверно.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
        "answer_correct": False,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "wrong", mock_return, difficulty=5)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == -1
    assert data["new_level"] == 4


def test_correct_answer_no_solution_level_up(client):
    """ТЗ FORMYLA v2: только ответ (без решения), ответ верный → +1 балл, +1 уровень."""
    mock_return = {
        "score": 0.3,
        "feedback": "🟡 Верный ответ.",
        "category": "correct_no_justification",
        "confidence": 0.7,
        "answer_correct": True,
        "method_correct": None,  # без решения метод не оценивается
    }
    resp = _call_check_answer(client, "5", mock_return, user_solution="")
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1
    assert data["new_level"] == 2


def test_wrong_answer_good_method_neutral(client):
    """ТЗ FORMYLA v2: ответ неверный, но метод понят правильно → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.0,
        "feedback": "🟡 Метод верный, но ответ не сошёлся.",
        "category": "wrong_answer_good_method",
        "confidence": 0.9,
        "answer_correct": False,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "wrong", mock_return, user_solution="правильное решение")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 0
    assert data["new_level"] == 1  # без изменений


def test_ai_failure_neutral(client):
    """ТЗ FORMYLA v2: сбой AI (answer_correct=None) → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.0,
        "feedback": "",
        "category": "suspicious",
        "confidence": 0.0,
        "answer_correct": None,
        "method_correct": None,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 0
    assert data["new_level"] == 1


# ═════════════════════════════════════════════════════════════════════════
# Regression tests for fix/adaptive-progress (calibration & clamp 1..8).
# ═════════════════════════════════════════════════════════════════════════


def test_two_consecutive_correct_answers_accumulate_level(client):
    """Регрессия: два верных ответа подряд → уровень накапливается 3 → 4 → 5.

    Бывший баг: new_level пересчитывался от difficulty показанной задачи,
    из-за чего после первого +1 уровень "застревал". Теперь new_level
    берётся от СОХРАНЁННОГО session['adaptive_current_difficulty'].
    """
    mock_return = {
        "score": 1.0,
        "feedback": "✅",
        "category": "correct",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": True,
    }
    # 1-й ответ: cur=3 → new=4
    resp1 = _call_check_answer(client, "5", mock_return, difficulty=3, slot=1)
    data1 = resp1.get_json()
    assert resp1.status_code == 200
    assert data1["new_level"] == 4, f"first answer: {data1}"

    # Проверяем что session обновилась
    with client.session_transaction() as sess:
        assert sess["adaptive_current_difficulty"] == 4

    # 2-й ответ: cur=4 → new=5 (НЕ "застрял" на 4)
    # Передаём difficulty=4 явно, так как _call_check_answer переинициализирует
    # session перед каждым вызовом — мы продолжаем накопленный уровень.
    # task_id=2 чтобы попасть в другой слот без already_answered.
    resp2 = _call_check_answer(client, "5", mock_return, slot=2, task_id=2, difficulty=4)
    data2 = resp2.get_json()
    assert resp2.status_code == 200
    assert data2["new_level"] == 5, (
        f"second answer should accumulate to 5, not stuck at 4. Got: {data2}"
    )

    with client.session_transaction() as sess:
        assert sess["adaptive_current_difficulty"] == 5


def test_correct_answer_at_level_7_advances_to_8(client):
    """Регрессия: clamp теперь 1..8 (а не 1..7). На уровне 7 верный ответ → 8."""
    mock_return = {
        "score": 1.0,
        "feedback": "✅",
        "category": "correct",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "5", mock_return, difficulty=7)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 1
    assert data["new_level"] == 8, (
        f"level 7 + correct should advance to 8 (clamp 1..8), not stuck at 7. Got: {data}"
    )


def test_correct_answer_at_level_8_stays_at_8(client):
    """Регрессия: на максимуме 8 верный ответ → остаётся 8 (clamp сверху)."""
    mock_return = {
        "score": 1.0,
        "feedback": "✅",
        "category": "correct",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "5", mock_return, difficulty=8)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 1
    assert data["new_level"] == 8  # clamp(1, 8, 8+1) = 8


def test_stale_pending_slot_reassigned_after_level_change(client):
    """Регрессия: если pending-слот был назначен при cur=3, а потом cur стал 5
    (юзер ответил на другой слот +1+1), то при открытии этого слота задача
    должна быть переназначена под текущий уровень (level_at_assign=5)."""
    from app import app as flask_app
    from models import db, AdaptiveTask

    flask_app.config["TESTING"] = True

    # Подготавливаем сессию: один pending-слот с task назначенной при cur=3,
    # потом меняем cur на 5 и открываем тот же слот.
    with flask_app.app_context():
        # Берём 2 реальные задачи разных уровней из БД для теста.
        # Если БД пуста — тест пропускаем.
        t3 = AdaptiveTask.query.filter_by(difficulty_level=3).first()
        t5 = AdaptiveTask.query.filter_by(difficulty_level=5).first()
        if not (t3 and t5):
            pytest.skip("Нет задач уровня 3 и 5 в формьила-БД для теста")

        with flask_app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "999"
                sess["adaptive_filtered_tasks"] = [t3.id, t5.id]
                sess["adaptive_grade"] = "9"
                sess["adaptive_topic"] = "algebra"
                sess["adaptive_current_difficulty"] = 5  # ← сменили уровень
                # Слот 1 был назначен при cur=3 (level_at_assign=3) — pending.
                slots = [
                    {
                        "task_id": t3.id,
                        "status": "pending",
                        "score": None,
                        "difficulty": 3,
                        "user_answer": "",
                        "correct_answer": "",
                        "level_at_assign": 3,
                    }
                ] + [
                    {
                        "task_id": None, "status": "pending", "score": None,
                        "difficulty": None, "user_answer": "", "correct_answer": "",
                        "level_at_assign": None,
                    }
                    for _ in range(24)
                ]
                sess["adaptive_slots"] = slots

            # Открываем слот 1 — он должен быть переназначен под cur=5
            resp = c.get("/adaptive_test_simple?slot=1")
            assert resp.status_code == 200, (
                f"slot=1 GET failed: status={resp.status_code}"
            )

            with c.session_transaction() as sess:
                slot_after = sess["adaptive_slots"][0]
                assert slot_after["task_id"] is not None, (
                    "Слот должен иметь назначенную задачу после render"
                )
                # level_at_assign должен соответствовать новому cur=5
                # (точное равенство — если задача уровня 5 нашлась)
                assert slot_after["level_at_assign"] == 5, (
                    f"После cur=5 слот должен быть переназначен с "
                    f"level_at_assign=5, получили {slot_after}"
                )


def test_picker_prefers_higher_levels_over_lower(client):
    """Регрессия (fix/adaptive-badge-level Fix 2): когда на текущем уровне
    нет задач, пикер должен сначала пробовать уровни ВЫШЕ, потом ниже.

    Это исправляет «застрявший бейдж 4/8»: при высоком уровне (7-8) и пустоте
    на этом уровне пикер не должен скатываться к простым задачам уровня 3-4.
    """
    from app import app as flask_app
    from models import db, AdaptiveTask

    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        # Берём задачи уровня 3 и 7 — НЕТ задачи уровня 5
        t3 = AdaptiveTask.query.filter_by(difficulty_level=3).first()
        t7 = AdaptiveTask.query.filter_by(difficulty_level=7).first()
        if not (t3 and t7):
            pytest.skip("Нет задач уровня 3 и 7 в БД для теста")

        with flask_app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "999"
                sess["adaptive_filtered_tasks"] = [t3.id, t7.id]
                sess["adaptive_grade"] = "9"
                sess["adaptive_topic"] = "algebra"
                # current=5, в банке только 3 и 7. Пикер должен выбрать 7 (выше),
                # а не 3 (ниже).
                sess["adaptive_current_difficulty"] = 5
                sess["adaptive_slots"] = [
                    {
                        "task_id": None, "status": "pending", "score": None,
                        "difficulty": None, "user_answer": "", "correct_answer": "",
                        "level_at_assign": None,
                    }
                    for _ in range(25)
                ]

            resp = c.get("/adaptive_test_simple?slot=1")
            assert resp.status_code == 200

            with c.session_transaction() as sess:
                slot_after = sess["adaptive_slots"][0]
                assert slot_after["task_id"] == t7.id, (
                    f"Должна была выбраться задача уровня 7 (выше cur=5), "
                    f"а не уровня 3 (ниже). Выбран task_id={slot_after['task_id']}, "
                    f"ожидали {t7.id}"
                )
                assert slot_after["difficulty"] == 7, (
                    f"slot.difficulty должен быть 7, получили {slot_after['difficulty']}"
                )
