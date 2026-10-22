# -*- coding: utf-8 -*-
"""
services/streak_service.py — T8 daily quest streak and days-off logic.

One StreakRecord per user.  Updated on daily task set completion,
on-open checks, and explicit day-off requests.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError

from models import db, StreakRecord

logger = logging.getLogger(__name__)

STREAK_DAYS_FOR_DAY_OFF = 3  # every 3 days of streak grant 1 day-off

# STREAK_V2: день засчитывается в серию, если пользователь
#   а) провёл на сайте больше 20 минут (учёт через site_stats/beat), ИЛИ
#   б) правильно решил хотя бы одну задачу дня.
# Максимум +1 за день, независимо от того, сколько условий выполнено.
STREAK_TIME_MIN_SEC = 20 * 60

_credit_column_ready = False


def _ensure_credit_column() -> None:
    """Идемпотентно добавить колонку streak_records.last_credit_date.

    На проде таблица уже существует, поэтому db.create_all() колонку не
    добавит — делаем ALTER TABLE. ВАЖНО: ALTER выполняется в ОТДЕЛЬНОМ
    соединении (db.engine), чтобы не коммитить/откатывать текущую
    транзакцию пользователя, в которой могут быть несохранённые данные.

    Одноразовый бэкфилл: last_credit_date = last_solved_date — чтобы
    день, уже засчитанный старой логикой (полный сет на 100%), не был
    засчитан повторно после деплоя. Консервативно: день, покрытый
    выходным, тоже помечается как зачтённый (двойного +1 не будет).
    """
    global _credit_column_ready
    if _credit_column_ready:
        return
    column_confirmed = False
    try:
        with db.engine.connect() as conn:
            exists = conn.execute(db.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'streak_records' "
                "AND column_name = 'last_credit_date'"
            )).first()
            if exists is None:
                # Отдельная автокоммит-транзакция, вне сессии пользователя.
                conn.execute(db.text(
                    "ALTER TABLE streak_records "
                    "ADD COLUMN last_credit_date DATE"
                ))
                # Бэкфилл переходного состояния (см. докстринг).
                conn.execute(db.text(
                    "UPDATE streak_records "
                    "SET last_credit_date = last_solved_date "
                    "WHERE last_solved_date IS NOT NULL "
                    "AND last_credit_date IS NULL"
                ))
                conn.commit()
                logger.info("streak_records.last_credit_date added + backfilled")
            column_confirmed = True
    except Exception as e:
        # SQLite (нет information_schema) или колонка уже добавлена
        # конкурентным процессом — пробуем простой ALTER и считаем
        # «duplicate column» успехом.
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text(
                    "ALTER TABLE streak_records "
                    "ADD COLUMN last_credit_date DATE"
                ))
                conn.commit()
                logger.info("streak_records.last_credit_date added (sqlite)")
                column_confirmed = True
        except Exception as e2:
            if 'duplicate column' in str(e2).lower():
                column_confirmed = True  # колонка есть — гонка деплоя
            else:
                logger.warning("ensure_credit_column: %r / %r", e, e2)
    if column_confirmed:
        _credit_column_ready = True
    # Без подтверждения флаг НЕ ставим — следующий вызов повторит попытку.


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def get_or_create_streak(user_id: int, *, for_update: bool = False) -> StreakRecord:
    """Return the StreakRecord for *user_id*, creating one if missing.

    *for_update* — захватить строку блокировкой (SELECT ... FOR UPDATE),
    чтобы конкурентные зачёты дня (время + задача одновременно) не дали
    двойной +1. Для SQLite блокировка — no-op, но там один писатель.

    Создание записи при гонке защищено SAVEPOINT (begin_nested): при
    конфликте уникальности откатывается ТОЛЬКО savepoint, а не вся
    транзакция вызывающего кода (например, уже начисленные секунды
    в heartbeat не теряются).
    """
    _ensure_credit_column()
    q = StreakRecord.query.filter_by(user_id=user_id)
    if for_update:
        q = q.with_for_update()
    rec = q.first()
    if rec is None:
        try:
            with db.session.begin_nested():
                rec = StreakRecord(user_id=user_id)
                db.session.add(rec)
                db.session.flush()
        except IntegrityError:
            # Гонка создания записи двумя запросами — берём существующую.
            # ORM-кэш мог держать «проигравший» объект — перечитываем.
            db.session.expire_all()
            rec = q.first()
            if rec is None:
                raise
    return rec


def credit_streak_day(user_id: int, today: date, source: str = "task") -> bool:
    """STREAK_V2: засчитать день в серию (идемпотентно, максимум +1 за день).

    Вызывается когда выполнено ЛЮБОЕ из условий:
      * ``source='time'``  — пользователь провёл на сайте > 20 минут;
      * ``source='task'``  — правильно решена хотя бы одна задача дня.

    Если день уже засчитан (last_credit_date == today) — ничего не делает.
    Возвращает True, если серия увеличилась именно этим вызовом.

    Атомарность: строка захватывается блокировкой SELECT ... FOR UPDATE,
    поэтому одновременные зачёты «за время» и «за задачу» не дадут +2.
    """
    rec = get_or_create_streak(user_id, for_update=True)

    if rec.last_credit_date == today:
        return False  # за день уже был +1

    # Пропуск > 1 дня без выходного — серия сломана, начинаем с 1.
    if rec.last_solved_date is not None:
        gap = (today - rec.last_solved_date).days
        if gap > 1:
            rec.current_streak = 0
            rec.days_off_available = 0

    rec.current_streak = (rec.current_streak or 0) + 1
    rec.max_streak = max(rec.max_streak or 0, rec.current_streak)
    if rec.current_streak % STREAK_DAYS_FOR_DAY_OFF == 0:
        rec.days_off_available = (rec.days_off_available or 0) + 1

    rec.last_solved_date = today
    rec.last_credit_date = today
    db.session.flush()
    logger.info(
        "streak credited: user=%s date=%s source=%s streak=%s",
        user_id, today, source, rec.current_streak,
    )
    return True


def check_streak_on_open(user_id: int, today: date) -> StreakRecord:
    """Called when the user opens the daily tasks page.

    If the user has a last_solved_date and it is older than
    ``today - 1 day`` AND they had no day-off taken, the streak
    is reset to 0.  Otherwise the streak is left untouched.
    """
    rec = get_or_create_streak(user_id)

    if rec.last_solved_date is not None:
        gap = (today - rec.last_solved_date).days
        # Gap of 1 day (= yesterday) is fine — streak is preserved.
        # Gap of >1 day without a day-off means the streak is broken.
        if gap > 1:
            rec.current_streak = 0
            rec.days_off_available = 0
            db.session.flush()

    return rec


def complete_day(user_id: int, today: date, all_correct: bool) -> StreakRecord:
    """STREAK_V2: день засчитывается при ПЕРВОМ верном ответе на задачу дня.

    Старая логика (сброс серии за неверно отвеченный сет) заменена:
    ошибки больше не обнуляют серию — день просто не засчитывается,
    если нет ни 20 минут на сайте, ни одного верного ответа.
    Метод оставлен для совместимости вызовов: при ``all_correct``
    делегирует :func:`credit_streak_day` (идемпотентно), иначе ничего
    не меняет.
    """
    if all_correct:
        credit_streak_day(user_id, today, source="task")
    return get_or_create_streak(user_id)


def take_day_off(user_id: int, today: date) -> bool:
    """Consume one day-off token.  mu/sigma are NOT touched.

    Returns True on success, False if no days-off available.
    """
    rec = get_or_create_streak(user_id)

    if not rec.days_off_available or rec.days_off_available <= 0:
        return False

    rec.days_off_available -= 1
    rec.last_solved_date = today  # mark today as "covered"
    # current_streak stays unchanged
    db.session.flush()
    return True


# ---------------------------------------------------------------------------
# Helper for the route layer
# ---------------------------------------------------------------------------

def compute_all_correct(daily_set_id: int) -> bool:
    """Return True when every item of the set is answered correctly."""
    from daily_tasks.models import DailyTaskItem

    items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
    if not items:
        return False
    for it in items:
        if it.user_answer is None:
            return False
        if not it.is_correct:
            return False
    return True


def set_is_fully_answered(daily_set_id: int) -> bool:
    """Return True when every item has a non-null user_answer."""
    from daily_tasks.models import DailyTaskItem

    items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
    if not items:
        return False
    return all(it.user_answer is not None for it in items)


def check_and_reset_streaks(today: Optional[date] = None) -> int:
    """Полночная cron-задача: сбросить «протухшие» streak всем пользователям.

    Если у пользователя есть last_solved_date и с тех пор прошло больше
    одного дня (без взятых выходных), current_streak обнуляется.
    Вызывается планировщиком в 00:00 MSK.

    Возвращает число сброшенных streak.
    """
    today = today or date.today()
    records = StreakRecord.query.all()
    reset_count = 0
    for rec in records:
        if rec.last_solved_date is None:
            continue
        gap = (today - rec.last_solved_date).days
        # Пропуск > 1 дня без day-off — streak сломан.
        if gap > 1:
            rec.current_streak = 0
            rec.days_off_available = 0
            reset_count += 1
    if reset_count:
        db.session.flush()
    return reset_count
