# -*- coding: utf-8 -*-
"""
USER_VISITS_V1 (2026-10-05): точный счётчик заходов на сайт.

Визит = серия запросов авторизованного пользователя, между которыми
нет паузы дольше VISIT_TIMEOUT_MIN минут (та же логика, что в Яндекс
Метрике / GA: 30 минут бездействия = новый визит).

Подключение в app.py (после создания app и db, рядом с остальными
blueprint'ами):

    from services.user_visits import init_user_visits
    init_user_visits(app)

Больше ничего менять не нужно: таблица user_visits создаётся
автоматически при первом запросе, хук before_request сам пишет визиты.
"""
from datetime import datetime, timedelta

from flask import request, g
from flask_login import current_user
from sqlalchemy import text, func

from models import db

VISIT_TIMEOUT_MIN = 30

# Пути, которые не считаем активностью (фоновые опросы, статика)
_SKIP_PREFIXES = ('/static/', '/api/chat/', '/api/presence', '/favicon', '/health')


class UserVisit(db.Model):
    __tablename__ = 'user_visits'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_hit_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    hits = db.Column(db.Integer, nullable=False, default=1)
    first_path = db.Column(db.String(255))
    user_agent = db.Column(db.String(255))
    ip = db.Column(db.String(64))

    def __repr__(self):
        return f'<UserVisit user={self.user_id} start={self.started_at:%Y-%m-%d %H:%M}>'


def _create_sql(autoinc: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS user_visits (
            id {autoinc},
            user_id INTEGER NOT NULL,
            started_at TIMESTAMP NOT NULL,
            last_hit_at TIMESTAMP NOT NULL,
            hits INTEGER NOT NULL DEFAULT 1,
            first_path VARCHAR(255),
            user_agent VARCHAR(255),
            ip VARCHAR(64)
        )
    """


def ensure_user_visits_table():
    """Авто-миграция в стиле ensure_support_replies_table (SQLite и PostgreSQL)."""
    for autoinc in ('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY'):
        try:
            db.session.execute(text(_create_sql(autoinc)))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_visits_user_id ON user_visits (user_id)"))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_visits_user_last ON user_visits (user_id, last_hit_at)"))
            db.session.commit()
            return
        except Exception:
            db.session.rollback()


def _should_track() -> bool:
    if request.method not in ('GET', 'POST'):
        return False
    p = request.path or '/'
    if p.startswith(_SKIP_PREFIXES):
        return False
    if not getattr(current_user, 'is_authenticated', False):
        return False
    if getattr(current_user, 'is_guest', False):
        return False
    return True


def touch_visit():
    """Вызывается на каждый запрос. Продлевает текущий визит или открывает новый."""
    if not _should_track():
        return
    now = datetime.utcnow()
    uid = current_user.id
    try:
        last = (UserVisit.query
                .filter_by(user_id=uid)
                .order_by(UserVisit.last_hit_at.desc())
                .first())
        if last is not None and (now - last.last_hit_at) <= timedelta(minutes=VISIT_TIMEOUT_MIN):
            # Чтобы не писать в БД на каждый клик — обновляем не чаще раза в минуту
            if (now - last.last_hit_at) >= timedelta(minutes=1):
                last.last_hit_at = now
                last.hits = (last.hits or 1) + 1
                db.session.commit()
            return
        v = UserVisit(
            user_id=uid,
            started_at=now,
            last_hit_at=now,
            hits=1,
            first_path=(request.path or '/')[:255],
            user_agent=(request.headers.get('User-Agent') or '')[:255],
            ip=(request.headers.get('X-Forwarded-For', request.remote_addr) or '')[:64],
        )
        db.session.add(v)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ──────────────────────────────────────────────────────────────────
# API для админки
# ──────────────────────────────────────────────────────────────────
def visit_stats(user_id: int) -> dict:
    """Сводка по заходам пользователя для /admin/support/user_intake/<id>."""
    q = UserVisit.query.filter_by(user_id=user_id)
    total = q.count()
    if not total:
        return {'visits_exact': 0, 'visit_days_exact': 0,
                'first_visit': None, 'last_visit': None,
                'avg_visit_minutes': None, 'visits_last_7d': 0,
                'visits_last_30d': 0, 'visit_log': []}
    now = datetime.utcnow()
    rows = q.order_by(UserVisit.started_at.asc()).all()
    days = {r.started_at.date() for r in rows}
    durations = [(r.last_hit_at - r.started_at).total_seconds() / 60 for r in rows]
    return {
        'visits_exact': total,
        'visit_days_exact': len(days),
        'first_visit': rows[0].started_at.isoformat(),
        'last_visit': rows[-1].last_hit_at.isoformat(),
        'avg_visit_minutes': round(sum(durations) / len(durations), 1),
        'visits_last_7d': sum(1 for r in rows if r.started_at >= now - timedelta(days=7)),
        'visits_last_30d': sum(1 for r in rows if r.started_at >= now - timedelta(days=30)),
        'visit_log': [
            {'start': r.started_at.isoformat(), 'end': r.last_hit_at.isoformat(),
             'hits': r.hits, 'path': r.first_path}
            for r in rows[-50:]
        ],
    }


def visits_by_user() -> dict:
    """{user_id: число визитов} — для таблицы /admin/users."""
    rows = (db.session.query(UserVisit.user_id, func.count(UserVisit.id))
            .group_by(UserVisit.user_id).all())
    return {uid: cnt for uid, cnt in rows}


def init_user_visits(app):
    @app.before_request
    def _user_visits_hook():
        if not getattr(g, '_user_visits_table_ok', False):
            ensure_user_visits_table()
            g._user_visits_table_ok = True
        touch_visit()
