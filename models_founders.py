# -*- coding: utf-8 -*-
"""FOUNDERS_V1 — модель бесплатной выдачи доступа Основателям.

Отличается от оплаченного доступа (subscriptions) честно и во всём:
  * amount = 0 (копейки), payment_id IS NULL, is_free_grant = True;
  * одна выдача на пользователя в рамках кампании
    (UNIQUE(user_id, campaign_id));
  * откат адресный: удаление выдачи кампании не трогает payments/orders/
    subscriptions.

Импортируется из models.py (late import), чтобы таблица попала в metadata
до services/auto_migrate.py. Моменты времени — naive UTC.
"""
from __future__ import annotations

from datetime import datetime

from models import db

CAMPAIGN_ID = 'founders_2026_v1'


class FounderGrant(db.Model):
    __tablename__ = 'founder_grants'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'campaign_id', name='uq_founder_user_campaign'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    campaign_id = db.Column(db.String(40), nullable=False, index=True, default=CAMPAIGN_ID)
    amount = db.Column(db.Integer, nullable=False, default=0)      # копейки; всегда 0 — бесплатная выдача
    payment_id = db.Column(db.String(64), nullable=True)           # NULL — не оплата
    is_free_grant = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    starts_at = db.Column(db.DateTime, nullable=False)              # 2026-11-02 21:00 UTC = 03.11.2026 00:00 МСК
    expires_at = db.Column(db.DateTime, nullable=False)            # 2027-01-31 21:00 UTC = 01.02.2027 00:00 МСК
    granted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    granted_by = db.Column(db.String(120), nullable=True)           # 'script:grant_founders' и т.п.
    grant_batch = db.Column(db.Integer, nullable=True)             # номер пачки — возобновление после сбоя

    def __repr__(self):
        return f'<FounderGrant user={self.user_id} campaign={self.campaign_id} ' \
               f'{self.starts_at}..{self.expires_at}>'
