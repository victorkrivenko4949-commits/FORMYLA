# -*- coding: utf-8 -*-
"""ADMIN_STATS_V1 (18.10.2026) — единая панель статистики /admin/stats с левым меню.

Реестр SECTIONS описывает все разделы. kind:
  view  — строится здесь (overview/funnel/sources/env_flags) или в
          routes/admin_stats_sections.py (блоки: карточки/таблицы/заметки);
  embed — существующая страница встраивается как есть (iframe);
  stub  — заглушка (на случай, если раздел временно отключён).
Данные — funnel_events (services/funnel.py), site_time_sections (services/site_stats.py),
users, subscriptions, usage_daily, streak_records, geo_drawing_history.

Откат: ADMIN_STATS_ENABLED=0. Доступ — только User.is_admin.
Не правит app.py: подключается через routes/__init__.py.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, abort, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import text

logger = logging.getLogger(__name__)

admin_stats_bp = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

ENABLED = os.environ.get('ADMIN_STATS_ENABLED', '1') != '0'

FUNNEL_STEPS = (
    ('visit', 'Визиты'),
    ('signup', 'Регистрации'),
    ('intake_done', 'Анкета пройдена'),
    ('first_task_solved', 'Первая задача решена'),
    ('payment_success', 'Оплаты'),
)

SOURCE_TITLES = {
    'tg': 'Telegram', 'teacher': 'Учителя', 'parent': 'Родители', 'referral': 'Рефералы / ссылки',
    'organic': 'Поиск (органика)', 'social': 'Соцсети', 'direct_visit': 'Прямые заходы',
    'internal': 'Внутренние', None: 'Не определён', '': 'Не определён',
}

ENV_FLAGS = ('PAYWALL_ENABLED', 'PAYWALL_START_DATE', 'PAYWALL_PREFIXES', 'PAYWALL_AB',
             'METHOD_WEEK_ALLOWED_USERS', 'FREE_TASKS_PER_DAY', 'FREE_AI_PER_DAY', 'TRIAL_DAYS',
             'FUNNEL_ENABLED', 'ADMIN_STATS_ENABLED', 'ADMIN_STATS_REDIRECTS', 'YANDEX_METRIKA_ID',
             'PLAUSIBLE_DOMAIN', 'ADMIN_BASE_AUTOREG', 'PWA_AUTOREG', 'SURVEYS_AUTOREG')

# slug, title, group, kind (view|embed|stub), target (url для embed), ready, since, note
SECTIONS = [
    # Сводка
    dict(slug='overview', title='Сводка', group='Сводка', kind='view', ready=True),
    # Привлечение
    dict(slug='funnel', title='Воронка', group='Привлечение', kind='view', ready=True),
    dict(slug='sources', title='Источники', group='Привлечение', kind='view', ready=True),
    dict(slug='referrals', title='Рефералы', group='Привлечение', kind='view', ready=True,
         note='Кто кого привёл (users.invited_by), визиты по ?ref=u_<id>, оплаты приглашённых.'),
    # Активность
    dict(slug='users', title='Пользователи', group='Активность', kind='embed', target='/admin/users', ready=True),
    dict(slug='sections', title='Разделы сайта', group='Активность', kind='embed', target='/admin/users/sections', ready=True),
    dict(slug='returns', title='Возвраты', group='Активность', kind='embed', target='/admin/users/returns', ready=True),
    dict(slug='daily_tasks', title='Задачи дня', group='Активность', kind='embed', target='/admin/daily_tasks/dashboard', ready=True),
    dict(slug='streaks', title='Серии и XP', group='Активность', kind='view', ready=True,
         note='Распределение серий (streak_records), доля ≥ 7 дней — контроль правила серии для Free с 3 задачами.'),
    # Монетизация
    dict(slug='limits', title='Лимиты', group='Монетизация', kind='view', ready=True,
         note='limit_hit по дням и когортам A/B, доля от DAU. Экран для решения 11.11.'),
    dict(slug='paywall', title='Paywall и витрина', group='Монетизация', kind='view', ready=True,
         note='paywall_view → subscribe_view → payment_success по точке входа (from=).'),
    dict(slug='subscriptions', title='Подписки', group='Монетизация', kind='view', ready=True,
         note='Активные по тарифам, MRR и прогресс к 100 тыс. ₽/мес, истекающие, отмены.'),
    dict(slug='founders', title='Основатели', group='Монетизация', kind='view', ready=True,
         note='users.is_founder (после PR 19.10), клики по офферу, годовые по 2 790 ₽, дни до 31.01.2027.'),
    dict(slug='trial', title='Триал', group='Монетизация', kind='view', ready=True,
         note='users.trial_until (после PR 20.10): выдано, активно, истекают, конверсия в оплату.'),
    dict(slug='payments', title='Платежи', group='Монетизация', kind='view', ready=True,
         note='payment_success из webhook ЮKassa: суммы по тарифам, последние платежи.'),
    dict(slug='cohorts', title='Когорты', group='Монетизация', kind='view', ready=True,
         note='По неделе регистрации: анкета, первая задача, оплата.'),
    # Продукт
    dict(slug='ai_usage', title='ИИ-разборы и бюджет', group='Продукт', kind='view', ready=True,
         note='usage_daily: разборы, токены, cost_usd, дни на лимите FREE_AI_PER_DAY, топ пользователей.'),
    dict(slug='curator', title='Куратор и план', group='Продукт', kind='view', ready=True,
         note='Состояния куратора и ссылки на существующие страницы статуса плана/бюджета.'),
    dict(slug='drawings_method_week', title='Чертежи и метод недели', group='Продукт', kind='view', ready=True,
         note='geo_drawing_history по дням + paywall_view по страницам.'),
    dict(slug='daily_pool', title='Пул задач дня', group='Продукт', kind='embed', target='/admin/daily_pool', ready=True),
    # Люди
    dict(slug='support', title='Поддержка', group='Люди', kind='embed', target='/admin/support', ready=True),
    dict(slug='surveys', title='Опросы и оценки', group='Люди', kind='embed', target='/admin/users/surveys', ready=True),
    dict(slug='teachers_parents', title='Учителя и родители', group='Люди', kind='view', ready=True,
         note='Роли, визиты по меткам teacher/parent, связки (когда появятся).'),
    # Система
    dict(slug='pwa', title='PWA-установки', group='Система', kind='embed', target='/admin/pwa/stats', ready=True),
    dict(slug='insights', title='Инсайты', group='Система', kind='embed', target='/api/admin/insights/stats', ready=True),
    dict(slug='env_flags', title='Флаги окружения', group='Система', kind='view', ready=True),
]
GROUP_ORDER = ('Сводка', 'Привлечение', 'Активность', 'Монетизация', 'Продукт', 'Люди', 'Система')
_BY_SLUG = {s['slug']: s for s in SECTIONS}

# старые адреса → новые разделы (redirect, если включён ADMIN_STATS_REDIRECTS=1)
LEGACY_REDIRECTS = {
    '/admin/users': 'users',
    '/admin/users/sections': 'sections',
    '/admin/users/returns': 'returns',
    '/admin/users/surveys': 'surveys',
}


# ──────────────────────────── helpers ────────────────────────────
def _db():
    from models import db
    return db


def _is_admin() -> bool:
    try:
        return getattr(current_user, 'is_admin', False) is True
    except Exception:
        return False


def _guard():
    if not current_user.is_authenticated or not _is_admin():
        abort(403)


def msk_today() -> date:
    return (datetime.utcnow() + timedelta(hours=3)).date()


def period_from_request():
    """(date_from, date_to, label) в МСК. ?p=today|7|30|custom&from=&to=."""
    p = (request.args.get('p') or '7').strip()
    today = msk_today()
    if p == 'today':
        return today, today, 'today'
    if p == '30':
        return today - timedelta(days=29), today, '30'
    if p == 'custom':
        try:
            d_from = date.fromisoformat(request.args.get('from') or '')
            d_to = date.fromisoformat(request.args.get('to') or '')
            if d_from <= d_to and (d_to - d_from).days <= 400:
                return d_from, d_to, 'custom'
        except Exception:
            pass
    return today - timedelta(days=6), today, '7'


def _utc_bounds(d_from: date, d_to: date):
    """funnel_events.created_at хранится в UTC → границы периода МСК сдвигаем на -3 ч."""
    start = datetime.combine(d_from, datetime.min.time()) - timedelta(hours=3)
    end = datetime.combine(d_to + timedelta(days=1), datetime.min.time()) - timedelta(hours=3)
    return start, end


def _day_expr() -> str:
    try:
        if _db().engine.dialect.name == 'postgresql':
            return "DATE(created_at + INTERVAL '3 hours')"
    except Exception:
        pass
    return "DATE(created_at, '+3 hours')"


def _q(sql: str, **params):
    try:
        return _db().session.execute(text(sql), params).fetchall()
    except Exception as e:
        _db().session.rollback()
        logger.warning('admin_stats query failed: %r', e)
        return []


def csv_response(rows, header, filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(header)
    for r in rows:
        w.writerow(list(r))
    data = '\ufeff' + buf.getvalue()
    return Response(data, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _nav():
    groups = []
    for g in GROUP_ORDER:
        items = [s for s in SECTIONS if s['group'] == g]
        if items:
            groups.append((g, items))
    return groups


def _render(section, template, **ctx):
    d_from, d_to, label = period_from_request()
    return render_template(template, nav=_nav(), section=section, sections=SECTIONS,
                           d_from=d_from, d_to=d_to, period=label, **ctx)


# ──────────────────────────── data ────────────────────────────
def funnel_counts(d_from: date, d_to: date) -> dict:
    """Уникальные пользователи/аноны по каждому шагу за период."""
    start, end = _utc_bounds(d_from, d_to)
    rows = _q("""
        SELECT event, COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id, CAST(id AS TEXT))) AS n
        FROM funnel_events WHERE created_at >= :s AND created_at < :e GROUP BY event
    """, s=start, e=end)
    return {str(r[0]): int(r[1] or 0) for r in rows}


def funnel_by_day(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    rows = _q(f"""
        SELECT {_day_expr()} AS day, event, COUNT(*) AS n
        FROM funnel_events WHERE created_at >= :s AND created_at < :e
        GROUP BY 1, 2 ORDER BY 1 DESC
    """, s=start, e=end)
    out = {}
    for day, ev, n in rows:
        out.setdefault(str(day), {})[str(ev)] = int(n or 0)
    return out


def revenue(d_from: date, d_to: date) -> float:
    start, end = _utc_bounds(d_from, d_to)
    pg = False
    try:
        pg = _db().engine.dialect.name == 'postgresql'
    except Exception:
        pass
    expr = "COALESCE((props->>'amount')::numeric, 0)" if pg else "COALESCE(CAST(json_extract(props, '$.amount') AS REAL), 0)"
    rows = _q(f"SELECT COALESCE(SUM({expr}), 0) FROM funnel_events "
              f"WHERE event = 'payment_success' AND created_at >= :s AND created_at < :e", s=start, e=end)
    try:
        return float(rows[0][0] or 0) if rows else 0.0
    except Exception:
        return 0.0


def dau(d: date) -> int:
    rows = _q("SELECT COUNT(DISTINCT user_id) FROM site_time_sections WHERE section = 'general' AND day = :d", d=d)
    try:
        return int(rows[0][0] or 0) if rows else 0
    except Exception:
        return 0


def sources_table(d_from: date, d_to: date):
    """По источнику первого визита: визиты, регистрации, анкеты, первые задачи, оплаты."""
    start, end = _utc_bounds(d_from, d_to)
    visits = {str(r[0] or ''): int(r[1] or 0) for r in _q("""
        SELECT COALESCE(source, ''), COUNT(DISTINCT COALESCE(anon_id, CAST(id AS TEXT)))
        FROM funnel_events WHERE event = 'visit' AND created_at >= :s AND created_at < :e GROUP BY 1
    """, s=start, e=end)}
    by_user = _q("""
        SELECT COALESCE(u.acq_source, fe.source, ''), fe.event, COUNT(DISTINCT fe.user_id)
        FROM funnel_events fe LEFT JOIN users u ON u.id = fe.user_id
        WHERE fe.user_id IS NOT NULL AND fe.event IN ('signup','intake_done','first_task_solved','payment_success')
          AND fe.created_at >= :s AND fe.created_at < :e
        GROUP BY 1, 2
    """, s=start, e=end)
    table = {}
    for src in set(list(visits.keys()) + [str(r[0] or '') for r in by_user]):
        table[src] = {'visit': visits.get(src, 0), 'signup': 0, 'intake_done': 0,
                      'first_task_solved': 0, 'payment_success': 0}
    for src, ev, n in by_user:
        table[str(src or '')][str(ev)] = int(n or 0)
    rows = []
    for src, d in table.items():
        rows.append({'source': src, 'title': SOURCE_TITLES.get(src, src or 'Не определён'), **d,
                     'cr_signup': _pct(d['signup'], d['visit']),
                     'cr_pay': _pct(d['payment_success'], d['signup'])})
    rows.sort(key=lambda r: (r['payment_success'], r['signup'], r['visit']), reverse=True)
    return rows


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


# ──────────────────────────── routes ────────────────────────────
@admin_stats_bp.route('/')
@login_required
def index():
    _guard()
    return redirect('/admin/stats/overview')


@admin_stats_bp.route('/<slug>')
@login_required
def section(slug):
    _guard()
    s = _BY_SLUG.get(slug)
    if not s:
        abort(404)
    if s['kind'] == 'embed':
        return _render(s, 'admin/stats_embed.html', target=s['target'])
    if s['kind'] == 'stub' or not s.get('ready'):
        return _render(s, 'admin/stats_stub.html')
    fn = globals().get(f'view_{slug}')
    if fn is not None:
        return fn(s)
    # блочные разделы из routes/admin_stats_sections.py
    try:
        from routes import admin_stats_sections as sec
        builder = sec.VIEWS.get(slug)
    except Exception as e:  # noqa: BLE001
        logger.warning('admin_stats_sections import failed: %r', e)
        builder = None
    if builder is None:
        return _render(s, 'admin/stats_stub.html')
    d_from, d_to, _ = period_from_request()
    try:
        blocks = builder(d_from, d_to)
    except Exception as e:  # noqa: BLE001
        logger.exception('admin_stats section %s failed', slug)
        blocks = [{'type': 'note', 'text': f'Раздел временно недоступен: {e!r}'}]
    return _render(s, 'admin/stats_blocks.html', blocks=blocks)


def view_overview(s):
    d_from, d_to, _ = period_from_request()
    today = msk_today()
    yesterday = today - timedelta(days=1)
    y_counts = funnel_counts(yesterday, yesterday)
    p_counts = funnel_counts(d_from, d_to)
    cards = []
    for ev, title in FUNNEL_STEPS:
        cards.append({'key': ev, 'title': title, 'yesterday': y_counts.get(ev, 0), 'period': p_counts.get(ev, 0),
                      'link': '/admin/stats/funnel'})
    cards.insert(0, {'key': 'dau', 'title': 'DAU (время на сайте)', 'yesterday': dau(yesterday),
                     'period': None, 'link': '/admin/stats/users'})
    cards.append({'key': 'limit_hit', 'title': 'Упёрлись в лимит', 'yesterday': y_counts.get('limit_hit', 0),
                  'period': p_counts.get('limit_hit', 0), 'link': '/admin/stats/limits'})
    rev_y = revenue(yesterday, yesterday)
    rev_p = revenue(d_from, d_to)
    return _render(s, 'admin/stats_overview.html', cards=cards, rev_y=rev_y, rev_p=rev_p,
                   yesterday=yesterday, today=today)


def view_funnel(s):
    d_from, d_to, _ = period_from_request()
    counts = funnel_counts(d_from, d_to)
    steps = []
    prev = None
    for ev, title in FUNNEL_STEPS:
        n = counts.get(ev, 0)
        steps.append({'event': ev, 'title': title, 'n': n,
                      'cr_prev': _pct(n, prev) if prev is not None else None,
                      'cr_first': _pct(n, counts.get('visit', 0)) if ev != 'visit' else None})
        prev = n
    days = funnel_by_day(d_from, d_to)
    if request.args.get('csv') == '1':
        rows = [(day,) + tuple(d.get(ev, 0) for ev, _ in FUNNEL_STEPS) for day, d in sorted(days.items())]
        return csv_response(rows, ('day',) + tuple(ev for ev, _ in FUNNEL_STEPS), 'funnel.csv')
    max_n = max([st['n'] for st in steps] + [1])
    return _render(s, 'admin/stats_funnel.html', steps=steps, days=days, step_keys=[ev for ev, _ in FUNNEL_STEPS],
                   max_n=max_n)


def view_sources(s):
    d_from, d_to, _ = period_from_request()
    rows = sources_table(d_from, d_to)
    if request.args.get('csv') == '1':
        return csv_response(
            [(r['source'], r['visit'], r['signup'], r['intake_done'], r['first_task_solved'], r['payment_success']) for r in rows],
            ('source', 'visit', 'signup', 'intake_done', 'first_task_solved', 'payment_success'), 'sources.csv')
    refs = _q("""
        SELECT COALESCE(ref, ''), COUNT(*) FROM funnel_events
        WHERE event = 'visit' AND ref IS NOT NULL AND created_at >= :s AND created_at < :e
        GROUP BY 1 ORDER BY 2 DESC LIMIT 30
    """, s=_utc_bounds(d_from, d_to)[0], e=_utc_bounds(d_from, d_to)[1])
    return _render(s, 'admin/stats_sources.html', rows=rows, refs=refs)


def view_env_flags(s):
    flags = []
    for k in ENV_FLAGS:
        v = os.environ.get(k)
        flags.append({'key': k, 'value': v if v is not None else '— (не задано)', 'set': v is not None})
    return _render(s, 'admin/stats_env.html', flags=flags)


# ──────────────────────────── install ────────────────────────────
def install(app) -> None:
    if not ENABLED or app.extensions.get('admin_stats_installed'):
        return
    app.extensions['admin_stats_installed'] = True
    if 'admin_stats' not in app.blueprints:
        app.register_blueprint(admin_stats_bp)

    if os.environ.get('ADMIN_STATS_REDIRECTS', '0') == '1':
        @app.before_request
        def _legacy_redirect():
            slug = LEGACY_REDIRECTS.get(request.path.rstrip('/'))
            if slug and request.args.get('embed') != '1' and _is_admin():
                return redirect(f'/admin/stats/{slug}')
    logger.info('ADMIN_STATS_V1 registered (/admin/stats)')
