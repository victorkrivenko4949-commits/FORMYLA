# -*- coding: utf-8 -*-
"""
Migration 003: FOUNDERS_V1 — поля Основателей и триала.

Adds columns to users:
    is_founder (bool, default false)
    founder_price_eligible (bool, default false)
    founder_granted_at (datetime, nullable)
    trial_until (datetime, nullable)
Creates table: founder_grants (см. models_founders.py)

IDEMPOTENT: safe to run multiple times (SQLite и PostgreSQL).
На Render это же делает services/auto_migrate.py при старте (колонки из
models.py попадают в metadata до его запуска). Данный скрипт — для локальной
проверки и явного применения.

Run:
    python migrations/003_add_founder_fields.py
Rollback:
    python migrations/003_add_founder_fields.py --rollback
    (удаляет ТОЛЬКО выдачи кампании founders_2026_v1 и её флаги;
     payments/orders/subscriptions не трогаются)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NEW_COLUMNS = {
    'users': [
        ("is_founder", "ALTER TABLE users ADD COLUMN is_founder BOOLEAN NOT NULL DEFAULT 0"),
        ("founder_price_eligible", "ALTER TABLE users ADD COLUMN founder_price_eligible BOOLEAN NOT NULL DEFAULT 0"),
        ("founder_granted_at", "ALTER TABLE users ADD COLUMN founder_granted_at DATETIME"),
        ("trial_until", "ALTER TABLE users ADD COLUMN trial_until DATETIME"),
    ],
}

GRANTS_TABLE = """
CREATE TABLE IF NOT EXISTS founder_grants (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    campaign_id VARCHAR(40) NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    payment_id VARCHAR(64),
    is_free_grant BOOLEAN NOT NULL DEFAULT 1,
    starts_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    granted_at DATETIME NOT NULL,
    granted_by VARCHAR(120),
    grant_batch INTEGER
)"""


def main() -> int:
    from models import db
    from app import app  # noqa: F401 — контекст БД

    rollback = '--rollback' in sys.argv
    with app.app_context():
        insp = __import__('sqlalchemy').inspect(db.engine)
        if rollback:
            print('Rollback FOUNDERS_V1: удаляю выдачи кампании founders_2026_v1 и флаги.')
            from models_founders import FounderGrant
            from models import User
            grants = FounderGrant.query.filter_by(campaign_id='founders_2026_v1').all()
            for g in grants:
                db.session.delete(g)
            for g in grants:
                u = db.session.get(User, g.user_id)
                if u is not None:
                    u.is_founder = False
                    u.founder_price_eligible = False
                    u.founder_granted_at = None
            db.session.commit()
            print(f'Удалено выдач: {len(grants)}. Платежи и оплаченные права не тронуты.')
            return 0

        added = []
        for table, cols in NEW_COLUMNS.items():
            existing = {c['name'] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in existing:
                    db.session.execute(db.text(ddl))
                    added.append(f'{table}.{name}')
        db.session.commit()
        db.session.execute(db.text(GRANTS_TABLE))
        db.session.commit()
        idx = db.engine.dialect.name
        if idx == 'postgresql':
            try:
                db.session.execute(db.text(
                    "ALTER TABLE founder_grants ADD CONSTRAINT uq_founder_user_campaign "
                    "UNIQUE (user_id, campaign_id)"))
                db.session.commit()
            except Exception:
                pass  # уже есть
        print(f'[OK] Migration 003 applied. Added columns: {added or "none (already present)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
