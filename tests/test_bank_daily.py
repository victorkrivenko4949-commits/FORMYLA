# -*- coding: utf-8 -*-
"""
tests/test_bank_daily.py — приёмка части 2: выдача задач дня из банка.

Все задачи создаются в тесте с меткой [TEST] в условии. Наполнение банка
человеком здесь не имитируется за пределами тестовых фикстур.
"""

from datetime import date, timedelta

from models import db, User, DailyTaskBank, BankIssue
from models import UserSubtopicAssignment
from models_curator import CuratorState
from services import bank_daily


def _make_user(app, email, nickname):
    with app.app_context():
        u = User(email=email, nickname=nickname)
        u.current_month = 1
        u.role = "student"
        db.session.add(u)
        db.session.commit()
        return u.id


def _make_assignments(app, user_id, subtopics, month=1):
    """Создать UserSubtopicAssignment для user_id по порядку positions."""
    with app.app_context():
        for pos, sub in enumerate(subtopics, 1):
            db.session.add(UserSubtopicAssignment(
                user_id=user_id,
                subtopic=sub,
                month_number=month,
                position=pos,
            ))
        db.session.commit()


def _set_plan_anchor(app, user_id, anchor_date):
    """Задать валидный prep_plan с нужной anchor_date для недели."""
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is None:
            cs = CuratorState(user_id=user_id, grade=7)
            db.session.add(cs)
        cs.grade = 7
        cs.prep_plan = {
            "version": 1,
            "anchor_date": anchor_date.isoformat(),
            "subtopics_per_month": 7,
            "grade": 7,
            "months": [{"index": 1, "subtopics": [
                "s1", "s2", "s3", "s4", "s5", "s6", "s7",
            ]}],
        }
        db.session.commit()


def _make_bank_tasks(app, subtopic, level, count, section="algebra"):
    """Создать count задач в daily_task_bank, вернуть список id."""
    with app.app_context():
        ids = []
        for i in range(count):
            t = DailyTaskBank(
                subtopic=subtopic,
                section=section,
                level=level,
                statement=f"[TEST] Синтетическая задача банка {subtopic} L{level} #{i}.",
                answer=f"answer_{i}",
                solution=f"solution_{i}",
                source_model="deepseek",
                position=(i % 35) + 1,
            )
            db.session.add(t)
            db.session.flush()
            ids.append(t.id)
        db.session.commit()
        return ids


def test_empty_bank_returns_bank_empty(app):
    """На пустом банке build_daily_set даёт пустой набор и bank_empty=True."""
    uid = _make_user(app, "bank_empty@test.invalid", "bank_empty")
    _make_assignments(app, uid, ["s1", "s2", "s3", "s4", "s5", "s6", "s7"])

    with app.app_context():
        result = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        assert result["bank_empty"] is True
        assert result["items"] == []
        assert result["plan_missing"] is False


def test_week1_gives_exactly_5_tasks(app):
    """На фикстурах неделя 1 даёт ровно 5 задач."""
    uid = _make_user(app, "bank_w1@test.invalid", "bank_w1")
    subs = ["w1a", "w1b", "w1c", "w1d", "w1e", "w1f", "w1g"]
    _make_assignments(app, uid, subs)
    _make_bank_tasks(app, "w1a", 3, 5)

    with app.app_context():
        result = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        assert result["plan_missing"] is False
        assert len(result["items"]) == 5


def test_week2_gives_exactly_10_tasks(app):
    """На фикстурах неделя 2 даёт ровно 10 задач (две подтемы по 5)."""
    uid = _make_user(app, "bank_w2@test.invalid", "bank_w2")
    subs = ["w2a", "w2b", "w2c", "w2d", "w2e", "w2f", "w2g"]
    _make_assignments(app, uid, subs)
    anchor = date(2026, 8, 10) - timedelta(days=7)
    _set_plan_anchor(app, uid, anchor)
    _make_bank_tasks(app, "w2b", 3, 5)
    _make_bank_tasks(app, "w2c", 3, 5)

    with app.app_context():
        result = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        assert result["plan_missing"] is False
        assert len(result["items"]) == 10


def test_repeat_call_same_date_is_idempotent(app):
    """Повторный вызов на ту же дату даёт тот же набор и не добавляет строк."""
    uid = _make_user(app, "bank_idem@test.invalid", "bank_idem")
    subs = ["ia", "ib", "ic", "id", "ie", "if", "ig"]
    _make_assignments(app, uid, subs)
    _make_bank_tasks(app, "ia", 3, 7)

    with app.app_context():
        first = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        first_ids = [t.id for t in first["items"]]
        count_before = BankIssue.query.filter_by(user_id=uid).count()

        second = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        second_ids = [t.id for t in second["items"]]
        count_after = BankIssue.query.filter_by(user_id=uid).count()

        assert first_ids == second_ids
        assert count_before == count_after
        assert count_before == len(first_ids)


def test_two_users_different_order_same_pair(app):
    """Два ученика на одной паре подтема-уровень получают неполностью совпадающие наборы."""
    u1 = _make_user(app, "bank_u1@test.invalid", "bank_u1")
    u2 = _make_user(app, "bank_u2@test.invalid", "bank_u2")
    _make_bank_tasks(app, "pair_x", 3, 35)

    with app.app_context():
        ids1, _ = bank_daily.pick_tasks(u1, "pair_x", 3, 5)
        ids2, _ = bank_daily.pick_tasks(u2, "pair_x", 3, 5)
        list1 = [t.id for t in ids1]
        list2 = [t.id for t in ids2]
        print("USER1_IDS", list1)
        print("USER2_IDS", list2)
        assert len(list1) == 5
        assert len(list2) == 5
        assert set(list1) != set(list2)


def test_issued_task_not_returned_again(app):
    """Задача из bank_issues во второй набор не попадает; все выданы — exhausted."""
    uid = _make_user(app, "bank_seen@test.invalid", "bank_seen")
    ids = _make_bank_tasks(app, "seen_sub", 3, 6)

    with app.app_context():
        # Помечаем одну задачу как уже выданную.
        db.session.add(BankIssue(
            user_id=uid,
            task_id=ids[0],
            subtopic="seen_sub",
            level=3,
            issued_date=date(2026, 8, 1),
        ))
        db.session.commit()

        second, exhausted = bank_daily.pick_tasks(uid, "seen_sub", 3, 5)
        second_ids = [t.id for t in second]
        assert ids[0] not in second_ids
        assert len(second_ids) == 5
        assert exhausted is False

        # Помечаем остальные 5 как выданные — теперь видел все 6.
        for tid in ids[1:]:
            db.session.add(BankIssue(
                user_id=uid,
                task_id=tid,
                subtopic="seen_sub",
                level=3,
                issued_date=date(2026, 8, 1),
            ))
        db.session.commit()

        third, exhausted = bank_daily.pick_tasks(uid, "seen_sub", 3, 5)
        assert third == []
        assert exhausted is True


def test_empty_plan_gives_plan_missing(app):
    """Пустой план даёт пустой набор и plan_missing=True."""
    uid = _make_user(app, "bank_noplan@test.invalid", "bank_noplan")
    # Нет UserSubtopicAssignment -> план не задан.

    with app.app_context():
        result = bank_daily.build_daily_set(uid, date(2026, 8, 10))
        assert result["plan_missing"] is True
        assert result["items"] == []


def test_bank_stats_empty_bank_returns_zeros(app):
    """bank_stats() на пустом банке возвращает нули и не падает."""
    with app.app_context():
        stats = bank_daily.bank_stats()
        assert stats["total"] == 0
        assert stats["solution_nonempty"] == 0
        assert stats["svg_nonempty"] == 0
        assert stats["needs_figure"] == 0
        assert stats["pairs_filled"] == 0
