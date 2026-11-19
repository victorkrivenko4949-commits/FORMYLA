# -*- coding: utf-8 -*-
"""Пробный день / Premium: досдача задач в сет, выданный по капу Free.

Прод-инцидент 2026-11-19: ученик активировал пробный день Premium, прошёл
тест по теме дня, но в «Задачах дня» осталась 1 задача. Сет был выдан по
капу Free (1 задача) ДО активации триала, а сеты с ответами никогда не
пересоздаются — ученик весь премиум-день видел «ВЫПОЛНЕНО 1/1».

top_up_undersized_set_for_paid: при платном доступе сет досдается до нормы,
существующие задачи и ответы не трогаются.
"""
import json
from datetime import datetime, timedelta

from daily_tasks.services import (
    top_up_undersized_set_for_paid,
    today_in_user_tz,
)
from daily_tasks.models import DailyTaskSet, DailyTaskItem


def _ensure_tables():
    from models import db
    from sqlalchemy import text
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    db.session.execute(text(f"""CREATE TABLE IF NOT EXISTS subscriptions (
        id {serial}, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
        payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
        is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    db.session.commit()


def _grant_trial(user):
    """Пробный день: premium-подписка на 24 часа с is_trial=1
    (как /api/subscribe/trial в app.py)."""
    from models import db
    from sqlalchemy import text
    _ensure_tables()
    now = datetime.utcnow()
    db.session.execute(text(
        "INSERT INTO subscriptions "
        "(user_id, plan, status, started_at, expires_at, is_trial, is_beta_access, created_at) "
        "VALUES (:u, 'premium_intense', 'active', :s, :e, 1, 1, :s)"),
        {'u': user.id, 's': now, 'e': now + timedelta(hours=24)})
    db.session.commit()


def _mk_set(user, n=1):
    """Сет «Задач дня», выданный по капу Free (n=1 задача), с ответом."""
    from models import db
    today = today_in_user_tz()
    s = DailyTaskSet(user_id=user.id, target_date=today, status='ready',
                     triggered_by='formyla_bank',
                     generated_at=datetime.utcnow(), class_level=9)
    db.session.add(s)
    db.session.flush()
    for pos in range(1, n + 1):
        db.session.add(DailyTaskItem(
            daily_set_id=s.id, position=pos, slot_kind='formyla_bank',
            subject='math', topic='G9_T03', difficulty_level=1,
            task_text=f'старая задача {pos}', correct_answer='1',
            solution='', hints='[]',
            gemini_spec_json=json.dumps(
                {'source': 'formyla_bank', 'grade': 9,
                 'topic': 'G9_T03', 'level': 1}),
            status='approved'))
    db.session.commit()
    return s


def _fake_bank(monkeypatch):
    """Банк задач: отдаёт сколько просим, с неповторяющимися текстами."""
    import daily_tasks.formyla_bank as fb

    def _get(grade, topic, level, count=5, user_id=None, **kw):
        return [{'task_text': f'новая задача {topic} L{level} #{i}',
                 'correct_answer': '2', 'solution': '', 'level': level,
                 'topic': topic}
                for i in range(count)]

    monkeypatch.setattr(fb, 'get_tasks', _get)


def test_topup_after_trial_extends_set(app, test_user, monkeypatch):
    """Триал активирован ПОСЛЕ выдачи урезанного сета: при заходе в
    «Задачи дня» сет досдается до нормы, ответ не теряется."""
    _grant_trial(test_user)
    _fake_bank(monkeypatch)

    s = _mk_set(test_user, n=1)
    # ученик уже ответил на единственную задачу (1/1)
    from models import db
    item = DailyTaskItem.query.filter_by(daily_set_id=s.id).first()
    item.user_answer = '42'
    db.session.commit()

    # у платного доступа лимиты Free не активны
    from services import limits as limits_svc
    assert not limits_svc.limits_active(test_user)

    added = top_up_undersized_set_for_paid(test_user)
    assert added >= 1, 'после триала сет должен дособраться до нормы'

    items = (DailyTaskItem.query
             .filter_by(daily_set_id=s.id)
             .order_by(DailyTaskItem.position).all())
    assert len(items) > 1
    # старая задача и ответ ученика не тронуты
    assert items[0].task_text == 'старая задача 1'
    assert items[0].user_answer == '42'
    # новые задачи продолжают позиции, а не затирают существующие
    assert [it.position for it in items] == list(range(1, len(items) + 1))
    # новые задачи не дублируют старые (anti-repeat)
    texts = [it.task_text for it in items]
    assert len(set(texts)) == len(texts)


def test_topup_skipped_for_free_user(app, test_user, monkeypatch):
    """Бесплатнику с активными лимитами Free досдача не положена:
    его норма — 1 задача в день."""
    _fake_bank(monkeypatch)
    s = _mk_set(test_user, n=1)

    # включаем лимиты Free (PAYWALL experiment) для free-аккаунта
    monkeypatch.setenv('PAYWALL_MODE', 'experiment')
    monkeypatch.setenv('PAYWALL_START_AT', '2026-10-01T00:00:00Z')
    monkeypatch.setenv('PAYWALL_EXPERIMENT_ID', 'limits_v1')
    monkeypatch.setenv('PAYWALL_AB', '50')
    monkeypatch.setenv('FREE_TASKS_PER_DAY', '1')
    monkeypatch.setenv('FREE_LIMITS_DISABLED', '0')
    import services.ab as ab_mod
    monkeypatch.setattr(ab_mod, 'cohort_for', lambda e, uid, percent=None: 'limits')

    from services import limits as limits_svc
    assert limits_svc.limits_active(test_user)

    added = top_up_undersized_set_for_paid(test_user)
    assert added == 0
    assert DailyTaskItem.query.filter_by(daily_set_id=s.id).count() == 1


def test_topup_noop_when_set_is_full(app, test_user, monkeypatch):
    """Полный сет не трогаем."""
    _grant_trial(test_user)
    _fake_bank(monkeypatch)
    s = _mk_set(test_user, n=10)

    added = top_up_undersized_set_for_paid(test_user)
    assert added == 0
    assert DailyTaskItem.query.filter_by(daily_set_id=s.id).count() == 10
