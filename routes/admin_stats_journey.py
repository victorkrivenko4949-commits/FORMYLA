# -*- coding: utf-8 -*-
"""ADMIN_STATS_V2 (2026-11-05) — разделы про путь пользователя:

  journey         — «Путь регистрации»: когорта зарегистрированных за период проходит шаги
                    (анкета → готовность → первая задача → возврат → paywall → оплата),
                    где бросили анкету, список «застрявших» на шаге;
  survey_behavior — «Опросы и поведение»: что делали после ответа те, кто ответил
                    «готов / не готов» и поставил оценку сайту (вернулись, решили, оплатили);
  lost_users      — «Ушли и не вернулись»: последняя страница у тех, кого нет N дней.

Формат блоков — как в routes/admin_stats_sections.py. Ячейка таблицы может быть
{'text', 'href'} — тогда это ссылка. Все запросы fail-open.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta

from flask import request

from routes.admin_stats_sections import (
    _fmt_pct, _has_table, _json_get, _pct, _q, _utc_bounds,
)

logger = logging.getLogger(__name__)

STEPS = (
    ('signup', 'Зарегистрировались'),
    ('intake_start', 'Начали анкету'),
    ('intake_done', 'Прошли анкету'),
    ('readiness', 'Ответили «готов ли заниматься»'),
    ('first_task', 'Решили первую задачу'),
    ('returned', 'Вернулись в другой день'),
    ('paywall', 'Увидели лимит или оплату'),
    ('paid', 'Оплатили'),
)
STEP_TITLES = dict(STEPS)
STUCK_LIMIT = 100
SURVEY_LABELS = {'yes': 'Готов заниматься каждый день', 'try': 'Постараюсь, не обещаю',
                 'not_yet': 'Пока не готов'}


def _d(v):
    """date из значения БД (строка или date/datetime)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ')[:26])
    except Exception:
        return None


def _in(ids) -> str:
    return ','.join(str(int(i)) for i in ids) or 'NULL'


def _msk_day(dt: datetime) -> date:
    return (dt + timedelta(hours=3)).date()


def _event_users(event_sql: str, cond: str, uids, **params) -> set:
    """user_id, у которых было хотя бы одно из событий (event IN event_sql)."""
    if not uids:
        return set()
    rows = _q(f"SELECT DISTINCT user_id FROM funnel_events WHERE event IN ({event_sql}) "
              f"AND user_id IN ({_in(uids)}) {cond}", **params) or []
    return {int(r[0]) for r in rows if r[0] is not None}


def _paid_users(uids) -> set:
    paid = _event_users("'payment_success'", '', uids)
    if uids and _has_table('subscriptions'):
        rows = _q("SELECT DISTINCT user_id FROM subscriptions WHERE payment_id IS NOT NULL "
                  f"AND COALESCE(is_beta_access, FALSE) = FALSE AND user_id IN ({_in(uids)})")
        if rows is None:   # у SQLite FALSE бывает не определено — запасной вариант
            rows = _q("SELECT DISTINCT user_id FROM subscriptions WHERE payment_id IS NOT NULL "
                      f"AND COALESCE(is_beta_access, 0) = 0 AND user_id IN ({_in(uids)})")
        paid |= {int(r[0]) for r in (rows or [])}
    return paid


def _activity_days(uids) -> dict:
    """user_id → множество дней (МСК) активности по трекеру времени."""
    out = {}
    if not uids or not _has_table('site_time_sections'):
        return out
    rows = _q("SELECT user_id, day FROM site_time_sections WHERE section = 'general' AND seconds > 0 "
              f"AND user_id IN ({_in(uids)})") or []
    for uid, day in rows:
        d = _d(day)
        if d is not None:
            out.setdefault(int(uid), set()).add(d)
    return out


def _last_pages(uids) -> dict:
    if not uids or not _has_table('site_time_beat'):
        return {}
    from services.page_views import normalize_path
    rows = _q(f"SELECT user_id, last_page FROM site_time_beat WHERE user_id IN ({_in(uids)})") or []
    return {int(u): normalize_path(p or '—') for u, p in rows}


# ──────────────────────────── Путь регистрации ────────────────────────────
def journey(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    users = _q("SELECT id, nickname, created_at FROM users WHERE created_at >= :s AND created_at < :e",
               s=start, e=end)
    if users is None:
        return [{'type': 'note', 'text': 'Не удалось прочитать пользователей.'}]
    if not users:
        return [{'type': 'note', 'text': 'За выбранный период регистраций нет.'}]
    info = {int(u[0]): (u[1] or '', _dt(u[2])) for u in users}
    uids = list(info)

    reach = {k: set() for k, _ in STEPS}
    reach['signup'] = set(uids)
    ev = _event_users("'intake_answer','intake_done','intake_skip'", '', uids)
    reach['intake_start'] = ev
    reach['intake_done'] = _event_users("'intake_done'", '', uids)
    reach['intake_start'] |= reach['intake_done']
    reach['first_task'] = _event_users("'first_task_solved'", '', uids)
    reach['paywall'] = _event_users("'paywall_view','limit_hit','limit_shown','subscribe_view'", '', uids)
    if _has_table('page_views'):   # витрина и оформление — по журналу страниц
        rows = _q("SELECT DISTINCT user_id FROM page_views WHERE path IN ('/subscribe', '/payments/premium/checkout') "
                  f"AND user_id IN ({_in(uids)})") or []
        reach['paywall'] |= {int(r[0]) for r in rows}
    reach['paid'] = _paid_users(uids)
    if _has_table('readiness_survey_answers'):
        rows = _q(f"SELECT user_id FROM readiness_survey_answers WHERE user_id IN ({_in(uids)})") or []
        reach['readiness'] = {int(r[0]) for r in rows}
    act = _activity_days(uids)
    for uid, (_, created) in info.items():
        if created and any(day > _msk_day(created) for day in act.get(uid, ())):
            reach['returned'].add(uid)

    n0 = len(uids)
    rows, prev = [], None
    for i, (key, title) in enumerate(STEPS):
        n = len(reach[key])
        nxt = STEPS[i + 1][0] if i + 1 < len(STEPS) else None
        stuck = len(reach[key] - reach[nxt]) if nxt else None
        stuck_cell = ({'text': stuck, 'href': f'?stop={key}&p=custom&from={d_from}&to={d_to}'}
                      if stuck else (stuck if stuck is not None else '—'))
        rows.append([title, n, _fmt_pct(_pct(n, n0)), _fmt_pct(_pct(n, prev)) if prev is not None else '—', stuck_cell])
        prev = n
    blocks = [
        {'type': 'note', 'text': f'Когорта: {n0} пользователей, зарегистрированных {d_from.strftime("%d.%m")}–{d_to.strftime("%d.%m.%Y")} (МСК). '
         'Шаги не обязаны идти строго по порядку (анкету можно пропустить), поэтому «% от предыдущего» может быть больше 100%. '
         '«Остановились» — дошли до шага, но не до следующего; число открывает список этих людей.'},
        {'type': 'table', 'title': 'Путь когорты', 'header': ['Шаг', 'Дошли', '% от регистраций', '% от предыдущего', 'Остановились'],
         'rows': rows},
    ]

    # где бросают анкету: последний отвеченный вопрос у начавших и не закончивших
    qid = _json_get('props', 'qid')
    started_only = reach['intake_start'] - reach['intake_done']
    if started_only:
        last_q = {}
        for uid, q, _t in _q(f"SELECT user_id, {qid}, created_at FROM funnel_events WHERE event = 'intake_answer' "
                             f"AND user_id IN ({_in(started_only)}) ORDER BY created_at") or []:
            if q:
                last_q[int(uid)] = str(q)
        cnt = Counter(last_q.get(u, '— (только открыли / пропустили)') for u in started_only)
        blocks.append({'type': 'table', 'title': 'Где бросают анкету (последний отвеченный вопрос)',
                       'header': ['Вопрос (qid)', 'Людей', 'Доля'],
                       'rows': [[q, n, _fmt_pct(_pct(n, len(started_only)))] for q, n in cnt.most_common(30)],
                       'empty': 'Нет данных.'})
        blocks.append({'type': 'note', 'text': 'Вопросы анкеты пишутся с момента выкладки этого обновления; '
                       'у более ранних пользователей будет «только открыли / пропустили».'})

    stop = request.args.get('stop')
    if stop in reach and stop != STEPS[-1][0]:
        nxt = STEPS[[k for k, _ in STEPS].index(stop) + 1][0]
        stuck_ids = sorted(reach[stop] - reach[nxt], key=lambda u: info[u][1] or datetime.min, reverse=True)
        pages = _last_pages(stuck_ids[:STUCK_LIMIT])
        blocks.append({'type': 'table', 'left': True,
                       'title': f'Остановились на шаге «{STEP_TITLES[stop]}» (не дошли до «{STEP_TITLES[nxt]}»)',
                       'header': ['Пользователь', 'ID', 'Зарегистрировался (UTC)', 'Последняя страница'],
                       'rows': [[{'text': info[u][0] or 'Без ника', 'href': f'/admin/stats/person?id={u}'}, u,
                                 info[u][1].strftime('%d.%m.%Y %H:%M') if info[u][1] else '—', pages.get(u, '—')]
                                for u in stuck_ids[:STUCK_LIMIT]],
                       'empty': 'Никого.'})
        if len(stuck_ids) > STUCK_LIMIT:
            blocks.append({'type': 'note', 'text': f'Показаны первые {STUCK_LIMIT} из {len(stuck_ids)}.'})
    return blocks


# ──────────────────────────── Опросы и поведение ────────────────────────────
def _group_stats(groups: dict, answered: dict, today: date):
    """groups: название → [user_id]; answered: user_id → дата ответа. → строки таблицы."""
    all_ids = [u for ids in groups.values() for u in ids]
    act = _activity_days(all_ids)
    solved = _event_users("'first_task_solved'", '', all_ids)
    paid = _paid_users(all_ids)
    rows = []
    for name, ids in groups.items():
        if not ids:
            continue
        n = len(ids)
        ret1 = ret7 = mat1 = mat7 = 0
        for u in ids:
            a = answered[u]
            days = act.get(u, set())
            if a + timedelta(days=1) <= today:
                mat1 += 1
                ret1 += any(d > a for d in days)
            if a + timedelta(days=7) <= today:
                mat7 += 1
                ret7 += any(a < d <= a + timedelta(days=7) for d in days)
        rows.append([name, n,
                     f'{ret1} из {mat1} ({_fmt_pct(_pct(ret1, mat1))})' if mat1 else '—',
                     f'{ret7} из {mat7} ({_fmt_pct(_pct(ret7, mat7))})' if mat7 else '—',
                     f'{sum(1 for u in ids if u in solved)} ({_fmt_pct(_pct(sum(1 for u in ids if u in solved), n))})',
                     f'{sum(1 for u in ids if u in paid)} ({_fmt_pct(_pct(sum(1 for u in ids if u in paid), n))})'])
    return rows


def survey_behavior(d_from: date, d_to: date):
    start, end = _utc_bounds(d_from, d_to)
    today = (datetime.utcnow() + timedelta(hours=3)).date()
    header = ['Ответ', 'Людей', 'Вернулись на след. день', 'Вернулись за 7 дней', 'Решали задачи', 'Оплатили']
    blocks = [{'type': 'note', 'text': 'Берутся ответы за выбранный период. «Вернулись» считается только среди тех, '
               'кто ответил достаточно давно (1 или 7 дней назад), активность — по трекеру времени. '
               '«Решали» и «Оплатили» — когда-либо, включая время после ответа. Это сравнение групп, а не доказательство причины.'}]
    if _has_table('readiness_survey_answers'):
        rows = _q("SELECT user_id, answer, answered_at FROM readiness_survey_answers "
                  "WHERE answered_at >= :s AND answered_at < :e", s=start, e=end) or []
        groups, answered = {SURVEY_LABELS[k]: [] for k in SURVEY_LABELS}, {}
        for uid, ans, at in rows:
            dt = _dt(at)
            if dt is None or ans not in SURVEY_LABELS:
                continue
            groups[SURVEY_LABELS[ans]].append(int(uid))
            answered[int(uid)] = _msk_day(dt)
        blocks.append({'type': 'table', 'title': 'Опрос «Готов заниматься каждый день?»', 'header': header,
                       'rows': _group_stats(groups, answered, today), 'empty': 'Ответов за период нет.'})
    if _has_table('site_feedback'):
        rows = _q("SELECT user_id, rating, answered_at FROM site_feedback "
                  "WHERE answered_at IS NOT NULL AND rating IS NOT NULL AND answered_at >= :s AND answered_at < :e",
                  s=start, e=end) or []
        groups, answered = {'Оценка 1–2': [], 'Оценка 3': [], 'Оценка 4–5': []}, {}
        for uid, rating, at in rows:
            dt = _dt(at)
            try:
                r = int(rating)
            except Exception:
                continue
            if dt is None:
                continue
            groups['Оценка 1–2' if r <= 2 else ('Оценка 3' if r == 3 else 'Оценка 4–5')].append(int(uid))
            answered[int(uid)] = _msk_day(dt)
        blocks.append({'type': 'table', 'title': 'Опрос «Как тебе сайт?»', 'header': header,
                       'rows': _group_stats(groups, answered, today), 'empty': 'Ответов за период нет.'})
    return blocks


# ──────────────────────────── Ушли и не вернулись ────────────────────────────
def lost_users(d_from: date, d_to: date):
    try:
        days = int(request.args.get('days', 7))
    except ValueError:
        days = 7
    days = days if days in (3, 7, 14) else 7
    today = (datetime.utcnow() + timedelta(hours=3)).date()
    rows = _q("SELECT user_id, MAX(day) FROM site_time_sections WHERE section = 'general' AND seconds > 0 "
              "GROUP BY user_id")
    if rows is None:
        return [{'type': 'note', 'text': 'Нет таблицы учёта времени (site_time_sections).'}]
    last = {int(u): _d(d) for u, d in rows if u is not None and _d(d)}
    lost = {u: d for u, d in last.items() if (today - d).days >= days}
    switch = {'type': 'tabs', 'title': 'Нет активности',
              'items': [{'text': f'{n} дн.', 'active': n == days, 'href': f'?days={n}'} for n in (3, 7, 14)]}
    if not lost:
        return [switch, {'type': 'note', 'text': 'Нет пользователей с такой паузой.'}]
    pages = _last_pages(list(lost))
    paid_now = _paid_users(list(lost))
    cnt = Counter(pages.get(u, '— (нет данных о странице)') for u in lost)
    nicks = {int(r[0]): (r[1] or '') for r in (_q(f"SELECT id, nickname FROM users WHERE id IN ({_in(list(lost)[:2000])})") or [])}
    recent = sorted(lost, key=lambda u: lost[u], reverse=True)[:STUCK_LIMIT]
    from routes.admin_stats_person import REASONS, reason_text, signals_for
    sig = signals_for(list(lost)[:3000])
    reasons = Counter(sig[u]['primary'] for u in sig)
    reason_rows = [[REASONS[c][0], n, _fmt_pct(_pct(n, len(sig)))] for c, n in
                   sorted(reasons.items(), key=lambda kv: (REASONS[kv[0]][1], -kv[1]))]
    return [
        switch,
        {'type': 'cards', 'items': [
            {'title': 'Ушли', 'value': len(lost), 'sub': f'нет активности {days}+ дн., из {len(last)} с активностью'},
            {'title': 'Из них платили', 'value': len(paid_now), 'sub': 'есть платёж за всё время'},
        ]},
        {'type': 'table', 'left': True, 'title': 'Вероятная причина ухода (главный сигнал у каждого)', 'header': ['Причина', 'Людей', 'Доля'],
         'rows': reason_rows},
        {'type': 'table', 'title': 'Последняя страница у ушедших', 'header': ['Страница', 'Людей', 'Доля'],
         'rows': [[p, n, _fmt_pct(_pct(n, len(lost)))] for p, n in cnt.most_common(30)]},
        {'type': 'table', 'left': True, 'title': f'Недавно ушедшие (до {STUCK_LIMIT})',
         'header': ['Пользователь', 'ID', 'Последняя активность', 'Дней назад', 'Последняя страница', 'Вероятная причина'],
         'rows': [[{'text': nicks.get(u) or 'Без ника', 'href': f'/admin/stats/person?id={u}'}, u, lost[u].strftime('%d.%m.%Y'),
                   (today - lost[u]).days, pages.get(u, '—'),
                   reason_text(sig[u]) if u in sig else '—'] for u in recent]},
        {'type': 'note', 'text': 'Причина — правило по фактам из базы (платёж, лимит, анкета, опросы, задачи), главный сигнал по важности; '
         'полный путь человека открывается по нику. Последняя страница — из трекера времени (site_time_beat.last_page), '
         'с точностью до пары минут. Период в панели на этот отчёт не влияет.'},
    ]


VIEWS = {'journey': journey, 'survey_behavior': survey_behavior, 'lost_users': lost_users}
