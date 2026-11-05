# -*- coding: utf-8 -*-
"""ADMIN_STATS_V3 (2026-11-05) — «Пользователи», «Возвраты» и «Опросы и оценки» как обычные
разделы панели с общим фильтром периода (раньше — iframe на отдельные страницы).

Старые страницы остаются доступными: /admin/users?embed=1, /admin/users/returns?embed=1,
/admin/users/surveys. Здесь — компактные отчёты на тех же данных, но за выбранный период.
Формат блоков — как в routes/admin_stats_sections.py (ячейка {'text','href'} = ссылка).
Builder может вернуть flask.Response (например, CSV) — панель отдаст его как есть.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import request

from routes.admin_stats_sections import _fmt_pct, _has_column, _has_table, _pct, _q, _utc_bounds

logger = logging.getLogger(__name__)

MSK = timedelta(hours=3)
LIMIT_USERS = 200
GAPS = (15, 30, 60, 120)
READINESS = {'yes': 'Да, готов!', 'try': 'Постараюсь, но не обещаю каждый день', 'not_yet': 'Пока не готов'}


def _dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ')[:26]) if v else None
    except Exception:
        return None


def _in(ids) -> str:
    return ','.join(str(int(i)) for i in ids) or 'NULL'


def _nicks(ids) -> dict:
    ids = list(ids)[:2000]
    if not ids or not _has_column('users', 'nickname'):
        return {}
    return {int(r[0]): (r[1] or '') for r in (_q(f'SELECT id, nickname FROM users WHERE id IN ({_in(ids)})') or [])}


def _user_cell(uid, nicks):
    return {'text': nicks.get(uid) or 'Без ника', 'href': f'/admin/stats/person?id={uid}'}


def _fmt_dt(v):
    d = _dt(v)
    return d.strftime('%d.%m.%Y %H:%M') if d else '—'


def _activity(start: datetime, end: datetime):
    """{user_id: [datetime в периоде]} по всем действиям в БД (как страница «Возвраты»)."""
    from services.user_returns import collect_events
    events, _ = collect_events()
    out = {}
    for uid, ts in events.items():
        inside = [t for t in ts if start <= t < end]
        if inside:
            out[uid] = inside
    return out


# ──────────────────────────── Возвраты ────────────────────────────
def returns(d_from: date, d_to: date):
    from services.user_returns import sessions_of
    try:
        gap = int(request.args.get('gap', 60))
    except ValueError:
        gap = 60
    gap = gap if gap in GAPS else 60
    start, end = _utc_bounds(d_from, d_to)
    try:
        act = _activity(start, end)
    except Exception as e:  # noqa: BLE001
        logger.warning('returns: %r', e)
        return [{'type': 'note', 'text': f'Не удалось собрать события: {e!r}'}]
    visits = {u: len(sessions_of(ts, gap)) for u, ts in act.items()}
    total = len(visits)
    if not total:
        return [{'type': 'note', 'text': 'За выбранный период действий пользователей нет.'}]
    exact = defaultdict(int)
    for n in visits.values():
        exact[n] += 1
    returned = sum(c for n, c in exact.items() if n >= 2)
    total_visits = sum(visits.values())
    max_n = 10
    rows = []
    for n in range(1, max_n + 1):
        at_least = sum(c for s, c in exact.items() if s >= n)
        rows.append(['первый визит (не возвращались)' if n == 1 else f'вернулись {n}-й раз',
                     exact.get(n, 0), at_least, _fmt_pct(_pct(at_least, total))])
    top = sorted(visits.items(), key=lambda kv: -kv[1])[:20]
    nicks = _nicks([u for u, _ in top])
    switch = {'type': 'tabs', 'title': 'Пауза между визитами',
              'items': [{'text': f'{g} мин', 'active': g == gap,
                         'href': f'?gap={g}&p={request.args.get("p", "7")}&from={d_from}&to={d_to}'} for g in GAPS]}
    return [
        switch,
        {'type': 'cards', 'items': [
            {'title': 'Людей с действиями', 'value': total, 'sub': 'в выбранном периоде'},
            {'title': 'Вернулись хотя бы раз', 'value': returned, 'sub': _fmt_pct(_pct(returned, total))},
            {'title': 'Визитов', 'value': total_visits, 'sub': f'в среднем {round(total_visits / total, 2)} на человека'},
        ]},
        {'type': 'table', 'title': 'Сколько раз возвращались',
         'header': ['Сколько визитов', 'Ровно столько', 'Столько и более', '% от всех'], 'rows': rows},
        {'type': 'table', 'title': 'Чаще всего заходят (топ-20)', 'header': ['Пользователь', 'ID', 'Визитов', 'Возвращений'],
         'rows': [[_user_cell(u, nicks), u, v, v - 1] for u, v in top]},
        {'type': 'note', 'text': 'Визит — серия действий с паузами не более выбранного порога. Действия берутся из всех таблиц БД '
         'с user_id и временем. Подробные таблицы «когда заходил в последний раз» — на старой странице: /admin/users/last_seen.'},
    ]


# ──────────────────────────── Опросы ────────────────────────────
def _dist_rows(counts: dict, labels: dict):
    total = sum(counts.get(k, 0) for k in labels)
    return [[label, counts.get(k, 0), _fmt_pct(_pct(counts.get(k, 0), total))] for k, label in labels.items()], total


def surveys(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    blocks = [{'type': 'note', 'text': 'Ответы за выбранный период (по дате ответа). Как это связано с возвратами и оплатой — '
               'в разделе «Опросы и поведение».'}]
    if _has_table('site_feedback'):
        rows = _q('SELECT user_id, rating, feedback_text, answered_at FROM site_feedback '
                  'WHERE answered_at IS NOT NULL AND rating BETWEEN 1 AND 5 AND answered_at >= :s AND answered_at < :e '
                  'ORDER BY answered_at DESC', s=start, e=end) or []
        counts = defaultdict(int)
        for _, r, _t, _a in rows:
            counts[int(r)] += 1
        pending = int((_q('SELECT COUNT(*) FROM site_feedback WHERE answered_at IS NULL') or [[0]])[0][0] or 0)
        table, total = _dist_rows(counts, {n: f'{n} / 5' for n in range(1, 6)})
        avg = round(sum(n * c for n, c in counts.items()) / total, 2) if total else 0
        nicks = _nicks([int(r[0]) for r in rows[:100]])
        blocks += [
            {'type': 'cards', 'items': [{'title': 'Ответили «Как тебе сайт?»', 'value': total, 'sub': 'за период'},
                                        {'title': 'Средняя оценка', 'value': avg, 'sub': 'из 5'},
                                        {'title': 'Ожидают ответа', 'value': pending, 'sub': 'за всё время'}]},
            {'type': 'table', 'title': 'Опрос «Как тебе сайт?»: оценки', 'header': ['Оценка', 'Ответов', 'Доля'], 'rows': table},
            {'type': 'table', 'left': True, 'title': 'Последние отзывы (до 100)', 'header': ['Пользователь', 'Оценка', 'Отзыв', 'Когда (UTC)'],
             'rows': [[_user_cell(int(u), nicks), f'{r} / 5', t or '—', _fmt_dt(a)] for u, r, t, a in rows[:100]],
             'empty': 'Ответов за период нет.'},
        ]
    if _has_table('readiness_survey_answers'):
        rows = _q('SELECT user_id, answer, answered_at FROM readiness_survey_answers '
                  'WHERE answered_at >= :s AND answered_at < :e ORDER BY answered_at DESC', s=start, e=end) or []
        counts = defaultdict(int)
        for _, a, _t in rows:
            counts[a] += 1
        table, total = _dist_rows(counts, READINESS)
        nicks = _nicks([int(r[0]) for r in rows[:100]])
        blocks += [
            {'type': 'cards', 'items': [{'title': 'Ответили «Готов заниматься каждый день?»', 'value': total, 'sub': 'за период'}]},
            {'type': 'table', 'title': 'Опрос «Готов заниматься каждый день?»', 'header': ['Ответ', 'Ответов', 'Доля'], 'rows': table},
            {'type': 'table', 'left': True, 'title': 'Последние ответы (до 100)', 'header': ['Пользователь', 'Ответ', 'Когда (UTC)'],
             'rows': [[_user_cell(int(u), nicks), READINESS.get(a, a), _fmt_dt(t)] for u, a, t in rows[:100]],
             'empty': 'Ответов за период нет.'},
        ]
    if _has_table('exit_answers'):
        from services.exit_question import OPTIONS, TRIGGER_TITLES
        rows = _q('SELECT user_id, kind, answer, answer_text, status, created_at FROM exit_answers '
                  'WHERE created_at >= :s AND created_at < :e ORDER BY created_at DESC', s=start, e=end) or []
        answered = [r for r in rows if r[4] == 'answered']
        dist = defaultdict(int)
        for _, kind, ans, _t, _s, _c in answered:
            dist[(kind, ans)] += 1
        dist_rows = [[TRIGGER_TITLES.get(k, k), OPTIONS.get(k, {}).get(a, a), n, _fmt_pct(_pct(n, sum(
            v for (kk, _), v in dist.items() if kk == k)))] for (k, a), n in sorted(dist.items(), key=lambda kv: (kv[0][0], -kv[1]))]
        nicks = _nicks([int(r[0]) for r in rows[:100]])
        blocks += [
            {'type': 'cards', 'items': [
                {'title': 'Спросили «что остановило?»', 'value': len(rows), 'sub': 'за период'},
                {'title': 'Ответили', 'value': len(answered), 'sub': _fmt_pct(_pct(len(answered), len(rows))) + ' от спрошенных'},
            ]},
            {'type': 'table', 'left': True, 'title': 'Вопрос «что остановило?»: ответы',
             'header': ['Когда спрашивали', 'Ответ', 'Ответов', 'Доля'], 'rows': dist_rows,
             'empty': 'Ответов за период нет. Вопрос задаётся после брошенной оплаты и после перерыва от 7 дней.'},
            {'type': 'table', 'left': True, 'title': 'Последние ответы «что остановило?» (до 100)',
             'header': ['Пользователь', 'Когда спрашивали', 'Ответ', 'Комментарий', 'Когда (UTC)'],
             'rows': [[_user_cell(int(u), nicks), TRIGGER_TITLES.get(k, k),
                       'пропустил' if st == 'dismissed' else OPTIONS.get(k, {}).get(a, a), t or '—', _fmt_dt(c)]
                      for u, k, a, t, st, c in rows[:100]],
             'empty': 'Пока никого не спрашивали.'},
        ]
    if len(blocks) == 1:
        blocks.append({'type': 'note', 'text': 'Таблиц с ответами опросов пока нет.'})
    return blocks


# ──────────────────────────── Пользователи ────────────────────────────
def users(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    need = ('nickname', 'created_at', 'last_login', 'login_count', 'experience_points', 'site_seconds_total')
    sel = ', '.join(c if _has_column('users', c) else f'NULL AS {c}' for c in need)
    guest = ' AND COALESCE(is_guest, FALSE) = FALSE' if _has_column('users', 'is_guest') else ''
    total_users = int((_q(f'SELECT COUNT(*) FROM users WHERE 1=1{guest}') or [[0]])[0][0] or 0)
    new_rows = _q(f'SELECT id, {sel} FROM users WHERE created_at >= :s AND created_at < :e{guest} '
                  'ORDER BY created_at DESC', s=start, e=end)
    if new_rows is None:
        return [{'type': 'note', 'text': 'Не удалось прочитать таблицу users.'}]

    table_rows = [[{'text': r[1] or 'Без ника', 'href': f'/admin/stats/person?id={r[0]}'}, r[0], _fmt_dt(r[2]), _fmt_dt(r[3]),
                   r[4] or 0, r[5] or 0, round((r[6] or 0) / 60, 1)] for r in new_rows]
    if request.args.get('csv') == '1':
        from routes.admin_stats import csv_response
        return csv_response([(r[0], r[1] or '', _fmt_dt(r[2]), _fmt_dt(r[3]), r[4] or 0, r[5] or 0, round((r[6] or 0) / 60, 1))
                             for r in new_rows],
                            ('id', 'nickname', 'registered_utc', 'last_login_utc', 'logins', 'xp', 'minutes_on_site'),
                            'users_registered.csv')

    blocks = []
    cards = [{'title': 'Всего пользователей', 'value': total_users, 'sub': 'без гостей'},
             {'title': 'Зарегистрировались за период', 'value': len(new_rows), 'sub': ''}]
    day_rows = []
    try:
        act = _activity(start, end)
        by_day = defaultdict(set)
        for uid, ts in act.items():
            for t in ts:
                by_day[(t + MSK).date()].add(uid)
        span = (d_to - d_from).days + 1
        dau = [len(by_day.get(d_from + timedelta(days=i), ())) for i in range(span)]
        cards += [{'title': 'Были активны за период', 'value': len(act), 'sub': 'любое действие в БД'},
                  {'title': 'Средний DAU', 'value': round(sum(dau) / max(1, span), 1), 'sub': f'за {span} дн.'},
                  {'title': 'Пик DAU', 'value': max(dau) if dau else 0, 'sub': ''}]
        reg_by_day = defaultdict(int)
        for r in new_rows:
            c = _dt(r[2])
            if c:
                reg_by_day[(c + MSK).date()] += 1
        for i in range(span - 1, -1, -1):
            d = d_from + timedelta(days=i)
            day_rows.append([d.strftime('%d.%m.%Y'), reg_by_day.get(d, 0), dau[i]])
    except Exception as e:  # noqa: BLE001
        logger.warning('users: activity failed: %r', e)
        blocks.append({'type': 'note', 'text': 'Активность по дням недоступна: не удалось собрать события.'})
    blocks.insert(0, {'type': 'cards', 'items': cards})
    if day_rows:
        blocks.append({'type': 'table', 'title': 'По дням (МСК)', 'header': ['День', 'Регистраций', 'Активных'], 'rows': day_rows[:120]})

    for title, col, fmt in (('Топ-10 по XP', 'experience_points', lambda v: v),
                            ('Топ-10 по времени на сайте, мин', 'site_seconds_total', lambda v: round(v / 60, 1))):
        if not _has_column('users', col):
            continue
        guest_q = ' AND COALESCE(is_guest, FALSE) = FALSE' if guest else ''
        top = _q(f'SELECT id, nickname, {col} FROM users WHERE {col} > 0{guest_q} ORDER BY {col} DESC LIMIT 10') or []
        blocks.append({'type': 'table', 'title': title + ' (за всё время)', 'header': ['Пользователь', 'ID', 'Значение'],
                       'rows': [[{'text': n or 'Без ника', 'href': f'/admin/stats/person?id={i}'}, i, fmt(v)] for i, n, v in top]})
    blocks.append({'type': 'table', 'title': f'Зарегистрировались за период (до {LIMIT_USERS}; полный список — CSV)',
                   'header': ['Пользователь', 'ID', 'Регистрация (UTC)', 'Последний вход (UTC)', 'Входов', 'XP', 'Минут на сайте'],
                   'rows': table_rows[:LIMIT_USERS], 'empty': 'Регистраций за период нет.'})
    blocks.append({'type': 'note', 'text': 'Онлайн сейчас, пики одновременных пользователей и полная таблица по всем пользователям '
                   '(решено, проверено, уровень) — в разделе «Пользователи» (вкладка «Люди»).'})
    return blocks


VIEWS = {'users_period': users, 'returns': returns, 'surveys': surveys}
