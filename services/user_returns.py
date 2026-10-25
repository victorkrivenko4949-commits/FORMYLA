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

USER_LAST_SEEN_V1 (2026-10-18): когда каждый заходил в последний раз.
    L(u) = max t_i (последнее действие), B(u) = начало последнего визита,
    dur(u) = L(u) - B(u), D(u) = now - L(u). Подробнее — в блоке ниже.
    Страницы: /admin/users/last_seen, /admin/users/last_seen.json (gap=60).

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
 <button>Пересчитать</button> &nbsp; <a href="/admin/users/returns.json?gap={{ d.gap_min }}&days={{ d.days }}">JSON</a> &nbsp; <a href="/admin/users/last_seen?gap={{ d.gap_min }}">Последний заход каждого →</a> &nbsp; <a href="/admin/users">← Статистика</a></form>

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


# ══════════════════════════════════════════════════════════════════════════
# USER_LAST_SEEN_V1 (2026-10-18): когда каждый пользователь заходил в последний раз.
#
# Формулы
#   L(u)      = max t_i                      — последнее действие пользователя u (UTC)
#   B(u)      = start(последнего визита)     — начало последнего визита (пауза > GAP => новый)
#   dur(u)    = L(u) − B(u)                  — длительность последнего визита
#   D(u)      = now − L(u)                   — давность: сколько прошло с последнего действия
#   bucket(u) = online  (D ≤ GAP)            — ещё в текущем визите
#             = today   (D < 24 ч)
#             = week    (D < 7 дн)
#             = month   (D < 30 дн)
#             = old     (D ≥ 30 дн)
#   Если действий в БД нет, берётся User.last_login (источник 'login').
# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# USER_PEAK_ONLINE_V1 (25.10.2026): максимум людей на сайте В ОДИН МОМЕНТ.
#
# «На сайте» = действие за последние GAP_MIN минут — то же правило, что и
# карточка «сейчас на сайте» (bucket online). Каждое действие держит
# пользователя «на сайте» ещё GAP_MIN минут, поэтому визит — интервал
# [B(u), L(u) + GAP]. Пик = максимум наложений таких интервалов (sweep-line).
# Время/дни — UTC, как и весь блок. peak_today >= online_now — инвариант.
# ══════════════════════════════════════════════════════════════════════════

def peak_from_events(events, gap_min: int, now: datetime) -> dict:
    """Чистая функция (для тестов): {user_id: [datetime]} → пики одновременных.

    Интервалы визитов продлеваются на gap после последнего действия — ровно
    как счётчик «сейчас на сайте» (D(u) ≤ gap). Метки из будущего пропускаются.
    """
    gap = timedelta(minutes=gap_min)
    intervals = []
    for ts in events.values():
        if not ts:
            continue
        for start, end, _n in sessions_of(ts, gap_min):
            if start > now:
                continue
            stop = end + gap
            if stop > now:
                stop = now
            intervals.append((start, stop))

    # пик за всё время: +1 на начале интервала, -1 на конце (в момент t
    # сначала засчитывается приход, потом уход — граница D ≤ gap включительна)
    points = []
    for s, e in intervals:
        points.append((s, 1))
        points.append((e, -1))
    cur = peak = 0
    peak_at = None
    for t, d in sorted(points, key=lambda p: (p[0], -p[1])):
        cur += d
        if cur > peak:
            peak, peak_at = cur, t

    def _day_peak(day_start: datetime, day_end: datetime) -> int:
        # база = интервалы, уже открытые на начало дня; внутри дня — обычный sweep
        base = 0
        pts = []
        for s, e in intervals:
            if s < day_start:
                if e >= day_start:
                    base += 1
            elif s < day_end:
                pts.append((s, 1))
                if e < day_end:
                    pts.append((e, -1))
        best = cur2 = base
        for _t, d2 in sorted(pts, key=lambda p: (p[0], -p[1])):
            cur2 += d2
            if cur2 > best:
                best = cur2
        return best

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    peak_today = _day_peak(today_start, now)
    peak_yesterday = _day_peak(today_start - timedelta(days=1), today_start)

    cutoff = now - gap
    online_now = sum(1 for ts in events.values()
                     if ts and cutoff <= ts[-1] <= now)
    return {
        'gap_min': gap_min,
        'now': now.strftime('%Y-%m-%d %H:%M'),
        'online_now': online_now,
        'peak_today': peak_today,
        'peak_yesterday': peak_yesterday,
        'peak_ever': peak,
        'peak_ever_at': peak_at.strftime('%d.%m.%Y %H:%M') if peak_at else '—',
        'visits': len(intervals),
    }


def peak_online(gap_min: int = GAP_MIN_DEFAULT, now: datetime = None) -> dict:
    """Пик одновременных «сейчас на сайте» по всем пользователям (см. выше)."""
    now = now or datetime.utcnow()
    events, _ = collect_events()
    return peak_from_events(events, gap_min, now)


# ══════════════════════════════════════════════════════════════════════════
# DEVICES_V1 (25.10.2026): с какого устройства (ПК / телефон) заходил каждый.
# Запись устройств включена 25.10.2026 (site_events.device + user_devices);
# более ранние визиты устройство не сохраняли → «нет данных».
# ══════════════════════════════════════════════════════════════════════════

def devices_by_user() -> dict:
    """{user_id: {'pc', 'mobile'}} — из сводной таблицы user_devices."""
    out = defaultdict(set)
    try:
        rows = db.session.execute(text(
            'SELECT user_id, device FROM user_devices'
        )).fetchall()
        for uid, dev in rows:
            if dev in ('pc', 'mobile'):
                try:
                    out[int(uid)].add(dev)
                except (TypeError, ValueError):
                    continue
    except Exception:
        db.session.rollback()
    return dict(out)


def _devices_label(devs) -> str | None:
    if not devs:
        return None
    if devs == {'pc'}:
        return 'ПК'
    if devs == {'mobile'}:
        return 'телефон'
    return 'ПК + телефон'


_BUCKETS = (
    ('online', 'сейчас на сайте', '#34d399'),
    ('today', 'за последние 24 ч', '#38bdf8'),
    ('week', '1–7 дней назад', '#a78bfa'),
    ('month', '7–30 дней назад', '#fbbf24'),
    ('old', 'больше 30 дней', '#f87171'),
)


def _ago_text(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    if s < 0:
        s = 0
    if s < 60:
        return 'только что'
    m = s // 60
    if m < 60:
        return f'{m} мин назад'
    h = m // 60
    if h < 24:
        return f'{h} ч {m % 60} мин назад'
    d = h // 24
    if d < 30:
        return f'{d} дн {h % 24} ч назад'
    if d < 365:
        return f'{d // 30} мес {d % 30} дн назад'
    return f'{d // 365} г {(d % 365) // 30} мес назад'


def _bucket_of(delta: timedelta, gap_min: int) -> str:
    if delta <= timedelta(minutes=gap_min):
        return 'online'
    if delta < timedelta(hours=24):
        return 'today'
    if delta < timedelta(days=7):
        return 'week'
    if delta < timedelta(days=30):
        return 'month'
    return 'old'


def _all_users():
    """{id: (display_name, last_login_dt|None, created_at|None)} — все пользователи."""
    out = {}
    try:
        from models import User
        for u in User.query.all():
            name = (getattr(u, 'username', None) or getattr(u, 'nickname', None)
                    or getattr(u, 'name', None) or getattr(u, 'email', None) or str(u.id))
            out[int(u.id)] = (name, _to_dt(getattr(u, 'last_login', None)),
                              _to_dt(getattr(u, 'created_at', None)))
    except Exception:
        db.session.rollback()
    return out


def last_seen_table(gap_min: int = GAP_MIN_DEFAULT, now: datetime = None) -> dict:
    """Для каждого пользователя: когда заходил в последний раз, сколько прошло, сколько визитов."""
    now = now or datetime.utcnow()
    events, sources = collect_events()
    users = _all_users()
    devices = devices_by_user()
    rows = []
    ids = set(events.keys()) | set(users.keys())
    for uid in ids:
        name, last_login, created = users.get(uid, (str(uid), None, None))
        ts = events.get(uid) or []
        sess = sessions_of(ts, gap_min) if ts else []
        if sess:
            start, end, n_ev = sess[-1]
            source = 'events'
        elif last_login is not None:
            start = end = last_login
            n_ev = 0
            source = 'login'
        else:
            rows.append({
                'user_id': uid, 'name': name, 'last_seen': None, 'last_visit_start': None,
                'last_visit_minutes': None, 'ago': 'ни разу', 'ago_seconds': None,
                'bucket': 'never', 'visits': 0, 'events_last_visit': 0, 'source': 'none',
                'registered': created.strftime('%Y-%m-%d') if created else '',
                'devices': _devices_label(devices.get(uid)),
            })
            continue
        delta = now - end
        rows.append({
            'user_id': uid,
            'name': name,
            'last_seen': end.strftime('%Y-%m-%d %H:%M'),
            'last_visit_start': start.strftime('%Y-%m-%d %H:%M'),
            'last_visit_minutes': int((end - start).total_seconds() // 60),
            'ago': _ago_text(delta),
            'ago_seconds': int(delta.total_seconds()),
            'bucket': _bucket_of(delta, gap_min),
            'visits': len(sess),
            'events_last_visit': n_ev,
            'source': source,
            'registered': created.strftime('%Y-%m-%d') if created else '',
            'devices': _devices_label(devices.get(uid)),
        })
    rows.sort(key=lambda r: (r['ago_seconds'] is None, r['ago_seconds'] or 0))
    counts = defaultdict(int)
    for r in rows:
        counts[r['bucket']] += 1
    total = len(rows)
    buckets = [{
        'key': k, 'label': lbl, 'color': col, 'count': counts.get(k, 0),
        'pct': round(100.0 * counts.get(k, 0) / total, 1) if total else 0.0,
    } for k, lbl, col in _BUCKETS]
    seen = [r['ago_seconds'] for r in rows if r['ago_seconds'] is not None]
    return {
        'gap_min': gap_min,
        'now': now.strftime('%Y-%m-%d %H:%M'),
        'total': total,
        'never': counts.get('never', 0),
        'buckets': buckets,
        'median_days_ago': round(sorted(seen)[len(seen) // 2] / 86400, 1) if seen else None,
        'rows': rows,
    }


_LAST_SEEN_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Последний заход каждого пользователя</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:24px;color:#222;max-width:1200px}
 table{border-collapse:collapse;margin:12px 0 24px} th,td{border:1px solid #ccc;padding:6px 10px;text-align:right}
 th:first-child,td:first-child,td:nth-child(2){text-align:left} th{background:#f3f3f3}
 .kpi{display:inline-block;background:#f7f7fb;border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin:4px 8px 4px 0}
 .kpi b{font-size:22px;display:block} code{background:#f3f3f3;padding:1px 4px} small{color:#666}
</style></head><body>
<h1>Последний заход каждого пользователя</h1>
<form method="get">Пауза между действиями, мин: <input name="gap" value="{{ d.gap_min }}" style="width:70px">
 <button>Пересчитать</button> &nbsp; <a href="/admin/users/last_seen.json?gap={{ d.gap_min }}">JSON</a> &nbsp; <a href="/admin/users">← Статистика</a></form>
<p><small>Сейчас (UTC): {{ d.now }}. Всего пользователей: {{ d.total }}, ни разу не заходили: {{ d.never }}.</small></p>
{% for b in d.buckets %}<div class="kpi"><small>{{ b.label }}</small><b style="color:{{ b.color }}">{{ b.count }}</b><small>{{ b.pct }}%</small></div>{% endfor %}
<table><tr><th>id</th><th>Пользователь</th><th>Последнее действие L(u)</th><th>Давность D(u)</th><th>Начало визита B(u)</th><th>Длит. визита</th><th>Действий</th><th>Визитов S(u)</th><th>Устройства</th><th>Источник</th></tr>
{% for r in d.rows %}<tr><td>{{ r.user_id }}</td><td>{{ r.name }}</td><td>{{ r.last_seen or '—' }}</td><td>{{ r.ago }}</td><td>{{ r.last_visit_start or '—' }}</td>
<td>{% if r.last_visit_minutes is not none %}{{ r.last_visit_minutes }} мин{% else %}—{% endif %}</td><td>{{ r.events_last_visit }}</td><td>{{ r.visits }}</td><td>{{ r.devices or '—' }}</td><td>{{ r.source }}</td></tr>{% endfor %}</table>
<h2>Формулы</h2>
<ul>
<li><code>L(u) = max t_i</code> — последнее действие (UTC)</li>
<li><code>B(u) = start(последнего визита)</code>, визит = серия действий с паузами ≤ {{ d.gap_min }} мин</li>
<li><code>dur(u) = L(u) − B(u)</code> — длительность последнего визита</li>
<li><code>D(u) = now − L(u)</code> — сколько прошло с последнего захода</li>
<li>Группы: online (D ≤ {{ d.gap_min }} мин), today (&lt; 24 ч), week (&lt; 7 дн), month (&lt; 30 дн), old (≥ 30 дн)</li>
<li>Если действий нет — берётся <code>User.last_login</code> (источник <code>login</code>)</li>
</ul>
</body></html>"""


@user_returns_bp.route('/admin/users/last_seen')
@login_required
def admin_user_last_seen():
    if not _is_admin():
        abort(403)
    gap = max(1, int(request.args.get('gap', GAP_MIN_DEFAULT) or GAP_MIN_DEFAULT))
    return render_template_string(_LAST_SEEN_HTML, d=last_seen_table(gap_min=gap))


@user_returns_bp.route('/admin/users/last_seen.json')
@login_required
def admin_user_last_seen_json():
    if not _is_admin():
        abort(403)
    gap = max(1, int(request.args.get('gap', GAP_MIN_DEFAULT) or GAP_MIN_DEFAULT))
    return jsonify(last_seen_table(gap_min=gap))


def register(app):
    if os.environ.get('USER_RETURNS_DISABLED') == '1':
        return
    if getattr(app, '_user_returns_registered', False):
        return
    app.register_blueprint(user_returns_bp)
    app._user_returns_registered = True
    log.info('USER_RETURNS_V1: registered')
