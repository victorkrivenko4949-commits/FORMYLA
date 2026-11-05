# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK (05.11.2026) — «Неделя Premium за подписку на Telegram-канал».

Одна строка = одна выданная неделя. Уникальность и по аккаунту, и по
Telegram-аккаунту: нельзя получить неделю дважды на один аккаунт и нельзя
«перевесить» один Telegram на новый аккаунт сайта и получить ещё раз.

Сам доступ — обычная строка в subscriptions (plan='premium_intense',
is_trial=1, expires_at = выдача + 7 дней), поэтому все гейты Premium
работают без изменений. Таблица создаётся auto_migrate (create_all).
Время — naive UTC, как во всём проекте.
"""
from __future__ import annotations

from datetime import datetime

from models import db


class TgTrialGrant(db.Model):
    __tablename__ = 'tg_trial_grants'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    telegram_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    channel = db.Column(db.String(100), nullable=False)
    granted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<TgTrialGrant user={self.user_id} tg={self.telegram_id} until={self.expires_at}>'


class TgTrialLink(db.Model):
    """Личная ссылка-приглашение в канал для пользователя сайта.

    Кто вступил в канал по этой ссылке — бот видит (апдейт chat_member с
    invite_link), так мы узнаём Telegram пользователя без входа через Telegram.
    start_token — для тех, кто уже был подписан: t.me/<бот>?start=<token>.
    """
    __tablename__ = 'tg_trial_links'

    user_id = db.Column(db.Integer, primary_key=True)
    invite_link = db.Column(db.String(255), unique=True, index=True)
    start_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    telegram_id = db.Column(db.String(64), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    matched_at = db.Column(db.DateTime)


class TgBotCursor(db.Model):
    """Смещение getUpdates бота (одна строка id=1)."""
    __tablename__ = 'tg_bot_cursor'

    id = db.Column(db.Integer, primary_key=True)
    offset = db.Column(db.BigInteger, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
