# -*- coding: utf-8 -*-
"""services/onboarding_nudge.py — утреннее email-напоминание новичкам.

Cron через APScheduler: каждый день 10:30 MSK шлём письмо тем, кто
зарегистрировался 22–26 часов назад и не завершил онбординг.
"""


def register_onboarding_nudge(scheduler, app):
    """Подключить задачу напоминания к планировщику."""

    @scheduler.task('cron', id='onboarding_nudge_email', hour=10, minute=30)
    def onboarding_nudge_email_job():
        """Утреннее email-напоминание новичкам, не прошедшим онбординг.

        Узкое окно 22–26 часов вокруг ежедневного запуска гарантирует,
        что письмо уходит ровно один раз. Признак onboarded_at не трогаем.
        """
        with app.app_context():
            try:
                from datetime import datetime, timedelta
                from models import User, db

                now = datetime.utcnow()
                window_from = now - timedelta(hours=26)
                window_to = now - timedelta(hours=22)

                fresh = User.query.filter(
                    User.created_at.between(window_from, window_to),
                    User.onboarded_at.is_(None),
                    User.is_guest.is_(False),
                    User.email.isnot(None),
                ).all()

                from services.email_service import send_onboarding_nudge
                sent = 0
                for user in fresh:
                    try:
                        if send_onboarding_nudge(user):
                            sent += 1
                    except Exception as user_err:
                        app.logger.warning(f"[onboarding_nudge] Error for user #{user.id}: {user_err}")
                if sent:
                    app.logger.info(f"[OK] Onboarding nudge sent to {sent} users")
            except Exception as e:
                app.logger.error(f" Onboarding nudge failed: {e}")
