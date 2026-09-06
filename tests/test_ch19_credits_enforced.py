# -*- coding: utf-8 -*-
"""CH19.1: восстановленное списание figure_credits (тесты).

Проверяет FIGURE_CREDITS_ENFORCED:
  * true  — done списывает 1 кредит, credit_charged=True;
  * true  — failed возвращает ровно один раз;
  * false — баланс не меняется, credit_charged=False;
  * двойной вызов _charge_credit не списывает дважды.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def user_with_credits(app, test_user):
    from models import db
    test_user.figure_credits = 10
    test_user.figures_built = 0
    db.session.commit()
    return test_user


def _make_job(app, test_user):
    from models import db, FigureBuildJob
    job = FigureBuildJob(
        user_id=test_user.id,
        problem_text="Тест",
        solution_text=None,
        generation_mode="condition_solution",
        status="queued",
    )
    db.session.add(job)
    db.session.commit()
    return job


class TestCreditEnforced:
    def test_done_charges_once(self, app, user_with_credits, monkeypatch):
        from models import db, User
        import routes.figures_generator as fg
        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)

        job = _make_job(app, user_with_credits)
        ok, msg = fg._charge_credit(job.id)
        assert ok is True, msg

        job = db.session.get(type(job), job.id)
        assert job.credit_charged is True
        user = db.session.get(User, user_with_credits.id)
        assert user.figure_credits == 9

    def test_double_charge_is_noop(self, app, user_with_credits, monkeypatch):
        from models import db, User
        import routes.figures_generator as fg
        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)

        job = _make_job(app, user_with_credits)
        ok1, _ = fg._charge_credit(job.id)
        ok2, msg2 = fg._charge_credit(job.id)  # повторный вызов
        assert ok1 is True
        assert ok2 is True  # "already charged" — не ошибка, но и не списание
        assert "already charged" in msg2

        user = db.session.get(User, user_with_credits.id)
        assert user.figure_credits == 9  # всё ещё 9, а не 8

    def test_failed_refunds_once(self, app, user_with_credits, monkeypatch):
        from models import db, User
        import routes.figures_generator as fg
        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)

        job = _make_job(app, user_with_credits)
        fg._charge_credit(job.id)
        assert db.session.get(type(job), job.id).credit_charged is True

        fg._refund_credit(job.id)
        fg._refund_credit(job.id)  # повторный refund — no-op

        job = db.session.get(type(job), job.id)
        assert job.credit_charged is False
        user = db.session.get(User, user_with_credits.id)
        assert user.figure_credits == 10  # вернули ровно 1, не 2

    def test_bypass_no_charge(self, app, user_with_credits, monkeypatch):
        from models import db, User
        import routes.figures_generator as fg
        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", False)

        job = _make_job(app, user_with_credits)
        ok, msg = fg._charge_credit(job.id)
        assert ok is True
        assert "bypass" in msg

        job = db.session.get(type(job), job.id)
        assert job.credit_charged is False
        user = db.session.get(User, user_with_credits.id)
        assert user.figure_credits == 10
