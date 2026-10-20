"""Regression coverage for checked/solved counters and XP level display."""

from datetime import datetime, timedelta

from daily_tasks.models import DailyTaskItem, DailyTaskSet
from models import (
    BankIssue, TestResult as StoredTestResult, User, VerifiedProblemCheck, db,
)
from services.solved_stats import solved_counts_by_user, task_counts_by_user


def test_checked_and_correct_tasks_include_all_recorded_outcomes(app, test_user):
    now = datetime.utcnow()
    old = now - timedelta(days=10)
    task_set = DailyTaskSet(
        user_id=test_user.id, target_date=now.date(), status="ready")
    db.session.add(task_set)
    db.session.flush()
    db.session.add_all([
        DailyTaskItem(daily_set_id=task_set.id, position=1,
                      task_text="Correct", is_correct=True, answered_at=now),
        DailyTaskItem(daily_set_id=task_set.id, position=2,
                      task_text="Incorrect", is_correct=False, answered_at=now),
        BankIssue(user_id=test_user.id, task_id=101, subtopic="Algebra",
                  level=1, issued_date=old.date(), is_correct=True,
                  answered_at=old),
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=42,
                   is_correct=True, created_at=now),
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=42,
                   is_correct=True, created_at=now),  # retry: one task
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=43,
                   is_correct=False, created_at=now),
    ])
    db.session.commit()

    assert solved_counts_by_user()[test_user.id] == 3
    assert task_counts_by_user(checked=True)[test_user.id] == 5
    since = now - timedelta(days=1)
    assert task_counts_by_user(since=since)[test_user.id] == 2
    assert task_counts_by_user(checked=True, since=since)[test_user.id] == 4
    assert task_counts_by_user(checked=True)[test_user.id] >= solved_counts_by_user()[test_user.id]


def test_xp_level_is_not_a_stale_cached_column(app, test_user):
    test_user.experience_points = 155
    test_user.current_level = 1
    db.session.commit()
    assert db.session.get(User, test_user.id).xp_level == 2
    assert test_user.get_leaderboard_score() == 155


def test_regular_problem_is_persisted_and_credited_only_once(
        app, auth_client, test_user, monkeypatch):
    import app as main_app

    monkeypatch.setattr(main_app, "PROBLEMS_DB", [
        {"id": 987654, "answer": "42", "solution": "42",
         "difficulty": 1, "title": "Test"},
    ])
    app.add_url_rule("/api/check_answer", view_func=main_app.check_answer,
                     methods=["POST"])
    payload = {"problem_id": 987654, "user_answer": "41"}
    first = auth_client.post("/api/check_answer", json=payload)
    assert first.status_code == 200
    assert first.json["correct"] is False
    assert task_counts_by_user(checked=True)[test_user.id] == 1
    assert solved_counts_by_user().get(test_user.id, 0) == 0

    payload["user_answer"] = "42"
    accepted = auth_client.post("/api/check_answer", json=payload)
    assert accepted.status_code == 200
    assert accepted.json["xp_gained"] == 10
    points = db.session.get(User, test_user.id).experience_points
    assert points == 30  # 10 base + 20 first-difficulty bonus

    repeated = auth_client.post("/api/check_answer", json=payload)
    assert repeated.status_code == 200
    assert repeated.json["xp_gained"] == 0
    assert db.session.get(User, test_user.id).experience_points == points
    assert VerifiedProblemCheck.query.count() == 1
    assert VerifiedProblemCheck.query.first().attempts_count == 3
    assert solved_counts_by_user()[test_user.id] == 1
    assert task_counts_by_user(checked=True)[test_user.id] == 1


# ── USERS_STATS_FIX (21.10.2026): граница «сегодня» и стирание решений ─────

def test_msk_day_start_utc_boundary():
    """Полночь московского дня в UTC — всегда 21:00 UTC предыдущих суток."""
    from services.solved_stats import msk_day_start_utc

    # 03:30 МСК (00:30 UTC) 21-го → московская полночь 21-го = 21:00 UTC 20-го
    assert msk_day_start_utc(datetime(2026, 10, 21, 0, 30)) == datetime(2026, 10, 20, 21, 0)
    # 14:00 МСК (11:00 UTC) 21-го → та же граница
    assert msk_day_start_utc(datetime(2026, 10, 21, 11, 0)) == datetime(2026, 10, 20, 21, 0)
    # 02:59 МСК (23:59 UTC 20-го) — уже новый московский день (21-го)
    assert msk_day_start_utc(datetime(2026, 10, 20, 23, 59)) == datetime(2026, 10, 20, 21, 0)


def test_solved_today_counts_tasks_solved_after_msk_midnight(app, test_user):
    """Задача, решённая после 00:00 МСК, попадает в «решено сегодня».

    Раньше границей была полночь UTC: решение в 00:30 МСК (21:30 UTC
    прошлых суток) при «сейчас» = 03:30 МСК не попадало в «сегодня».
    """
    from services.solved_stats import msk_day_start_utc

    solved_at_msk_0030 = datetime(2026, 10, 20, 21, 30)   # = 00:30 МСК 21-го
    now_utc = datetime(2026, 10, 21, 0, 30)                # = 03:30 МСК 21-го
    task_set = DailyTaskSet(
        user_id=test_user.id, target_date=solved_at_msk_0030.date(), status="ready")
    db.session.add(task_set)
    db.session.flush()
    db.session.add(DailyTaskItem(
        daily_set_id=task_set.id, position=1, task_text="Late night",
        is_correct=True, answered_at=solved_at_msk_0030))
    db.session.commit()

    since_msk = msk_day_start_utc(now_utc)
    # Новая граница (21:00 UTC 20-го) включает ночное решение:
    assert since_msk == datetime(2026, 10, 20, 21, 0)
    assert task_counts_by_user(since=since_msk)[test_user.id] == 1
    # Старая UTC-граница это же решение теряла:
    since_utc_old = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    assert task_counts_by_user(since=since_utc_old).get(test_user.id, 0) == 0


def test_wrong_repeat_does_not_erase_solved_insight_task(app, auth_client, test_user):
    """Повторный неверный ответ не стирает уже решённую задачу отработки.

    Раньше is_correct перезаписывался: решённая вчера задача исчезала из
    «решено всего», а её повторное верное решение не попадало в «сегодня»
    (solved_at оставался от первого раза). Счётчик и XP при этом уже были
    начислены — числа в статистике расходились с фактическими.
    """
    from models_insights import Insight, InsightPracticeTask

    insight = Insight(
        user_id=test_user.id, title="t", title_normalized="t", type="regular")
    db.session.add(insight)
    db.session.flush()
    task = InsightPracticeTask(
        insight_id=insight.id, position=1, statement="2+2?", answer="4")
    db.session.add(task)
    db.session.commit()
    url = f"/api/insights/{insight.id}/practice/{task.id}/answer"

    # 1) Верный ответ — задача решена.
    ok = auth_client.post(url, json={"answer": "4"})
    assert ok.status_code == 200 and ok.json["correct"] is True
    assert solved_counts_by_user()[test_user.id] == 1
    assert task_counts_by_user(since=datetime.utcnow() - timedelta(hours=1))[test_user.id] == 1

    # 2) Повторный НЕверный ответ — решение остаётся (оно не стирается).
    wrong = auth_client.post(url, json={"answer": "5"})
    assert wrong.status_code == 200 and wrong.json["correct"] is False
    db.session.refresh(task)
    assert task.is_correct is True
    assert solved_counts_by_user()[test_user.id] == 1

    # 3) XP и счётчик пользователя не задваиваются при повторной верной отправке.
    xp_before = db.session.get(User, test_user.id).experience_points
    solved_before = db.session.get(User, test_user.id).total_problems_solved
    again = auth_client.post(url, json={"answer": "4"})
    assert again.status_code == 200
    assert db.session.get(User, test_user.id).experience_points == xp_before
    assert db.session.get(User, test_user.id).total_problems_solved == solved_before
    assert solved_counts_by_user()[test_user.id] == 1


def test_corrupted_insight_rows_restored_via_solved_at(app, auth_client, test_user):
    """Строки, испорченные старым обработчиком, снова считаются решёнными.

    Старый код при повторном неверном ответе стирал is_correct у уже решённой
    задачи — она исчезала из «решено за всё время». Признак первого решения
    (solved_at) при этом сохранялся: по нему счётчики восстанавливаются без
    миграции данных. Повторный верный ответ не начисляет XP/счётчик повторно.
    """
    from models_insights import Insight, InsightPracticeTask

    first_solve_at = datetime.utcnow() - timedelta(days=2)
    insight = Insight(
        user_id=test_user.id, title="c", title_normalized="c", type="regular")
    db.session.add(insight)
    db.session.flush()
    task = InsightPracticeTask(
        insight_id=insight.id, position=1, statement="3+3?", answer="6",
        # Испорченная строка: is_correct стёрт неверным повтором,
        # но solved_at (факт первого решения) сохранён.
        is_correct=False, solved_at=first_solve_at)
    db.session.add(task)
    db.session.commit()

    # «Решено за всё время» восстанавливается из сохранённого solved_at…
    assert solved_counts_by_user()[test_user.id] == 1
    # …но «сегодня» её не содержит: первое решение было два дня назад.
    assert task_counts_by_user(
        since=datetime.utcnow() - timedelta(hours=1)).get(test_user.id, 0) == 0

    # Повторный верный ответ: решение остаётся, дата не переезжает,
    # XP и счётчик пользователя не начисляются второй раз.
    xp_before = db.session.get(User, test_user.id).experience_points
    solved_before = db.session.get(User, test_user.id).total_problems_solved
    resp = auth_client.post(
        f"/api/insights/{insight.id}/practice/{task.id}/answer",
        json={"answer": "6"})
    assert resp.status_code == 200 and resp.json["correct"] is True
    db.session.refresh(task)
    assert task.is_correct is True
    assert task.solved_at == first_solve_at
    assert db.session.get(User, test_user.id).experience_points == xp_before
    assert db.session.get(User, test_user.id).total_problems_solved == solved_before
    assert solved_counts_by_user()[test_user.id] == 1
