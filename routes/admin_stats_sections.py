# -*- coding: utf-8 -*-
"""ADMIN_STATS_V1 — разделы панели, которые строятся на уже существующих таблицах
и на событиях funnel_events. Каждый view возвращает список «блоков» для
templates/admin/stats_blocks.html:

    {'type': 'cards', 'items': [{'title', 'value', 'sub'}]}
    {'type': 'table', 'title', 'header': [...], 'rows': [[...]], 'empty': '...'}
    {'type': 'note',  'text': '...'}
    {'type': 'bar',   'title', 'items': [{'label', 'value', 'pct'}]}

Все запросы fail-open: отсутствующая таблица/колонка превращается в заметку,
а не в 500. Поля users.is_founder / users.trial_until появятся в PR 19–20.10 —
до этого разделы «Основатели»/«Триал» показывают, чего не хватает.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta

from flask import request
from sqlalchemy import text

logger = logging.getLogger(__name__)

PLAN_PRICES = {  # ₽ в месяц для MRR
    'premium_monthly': 390, 'premium_yearly': 2790 / 12,
    'student_month': 490, 'student_year': 2990 / 12,
    'family_month': 890, 'teacher_month': 1990,
}
PLAN_TITLES = {
    'premium_monthly': 'Premium / мес (legacy)', 'premium_yearly': 'Premium / год (legacy)',
    'student_month': 'Ученик / мес', 'student_year': 'Ученик / год', 'family_month': 'Семья / мес',
    'teacher_month': 'Учитель / мес', 'probe_once': 'Пробник (разово)', 'sheet_once': 'PDF-листок (разово)',
    'method_week_once': 'Неделя метода (разово)', 'free': 'Бесплатный',
}
MRR_TARGET = 100_000
FOUNDER_DEADLINE = date(2027, 1, 31)


# ──────────────────────────── helpers ────────────────────────────
def _db():
    from models import db
    return db


def _pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


def _q(sql: str, **params):
    try:
        return _db().session.execute(text(sql), params).fetchall()
    except Exception as e:
        _db().session.rollback()
        logger.info('admin_stats_sections query skipped: %r', e)
        return None   # None = запрос не удался (нет таблицы/колонки)


def _scalar(sql: str, default=0, **params):
    rows = _q(sql, **params)
    if not rows:
        return default
    try:
        return rows[0][0] if rows[0][0] is not None else default
    except Exception:
        return default


def _has_column(table: str, col: str) -> bool:
    try:
        from sqlalchemy import inspect
        cols = [c['name'] for c in inspect(_db().engine).get_columns(table)]
        return col in cols
    except Exception:
        return False


def _has_table(table: str) -> bool:
    try:
        from sqlalchemy import inspect
        return inspect(_db().engine).has_table(table)
    except Exception:
        return False


def _utc_bounds(d_from: date, d_to: date):
    start = datetime.combine(d_from, datetime.min.time()) - timedelta(hours=3)
    end = datetime.combine(d_to + timedelta(days=1), datetime.min.time()) - timedelta(hours=3)
    return start, end


def _day_expr(col='created_at') -> str:
    return f"DATE({col} + INTERVAL '3 hours')" if _pg() else f"DATE({col}, '+3 hours')"


def _json_get(col: str, key: str) -> str:
    """SQL-выражение: props->>'key' (PG) / json_extract (SQLite)."""
    return f"({col}->>'{key}')" if _pg() else f"json_extract({col}, '$.{key}')"


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _fmt_pct(v):
    return '—' if v is None else f'{v}%'


def _events_by_day(event: str, d_from: date, d_to: date, uniq: bool = True):
    start, end = _utc_bounds(d_from, d_to)
    cnt = 'COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id))' if uniq else 'COUNT(*)'
    rows = _q(f"SELECT {_day_expr()} AS d, {cnt} FROM funnel_events "
              f"WHERE event = :e AND created_at >= :s AND created_at < :en GROUP BY 1 ORDER BY 1 DESC",
              e=event, s=start, en=end)
    return rows or []


def _event_total(event: str, d_from: date, d_to: date, uniq: bool = True):
    start, end = _utc_bounds(d_from, d_to)
    cnt = 'COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id))' if uniq else 'COUNT(*)'
    return int(_scalar(f"SELECT {cnt} FROM funnel_events WHERE event = :e AND created_at >= :s AND created_at < :en",
                       e=event, s=start, en=end) or 0)


def _dau_avg(d_from: date, d_to: date) -> float:
    rows = _q("SELECT day, COUNT(DISTINCT user_id) FROM site_time_sections "
              "WHERE section = 'general' AND day >= :a AND day <= :b GROUP BY day", a=d_from, b=d_to)
    if not rows:
        return 0.0
    return round(sum(int(r[1] or 0) for r in rows) / max(1, (d_to - d_from).days + 1), 1)


# ──────────────────────────── Монетизация ────────────────────────────
def subscriptions(d_from: date, d_to: date):
    blocks = []
    if not _has_table('subscriptions'):
        return [{'type': 'note', 'text': 'Таблица subscriptions ещё не создана.'}]
    now_iso = datetime.utcnow().isoformat()
    rows = _q("""SELECT plan, COUNT(*), COALESCE(SUM(CASE WHEN is_beta_access THEN 1 ELSE 0 END), 0)
                 FROM subscriptions WHERE status = 'active' AND (expires_at IS NULL OR expires_at > :now)
                 GROUP BY plan ORDER BY 2 DESC""", now=now_iso)
    if rows is None:
        rows = _q("""SELECT plan, COUNT(*), 0 FROM subscriptions WHERE status = 'active'
                     AND (expires_at IS NULL OR expires_at > :now) GROUP BY plan ORDER BY 2 DESC""", now=now_iso) or []
    active_total, paid_total, mrr = 0, 0, 0.0
    table_rows = []
    for plan, n, beta in rows:
        n, beta = int(n or 0), int(beta or 0)
        paid = n - beta
        price = PLAN_PRICES.get(str(plan), 0)
        plan_mrr = paid * price
        active_total += n
        paid_total += paid
        mrr += plan_mrr
        table_rows.append([PLAN_TITLES.get(str(plan), str(plan)), n, beta, paid, f'{plan_mrr:,.0f}'.replace(',', ' ')])
    start, end = _utc_bounds(d_from, d_to)
    new_in_period = int(_scalar("SELECT COUNT(*) FROM subscriptions WHERE created_at >= :s AND created_at < :e",
                                s=start.isoformat(), e=end.isoformat()) or 0)
    cancelled = int(_scalar("SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled'") or 0)
    expiring_7 = int(_scalar("""SELECT COUNT(*) FROM subscriptions WHERE status = 'active'
                                AND expires_at > :now AND expires_at <= :week""",
                             now=now_iso, week=(datetime.utcnow() + timedelta(days=7)).isoformat()) or 0)
    blocks.append({'type': 'cards', 'items': [
        {'title': 'Активных подписок', 'value': active_total, 'sub': f'из них бета/бесплатных: {active_total - paid_total}'},
        {'title': 'Платных', 'value': paid_total, 'sub': 'is_beta_access = false'},
        {'title': 'MRR, ₽ (оценка)', 'value': f'{mrr:,.0f}'.replace(',', ' '), 'sub': f'цель {MRR_TARGET:,} ₽ к концу февраля'.replace(',', ' ')},
        {'title': 'Новых за период', 'value': new_in_period, 'sub': 'строк в subscriptions'},
        {'title': 'Истекают за 7 дней', 'value': expiring_7, 'sub': 'активные, expires_at ≤ +7 дн'},
        {'title': 'Отмен всего', 'value': cancelled, 'sub': "status = 'cancelled'"},
    ]})
    blocks.append({'type': 'bar', 'title': 'Прогресс к 100 000 ₽/мес', 'items': [
        {'label': 'MRR', 'value': f'{mrr:,.0f} ₽'.replace(',', ' '), 'pct': min(100, round(100 * mrr / MRR_TARGET, 1))}]})
    blocks.append({'type': 'table', 'title': 'Активные подписки по тарифам',
                   'header': ['Тариф', 'Активных', 'Бета', 'Платных', 'MRR, ₽'], 'rows': table_rows,
                   'empty': 'Активных подписок нет.'})
    plans = _q("SELECT COALESCE(current_plan, 'free'), COUNT(*) FROM users GROUP BY 1 ORDER BY 2 DESC")
    if plans:
        blocks.append({'type': 'table', 'title': 'users.current_plan', 'header': ['План', 'Пользователей'],
                       'rows': [[PLAN_TITLES.get(str(p), str(p)), int(n)] for p, n in plans]})
    blocks.append({'type': 'note', 'text': 'MRR считается как платные активные подписки × цена/мес (годовые — /12). '
                   'Тарифы student_*/family/teacher появятся в PLAN_LIMITS после PR ЮKassa (19.10).'})
    return blocks


def payments(d_from: date, d_to: date):
    blocks = []
    start, end = _utc_bounds(d_from, d_to)
    amt, plan, pid = _json_get('props', 'amount'), _json_get('props', 'plan'), _json_get('props', 'payment_id')
    cast_amt = f"CAST({amt} AS NUMERIC)" if _pg() else f"CAST({amt} AS REAL)"
    totals = _q(f"""SELECT COALESCE({plan}, '—'), COUNT(*), COALESCE(SUM({cast_amt}), 0)
                    FROM funnel_events WHERE event = 'payment_success' AND created_at >= :s AND created_at < :e
                    GROUP BY 1 ORDER BY 3 DESC""", s=start, e=end) or []
    total_sum = sum(float(r[2] or 0) for r in totals)
    total_n = sum(int(r[1] or 0) for r in totals)
    blocks.append({'type': 'cards', 'items': [
        {'title': 'Оплат за период', 'value': total_n, 'sub': 'payment_success'},
        {'title': 'Выручка, ₽', 'value': f'{total_sum:,.0f}'.replace(',', ' '), 'sub': 'сумма props.amount'},
        {'title': 'Средний чек, ₽', 'value': f'{(total_sum / total_n) if total_n else 0:,.0f}'.replace(',', ' '), 'sub': ''},
    ]})
    blocks.append({'type': 'table', 'title': 'По тарифам', 'header': ['Тариф', 'Оплат', 'Сумма, ₽'],
                   'rows': [[PLAN_TITLES.get(str(p), str(p)), int(n), f'{float(s or 0):,.0f}'.replace(',', ' ')] for p, n, s in totals],
                   'empty': 'Оплат пока нет. События пишет services.funnel.payment_success() из webhook ЮKassa (PR 19.10).'})
    last = _q(f"""SELECT created_at, user_id, {plan}, {amt}, {pid}
                  FROM funnel_events WHERE event = 'payment_success' ORDER BY created_at DESC LIMIT 100""") or []
    blocks.append({'type': 'table', 'title': 'Последние 100 платежей', 'header': ['Когда (UTC)', 'user_id', 'Тариф', 'Сумма', 'payment_id'],
                   'rows': [[str(c)[:19], u, PLAN_TITLES.get(str(p), p), a, i] for c, u, p, a, i in last], 'empty': 'Пусто.'})
    if _has_table('subscriptions'):
        subs = _q("""SELECT created_at, user_id, plan, amount_rub, payment_id, status FROM subscriptions
                     WHERE payment_id IS NOT NULL ORDER BY id DESC LIMIT 50""") or []
        blocks.append({'type': 'table', 'title': 'subscriptions с payment_id (последние 50)',
                       'header': ['Создано', 'user_id', 'План', 'Сумма', 'payment_id', 'Статус'],
                       'rows': [[str(c)[:19], u, p, a, i, s] for c, u, p, a, i, s in subs], 'empty': 'Нет записей с payment_id.'})
    return blocks


def founders(d_from: date, d_to: date):
    blocks = []
    days_left = (FOUNDER_DEADLINE - (datetime.utcnow() + timedelta(hours=3)).date()).days
    cards = [{'title': 'До конца срока Основателей', 'value': max(0, days_left), 'sub': 'дней до 31.01.2027'}]
    if _has_column('users', 'is_founder'):
        n_f = int(_scalar("SELECT COUNT(*) FROM users WHERE is_founder = TRUE") or 0)
        cards.append({'title': 'Основателей', 'value': n_f, 'sub': 'users.is_founder'})
        paid = int(_scalar("""SELECT COUNT(DISTINCT fe.user_id) FROM funnel_events fe JOIN users u ON u.id = fe.user_id
                              WHERE fe.event = 'payment_success' AND u.is_founder = TRUE""") or 0)
        cards.append({'title': 'Основателей оплатили', 'value': paid, 'sub': _fmt_pct(_pct(paid, n_f)) + ' от основателей'})
    else:
        blocks.append({'type': 'note', 'text': 'Поля users.is_founder ещё нет — появится с миграцией в PR «/subscribe» (19.10). '
                       'Пока показываем только события оффера и оплаты годового доступа.'})
    start, end = _utc_bounds(d_from, d_to)
    clicks = _event_total('founder_offer_click', d_from, d_to)
    amt = _json_get('props', 'amount')
    yearly = int(_scalar(f"""SELECT COUNT(*) FROM funnel_events WHERE event = 'payment_success'
                             AND ({_json_get('props', 'plan')} = 'student_year' OR CAST({amt} AS TEXT) LIKE '2790%')
                             AND created_at >= :s AND created_at < :e""", s=start, e=end) or 0)
    cards += [{'title': 'Кликов по офферу', 'value': clicks, 'sub': 'founder_offer_click за период'},
              {'title': 'Годовых по 2 790 ₽', 'value': yearly, 'sub': 'ранний доступ Основателя'}]
    blocks.insert(0, {'type': 'cards', 'items': cards})
    blocks.append({'type': 'table', 'title': 'Клики по офферу по дням', 'header': ['День', 'Уникальных'],
                   'rows': [[str(d), int(n)] for d, n in _events_by_day('founder_offer_click', d_from, d_to)],
                   'empty': 'Кликов пока нет — событие шлёт window.track("founder_offer_click") с кнопки оффера (PR 20.10).'})
    return blocks


def trial(d_from: date, d_to: date):
    if not _has_column('users', 'trial_until'):
        return [{'type': 'note', 'text': 'Поля users.trial_until ещё нет — появится в PR «Триал 14 дней» (20.10, промпт 9). '
                 f'TRIAL_DAYS сейчас = {os.environ.get("TRIAL_DAYS", "не задан")}.'}]
    now = datetime.utcnow()
    active = int(_scalar("SELECT COUNT(*) FROM users WHERE trial_until > :n", n=now) or 0)
    expired = int(_scalar("SELECT COUNT(*) FROM users WHERE trial_until IS NOT NULL AND trial_until <= :n", n=now) or 0)
    soon = int(_scalar("SELECT COUNT(*) FROM users WHERE trial_until > :n AND trial_until <= :n3", n=now, n3=now + timedelta(days=3)) or 0)
    conv = int(_scalar("""SELECT COUNT(DISTINCT fe.user_id) FROM funnel_events fe JOIN users u ON u.id = fe.user_id
                          WHERE fe.event = 'payment_success' AND u.trial_until IS NOT NULL""") or 0)
    given = active + expired
    return [{'type': 'cards', 'items': [
        {'title': 'Выдано триалов', 'value': given, 'sub': 'users.trial_until IS NOT NULL'},
        {'title': 'Активных', 'value': active, 'sub': 'trial_until > сейчас'},
        {'title': 'Истекают за 3 дня', 'value': soon, 'sub': 'момент для письма'},
        {'title': 'Истекли', 'value': expired, 'sub': ''},
        {'title': 'Триал → оплата', 'value': conv, 'sub': _fmt_pct(_pct(conv, given)) + ' от выданных'},
    ]}]


def limits(d_from: date, d_to: date):
    blocks = []
    hits_users = _event_total('limit_hit', d_from, d_to)
    hits_total = _event_total('limit_hit', d_from, d_to, uniq=False)
    dau = _dau_avg(d_from, d_to)
    blocks.append({'type': 'cards', 'items': [
        {'title': 'Упёрлись в лимит (уник.)', 'value': hits_users, 'sub': 'limit_hit за период'},
        {'title': 'Срабатываний', 'value': hits_total, 'sub': 'всего событий'},
        {'title': 'Средний DAU', 'value': dau, 'sub': 'site_time_sections'},
        {'title': 'Доля от DAU', 'value': _fmt_pct(_pct(hits_users / max(1, (d_to - d_from).days + 1), dau) if dau else None),
         'sub': 'уник. в день / DAU'},
        {'title': 'FREE_TASKS_PER_DAY', 'value': os.environ.get('FREE_TASKS_PER_DAY', '—'), 'sub': f"FREE_AI_PER_DAY = {os.environ.get('FREE_AI_PER_DAY', '—')}"},
        {'title': 'PAYWALL_AB', 'value': os.environ.get('PAYWALL_AB', '—'), 'sub': f"PAYWALL_ENABLED = {os.environ.get('PAYWALL_ENABLED', '—')}"},
    ]})
    start, end = _utc_bounds(d_from, d_to)
    kind, ab = _json_get('props', 'kind'), _json_get('props', 'ab')
    by_kind = _q(f"""SELECT COALESCE({kind}, 'task'), COALESCE(CAST({ab} AS TEXT), '—'), COUNT(DISTINCT user_id), COUNT(*)
                     FROM funnel_events WHERE event = 'limit_hit' AND created_at >= :s AND created_at < :e
                     GROUP BY 1, 2 ORDER BY 3 DESC""", s=start, e=end) or []
    blocks.append({'type': 'table', 'title': 'По типу лимита и A/B-когорте', 'header': ['Лимит', 'Когорта', 'Уник.', 'Событий'],
                   'rows': [[k, a, int(u), int(n)] for k, a, u, n in by_kind],
                   'empty': 'Событий limit_hit пока нет. Их будет слать экран лимита: window.track("limit_hit", {kind: "task"|"ai", ab: 0|1}) — PR 21.10.'})
    blocks.append({'type': 'table', 'title': 'По дням', 'header': ['День', 'Уник. пользователей'],
                   'rows': [[str(d), int(n)] for d, n in _events_by_day('limit_hit', d_from, d_to)], 'empty': 'Пусто.'})
    blocks.append({'type': 'note', 'text': 'Решение 11.11 о 100% лимитов: сравните долю упёршихся и оплаты в когортах ab=1 (лимиты) и ab=0 (контроль).'})
    return blocks


def paywall(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    frm = _json_get('props', 'from')
    rows = _q(f"""SELECT COALESCE({frm}, COALESCE(path, '—')), event, COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id))
                  FROM funnel_events WHERE event IN ('paywall_view', 'subscribe_view', 'payment_success')
                  AND created_at >= :s AND created_at < :e GROUP BY 1, 2""", s=start, e=end) or []
    table = {}
    for src, ev, n in rows:
        table.setdefault(str(src), {'paywall_view': 0, 'subscribe_view': 0, 'payment_success': 0})[str(ev)] = int(n or 0)
    out = []
    for src, d in sorted(table.items(), key=lambda kv: -kv[1]['payment_success'] - kv[1]['subscribe_view']):
        out.append([src, d['paywall_view'], d['subscribe_view'], _fmt_pct(_pct(d['subscribe_view'], d['paywall_view'])),
                    d['payment_success'], _fmt_pct(_pct(d['payment_success'], d['subscribe_view']))])
    pv, sv, ps = (_event_total(e, d_from, d_to) for e in ('paywall_view', 'subscribe_view', 'payment_success'))
    return [
        {'type': 'cards', 'items': [
            {'title': 'Видели paywall', 'value': pv, 'sub': 'paywall_view'},
            {'title': 'Открыли /subscribe', 'value': sv, 'sub': _fmt_pct(_pct(sv, pv)) + ' от paywall'},
            {'title': 'Оплатили', 'value': ps, 'sub': _fmt_pct(_pct(ps, sv)) + ' от витрины'},
        ]},
        {'type': 'table', 'title': 'По точке входа (from=)', 'header': ['Откуда', 'Paywall', 'Витрина', 'CR', 'Оплаты', 'CR'],
         'rows': out, 'empty': 'Нет событий. paywall_view шлёт экран лимита/paywall, subscribe_view — страница /subscribe?from=… (PR 19–21.10).'},
        {'type': 'note', 'text': f"PAYWALL_PREFIXES = {os.environ.get('PAYWALL_PREFIXES', '—')}"},
    ]


def cohorts(d_from: date, d_to: date):
    if not _has_column('users', 'created_at'):
        return [{'type': 'note', 'text': 'Нет users.created_at.'}]
    weeks = 10
    since = datetime.utcnow() - timedelta(weeks=weeks)
    wk = "TO_CHAR(DATE_TRUNC('week', u.created_at), 'YYYY-MM-DD')" if _pg() else "DATE(u.created_at, 'weekday 1', '-7 days')"
    rows = _q(f"""
        SELECT {wk} AS week,
               COUNT(DISTINCT u.id),
               COUNT(DISTINCT CASE WHEN fe.event = 'intake_done' THEN u.id END),
               COUNT(DISTINCT CASE WHEN fe.event = 'first_task_solved' THEN u.id END),
               COUNT(DISTINCT CASE WHEN fe.event = 'payment_success' THEN u.id END)
        FROM users u LEFT JOIN funnel_events fe ON fe.user_id = u.id
        WHERE u.created_at >= :since AND COALESCE(u.is_guest, FALSE) = FALSE
        GROUP BY 1 ORDER BY 1 DESC""", since=since) or []
    out = []
    for w, n, i, f, p in rows:
        n, i, f, p = int(n or 0), int(i or 0), int(f or 0), int(p or 0)
        out.append([str(w)[:10], n, i, _fmt_pct(_pct(i, n)), f, _fmt_pct(_pct(f, n)), p, _fmt_pct(_pct(p, n))])
    return [
        {'type': 'table', 'title': f'Когорты по неделе регистрации (последние {weeks})',
         'header': ['Неделя с', 'Регистраций', 'Анкета', '%', 'Первая задача', '%', 'Оплата', '%'], 'rows': out,
         'empty': 'Нет регистраций за период.'},
        {'type': 'note', 'text': 'События intake_done/first_task_solved пишутся с момента деплоя FUNNEL_V1, поэтому у старых когорт '
         'эти колонки будут занижены. Оплаты — полные (из webhook).'},
    ]


# ──────────────────────────── Активность / Продукт ────────────────────────────
def streaks(d_from: date, d_to: date):
    blocks = []
    if not _has_table('streak_records'):
        return [{'type': 'note', 'text': 'Таблицы streak_records нет.'}]
    buckets = [('0', 0, 0), ('1–2', 1, 2), ('3–6', 3, 6), ('7–13', 7, 13), ('14–29', 14, 29), ('30+', 30, 10 ** 6)]
    total = int(_scalar("SELECT COUNT(*) FROM streak_records") or 0)
    items = []
    for label, lo, hi in buckets:
        n = int(_scalar("SELECT COUNT(*) FROM streak_records WHERE current_streak >= :lo AND current_streak <= :hi", lo=lo, hi=hi) or 0)
        items.append({'label': f'серия {label}', 'value': n, 'pct': _pct(n, total) or 0})
    ge7 = int(_scalar("SELECT COUNT(*) FROM streak_records WHERE current_streak >= 7") or 0)
    avg_max = _scalar("SELECT AVG(max_streak) FROM streak_records", default=0)
    cards = [{'title': 'Записей серий', 'value': total, 'sub': 'streak_records'},
             {'title': 'Серия ≥ 7 дней', 'value': ge7, 'sub': _fmt_pct(_pct(ge7, total)) + ' от всех'},
             {'title': 'Средняя макс. серия', 'value': round(float(avg_max or 0), 1), 'sub': 'max_streak'}]
    if _has_column('users', 'xp'):
        cards.append({'title': 'XP всего', 'value': f"{int(_scalar('SELECT COALESCE(SUM(xp),0) FROM users') or 0):,}".replace(',', ' '), 'sub': 'users.xp'})
    blocks.append({'type': 'cards', 'items': cards})
    blocks.append({'type': 'bar', 'title': 'Распределение текущих серий', 'items': items})
    top = _q("""SELECT s.user_id, u.nickname, s.current_streak, s.max_streak FROM streak_records s
                LEFT JOIN users u ON u.id = s.user_id ORDER BY s.current_streak DESC LIMIT 20""") or []
    blocks.append({'type': 'table', 'title': 'Топ-20 по текущей серии', 'header': ['user_id', 'Ник', 'Серия', 'Макс.'],
                   'rows': [[a, b or '—', c, d] for a, b, c, d in top], 'empty': 'Пусто.'})
    blocks.append({'type': 'note', 'text': 'Контроль красной линии: после включения лимита 3 задачи доля «серия ≥ 7» не должна падать. '
                   'Снимайте значение каждое утро 1–11 ноября.'})
    return blocks


def ai_usage(d_from: date, d_to: date):
    if not _has_table('usage_daily'):
        return [{'type': 'note', 'text': 'Таблицы usage_daily нет.'}]
    a, b = d_from.isoformat(), d_to.isoformat()
    rows = _q("""SELECT date, COUNT(DISTINCT user_id), COALESCE(SUM(tasks_completed),0), COALESCE(SUM(ai_explanations_used),0),
                        COALESCE(SUM(tokens_consumed),0), COALESCE(SUM(cost_usd),0)
                 FROM usage_daily WHERE date >= :a AND date <= :b GROUP BY date ORDER BY date DESC""", a=a, b=b) or []
    tot_users = int(_scalar("SELECT COUNT(DISTINCT user_id) FROM usage_daily WHERE date >= :a AND date <= :b", a=a, b=b) or 0)
    tot_ai = sum(int(r[3] or 0) for r in rows)
    tot_cost = sum(float(r[5] or 0) for r in rows)
    free_ai = int(os.environ.get('FREE_AI_PER_DAY', '3') or 3)
    at_limit = int(_scalar("SELECT COUNT(*) FROM usage_daily WHERE date >= :a AND date <= :b AND ai_explanations_used >= :l",
                           a=a, b=b, l=free_ai) or 0)
    top = _q("""SELECT ud.user_id, u.nickname, COALESCE(u.current_plan,'free'), SUM(ud.ai_explanations_used), SUM(ud.tasks_completed), SUM(ud.cost_usd)
                FROM usage_daily ud LEFT JOIN users u ON u.id = ud.user_id WHERE ud.date >= :a AND ud.date <= :b
                GROUP BY ud.user_id, u.nickname, u.current_plan ORDER BY 4 DESC LIMIT 15""", a=a, b=b) or []
    return [
        {'type': 'cards', 'items': [
            {'title': 'Пользователей с активностью', 'value': tot_users, 'sub': 'usage_daily за период'},
            {'title': 'ИИ-разборов', 'value': tot_ai, 'sub': 'ai_explanations_used'},
            {'title': 'Расход на модели, $', 'value': round(tot_cost, 2), 'sub': 'cost_usd'},
            {'title': f'Дней на лимите ≥{free_ai}', 'value': at_limit, 'sub': 'user-day с ai ≥ FREE_AI_PER_DAY'},
        ]},
        {'type': 'table', 'title': 'По дням', 'header': ['Дата', 'Польз.', 'Задач', 'ИИ-разборов', 'Токенов', 'Cost $'],
         'rows': [[str(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), round(float(r[5] or 0), 3)] for r in rows], 'empty': 'Нет данных.'},
        {'type': 'table', 'title': 'Топ-15 по ИИ-разборам', 'header': ['user_id', 'Ник', 'План', 'ИИ', 'Задач', 'Cost $'],
         'rows': [[u, n or '—', PLAN_TITLES.get(str(p), p), int(ai or 0), int(t or 0), round(float(c or 0), 3)] for u, n, p, ai, t, c in top], 'empty': 'Пусто.'},
    ]


def drawings_method_week(d_from: date, d_to: date):
    blocks = []
    if _has_table('geo_drawing_history'):
        rows = _q(f"""SELECT {_day_expr()} AS d, COUNT(*), COUNT(DISTINCT user_id) FROM geo_drawing_history
                      WHERE created_at >= :s AND created_at < :e GROUP BY 1 ORDER BY 1 DESC""", s=_utc_bounds(d_from, d_to)[0], e=_utc_bounds(d_from, d_to)[1]) or []
        total = sum(int(r[1]) for r in rows)
        blocks.append({'type': 'cards', 'items': [
            {'title': 'Чертежей за период', 'value': total, 'sub': 'geo_drawing_history'},
            {'title': 'Уник. пользователей', 'value': int(_scalar("SELECT COUNT(DISTINCT user_id) FROM geo_drawing_history WHERE created_at >= :s AND created_at < :e",
                                                                  s=_utc_bounds(d_from, d_to)[0], e=_utc_bounds(d_from, d_to)[1]) or 0), 'sub': ''},
        ]})
        blocks.append({'type': 'table', 'title': 'Чертежи по дням', 'header': ['День', 'Чертежей', 'Пользователей'],
                       'rows': [[str(d), int(n), int(u)] for d, n, u in rows], 'empty': 'Нет чертежей за период.'})
    else:
        blocks.append({'type': 'note', 'text': 'Таблицы geo_drawing_history нет.'})
    start, end = _utc_bounds(d_from, d_to)
    pw = _q("""SELECT COALESCE(path, '—'), COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id)) FROM funnel_events
               WHERE event = 'paywall_view' AND created_at >= :s AND created_at < :e GROUP BY 1 ORDER BY 2 DESC LIMIT 20""", s=start, e=end) or []
    blocks.append({'type': 'table', 'title': 'Paywall по страницам (/geometry/draw, /method_week, /figures/generate)',
                   'header': ['Путь', 'Уник.'], 'rows': [[p, int(n)] for p, n in pw],
                   'empty': 'Событий paywall_view пока нет — их начнёт слать method_week/paywall.py после PR 21.10.'})
    return blocks


def referrals(d_from: date, d_to: date):
    blocks = []
    start, end = _utc_bounds(d_from, d_to)
    ref_visits = _q(r"""SELECT ref, COUNT(*) FROM funnel_events WHERE event = 'visit' AND ref LIKE 'u\_%' ESCAPE '\'
                       AND created_at >= :s AND created_at < :e GROUP BY ref ORDER BY 2 DESC LIMIT 30""", s=start, e=end) or []
    if _has_column('users', 'invited_by'):
        inv_total = int(_scalar("SELECT COUNT(*) FROM users WHERE invited_by IS NOT NULL") or 0)
        top = _q("""SELECT i.invited_by, u.nickname, COUNT(*) AS invited,
                           COUNT(DISTINCT CASE WHEN fe.event = 'payment_success' THEN i.id END) AS paid
                    FROM users i LEFT JOIN users u ON u.id = i.invited_by
                    LEFT JOIN funnel_events fe ON fe.user_id = i.id
                    WHERE i.invited_by IS NOT NULL GROUP BY i.invited_by, u.nickname ORDER BY invited DESC LIMIT 20""") or []
        blocks.append({'type': 'cards', 'items': [
            {'title': 'Приглашённых всего', 'value': inv_total, 'sub': 'users.invited_by'},
            {'title': 'Визитов по u_-ссылкам', 'value': sum(int(n) for _, n in ref_visits), 'sub': 'за период'},
        ]})
        blocks.append({'type': 'table', 'title': 'Топ пригласивших', 'header': ['user_id', 'Ник', 'Приглашено', 'Из них оплатили'],
                       'rows': [[a, b or '—', int(c), int(d)] for a, b, c, d in top],
                       'empty': 'invited_by пока никому не проставлен. Проставлять при регистрации по ?ref=u_<id> — PR 27.10.'})
    else:
        blocks.append({'type': 'note', 'text': 'Поля users.invited_by нет — его создаёт services/funnel.py при первом запуске.'})
    blocks.append({'type': 'table', 'title': 'Визиты по реферальным меткам', 'header': ['ref', 'Визитов'],
                   'rows': [[r, int(n)] for r, n in ref_visits], 'empty': 'Нет визитов с ?ref=u_<id>.'})
    return blocks


def teachers_parents(d_from: date, d_to: date):
    blocks = []
    roles = _q("SELECT COALESCE(role, 'student'), COUNT(*) FROM users WHERE COALESCE(is_guest, FALSE) = FALSE GROUP BY 1 ORDER BY 2 DESC") or []
    blocks.append({'type': 'table', 'title': 'Пользователи по ролям', 'header': ['Роль', 'Кол-во'],
                   'rows': [[r, int(n)] for r, n in roles], 'empty': 'Нет данных.'})
    start, end = _utc_bounds(d_from, d_to)
    src = _q("""SELECT COALESCE(source, '—'), COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), anon_id)) FROM funnel_events
                WHERE event = 'visit' AND source IN ('teacher', 'parent') AND created_at >= :s AND created_at < :e GROUP BY 1""", s=start, e=end) or []
    blocks.append({'type': 'table', 'title': 'Визиты по меткам teacher/parent за период', 'header': ['Источник', 'Уник.'],
                   'rows': [[s, int(n)] for s, n in src], 'empty': 'Нет визитов с ?ref=teacher_<id> / ?ref=parent.'})
    for table, title in (('teacher_students', 'Связки учитель–ученик'), ('parent_children', 'Связки родитель–ребёнок'),
                         ('classes', 'Классы')):
        if _has_table(table):
            blocks.append({'type': 'cards', 'items': [{'title': title, 'value': int(_scalar(f'SELECT COUNT(*) FROM {table}') or 0), 'sub': table}]})
    blocks.append({'type': 'note', 'text': 'Тарифы Семья 890 ₽ и Учитель 1 990 ₽ появятся в PLAN_LIMITS в PR ЮKassa (19.10); '
                   'активность классов добавим, когда появятся связки в routes/parent_teacher.py.'})
    return blocks


def curator(d_from: date, d_to: date):
    blocks = []
    if _has_table('curator_states'):
        n = int(_scalar('SELECT COUNT(*) FROM curator_states') or 0)
        blocks.append({'type': 'cards', 'items': [{'title': 'Состояний куратора', 'value': n, 'sub': 'curator_states'}]})
    try:
        from flask import current_app
        links = [str(r.rule) for r in current_app.url_map.iter_rules()
                 if 'plan-status' in str(r.rule) or 'budget' in str(r.rule)]
    except Exception:
        links = []
    if links:
        blocks.append({'type': 'links', 'title': 'Существующие страницы', 'items': links})
    blocks.append({'type': 'note', 'text': 'Статусы планов куратора считаются в services/curator_plan_service.check_plan_status(); '
                   'сводную таблицу по статусам добавим после PR 25.10, когда план куратора станет частью Premium.'})
    return blocks


VIEWS = {
    'subscriptions': subscriptions, 'payments': payments, 'founders': founders, 'trial': trial,
    'limits': limits, 'paywall': paywall, 'cohorts': cohorts, 'streaks': streaks, 'ai_usage': ai_usage,
    'drawings_method_week': drawings_method_week, 'referrals': referrals, 'teachers_parents': teachers_parents,
    'curator': curator,
}
