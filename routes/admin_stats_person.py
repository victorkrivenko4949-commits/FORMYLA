# -*- coding: utf-8 -*-
"""ADMIN_STATS_PERSON_V1 (2026-11-05) — путь одного человека и вероятная причина ухода.

  /admin/stats/person?id=<user_id>  (или ?q=<ник>)

Собирает в одну ленту всё, что о человеке знает сайт: просмотры страниц (page_views),
события воронки (регистрация, шаги анкеты, первая задача, экран лимита, оплата),
ответы в опросах, подписки и попытки платежа ЮKassa, дни активности.

signals_for(uids) — те же данные пачкой для многих людей: по ним «Ушли и не вернулись»
считает причины ухода. Причина — это не догадка модели, а правило по фактам
(«начал оплату и не оплатил», «бросил анкету на вопросе X» и т. д.); если фактов нет,
так и пишем, а ориентир — последняя страница.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from flask import request

from routes.admin_stats_labels import page_title, question_title, source_title
from routes.admin_stats_sections import PLAN_TITLES, _has_column, _has_table, _json_get, _q

logger = logging.getLogger(__name__)

MSK = timedelta(hours=3)
TIMELINE_LIMIT = 400
LIMIT_EVENTS = ('limit_hit', 'limit_shown')
PAY_PAGES = ('/subscribe', '/payments/premium/checkout')
READINESS = {'yes': 'готов', 'try': 'постараюсь', 'not_yet': 'пока не готов'}

# код причины → (название, порядок важности: меньше = важнее)
REASONS = {
    'said': ('Сам назвал причину', 0),
    'checkout_abandoned': ('Начал оплату и не оплатил', 1),
    'sub_expired': ('Подписка закончилась, не продлил', 2),
    'limit_no_pay': ('Упёрся в лимит и не оплатил', 3),
    'saw_price': ('Смотрел тарифы и не купил', 4),
    'low_rating': ('Низко оценил сайт', 5),
    'intake_quit': ('Бросил анкету', 6),
    'not_ready': ('Ответил «пока не готов»', 7),
    'intake_skip': ('Пропустил анкету', 8),
    'no_task': ('Не решил ни одной задачи', 9),
    'one_day': ('Был только в день регистрации', 10),
    'unknown': ('Явных сигналов нет', 99),
}
EVENT_TITLES = {
    'visit': 'Первый визит', 'signup': 'Регистрация', 'intake_answer': 'Ответил на вопрос анкеты',
    'intake_skip': 'Пропустил анкету', 'intake_done': 'Прошёл анкету', 'first_task_solved': 'Решил первую задачу',
    'limit_shown': 'Упёрся в лимит', 'limit_hit': 'Упёрся в лимит', 'limit_applied': 'Лимит отклонил запрос',
    'payment_success': 'Оплатил', 'ab_assigned': 'Попал в A/B-группу', 'founder_offer_click': 'Нажал оффер основателя',
}


def _dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ')[:26]) if v else None
    except Exception:
        return None


def _d(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _in(ids) -> str:
    return ','.join(str(int(i)) for i in ids) or 'NULL'


def _props(v) -> dict:
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v) if v else {}
    except Exception:
        return {}


# ──────────────────────────── сигналы пачкой ────────────────────────────
def signals_for(uids) -> dict:
    """{user_id: {'codes': [...], 'details': {code: текст}, 'primary': code}} по фактам из БД."""
    uids = [int(u) for u in uids]
    if not uids:
        return {}
    ids = _in(uids)
    ev = {u: set() for u in uids}
    last_qid = {}
    for uid, name in (_q(f"SELECT DISTINCT user_id, event FROM funnel_events WHERE user_id IN ({ids})") or []):
        ev.setdefault(int(uid), set()).add(str(name))
    qid = _json_get('props', 'qid')
    for uid, q in (_q(f"SELECT user_id, {qid} FROM funnel_events WHERE event = 'intake_answer' AND user_id IN ({ids}) "
                      "ORDER BY created_at") or []):
        if q:
            last_qid[int(uid)] = str(q)
    pages = {}
    if _has_table('page_views'):
        ph = ','.join("'" + p + "'" for p in PAY_PAGES)
        for uid, in (_q(f"SELECT DISTINCT user_id FROM page_views WHERE path IN ({ph}) AND user_id IN ({ids})") or []):
            pages[int(uid)] = True
    pay_try, pay_ok = set(), set()
    if _has_table('yookassa_payments'):
        for uid, st in (_q(f"SELECT user_id, status FROM yookassa_payments WHERE user_id IN ({ids})") or []):
            pay_try.add(int(uid))
            if st == 'succeeded':
                pay_ok.add(int(uid))
    subs = {}
    if _has_table('subscriptions'):
        now = datetime.utcnow()
        for uid, status, exp, pid in (_q(f"SELECT user_id, status, expires_at, payment_id FROM subscriptions "
                                         f"WHERE user_id IN ({ids})") or []):
            d = subs.setdefault(int(uid), {'paid_ever': False, 'live': False})
            e = _dt(exp)
            if pid:
                d['paid_ever'] = True
            if status == 'active' and (e is None or e > now):
                d['live'] = True
    ready = {}
    if _has_table('readiness_survey_answers'):
        ready = {int(u): a for u, a in (_q(f"SELECT user_id, answer FROM readiness_survey_answers WHERE user_id IN ({ids})") or [])}
    rating = {}
    if _has_table('site_feedback'):
        rating = {int(u): (r, t) for u, r, t in (_q(f"SELECT user_id, rating, feedback_text FROM site_feedback "
                                                    f"WHERE rating IS NOT NULL AND user_id IN ({ids})") or [])}
    days = {}
    if _has_table('site_time_sections'):
        for uid, n in (_q(f"SELECT user_id, COUNT(DISTINCT day) FROM site_time_sections WHERE section = 'general' "
                          f"AND seconds > 0 AND user_id IN ({ids}) GROUP BY user_id") or []):
            days[int(uid)] = int(n or 0)

    said = {}
    if _has_table('exit_answers'):
        from services.exit_question import OPTIONS, TRIGGER_TITLES
        for uid, kind, ans, note in (_q(f"SELECT user_id, kind, answer, answer_text FROM exit_answers "
                                        f"WHERE status = 'answered' AND user_id IN ({ids}) ORDER BY created_at") or []):
            label = OPTIONS.get(kind, {}).get(ans, ans)
            said[int(uid)] = f"{TRIGGER_TITLES.get(kind, kind).lower()}: «{label}»" + (f', «{note}»' if note else '')

    out = {}
    for u in uids:
        e = ev.get(u, set())
        paid = 'payment_success' in e or u in pay_ok or subs.get(u, {}).get('paid_ever')
        codes, det = [], {}
        if u in said:
            codes.append('said')
            det['said'] = said[u]
        if u in pay_try and not paid:
            codes.append('checkout_abandoned')
        s = subs.get(u)
        if s and s['paid_ever'] and not s['live']:
            codes.append('sub_expired')
        if e & set(LIMIT_EVENTS) and not paid:
            codes.append('limit_no_pay')
        if pages.get(u) and not paid and 'checkout_abandoned' not in codes:
            codes.append('saw_price')
        if u in rating:
            try:
                r = int(rating[u][0])
            except Exception:
                r = 5
            if r <= 2:
                codes.append('low_rating')
                det['low_rating'] = f'{r}/5' + (f': «{rating[u][1]}»' if rating[u][1] else '')
        if 'intake_answer' in e and 'intake_done' not in e and 'intake_skip' not in e:
            codes.append('intake_quit')
            if u in last_qid:
                det['intake_quit'] = f'последний отвеченный вопрос: {question_title(last_qid[u])}'
        if ready.get(u) == 'not_yet':
            codes.append('not_ready')
        if 'intake_skip' in e and 'intake_done' not in e:
            codes.append('intake_skip')
        if 'first_task_solved' not in e:
            codes.append('no_task')
        if days.get(u, 0) <= 1:
            codes.append('one_day')
        if not codes:
            codes.append('unknown')
        codes.sort(key=lambda c: REASONS[c][1])
        out[u] = {'codes': codes, 'details': det, 'primary': codes[0]}
    return out


def reason_text(sig: dict, code: str | None = None) -> str:
    code = code or sig['primary']
    t = REASONS[code][0]
    d = sig['details'].get(code)
    return f'{t} ({d})' if d else t


# ──────────────────────────── лента одного человека ────────────────────────────
def timeline(uid: int):
    """[(datetime_utc, что, подробности)] по убыванию времени."""
    items = []
    if _has_table('page_views'):
        for p, t in (_q('SELECT path, created_at FROM page_views WHERE user_id = :u ORDER BY created_at DESC LIMIT 500', u=uid) or []):
            items.append((_dt(t), 'Открыл страницу', page_title(p)))
    for name, props, path, src, t in (_q('SELECT event, props, path, source, created_at FROM funnel_events WHERE user_id = :u '
                                         'ORDER BY created_at DESC LIMIT 500', u=uid) or []):
        pr = _props(props)
        detail = ''
        if name == 'intake_answer':
            detail = question_title(pr.get('qid', '—'))
        elif name == 'payment_success':
            detail = f"{PLAN_TITLES.get(str(pr.get('plan')), pr.get('plan') or '—')}, {pr.get('amount', '—')} ₽"
        elif name == 'visit':
            detail = 'зашёл на «' + page_title(path or '/') + '»' + (f" · источник: {source_title(src)}" if src else '')
        elif name == 'signup':
            detail = {'telegram': 'через Telegram', 'email': 'по почте'}.get(pr.get('via'), '')
        elif name in LIMIT_EVENTS or name == 'limit_applied':
            detail = page_title(path) if path else ''
        items.append((_dt(t), EVENT_TITLES.get(name, name), detail))
    if _has_table('readiness_survey_answers'):
        for a, t in (_q('SELECT answer, answered_at FROM readiness_survey_answers WHERE user_id = :u', u=uid) or []):
            items.append((_dt(t), 'Опрос «Готов заниматься каждый день?»', READINESS.get(a, a)))
    if _has_table('wish_survey_answers'):
        for txt, g, t in (_q('SELECT answer_text, discount_granted, answered_at FROM wish_survey_answers '
                             'WHERE user_id = :u', u=uid) or []):
            items.append((_dt(t), 'Опрос «Что ты хочешь от Формулы?»',
                          f'«{txt}»' + (' — скидка 30%' if int(g or 0) else ' — без скидки')))
    if _has_table('site_feedback'):
        for r, txt, t in (_q('SELECT rating, feedback_text, answered_at FROM site_feedback WHERE user_id = :u '
                             'AND answered_at IS NOT NULL', u=uid) or []):
            items.append((_dt(t), 'Оценил сайт', f'{r}/5' + (f': «{txt}»' if txt else '')))
    if _has_table('subscriptions'):
        for plan, st, start, exp, amt in (_q('SELECT plan, status, started_at, expires_at, amount_rub FROM subscriptions '
                                             'WHERE user_id = :u', u=uid) or []):
            title = PLAN_TITLES.get(str(plan), plan)
            items.append((_dt(start), 'Подписка началась', f'{title}, {amt or 0} ₽, статус {st}'))
            e = _dt(exp)
            if e and e <= datetime.utcnow():
                items.append((e, 'Подписка закончилась', title))
    if _has_table('yookassa_payments'):
        for code, st, amt, t in (_q('SELECT item_code, status, amount_rub, created_at FROM yookassa_payments '
                                    'WHERE user_id = :u', u=uid) or []):
            items.append((_dt(t), 'Платёж ЮKassa', f"{PLAN_TITLES.get(str(code), code)}, {amt} ₽ — "
                                                     f"{'прошёл' if st == 'succeeded' else 'не завершён (' + str(st) + ')'}"))
    if _has_table('exit_answers'):
        from services.exit_question import OPTIONS, TRIGGER_TITLES
        for kind, ans, note, st, t in (_q('SELECT kind, answer, answer_text, status, created_at FROM exit_answers '
                                          'WHERE user_id = :u', u=uid) or []):
            what = f'Вопрос «что остановило?» ({TRIGGER_TITLES.get(kind, kind).lower()})'
            if st == 'dismissed':
                items.append((_dt(t), what, 'пропустил'))
            else:
                items.append((_dt(t), what, OPTIONS.get(kind, {}).get(ans, ans) + (f': «{note}»' if note else '')))
    items = [i for i in items if i[0] is not None]
    items.sort(key=lambda i: i[0], reverse=True)
    return items


def login_method(uid: int) -> str:
    """Telegram / Яндекс / Google по привязанным аккаунтам, иначе — почта (код на email)."""
    ways = []
    if _has_column('users', 'telegram_id'):
        r = _q('SELECT telegram_id FROM users WHERE id = :u', u=uid) or []
        if r and r[0][0]:
            ways.append('Telegram')
    if _has_table('oauth_accounts'):
        names = {'yandex': 'Яндекс', 'google': 'Google', 'vk': 'VK'}
        for (prov,) in (_q('SELECT DISTINCT provider FROM oauth_accounts WHERE user_id = :u', u=uid) or []):
            ways.append(names.get(str(prov).lower(), str(prov)))
    return ', '.join(ways) if ways else 'Почта (код на email)'


def _find_user():
    raw = (request.args.get('id') or '').strip()
    q = (request.args.get('q') or '').strip()
    if raw.isdigit():
        return int(raw)
    if q.isdigit():
        return int(q)
    if q and _has_column('users', 'nickname'):
        rows = _q('SELECT id FROM users WHERE LOWER(nickname) = :n LIMIT 1', n=q.lower()) or \
            _q('SELECT id FROM users WHERE LOWER(nickname) LIKE :n ORDER BY id LIMIT 1', n=f'%{q.lower()}%') or []
        if rows:
            return int(rows[0][0])
    return None


def person(d_from: date, d_to: date):
    search = {'type': 'search', 'placeholder': 'ID или ник', 'value': request.args.get('q') or request.args.get('id') or ''}
    uid = _find_user()
    if uid is None:
        return [search, {'type': 'note', 'text': 'Введите ID или ник. Сюда ведут ссылки с ников в разделах статистики.'}]
    cols = [c for c in ('nickname', 'created_at', 'acq_source', 'acq_ref', 'current_plan') if _has_column('users', c)]
    row = _q(f"SELECT {', '.join(cols) or 'id'} FROM users WHERE id = :u", u=uid)
    if not row:
        return [search, {'type': 'note', 'text': f'Пользователь #{uid} не найден.'}]
    info = dict(zip(cols, row[0])) if cols else {}
    items = timeline(uid)
    sig = signals_for([uid])[uid]
    last = items[0][0] if items else None
    last_page = next((d for t, w, d in items if w == 'Открыл страницу'), None)
    if _has_table('site_time_beat'):
        beat = _q('SELECT last_beat, last_page FROM site_time_beat WHERE user_id = :u', u=uid) or []
        if beat and _dt(beat[0][0]) and (last is None or _dt(beat[0][0]) > last):
            last = _dt(beat[0][0])
            from services.page_views import normalize_path
            last_page = page_title(normalize_path(beat[0][1] or '')) if beat[0][1] else last_page
    days_away = (datetime.utcnow() - last).days if last else None
    created = _dt(info.get('created_at'))

    def msk(t):
        return (t + MSK).strftime('%d.%m.%Y %H:%M') if t else '—'

    status = '—' if days_away is None else ('активен' if days_away < 3 else f'не заходил {days_away} дн.')
    blocks = [
        search,
        {'type': 'cards', 'items': [
            {'title': 'Пользователь', 'value': info.get('nickname') or 'Без ника', 'small': True,
             'sub': f'#{uid} · регистрация {msk(created)}'},
            {'title': 'Последняя активность', 'value': status, 'small': True, 'sub': msk(last) + ' (МСК)'},
            {'title': 'Последняя страница', 'value': last_page or '—', 'small': True, 'sub': 'где был в последний раз'},
            {'title': 'Откуда пришёл', 'value': source_title(info.get('acq_source')) if info.get('acq_source') else 'Не записано',
             'small': True, 'sub': (f"метка ссылки: {info.get('acq_ref')}" if info.get('acq_ref') else
                                    'источник записывается у тех, кто пришёл после 18.10.2026') if info.get('acq_source') or info.get('acq_ref')
             else 'источник записывается у тех, кто пришёл после 18.10.2026'},
            {'title': 'Как входит', 'value': login_method(uid), 'small': True, 'sub': 'по привязанным аккаунтам'},
        ]},
        {'type': 'note', 'text': 'Вероятная причина: ' + reason_text(sig) +
         ('. Другие сигналы: ' + '; '.join(reason_text(sig, c) for c in sig['codes'][1:]) if len(sig['codes']) > 1 else '') +
         ('. Причину назвал сам человек.' if sig['primary'] == 'said' else
          '. Это правило по фактам из базы, а не ответ самого человека.')},
        {'type': 'table', 'left': True, 'title': f'Лента действий (новые сверху, до {TIMELINE_LIMIT})', 'header': ['Когда (МСК)', 'Что', 'Подробности'],
         'rows': [[msk(t), w, d or '—'] for t, w, d in items[:TIMELINE_LIMIT]],
         'empty': 'О действиях этого человека данных нет.'},
        {'type': 'tabs', 'title': 'Ещё', 'items': [{'text': 'Карточка в «Базе»', 'href': f'/admin/base/user/{uid}'}]},
    ]
    return blocks


VIEWS = {'person': person}
