# -*- coding: utf-8 -*-
"""
T-WEEKLY: недельная оценка куратора (services/curator_chat.py, 26.10.2026).

Проверяем:
  * оценка отправляется один раз на каждую неделю подписки (week=1, 2, ...);
  * окно статистики — именно та неделя (build_context(since, until));
  * при сбое DeepSeek — шаблонный фолбэк, пользователь не встречает тишину;
  * обычная переписка использует последние 7 дней (не первую неделю).
"""
import json
from datetime import datetime, timedelta

import pytest

import services.pilot as pilot_mod
from models import db, User, Subscription, CuratorChatMessage
import services.curator_chat as curator_chat


@pytest.fixture
def sub_user(app, monkeypatch):
    """Пилотный пользователь с пилотной подпиской (старт — days назад)."""
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: True)
    monkeypatch.setattr(pilot_mod, 'is_pilot_id', lambda uid=None, **k: True)
    u = User(email='weekly@test.ru', nickname='weekly')
    db.session.add(u)
    db.session.commit()
    return u


def _add_sub(uid, started):
    db.session.add(Subscription(
        user_id=uid, plan='premium_intense', status='active',
        is_beta_access=True, started_at=started,
        expires_at=started + timedelta(days=30)))
    db.session.commit()


def _system_msgs(uid):
    return CuratorChatMessage.query.filter_by(user_id=uid, role='system').all()


def test_weekly_message_once_per_week(sub_user, monkeypatch):
    """Неделя 1: одна оценка; повторный вызов — нет; неделя 2 — новая оценка."""
    uid = sub_user.id
    started = datetime.utcnow() - timedelta(days=8)  # 8 дней = завершена неделя 1
    _add_sub(uid, started)
    monkeypatch.setattr(curator_chat, '_call_deepseek',
                        lambda msgs, thinking=False: 'Оценка недели: отличное начало!')

    assert curator_chat.send_weekly_message(uid) is True
    msgs = _system_msgs(uid)
    assert len(msgs) == 1
    meta = json.loads(msgs[0].meta_json or '{}')
    assert meta.get('kind') == 'weekly'
    assert meta.get('week') == 1

    # идемпотентно: повторный вызов в ту же неделю ничего не шлёт
    assert curator_chat.send_weekly_message(uid) is False
    assert len(_system_msgs(uid)) == 1

    # через 7 дней (завершена неделя 2) — новая оценка
    db.session.execute(db.text(
        "UPDATE subscriptions SET started_at = :s WHERE user_id = :u"),
        {'s': datetime.utcnow() - timedelta(days=15), 'u': uid})
    db.session.commit()
    assert curator_chat.send_weekly_message(uid) is True
    msgs = _system_msgs(uid)
    assert len(msgs) == 2
    assert json.loads(msgs[-1].meta_json or '{}').get('week') == 2


def test_weekly_not_sent_during_first_week(sub_user, monkeypatch):
    """Пока первая неделя не завершилась — оценки нет (оценивать нечего)."""
    uid = sub_user.id
    _add_sub(uid, datetime.utcnow() - timedelta(days=3))
    monkeypatch.setattr(curator_chat, '_call_deepseek',
                        lambda msgs, thinking=False: 'не должно отправиться')
    assert curator_chat.send_weekly_message(uid) is False
    assert len(_system_msgs(uid)) == 0


def test_weekly_fallback_when_llm_fails(sub_user, monkeypatch):
    """DeepSeek упал — куратор всё равно говорит (шаблон по активности)."""
    uid = sub_user.id
    _add_sub(uid, datetime.utcnow() - timedelta(days=9))

    def _boom(msgs, thinking=False):
        raise RuntimeError('llm down')
    monkeypatch.setattr(curator_chat, '_call_deepseek', _boom)

    assert curator_chat.send_weekly_message(uid) is True
    msgs = _system_msgs(uid)
    assert len(msgs) == 1
    assert msgs[0].content.strip()  # непустое сообщение-фолбэк


def test_build_context_window_counts_only_that_week(sub_user):
    """Задачи считаются только внутри переданного окна недели."""
    uid = sub_user.id
    started = datetime.utcnow() - timedelta(days=8)
    _add_sub(uid, started)

    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    s = DailyTaskSet(user_id=uid, target_date=started.date(), status='ready')
    db.session.add(s)
    db.session.commit()
    # задача в первой неделе (в окне) и задача до подписки (вне окна)
    db.session.add(DailyTaskItem(
        daily_set_id=s.id, position=1, task_text='В окне',
        user_answer='1', answered_at=started + timedelta(days=1)))
    db.session.add(DailyTaskItem(
        daily_set_id=s.id, position=2, task_text='Вне окна',
        user_answer='2', answered_at=started - timedelta(days=5)))
    db.session.commit()

    ctx = curator_chat.build_context(
        uid, since=started, until=started + timedelta(days=7))
    assert ctx['attempted_7d'] == 1  # только задача из недели подписки


def test_build_context_default_recent_window(sub_user):
    """Без аргументов — окно последних 7 дней (не первая неделя подписки)."""
    uid = sub_user.id
    started = datetime.utcnow() - timedelta(days=30)
    _add_sub(uid, started)

    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    s = DailyTaskSet(user_id=uid, target_date=datetime.utcnow().date(),
                     status='ready')
    db.session.add(s)
    db.session.commit()
    db.session.add(DailyTaskItem(
        daily_set_id=s.id, position=1, task_text='Свежая',
        user_answer='1', answered_at=datetime.utcnow() - timedelta(days=1)))
    db.session.commit()

    ctx = curator_chat.build_context(uid)
    assert ctx['week_number'] == 5
    assert ctx['attempted_7d'] == 1  # свежая задача видна в дефолтном окне


def test_weekly_uses_reasoning_chat_does_not(sub_user, monkeypatch):
    """Анализ недели — С рассуждением (thinking=True); ответ в чате — БЕЗ."""
    uid = sub_user.id
    started = datetime.utcnow() - timedelta(days=8)
    _add_sub(uid, started)

    thinking_flags = []

    def _spy(msgs, thinking=False, max_tokens=1200, **kwargs):
        thinking_flags.append(thinking)
        return 'Ок.'

    monkeypatch.setattr(curator_chat, '_call_deepseek', _spy)

    # недельный анализ — с рассуждением
    assert curator_chat.send_weekly_message(uid) is True
    assert thinking_flags[-1] is True

    # обычный ответ куратора в чате — без рассуждения
    reply = curator_chat.generate_reply(uid, 'как дела?')
    assert reply['fallback'] is False
    assert thinking_flags[-1] is False


def test_weekly_not_sent_for_non_pilot(app, monkeypatch):
    """НЕ-пилоту недельная оценка не отправляется (только victor + lavrik)."""
    u = User(id=42, email='regular@test.ru', nickname='regular')  # id вне PILOT_USER_IDS
    db.session.add(u)
    db.session.commit()
    uid = u.id
    # is_pilot_id остаётся реальным: id не входит в PILOT_USER_IDS (1, 5)
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda usr=None, **k: False)
    _add_sub(uid, datetime.utcnow() - timedelta(days=8))

    monkeypatch.setattr(curator_chat, '_call_deepseek',
                        lambda msgs, thinking=False, max_tokens=1200, **kw:
                        'не должно отправиться')
    assert curator_chat.send_weekly_message(uid) is False
    assert len(_system_msgs(uid)) == 0
