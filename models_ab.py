# -*- coding: utf-8 -*-
"""AB_V1 — модель A/B-групп эксперимента лимитов.

Таблица ab_cohort: историческая группа назначения. Смена PAYWALL_MODE /
PAYWALL_AB / PAYWALL_EXPERIMENT_ID НЕ переписывает ни одной строки.
Новый эксперимент = новый PAYWALL_EXPERIMENT_ID = новые строки
(PK (experiment_id, user_id)).

Импортируется из models.py (late import) — таблица попадает в metadata
до services/auto_migrate.py.
"""
from __future__ import annotations

from datetime import datetime

from models import db


class AbCohort(db.Model):
    __tablename__ = 'ab_cohort'
    __table_args__ = (
        db.PrimaryKeyConstraint('experiment_id', 'user_id'),
    )

    experiment_id = db.Column(db.String(40), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    cohort = db.Column(db.String(10), nullable=False)          # 'limits' | 'control'
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    eligible_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    first_limit_shown_at = db.Column(db.DateTime, nullable=True)
    algo_version = db.Column(db.String(30), nullable=False)

    def __repr__(self):
        return f'<AbCohort user={self.user_id} exp={self.experiment_id} {self.cohort}>'
