# -*- coding: utf-8 -*-
"""
Scheduled tasks for the Prep module (personal olympiad preparation).

These functions are called by APScheduler jobs registered in app.py.
They can also be called directly for testing.

Tasks:
  1. daily_prep_cron()       — 00:05 MSK: close yesterday, activate today, expire plans
  2. send_morning_reminder() — 08:00 MSK: push notification per active plan
  3. weekly_prep_review()    — Sunday 20:00 MSK: recompute upcoming days
  4. send_weekly_report()    — per-plan weekly summary
  5. streak_rescue_cron()    — 20:00 MSK daily: warn users about to lose streak

All date operations use Europe/Moscow timezone via ZoneInfo.
"""
import json
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from models import db, PrepPlan, PrepDay
from services.notifications import send_telegram, send_email

logger = logging.getLogger(__name__)

BASE_URL = "https://formyla-com.onrender.com"
MSK = ZoneInfo("Europe/Moscow")


def _today_msk():
    """Return today's date in Europe/Moscow timezone."""
    return datetime.now(MSK).date()


# ---------------------------------------------------------------------------
# Task 1: Daily cron (runs at 00:05 MSK)
# ---------------------------------------------------------------------------

def daily_prep_cron():
    """Close yesterday's day, activate today, expire overdue plans.

    Returns dict with counts for logging/testing.
    """
    today = _today_msk()
    yesterday = today - timedelta(days=1)

    # 1. Close yesterday's days for all active plans
    yesterday_days = (
        PrepDay.query
        .filter_by(date=yesterday, status='today')
        .all()
    )
    for day in yesterday_days:
        plan = db.session.get(PrepPlan, day.plan_id)
        if not plan:
            continue

        completed_ids = day.completed_problem_ids_list
        if len(completed_ids) == 0:
            day.status = 'missed'
            plan.current_streak = 0
        else:
            day.status = 'completed'
            plan.current_streak = (plan.current_streak or 0) + 1
            if plan.current_streak > (plan.longest_streak or 0):
                plan.longest_streak = plan.current_streak
            plan.last_solved_date = yesterday

    # 2. Activate today's days
    today_days = (
        PrepDay.query
        .filter_by(date=today, status='upcoming')
        .all()
    )
    for day in today_days:
        day.status = 'today'

    # 3. Expire overdue plans
    expired = (
        PrepPlan.query
        .filter(PrepPlan.target_date < today, PrepPlan.status == 'active')
        .all()
    )
    for plan in expired:
        plan.status = 'completed'

    db.session.commit()

    result = dict(
        closed_yesterday=len(yesterday_days),
        activated_today=len(today_days),
        expired=len(expired),
    )
    logger.info("daily_prep_cron: %s", result)
    return result


# ---------------------------------------------------------------------------
# Task 2: Morning reminder (runs at 08:00 MSK per plan)
# ---------------------------------------------------------------------------

def send_morning_reminder(plan_id):
    """Send a morning push to the plan owner.

    Message depends on streak:
      - streak == 0 -> «Доброе утро! ...»
      - streak >= 7 -> « N дней подряд! ...»
      - else        -> «День N/total. ...»

    Channels: Telegram (if tg_chat_id), email (if email).
    """
    plan = db.session.get(PrepPlan, plan_id)
    if not plan or plan.status != 'active':
        return None

    user = plan.user
    today_day = PrepDay.query.filter_by(plan_id=plan_id, status='today').first()
    if not today_day:
        return None

    days_left = max(0, (plan.target_date - _today_msk()).days)
    streak = plan.current_streak or 0
    short = plan.olympiad.short_name if plan.olympiad else "олимпиаде"

    if streak == 0:
        msg = (
            "Доброе утро! ️\n"
            "%d задач ждут тебя сегодня. До %s осталось %d дн."
            % (plan.daily_task_count, short, days_left)
        )
    elif streak >= 7:
        msg = (
            " %d дней подряд! Не останавливайся — "
            "сегодня %d задач."
            % (streak, plan.daily_task_count)
        )
    else:
        msg = (
            "День %d/%d. Задачи готовы! "
            % (plan.days_elapsed, plan.days_total)
        )

    link = BASE_URL + "/prep/%d/today" % plan.id
    full_msg = msg + "\n\n" + link

    channels = []

    # Telegram
    tg_id = getattr(user, 'tg_chat_id', None)
    if tg_id:
        try:
            send_telegram(tg_id, full_msg)
            channels.append('telegram')
        except Exception as exc:
            logger.warning("Morning TG failed plan=%d: %s", plan_id, exc)

    # Email
    email_addr = getattr(user, 'email', None)
    if email_addr and not email_addr.startswith('guest_'):
        try:
            subject = "FORMYLA — %s" % msg[:60]
            send_email(email_addr, subject, full_msg)
            channels.append('email')
        except Exception as exc:
            logger.warning("Morning email failed plan=%d: %s", plan_id, exc)

    return dict(sent_to=user.id, channels=channels)


# ---------------------------------------------------------------------------
# Task 3: Weekly review (runs Sunday 20:00 MSK)
# ---------------------------------------------------------------------------

def weekly_prep_review():
    """Recompute upcoming days for all active plans based on current radar."""
    from services.prep_planner import recompute_plan

    active_plans = PrepPlan.query.filter_by(status='active').all()
    reviewed = 0
    for plan in active_plans:
        try:
            recompute_plan(plan.id)
            reviewed += 1
        except Exception as exc:
            logger.error("recompute_plan(%d) failed: %s", plan.id, exc)

    result = dict(reviewed=reviewed)
    logger.info("weekly_prep_review: %s", result)
    return result


# ---------------------------------------------------------------------------
# Task 4: Weekly report (per plan)
# ---------------------------------------------------------------------------

def send_weekly_report(plan_id):
    """Send a weekly progress summary to the plan owner.

    Report includes: solved/total for the week, streak, best topic growth,
    days remaining until olympiad.
    """
    plan = db.session.get(PrepPlan, plan_id)
    if not plan or plan.status != 'active':
        return None

    today = _today_msk()
    last_week_days = (
        PrepDay.query
        .filter(
            PrepDay.plan_id == plan_id,
            PrepDay.date >= today - timedelta(days=7),
        )
        .all()
    )

    solved = sum(d.day_score for d in last_week_days)
    total = sum(d.total_problems for d in last_week_days)
    missed = sum(1 for d in last_week_days if d.status == 'missed')

    bl = plan.baseline_radar_dict
    cr = plan.current_radar_dict
    delta = {}
    for t in bl:
        delta[t] = cr.get(t, 50) - bl.get(t, 50)

    best_topic = max(delta, key=delta.get) if delta else "—"
    best_val = delta.get(best_topic, 0)

    short = plan.olympiad.short_name if plan.olympiad else "олимпиаде"
    msg_lines = [
        " Еженедельный отчёт — %s" % short,
        "",
        "Решено: %d / %d" % (solved, total),
        "Серия: %d дн. подряд" % (plan.current_streak or 0),
        "Лучший рост: %s +%.1f" % (best_topic, best_val),
        "Дней до олимпиады: %d" % plan.days_remaining,
        "",
        "План пересчитан по твоему новому Радару.",
        BASE_URL + "/prep/%d" % plan.id,
    ]
    msg = "\n".join(msg_lines)

    channels = []

    # Telegram
    tg_id = getattr(plan.user, 'tg_chat_id', None)
    if tg_id:
        try:
            send_telegram(tg_id, msg)
            channels.append('telegram')
        except Exception as exc:
            logger.warning("Weekly report TG failed plan=%d: %s", plan_id, exc)

    # Email
    email_addr = getattr(plan.user, 'email', None)
    if email_addr and not email_addr.startswith('guest_'):
        try:
            subject = "FORMYLA — Еженедельный отчёт: %s" % short
            send_email(email_addr, subject, msg)
            channels.append('email')
        except Exception as exc:
            logger.warning("Weekly report email failed plan=%d: %s", plan_id, exc)

    return dict(
        plan_id=plan_id,
        solved=solved,
        total=total,
        missed=missed,
        channels=channels,
    )


# ---------------------------------------------------------------------------
# Task 5: Streak rescue (runs daily at 20:00 MSK)
# ---------------------------------------------------------------------------

def streak_rescue_cron():
    """Warn users who haven't solved anything today but have streak >= 3.

    Message: «Твоя серия N дней для <olympiad> под угрозой!
    Реши хотя бы 1 задачу до полуночи.»
    """
    today_date = _today_msk()

    plans_in_danger = (
        PrepPlan.query
        .filter(PrepPlan.status == 'active', PrepPlan.current_streak >= 3)
        .all()
    )

    warned = 0
    for plan in plans_in_danger:
        today_day = PrepDay.query.filter_by(
            plan_id=plan.id, date=today_date
        ).first()

        if not today_day or today_day.status != 'today':
            continue
        if len(today_day.completed_problem_ids_list) > 0:
            continue

        short = plan.olympiad.short_name if plan.olympiad else "олимпиаде"
        msg = (
            "[!]️ Твоя серия %d дн. для %s под угрозой!\n"
            "Реши хотя бы 1 задачу до полуночи.\n\n"
            "%s/prep/%d/today"
            % (plan.current_streak, short, BASE_URL, plan.id)
        )

        # Telegram
        tg_id = getattr(plan.user, 'tg_chat_id', None)
        if tg_id:
            try:
                send_telegram(tg_id, msg)
                warned += 1
            except Exception as exc:
                logger.warning("Streak rescue TG failed plan=%d: %s", plan.id, exc)

        # Email
        email_addr = getattr(plan.user, 'email', None)
        if email_addr and not email_addr.startswith('guest_'):
            try:
                subject = "FORMYLA — Серия под угрозой! "
                send_email(email_addr, subject, msg)
                if not tg_id:
                    warned += 1  # count only if TG wasn't sent
            except Exception as exc:
                logger.warning("Streak rescue email failed plan=%d: %s", plan.id, exc)

    result = dict(warned=warned)
    logger.info("streak_rescue_cron: %s", result)
    return result
