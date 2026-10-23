# -*- coding: utf-8 -*-
"""Tests for DQ_ATTEMPTS_V1 + DQ_REGEN_COOLDOWN_V1.

Covers:
  • register_wrong_attempt — счётчик, блокировка после MAX_ATTEMPTS_PER_TASK.
  • is_task_locked, get_failed_indices, get_attempt_count helpers.
  • regenerate_cooldown_remaining — 1-час cooldown.
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

# Allow `import app` / `import services` from project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def quest_app_ctx():
    """Тестовый контекст приложения на временной БД из conftest.py.

    Важно: НЕ переключает глобальный app/db на :memory: и НЕ вызывает drop_all().
    Очистка: удаление созданных записей.
    """
    from app import app, db  # noqa: WPS433
    from models import DailyQuest, User  # noqa: WPS433

    with app.app_context():
        # Минимальный пользователь
        user = User(email="dq_test@formyla.test", name="DQ Test", preferred_grade=7)
        db.session.add(user)
        db.session.commit()

        # Минимальный квест с 3 фейковыми задачами
        quest = DailyQuest(
            user_id=user.id,
            date=datetime.utcnow().date(),
            task_ids=json.dumps([1001, 1002, 1003]),
            total_count=3,
        )
        db.session.add(quest)
        db.session.commit()

        yield {"app": app, "db": db, "quest": quest, "user": user}

        # Очистка: удаляем созданные записи, не дропаем таблицы
        DailyQuest.query.filter_by(id=quest.id).delete()
        User.query.filter_by(id=user.id).delete()
        db.session.commit()


def test_initial_state_empty(quest_app_ctx):
    """Свежесозданный квест: нет ни попыток, ни заблокированных задач."""
    from services.daily_quest_service import (
        get_attempts_map, get_failed_indices, is_task_locked, get_attempt_count,
    )
    q = quest_app_ctx["quest"]
    assert get_attempts_map(q) == {}
    assert get_failed_indices(q) == []
    assert is_task_locked(q, 0) is False
    assert get_attempt_count(q, 0) == 0


def test_first_wrong_attempt_does_not_lock(quest_app_ctx):
    """Первая неправильная попытка увеличивает счётчик, но не блокирует."""
    from services.daily_quest_service import register_wrong_attempt, is_task_locked

    q = quest_app_ctx["quest"]
    info = register_wrong_attempt(q, task_index=0)

    assert info["attempts_used"] == 1
    assert info["attempts_left"] == 1
    assert info["is_locked"] is False
    assert is_task_locked(q, 0) is False


def test_second_wrong_attempt_locks_task(quest_app_ctx):
    """Вторая неправильная попытка блокирует задачу и переносит её в failed_indices."""
    from services.daily_quest_service import (
        register_wrong_attempt, is_task_locked, get_failed_indices,
    )
    q = quest_app_ctx["quest"]

    register_wrong_attempt(q, task_index=2)
    info = register_wrong_attempt(q, task_index=2)

    assert info["attempts_used"] == 2
    assert info["attempts_left"] == 0
    assert info["is_locked"] is True
    assert is_task_locked(q, 2) is True
    assert 2 in get_failed_indices(q)


def test_other_tasks_unaffected_when_one_locked(quest_app_ctx):
    """Блокировка одной задачи не влияет на остальные."""
    from services.daily_quest_service import register_wrong_attempt, is_task_locked

    q = quest_app_ctx["quest"]
    register_wrong_attempt(q, task_index=0)
    register_wrong_attempt(q, task_index=0)

    assert is_task_locked(q, 0) is True
    assert is_task_locked(q, 1) is False
    assert is_task_locked(q, 2) is False


def test_cooldown_zero_for_fresh_quest(quest_app_ctx):
    """Свежий квест без last_regenerated_at -> cooldown = 0 (можно перегенерить)."""
    from services.daily_quest_service import regenerate_cooldown_remaining
    q = quest_app_ctx["quest"]
    assert q.last_regenerated_at is None
    assert regenerate_cooldown_remaining(q, cooldown_seconds=3600) == 0


def test_cooldown_active_just_regenerated(quest_app_ctx):
    """Только что перегенерили -> cooldown ≈ 3600 секунд."""
    from services.daily_quest_service import regenerate_cooldown_remaining
    q = quest_app_ctx["quest"]
    q.last_regenerated_at = datetime.utcnow()
    remaining = regenerate_cooldown_remaining(q, cooldown_seconds=3600)
    # Допускаем 5-секундный дрейф (на тесты CI)
    assert 3550 <= remaining <= 3600


def test_cooldown_expired_after_1h(quest_app_ctx):
    """Если перегенерили час назад — cooldown истёк."""
    from services.daily_quest_service import regenerate_cooldown_remaining
    q = quest_app_ctx["quest"]
    q.last_regenerated_at = datetime.utcnow() - timedelta(hours=1, seconds=10)
    assert regenerate_cooldown_remaining(q, cooldown_seconds=3600) == 0


def test_cooldown_mid_window(quest_app_ctx):
    """Перегенерили 30 мин назад -> осталось ≈ 30 мин."""
    from services.daily_quest_service import regenerate_cooldown_remaining
    q = quest_app_ctx["quest"]
    q.last_regenerated_at = datetime.utcnow() - timedelta(minutes=30)
    remaining = regenerate_cooldown_remaining(q, cooldown_seconds=3600)
    # ~1800 сек, допускаем дрейф
    assert 1750 <= remaining <= 1810


def test_max_attempts_constant(quest_app_ctx):
    """MAX_ATTEMPTS_PER_TASK = 2 (по требованию: 1-я попытка + 1 шанс)."""
    from services.daily_quest_service import MAX_ATTEMPTS_PER_TASK
    assert MAX_ATTEMPTS_PER_TASK == 2


def test_attempts_persist_across_helper_calls(quest_app_ctx):
    """get_attempt_count корректно отражает накопленные попытки между вызовами."""
    from services.daily_quest_service import (
        register_wrong_attempt, get_attempt_count,
    )
    q = quest_app_ctx["quest"]
    assert get_attempt_count(q, 1) == 0
    register_wrong_attempt(q, 1)
    assert get_attempt_count(q, 1) == 1
    register_wrong_attempt(q, 1)
    assert get_attempt_count(q, 1) == 2
