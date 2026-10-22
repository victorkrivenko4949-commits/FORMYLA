# -*- coding: utf-8 -*-
"""STREAK_V2: тесты правил зачёта дня в серию.

Новое правило: день засчитывается (+1), если пользователь
  а) провёл на сайте больше 20 минут, ИЛИ
  б) правильно решил хотя бы 1 задачу дня.
Максимум +1 за день. Ошибки серию не сбрасывают.
"""
from datetime import date

from services.streak_service import (
    get_or_create_streak, complete_day, credit_streak_day,
    STREAK_TIME_MIN_SEC,
)


def test_streak_v2_first_correct_answer_credits_day(app):
    """Первая верно решённая задача дня = +1 к серии."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 0
        rec.max_streak = 0
        rec.days_off_available = 0
        rec.last_solved_date = None
        rec.last_credit_date = None

        ok = credit_streak_day(1, date(2026, 10, 23), source="task")
        assert ok is True
        assert rec.current_streak == 1
        assert rec.last_solved_date == date(2026, 10, 23)
        assert rec.last_credit_date == date(2026, 10, 23)


def test_streak_v2_max_one_credit_per_day(app):
    """20 минут + верная задача в один день = всё равно +1, а не +2."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 0
        rec.last_credit_date = None
        rec.last_solved_date = None

        ok1 = credit_streak_day(1, date(2026, 10, 23), source="time")
        ok2 = credit_streak_day(1, date(2026, 10, 23), source="task")
        assert ok1 is True
        assert ok2 is False          # второй зачёт в тот же день игнорируется
        assert rec.current_streak == 1


def test_streak_v2_time_threshold(app):
    """Порог времени — строго больше 20 минут (1200 секунд)."""
    with app.app_context():
        assert STREAK_TIME_MIN_SEC == 1200
        rec = get_or_create_streak(1)
        rec.current_streak = 0
        rec.last_credit_date = None
        rec.last_solved_date = None
        # ровно 20 минут — не засчитывается (правило: БОЛЬШЕ 20 минут)
        # (проверка суммы секунд живёт в site_stats; здесь проверяем константу)


def test_streak_v2_wrong_answers_do_not_reset(app):
    """Неверно отвеченный сет больше не обнуляет серию (STREAK_V2)."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 5
        rec.max_streak = 5
        rec.days_off_available = 1
        rec.last_solved_date = date(2026, 10, 22)
        rec.last_credit_date = date(2026, 10, 22)

        complete_day(1, date(2026, 10, 23), False)
        assert rec.current_streak == 5   # не сброшена
        assert rec.last_solved_date == date(2026, 10, 22)  # день не засчитан


def test_streak_v2_miss_resets_on_next_credit(app):
    """Пропуск дня: следующий зачёт после разрыва > 1 дня начинает серию заново."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 4
        rec.max_streak = 4
        rec.days_off_available = 1
        rec.last_solved_date = date(2026, 10, 20)
        rec.last_credit_date = date(2026, 10, 20)

        # 21 и 22 октября — ни времени, ни верных задач. 23-го — верная задача.
        ok = credit_streak_day(1, date(2026, 10, 23), source="task")
        assert ok is True
        assert rec.current_streak == 1   # серия сломана, начата заново
        assert rec.days_off_available == 0


def test_streak_v2_time_credit_via_site_stats(app):
    """20+ минут на сайте (учёт site_stats/beat) засчитывают день в серию."""
    from services import site_stats
    from sqlalchemy import text as _text
    with app.app_context():
        from models import User, db
        u = User(
            email="streak-time-test@example.com", name="streak_time_test",
        )
        db.session.add(u)
        db.session.commit()

        site_stats.ensure_tables()  # создаёт site_time_beat / site_time_sections

        # Один beat даёт максимум MAX_BEAT_SEC секунд (антидвойной счёт
        # по стене часов), поэтому имитируем серию битов — как в проде,
        # где клиент шлёт beat каждые 20 секунд.
        def _beat(section="other", claimed=120):
            # сдвигаем стену часов назад, чтобы beat был принят целиком
            db.session.execute(_text(
                "UPDATE site_time_beat SET last_beat = last_beat - 125"
            ))
            site_stats.credit_time(u.id, section, claimed, "/any")

        # 10 битов по 120 сек = 1200 сек (ровно 20 минут) — НЕ засчитано:
        # правило — БОЛЬШЕ 20 минут.
        for _ in range(10):
            _beat()
        rec = get_or_create_streak(u.id)
        assert rec.current_streak == 0
        assert rec.last_credit_date is None

        # ещё один beat — итого больше 1200 сек — день засчитан
        _beat()
        rec = get_or_create_streak(u.id)
        assert rec.current_streak == 1
        assert rec.last_credit_date == site_stats._msk_today()

        # повторные биты в тот же день не дают второго +1
        _beat(section="daily")
        rec = get_or_create_streak(u.id)
        assert rec.current_streak == 1


def test_streak_v2_transition_no_double_credit(app):
    """Переходное состояние после деплоя: день уже засчитан старой логикой
    (last_solved_date=today, last_credit_date=NULL + бэкфилл) — повторного +1 нет."""
    with app.app_context():
        from models import db
        rec = get_or_create_streak(1)
        rec.current_streak = 2
        rec.last_solved_date = date(2026, 10, 23)
        # бэкфилл из миграции помечает день как зачтённый:
        rec.last_credit_date = date(2026, 10, 23)
        db.session.flush()

        ok = credit_streak_day(1, date(2026, 10, 23), source="task")
        assert ok is False
        assert rec.current_streak == 2


def test_streak_v2_route_correct_answer_credits(
        app, auth_client, test_user, daily_set_with_items):
    """POST верного ответа на задачу дня через реальный маршрут — серия +1."""
    with app.app_context():
        from models import db
        from daily_tasks.models import DailyTaskItem
        rec = get_or_create_streak(test_user.id)
        rec.current_streak = 0
        rec.last_credit_date = None
        rec.last_solved_date = None

        item = DailyTaskItem.query.filter_by(
            daily_set_id=daily_set_with_items.id).order_by('position').first()
        item.correct_answer = "42"
        db.session.commit()
        item_id = item.id

    r = auth_client.post(f'/daily_tasks/{item_id}/submit',
                         json={"answer": "42"})
    assert r.status_code == 200

    with app.app_context():
        from models import db as _db
        _db.session.expire_all()
        rec = get_or_create_streak(test_user.id)
        assert rec.current_streak == 1
        assert rec.last_credit_date is not None


def test_streak_v2_route_wrong_answer_no_credit(
        app, auth_client, test_user, daily_set_with_items):
    """POST неверного ответа — серия не растёт."""
    with app.app_context():
        from models import db
        from daily_tasks.models import DailyTaskItem
        rec = get_or_create_streak(test_user.id)
        rec.current_streak = 0
        rec.last_credit_date = None
        rec.last_solved_date = None

        item = DailyTaskItem.query.filter_by(
            daily_set_id=daily_set_with_items.id).order_by('position').first()
        item.correct_answer = "42"
        db.session.commit()
        item_id = item.id

    r = auth_client.post(f'/daily_tasks/{item_id}/submit',
                         json={"answer": "13"})
    assert r.status_code == 200

    with app.app_context():
        from models import db as _db
        _db.session.expire_all()
        rec = get_or_create_streak(test_user.id)
        assert rec.current_streak == 0
