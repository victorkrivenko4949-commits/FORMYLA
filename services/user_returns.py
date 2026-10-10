# -*- coding: utf-8 -*-
"""
USER_RETURNS_V1 (2026-10-10): статистика возвращений пользователей.

Определения
-----------
Событие      — любое действие пользователя, у которого в БД есть отметка времени
               (строки с user_id и колонкой DateTime: заходы user_visits, выдачи задач,
               сообщения, чертежи, отзывы и т.д.). Таблицы находятся автоматически.
Визит (сеанс) — серия событий одного пользователя, между соседними событиями которой
               пауза <= GAP_MIN минут (по умолчанию 60). Пауза > GAP_MIN => новый визит.
Возвращение  — каждый визит, начиная со второго. Если у пользователя S визитов,
               он «вернулся» S-1 раз.

Формулы (для админ-страницы)
---------------------------
    S(u)        = 1 + |{ i : t_{i+1} - t_i > GAP }|      — число визитов пользователя u
    R(u)        = S(u) - 1                                — число возвращений
    exact[n]    = |{ u : S(u) = n }|                      — ровно n визитов
    atleast[n]  = |{ u : S(u) >= n }|                     — вернулись n-й раз (и более)
    retention_n = atleast[n] / |U|                        — доля вернувшихся n-й раз

Подключение (одна строка, рядом с services.site_stats в gunicorn.conf.py или app.py):

    from services.user_returns import register as _register_user_returns; _register_user_returns(app)

Страницы:  /admin/users/returns         — HTML-таблица
           /admin/users/returns.json    — JSON (параметры: gap=60, days=0, user_id=)
Отключение без деплоя: env USER_RETURNS_DISABLED=1.
"""
import os
import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, render_template_string, abort
from flask_login import current_user, login_required
from sqlalchemy import text, inspect
from sqlalchemy.types import DateTime, TIMESTAMP, Date

from models import db

log = logging.getLogger(__name__)

GAP_MIN_DEFAULT = int(os.environ.get('USER_RETURNS_GAP_MIN', '60'))
CACHE_TTL_SEC = int(os.environ.get('USER_RETURNS_CACHE_SEC', '300'))

# Колонки-кандидаты «кто сделал действие»
_USER_COLS = ('user_id', 'sender_id', 'author_id', 'student_id')
# Таблицы, где время не означает действие пользователя
_SKIP_TABLES = {'users', 'user_presence', 'site_time_beat', 'alembic_version',
                'push_subscriptions', 'notifications'}
_SKIP_TS_COLS = {'updated_at', 'edited_at', 'deleted_at', 'read_at', 'delivered_at',
                 'expires_at', 'typing_at', 'target_date'}

user_returns_bp = Blueprint('user_returns', __name__)
_cache = {'ts': 0.0, 'key': None, 'events': None, 'sources': None}


def _is_admin() -> bool:
    return getattr(current_user, 'is_admin', False) is True


def _to_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str):
        s = v.strip().replace('T', ' ')
        if '.' in s:
            s = s.split('.')[0]
        s = s.split('+')[0]
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(s[:19], fmt)
            except ValueError:
                pass
    return None


def _discover_sources():
    """[(table, user_col, ts_col)] — все таблицы с user_id и DateTime-колонкой."""
    out = []
    insp = inspect(db.engine)
    for tbl in insp.get_table_names():
        if tbl in _SKIP_TABLES:
            continue
        try:
            cols = insp.get_columns(tbl)
        except Exception:
            continue
        names = {c['name']: c['type'] for c in cols}
        ucol = next((c for c in _USER_COLS if c in names), None)
        if not ucol:
            continue
        for cname, ctype in names.items():
            if cname in _SKIP_TS_COLS:
                continue
            if isinstance(ctype, Date) and not isinstance(ctype, (DateTime, TIMESTAMP)):
                continue
            if isinstance(ctype, (DateTime, TIMESTAMP)):
                out.append((tbl, ucol, cname))
    return out


def collect_events(force: bool = False):
    """{user_id: [datetime, ...]} по всем источникам; кэш CACHE_TTL_SEC."""
    now = time.time()
    if not force and _cache['events'] is not None and now - _cache['ts'] < CACHE_TTL_SEC:
        return _cache['events'], _cache['sources']
    events = defaultdict(list)
    used = []
    for tbl, ucol, tcol in _discover_sources():
        try:
            rows = db.session.execute(text(
                f'SELECT {ucol}, {tcol} FROM {tbl} '
                f'WHERE {ucol} IS NOT NULL AND {tcol} IS NOT NULL')).fetchall()
        except Exception as e:
            db.session.rollback()
            log.debug('user_returns: skip %s.%s: %r', tbl, tcol, e)
            continue
        n = 0
        for uid, ts in rows:
            dt = _to_dt(ts)
            if dt is None:
                continue
            try:
                events[int(uid)].append(dt)
            except (TypeError, ValueError):
                continue
            n += 1
        if n:
            used.append({'table': tbl, 'user_col': ucol, 'ts_col': tcol, 'rows': n})
    for uid in events:
        events[uid].sort()
    _cache.update(ts=now, events=dict(events), sources=used)
    return _cache['events'], used


def sessions_of(timestamps, gap_min: int = GAP_MIN_DEFAULT):
    """Список визитов [(start, end, n_events)] по правилу «пауза > gap => новый визит»."""
    if not timestamps:
        return []
    gap = timedelta(minutes=gap_min)
    ts = sorted(timestamps)
    out = []
    start = prev = ts[0]
    cnt = 1
    for t in ts[1:]:
        if t - prev > gap:
            out.append((start, prev, cnt))
            start, cnt = t, 0
        prev = t
        cnt += 1
    out.append((start, prev, cnt))
    return out


def user_returns(user_id: int, gap_min: int = GAP_MIN_DEFAULT) -> dict:
    """Сводка по одному пользователю: визиты, возвращения, журнал визитов."""
    events, _ = collect_events()
    sess = sessions_of(events.get(int(user_id), []), gap_min)
    return {
        'user_id': int(user_id),
        'gap_min': gap_min,
        'events': len(events.get(int(user_id), [])),
        'visits': len(sess),
        'returns': max(len(sess) - 1, 0),
        'first_visit': sess[0][0].isoformat() if sess else None,
        'last_visit': sess[-1][1].isoformat() if sess else None,
        'visit_log': [{'start': s.isoformat(), 'end': e.isoformat(), 'events': n}
                      for s, e, n in sess[-50:]],
    }


def returns_distribution(gap_min: int = GAP_MIN_DEFAULT, days: int = 0,
                         max_n: int = 10) -> dict:
    """Распределение: сколько людей вернулись 2-й, 3-й, ... раз."""
    events, sources = collect_events()
    since = datetime.utcnow() - timedelta(days=days) if days > 0 else None
    visits_by_user = {}
    for uid, ts in events.items():
        if since is not None:
            ts = [t for t in ts if t >= since]
        if not ts:
            continue
        visits_by_user[uid] = len(sessions_of(ts, gap_min))
    total = len(visits_by_user)
    exact = defaultdict(int)
    for s in visits_by_user.values():
        exact[s] += 1
    max_visits = max(visits_by_user.values()) if visits_by_user else 0
    rows = []
    for n in range(1, max(max_n, 1) + 1):
        ex = exact.get(n, 0)
        al = sum(c for s, c in exact.items() if s >= n)
        rows.append({
            'n': n,
            'label': 'первый визит (не возвращались)' if n == 1 else f'вернулись {n}-й раз',
            'exact': ex,
            'at_least': al,
            'share_at_least': round(100.0 * al / total, 1) if total else 0.0,
        })
    tail = sum(c for s, c in exact.items() if s > max_n)
    returned_any = sum(c for s, c in exact.items() if s >= 2)
    total_visits = sum(visits_by_user.values())
    top = sorted(visits_by_user.items(), key=lambda kv: -kv[1])[:20]
    return {
        'gap_min': gap_min,
        'days': days,
        'users_with_events': total,
        'returned_at_least_once': returned_any,
        'retention_pct': round(100.0 * returned_any / total, 1) if total else 0.0,
        'total_visits': total_visits,
        'avg_visits_per_user': round(total_visits / total, 2) if total else 0.0,
        'max_visits': max_visits,
        'rows': rows,
        'more_than_max': tail,
        'top_users': [{'user_id': u, 'visits': v, 'returns': v - 1} for u, v in top],
        'sources': sources,
    }


def _usernames(ids):
    if not ids:
        return {}
    try:
        from models import User
        q = User.query.filter(User.id.in_(list(ids))).all()
        return {u.id: (getattr(u, 'username', None) or getattr(u, 'name', None)
                       or getattr(u, 'email', None) or str(u.id)) for u in q}
    except Exception:
        db.session.rollback()
        return {}


_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Возвращения пользователей</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:24px;color:#222;max-width:1100px}
 table{border-collapse:collapse;margin:12px 0 24px} th,td{border:1px solid #ccc;padding:6px 10px;text-align:right}
 th:first-child,td:first-child{text-align:left} th{background:#f3f3f3}
 .kpi{display:inline-block;background:#f7f7fb;border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin:4px 8px 4px 0}
 .kpi b{font-size:22px;display:block} code{background:#f3f3f3;padding:1px 4px} small{color:#666}
 form input{width:70px}
</style></head><body>
<h1>Возвращения пользователей</h1>
<form method="get">Пауза между действиями, мин: <input name="gap" value="{{ d.gap_min }}">
 За последние дней (0 = всё время): <input name="days" value="{{ d.days }}">
 <button>Пересчитать</button> &nbsp; <a href="/admin/users/returns.json?gap={{ d.gap_min }}&days={{ d.days }}">JSON</a> &nbsp; <a href="/admin/users">← Статистика</a></form>

<div class="kpi"><small>Пользователей с действиями</small><b>{{ d.users_with_events }}</b></div>
<div class="kpi"><small>Вернулись хотя бы раз (визитов ≥ 2)</small><b>{{ d.returned_at_least_once }}</b></div>
<div class="kpi"><small>Доля вернувшихся</small><b>{{ d.retention_pct }}%</b></div>
<div class="kpi"><small>Всего визитов</small><b>{{ d.total_visits }}</b></div>
<div class="kpi"><small>Визитов на пользователя</small><b>{{ d.avg_visits_per_user }}</b></div>
<div class="kpi"><small>Максимум визитов у одного</small><b>{{ d.max_visits }}</b></div>

<h2>Сколько людей вернулись n-й раз</h2>
<table><tr><th>n</th><th>Что это</th><th>Ровно n визитов</th><th>Вернулись n-й раз (визитов ≥ n)</th><th>% от всех</th></tr>
{% for r in d.rows %}<tr><td>{{ r.n }}</td><td style="text-align:left">{{ r.label }}</td><td>{{ r.exact }}</td><td>{{ r.at_least }}</td><td>{{ r.share_at_least }}%</td></tr>{% endfor %}
<tr><td>&gt;{{ d.rows[-1].n }}</td><td style="text-align:left">больше {{ d.rows[-1].n }} визитов</td><td>{{ d.more_than_max }}</td><td>—</td><td>—</td></tr>
</table>

<h2>Топ по числу визитов</h2>
<table><tr><th>Пользователь</th><th>id</th><th>Визитов</th><th>Возвращений</th><th></th></tr>
{% for t in d.top_users %}<tr><td style="text-align:left">{{ names.get(t.user_id, '') }}</td><td>{{ t.user_id }}</td><td>{{ t.visits }}</td><td>{{ t.returns }}</td>
<td><a href="/admin/users/returns.json?user_id={{ t.user_id }}&gap={{ d.gap_min }}">визиты</a></td></tr>{% endfor %}</table>

<h2>Формулы</h2>
<p>Событие — любое действие с отметкой времени. Визит — серия событий с паузами ≤ {{ d.gap_min }} мин; пауза &gt; {{ d.gap_min }} мин открывает новый визит.</p>
<ul>
<li><code>S(u) = 1 + |{ i : t(i+1) − t(i) &gt; {{ d.gap_min }} мин }|</code> — визитов у пользователя u</li>
<li><code>R(u) = S(u) − 1</code> — возвращений</li>
<li><code>exact[n] = |{ u : S(u) = n }|</code> — ровно n визитов</li>
<li><code>atleast[n] = |{ u : S(u) ≥ n }|</code> — «вернулись n-й раз»</li>
<li><code>retention_n = atleast[n] / |U|</code>, где |U| = {{ d.users_with_events }}</li>
</ul>

<h2>Источники событий</h2>
<table><tr><th>Таблица</th><th>Колонка пользователя</th><th>Колонка времени</th><th>Строк</th></tr>
{% for s in d.sources %}<tr><td style="text-align:left">{{ s.table }}</td><td>{{ s.user_col }}</td><td>{{ s.ts_col }}</td><td>{{ s.rows }}</td></tr>{% endfor %}</table>
<p><small>Кэш {{ ttl }} с. Чем больше действий пишется в БД (например, user_visits из PR #99), тем точнее счёт; до их появления считаются только действия, оставившие след в таблицах.</small></p>
</body></html>"""


@user_returns_bp.route('/admin/users/returns')
@login_required
def admin_user_returns():
    if not _is_admin():
        abort(403)
    gap = max(1, int(request.args.get('gap', GAP_MIN_DEFAULT) or GAP_MIN_DEFAULT))
    days = max(0, int(request.args.get('days', 0) or 0))
    d = returns_distribution(gap_min=gap, days=days)
    names = _usernames([t['user_id'] for t in d['top_users']])
    return render_template_string(_HTML, d=d, names=names, ttl=CACHE_TTL_SEC)


@user_returns_bp.route('/admin/users/returns.json')
@login_required
def admin_user_returns_json():
    if not _is_admin():
        abort(403)
    gap = max(1, int(request.args.get('gap', GAP_MIN_DEFAULT) or GAP_MIN_DEFAULT))
    uid = request.args.get('user_id')
    if uid:
        return jsonify(user_returns(int(uid), gap_min=gap))
    days = max(0, int(request.args.get('days', 0) or 0))
    return jsonify(returns_distribution(gap_min=gap, days=days))


def register(app):
    if os.environ.get('USER_RETURNS_DISABLED') == '1':
        return
    if getattr(app, '_user_returns_registered', False):
        return
    app.register_blueprint(user_returns_bp)
    app._user_returns_registered = True
    log.info('USER_RETURNS_V1: registered')
