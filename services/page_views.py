# -*- coding: utf-8 -*-
"""PAGE_VIEWS_V1 (2026-11-05) — журнал просмотров страниц для раздела «Где уходят».

Что делает:
  * таблица page_views (user_id / anon_id, нормализованный path, created_at);
  * after_request: пишет успешные HTML-GET (без /api, /static, /admin);
    админов и повторную загрузку той же страницы в течение 3 секунд не пишет;
  * хранит 90 дней — старые строки удаляются при записи (редко, случайно);
  * analyze() — чистая функция: из просмотров делает визиты (пауза > 30 мин =
    новый визит) и считает страницы выхода, отскок и «выход из анкеты».

Запись идёт через отдельное соединение engine.begin(), чтобы не трогать
сессию запроса. Любая ошибка БД — fail-open (сайт не падает, строка теряется).
Откат: PAGE_VIEWS_ENABLED=0 — ни таблицы, ни хука.
"""
from __future__ import annotations

import logging
import os
import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import request, session
from sqlalchemy import text

logger = logging.getLogger(__name__)

ENABLED = os.environ.get('PAGE_VIEWS_ENABLED', '1') != '0'
RETENTION_DAYS = 90
VISIT_GAP_MIN = 30
DEDUP_SEC = 3
INTAKE_PREFIX = '/intake'

SKIP_PREFIXES = ('/static/', '/api/', '/admin/', '/sw.js', '/offline', '/favicon',
                 '/site.webmanifest', '/login/', '/_')

_BOT_RE = re.compile(r'bot|crawl|spider|slurp|headless|python-requests|curl/|wget|httpx', re.I)
_ID_SEG = re.compile(r'^(\d+|[0-9a-fA-F]{16,}|[0-9a-fA-F-]{32,36})$')
_tables_ready = False


# ──────────────────────────── helpers ────────────────────────────
def _db():
    from models import db
    return db


def _is_pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


def normalize_path(path: str) -> str:
    """/problems/123?x=1 → /problems/<id>; не длиннее 120 символов."""
    p = (path or '/').split('?', 1)[0].split('#', 1)[0] or '/'
    segs = ['<id>' if _ID_SEG.match(s) else s for s in p.split('/')]
    p = '/'.join(segs)
    if len(p) > 1:
        p = p.rstrip('/')
    return p[:120] or '/'


def ensure_tables() -> None:
    global _tables_ready
    if _tables_ready or not ENABLED:
        return
    pg = _is_pg()
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ts_default = 'TIMESTAMP NOT NULL DEFAULT NOW()' if pg else 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
    stmts = [
        f"""CREATE TABLE IF NOT EXISTS page_views (
                id {serial},
                user_id INTEGER,
                anon_id VARCHAR(36),
                path VARCHAR(120) NOT NULL,
                created_at {ts_default}
            )""",
        'CREATE INDEX IF NOT EXISTS ix_pv_created ON page_views (created_at)',
        'CREATE INDEX IF NOT EXISTS ix_pv_user_created ON page_views (user_id, created_at)',
    ]
    try:
        with _db().engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        _tables_ready = True
    except Exception as e:  # noqa: BLE001
        logger.warning('page_views.ensure_tables: %r', e)


def _is_admin_user() -> bool:
    try:
        from flask_login import current_user
        return bool(current_user.is_authenticated and getattr(current_user, 'is_admin', False) is True)
    except Exception:
        return False


def _uid_or_none():
    try:
        from flask_login import current_user
        if current_user.is_authenticated and not getattr(current_user, 'is_guest', False):
            return int(current_user.id)
    except Exception:
        pass
    return None


def record_view(path: str, user_id, anon_id) -> bool:
    ensure_tables()
    if not _tables_ready:
        return False
    try:
        with _db().engine.begin() as conn:
            conn.execute(text('INSERT INTO page_views (user_id, anon_id, path, created_at) '
                              'VALUES (:u, :a, :p, :t)'),
                         {'u': user_id, 'a': anon_id, 'p': normalize_path(path), 't': datetime.utcnow()})
            if random.random() < 0.002:  # ~ раз на 500 записей чистим старьё
                conn.execute(text('DELETE FROM page_views WHERE created_at < :t'),
                             {'t': datetime.utcnow() - timedelta(days=RETENTION_DAYS)})
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning('page_views.record_view: %r', e)
        return False


def _after_request(resp):
    try:
        if (request.method != 'GET' or resp.status_code != 200 or resp.mimetype != 'text/html'
                or resp.direct_passthrough):
            return resp
        p = request.path or '/'
        if p.startswith(SKIP_PREFIXES) or _is_admin_user():
            return resp
        if _BOT_RE.search(request.headers.get('User-Agent') or ''):
            return resp
        norm = normalize_path(p)
        now = time.time()
        last = session.get('pv_last')
        # дубль = та же страница (по сырому пути) в течение пары секунд, например F5
        if isinstance(last, (list, tuple)) and len(last) == 2 and last[0] == p and now - float(last[1]) < DEDUP_SEC:
            return resp
        session['pv_last'] = [p[:200], now]
        record_view(norm, _uid_or_none(), session.get('anon_id'))
    except Exception as e:  # noqa: BLE001
        logger.debug('page_views after_request skipped: %r', e)
    return resp


def install(app) -> None:
    if not ENABLED or app.extensions.get('page_views_installed'):
        return
    app.extensions['page_views_installed'] = True
    try:
        with app.app_context():
            ensure_tables()
    except Exception as e:  # noqa: BLE001
        logger.warning('page_views: ensure_tables at startup failed: %r', e)
    app.after_request(_after_request)
    logger.info('PAGE_VIEWS_V1 registered (page_views)')


# ──────────────────────────── analysis ────────────────────────────
def to_dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ')[:26])
    except Exception:
        return None


def build_visits(rows, gap_min: int = VISIT_GAP_MIN):
    """rows: (user_id, anon_id, path, created_at) → список визитов.

    Визит = [(path, ts, key), ...]; ключ человека — user_id, иначе anon_id.
    """
    gap = timedelta(minutes=gap_min)
    per_key = defaultdict(list)
    for uid, anon, path, ts in rows:
        t = to_dt(ts)
        if t is None:
            continue
        key = f'u{uid}' if uid is not None else (f'a{anon}' if anon else None)
        if key is None:
            continue
        per_key[key].append((str(path), t))
    visits = []
    for key, items in per_key.items():
        items.sort(key=lambda x: x[1])
        cur = [items[0]]
        for it in items[1:]:
            if it[1] - cur[-1][1] > gap:
                visits.append((key, cur))
                cur = [it]
            else:
                cur.append(it)
        visits.append((key, cur))
    return visits


def analyze(rows, gap_min: int = VISIT_GAP_MIN, intake_prefix: str = INTAKE_PREFIX) -> dict:
    visits = build_visits(rows, gap_min)
    views = Counter()
    exits = Counter()
    exit_people = defaultdict(set)
    entries = Counter()
    bounces = Counter()
    people = set()
    total_views = 0
    intake_visits = 0
    intake_exit = Counter()
    intake_left_inside = 0
    for key, v in visits:
        people.add(key)
        total_views += len(v)
        for path, _ in v:
            views[path] += 1
        last = v[-1][0]
        exits[last] += 1
        exit_people[last].add(key)
        entries[v[0][0]] += 1
        if len(v) == 1:
            bounces[v[0][0]] += 1
        if any(p.startswith(intake_prefix) for p, _ in v):
            intake_visits += 1
            intake_exit[last] += 1
            if last.startswith(intake_prefix):
                intake_left_inside += 1
    return {
        'visits': len(visits), 'people': len(people), 'views': total_views,
        'views_by_path': views, 'exits': exits,
        'exit_people': {k: len(s) for k, s in exit_people.items()},
        'entries': entries, 'bounces': bounces,
        'intake_visits': intake_visits, 'intake_exit': intake_exit,
        'intake_left_inside': intake_left_inside,
    }


def load_rows(d_from, d_to, only_users: bool = True, limit: int = 300000):
    """Просмотры за период (МСК-даты включительно)."""
    start = datetime.combine(d_from, datetime.min.time()) - timedelta(hours=3)
    end = datetime.combine(d_to + timedelta(days=1), datetime.min.time()) - timedelta(hours=3)
    where = 'created_at >= :s AND created_at < :e' + (' AND user_id IS NOT NULL' if only_users else '')
    try:
        return _db().session.execute(
            text(f'SELECT user_id, anon_id, path, created_at FROM page_views WHERE {where} '
                 f'ORDER BY created_at LIMIT {int(limit)}'), {'s': start, 'e': end}).fetchall()
    except Exception as e:  # noqa: BLE001
        _db().session.rollback()
        logger.warning('page_views.load_rows: %r', e)
        return None


def first_view_at():
    try:
        v = _db().session.execute(text('SELECT MIN(created_at) FROM page_views')).scalar()
        return to_dt(v)
    except Exception:
        _db().session.rollback()
        return None


def link_anon_to_user(anon_id, user_id) -> int:
    """После регистрации: просмотры гостя с этим anon_id привязываем к аккаунту,
    чтобы был виден путь ДО регистрации. Возвращает число строк."""
    if not anon_id or not user_id:
        return 0
    ensure_tables()
    if not _tables_ready:
        return 0
    try:
        with _db().engine.begin() as conn:
            res = conn.execute(text('UPDATE page_views SET user_id = :u WHERE anon_id = :a AND user_id IS NULL'),
                               {'u': int(user_id), 'a': str(anon_id)})
            return int(getattr(res, 'rowcount', 0) or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning('page_views.link_anon_to_user: %r', e)
        return 0
