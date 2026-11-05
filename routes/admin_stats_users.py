# -*- coding: utf-8 -*-
"""ADMIN_STATS_USERS_V1 (2026-11-05) — раздел «Пользователи» панели /admin/stats:
всё, что было на прежней странице «Статистика пользователей» (/admin/users), по вкладкам.

Данные — те же, что у прежней страницы: routes.admin_support.users_stats_context()
(онлайн, DAU/WAU/MAU, пики, по дням/часам, устройства, топы, отвалившиеся, отзывы,
фото решений, таблица людей, воронка/удержание, типы задач, слабые темы,
проблемные задачи, серии, ИИ-тьютор, обещание регулярности, роли) и
services.user_returns (возвращения, последний заход). Цифры совпадают со старой страницей.

Вкладки: ?tab=online | people | study | feedback.
"""
from __future__ import annotations

import logging

from flask import request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

TABS = (('online', 'Онлайн и активность'), ('people', 'Люди'), ('study', 'Учёба'), ('feedback', 'Отзывы и фото'))
PEOPLE_LIMIT = 300


def _tabs(active: str) -> dict:
    return {'type': 'tabs', 'title': 'Вкладка',
            'items': [{'text': t, 'href': f'?tab={k}', 'active': k == active} for k, t in TABS]}


def _person(uid, text):
    return {'text': text or 'Без ника', 'href': f'/admin/stats/person?id={uid}'}


def _hours(sec) -> str:
    sec = int(sec or 0)
    return f'{sec // 3600} ч {sec % 3600 // 60} мин' if sec >= 3600 else f'{sec // 60} мин'


def _vbars(title, items, note=None):
    top = max([v for _, v, _ in items] + [1])
    return {'type': 'vbars', 'title': title, 'note': note,
            'items': [{'label': lbl, 'value': v, 'tip': tip, 'h': round(100 * v / top)} for lbl, v, tip in items]}


def _ctx():
    from routes.admin_support import users_stats_context
    return users_stats_context()


def _returns_and_last_seen():
    ret = ls = None
    try:
        from services.user_returns import last_seen_table, returns_distribution
        ret = returns_distribution(gap_min=60)
        ls = last_seen_table(gap_min=60)
    except Exception as e:  # noqa: BLE001 — блок не должен ронять раздел
        logger.warning('admin_stats_users: returns/last_seen failed: %r', e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
    return ret, ls


# ──────────────────────────── вкладки ────────────────────────────
def _online(c):
    t, dev = c['total'], c['devices_stats']
    ret, ls = _returns_and_last_seen()
    blocks = [
        {'type': 'cards', 'title': 'Прямо сейчас', 'items': [
            {'title': 'Сейчас на сайте', 'value': t['online_now'], 'sub': 'действие за последние 60 мин, включая гостей', 'accent': 'green'},
            {'title': 'Макс. онлайн сегодня', 'value': t['peak_today'], 'sub': 'людей в один момент'},
            {'title': 'Макс. онлайн вчера', 'value': t['peak_yesterday']},
            {'title': 'Рекорд онлайна', 'value': t['peak_ever'], 'sub': str(t['peak_ever_at'])},
            {'title': 'Активны сегодня (DAU)', 'value': t['dau'], 'sub': 'с 00:00 МСК, включая гостей'},
            {'title': 'За 7 дней (WAU)', 'value': t['wau']},
            {'title': 'За 30 дней (MAU)', 'value': t['mau']},
        ]},
        {'type': 'cards', 'title': 'Всего', 'items': [
            {'title': 'Пользователей', 'value': t['users'], 'sub': 'без гостей'},
            {'title': 'Входов', 'value': t['logins']},
            {'title': 'Решено задач', 'value': t['problems'], 'sub': f"сегодня {t['solved_today']} · за 7 дней {t['solved_week']}"},
            {'title': 'Проверено задач', 'value': t['checked'], 'sub': 'верные и неверные'},
            {'title': 'Время на сайте', 'value': _hours(t['seconds']), 'small': True, 'sub': 'сумма по всем'},
        ]},
    ]
    by_day = c['by_day']
    blocks.append(_vbars('Активные по дням (14 дней, МСК)',
                         [(d['day'][8:] + '.' + d['day'][5:7], d['active'],
                           f"{d['active']} активных · {d['logins']} входили · {d['hours']} ч") for d in by_day],
                         'Активные — любое действие в БД, включая гостей.'))
    reg = c['reg_map']
    blocks.append(_vbars('Регистрации по дням', [(d['day'][8:] + '.' + d['day'][5:7], int(reg.get(d['day'], 0)),
                                                  f"{reg.get(d['day'], 0)} регистраций") for d in by_day]))
    blocks.append(_vbars('Активность по часам сегодня (МСК)',
                         [(f'{h:02d}', n, f'{h:02d}:00 — {n} чел.') for h, n in enumerate(c['by_hour'])]))
    blocks.append({'type': 'cards', 'title': 'Устройства — с ПК или с телефона', 'items': [
        {'title': 'Только с ПК', 'value': dev['pc_only']},
        {'title': 'Только с телефона', 'value': dev['mobile_only'], 'sub': 'планшеты — как телефоны'},
        {'title': 'И с ПК, и с телефона', 'value': dev['both']},
        {'title': 'Нет данных', 'value': dev['unknown'], 'sub': 'заходили до 25.10.2026'},
    ]})
    if ls:
        items = [{'title': b['label'], 'value': b['count'], 'sub': f"{b['pct']}% из {ls['total']}"} for b in ls['buckets']]
        items.append({'title': 'Ни разу не заходили', 'value': ls['never']})
        if ls.get('median_days_ago') is not None:
            items.append({'title': 'Медиана давности', 'value': f"{ls['median_days_ago']} дн", 'sub': 'половина заходила не позже'})
        blocks.append({'type': 'cards', 'title': 'Последний заход — когда были в последний раз', 'items': items})
    if ret:
        blocks.append({'type': 'cards', 'title': 'Возвращения (новый визит — пауза больше 60 мин)', 'items': [
            {'title': 'С действиями', 'value': ret['users_with_events']},
            {'title': 'Вернулись хотя бы раз', 'value': ret['returned_at_least_once'], 'sub': f"{ret['retention_pct']}%"},
            {'title': 'Всего визитов', 'value': ret['total_visits'], 'sub': f"{ret['avg_visits_per_user']} на человека, максимум {ret['max_visits']}"},
        ]})
        blocks.append({'type': 'table', 'left': True, 'title': 'Сколько раз приходили',
                       'header': ['Визитов', 'Что это', 'Ровно столько', 'Столько и более', '% от всех'],
                       'rows': [[r['n'], 'только первый визит' if r['n'] == 1 else f"пришли {r['n']}-й раз",
                                 r['exact'], r['at_least'], f"{r['share_at_least']}%"] for r in ret['rows']]})
    return blocks


def _people(c):
    rows = c['rows']
    q = (request.args.get('q') or '').strip().lower()
    if q:
        rows = [r for r in rows if q in str(r['nickname']).lower() or q in str(r['name']).lower()
                or q in str(r['email']).lower() or q == str(r['id'])]
    if request.args.get('csv') == '1':
        from routes.admin_stats import csv_response
        return csv_response([(r['id'], r['nickname'], r['name'], r['email'], r['created_at'], r['last_login'], r['login_count'],
                              r['problems'], r['checked'], r['level'], r['xp'], r['minutes'], 'да' if r['online'] else '')
                             for r in rows],
                            ('id', 'nickname', 'name', 'email', 'registered', 'last_login', 'logins', 'solved', 'checked',
                             'level', 'xp', 'minutes_on_site', 'online'), 'users.csv')
    blocks = [{'type': 'search', 'label': 'Найти', 'placeholder': 'Ник, имя, email или ID', 'value': request.args.get('q') or '',
               'hidden': {'tab': 'people'}},
              {'type': 'tabs', 'title': 'Выгрузка', 'items': [{'text': 'CSV — все пользователи' + (' (по поиску)' if q else ''),
                                                              'href': f"?tab=people&csv=1&q={request.args.get('q') or ''}"}]}]
    blocks.append({'type': 'table', 'left': True, 'nowrap': True,
                   'title': f'Все пользователи — {len(rows)}' + (f' (показаны первые {PEOPLE_LIMIT}, остальные — в CSV)' if len(rows) > PEOPLE_LIMIT else ''),
                   'header': ['Пользователь', 'ID', 'Имя', 'Email', 'Регистрация', 'Последний вход', 'Входов', 'Решено',
                              'Проверено', 'Уровень', 'XP', 'Время на сайте'],
                   'rows': [[_person(r['id'], ('🟢 ' if r['online'] else '') + str(r['nickname'])), r['id'], r['name'], r['email'],
                             r['created_at'], r['last_login'], r['login_count'], r['problems'], r['checked'], f"{r['level']}/4",
                             r['xp'], _hours(r['seconds'])] for r in rows[:PEOPLE_LIMIT]],
                   'empty': 'Никого не найдено.'})
    for title, key, fmt in (('Топ-5 по XP', 'top_xp', lambda r: f"{r['xp']} XP"),
                            ('Топ-5 по задачам', 'top_problems', lambda r: r['problems']),
                            ('Топ-5 по времени на сайте', 'top_time', lambda r: f"{r['hours']} ч")):
        blocks.append({'type': 'table', 'left': True, 'title': title, 'header': ['Пользователь', 'Значение'],
                       'rows': [[_person(r['id'], r['nickname']), fmt(r)] for r in c[key]]})
    blocks.append({'type': 'table', 'left': True, 'title': 'Отвалившиеся — нет входа 7+ дней (топ-10 по XP)',
                   'header': ['Пользователь', 'Последний вход'],
                   'rows': [[_person(r['id'], r['nickname']), r['last_login']] for r in c['inactive']], 'empty': 'Все активны.'})
    _ret, ls = _returns_and_last_seen()
    if ls:
        blocks.append({'type': 'table', 'left': True, 'nowrap': True, 'title': f"Последний заход каждого (UTC, визит — паузы ≤ {ls['gap_min']} мин)",
                       'header': ['Пользователь', 'ID', 'Последнее действие', 'Сколько прошло', 'Начало визита', 'Длит. визита',
                                  'Действий', 'Визитов', 'Устройства'],
                       'rows': [[_person(r['user_id'], ('🟢 ' if r['bucket'] == 'online' else '') + str(r['name'])), r['user_id'],
                                 r['last_seen'] or '—', r['ago'], r['last_visit_start'] or '—',
                                 f"{r['last_visit_minutes']} мин" if r['last_visit_minutes'] is not None else '—',
                                 r['events_last_visit'], r['visits'], r['devices'] or '—'] for r in ls['rows'][:PEOPLE_LIMIT]]})
    return blocks


def _study(c):
    blocks = []
    f = c.get('funnel') or {}
    if f.get('steps'):
        blocks.append({'type': 'table', 'left': True, 'title': 'Воронка', 'header': ['Шаг', 'Пользователей', '% от регистраций'],
                       'rows': [[s['name'], s['count'], f"{s['pct']}%"] for s in f['steps']]})
        items = []
        for label, key in (('через 1 день', 'd1'), ('через 7 дней', 'd7'), ('через 30 дней', 'd30')):
            rr = (f.get('retention') or {}).get(key)
            items.append({'title': f'Возвращаются {label}', 'value': f"{rr['pct'] if rr else 0}%",
                          'sub': f"{rr['retained']} из {rr['cohort']} зарегистрированных" if rr else ''})
        blocks.append({'type': 'cards', 'title': 'Удержание', 'items': items})
    if c.get('task_types'):
        blocks.append({'type': 'table', 'left': True, 'title': 'По типам задач — где решают и с каким успехом',
                       'header': ['Раздел', 'Отвечено', 'Верно', '% верных', 'Ср. время на задачу'],
                       'rows': [[t['name'], t['answered'], t['correct'], f"{t['pct']}%",
                                 f"{t['avg_sec']} сек" if t.get('avg_sec') is not None else '—'] for t in c['task_types']]})
    if c.get('weak_themes'):
        blocks.append({'type': 'table', 'left': True, 'title': 'Слабые темы — худший процент верных (от 5 ответов)',
                       'header': ['Источник', 'Тема', 'Отвечено', 'Верно', '% верных'],
                       'rows': [[w['source'], w['theme'], w['answered'], w['correct'], f"{w['pct']}%"] for w in c['weak_themes']]})
    if c.get('problem_tasks'):
        blocks.append({'type': 'table', 'left': True, 'title': 'Проблемные задачи — чаще всего решают неверно',
                       'header': ['Условие (начало)', 'Отвечено', 'Неверных', '% верных'],
                       'rows': [[p['text'], p['answered'], p['wrong'], f"{p['pct']}%"] for p in c['problem_tasks']]})
    st = c.get('streaks')
    if st:
        items = [{'title': 'Средняя серия', 'value': st['avg']}, {'title': 'Рекорд серии', 'value': st['max_ever']}]
        items += [{'title': f'Серия {label} дн.', 'value': cnt} for label, cnt in (st.get('buckets') or {}).items()]
        blocks.append({'type': 'cards', 'title': 'Серии дней подряд', 'items': items})
    ai = c.get('ai_tutor')
    if ai:
        blocks.append({'type': 'cards', 'title': 'ИИ-тьютор и генерация задач', 'items': [
            {'title': 'Ответов тьютора всего', 'value': ai['assistant_total']},
            {'title': 'За 7 дней', 'value': ai['assistant_week']},
            {'title': 'Общались за 7 дней', 'value': ai['users_week']}]})
        if ai.get('top_agents'):
            blocks.append({'type': 'table', 'left': True, 'title': 'Агенты (30 дней)', 'header': ['Агент', 'Сообщений'],
                           'rows': [[a['name'], a['count']] for a in ai['top_agents']]})
    pl = c.get('pledge')
    if pl:
        blocks.append({'type': 'cards', 'title': 'Обещание регулярности — «Согласен» (задачи дня)', 'items': [
            {'title': 'Нажатий всего', 'value': pl['total']}, {'title': 'Нажали хотя бы раз', 'value': pl['users_count']},
            {'title': 'Сегодня', 'value': pl['today']}, {'title': 'За 7 дней', 'value': pl['week']}]})
        if pl.get('users'):
            blocks.append({'type': 'table', 'left': True, 'title': 'Кто обещал',
                           'header': ['Пользователь', 'Нажатий', 'Сегодня', 'За 7 дней', 'Первое', 'Последнее', 'Сетов дня',
                                      'Отвечено', 'Верно', '% верных'],
                           'rows': [[p['nickname'] + (' (гость)' if p.get('is_guest') else ''), p['presses'], p['today'], p['week'],
                                     p['first'], p['last'], p['dt_sets'], p['dt_answered'], p['dt_correct'], f"{p['dt_accuracy']}%"]
                                    for p in pl['users']]})
    ro = c.get('roles')
    if ro:
        act = ro.get('active_by_role') or {}
        blocks.append({'type': 'cards', 'title': 'Роли — ученики, учителя, родители', 'items': [
            {'title': 'Учеников', 'value': ro['students'], 'sub': f"активны за 7 дней: {act.get('student', 0)}"},
            {'title': 'Учителей', 'value': ro['teachers'], 'sub': f"активны за 7 дней: {act.get('teacher', 0)}"},
            {'title': 'Родителей', 'value': ro['parents'], 'sub': f"активны за 7 дней: {act.get('parent', 0)}"},
            {'title': 'Родителей привязали ребёнка', 'value': ro['parents_bound']},
            {'title': 'Групп учителей', 'value': ro['groups'], 'sub': f"с учениками: {ro.get('groups_with_members', 0)}"}]})
    if not blocks:
        blocks.append({'type': 'note', 'text': 'Учебные блоки временно недоступны (services.admin_stats_extra не ответил).'})
    return blocks


def _feedback(c):
    fs = c['feedback_stats']
    answered = [f for f in c['feedback_list'] if f['answered']]
    total = sum(fs['dist']) or 1
    blocks = [
        {'type': 'cards', 'title': 'Опрос «Как тебе сайт?»', 'items': [
            {'title': 'Ответили', 'value': fs['answered']}, {'title': 'Средняя оценка', 'value': fs['avg'], 'sub': 'из 5'},
            {'title': 'Ожидают ответа', 'value': fs['pending']}]},
        {'type': 'bar', 'title': 'Распределение оценок',
         'items': [{'label': f'{n} / 5', 'value': fs['dist'][n - 1], 'pct': round(100 * fs['dist'][n - 1] / total)} for n in (5, 4, 3, 2, 1)]},
        {'type': 'table', 'left': True, 'title': 'Отзывы', 'header': ['Пользователь', 'Оценка', 'Отзыв', 'Ответил'],
         'rows': [[_person(f['user_id'], f['nickname']), f"{f['rating']}/5" if f['rating'] else '—', f['text'] or '—', f['answered']]
                  for f in answered], 'empty': 'Ответов пока нет.'},
        {'type': 'photos', 'title': f"Фото решений задач дня ({len(c['photo_items'])})", 'items': c['photo_items'],
         'empty': 'Фото-решений пока нет.'},
    ]
    return blocks


def users(d_from, d_to):
    tab = request.args.get('tab', 'online')
    tab = tab if tab in dict(TABS) else 'online'
    try:
        c = _ctx()
    except HTTPException as e:
        return [_tabs(tab), {'type': 'note', 'text': f'Статистика временно недоступна: {e.description}'}]
    out = {'online': _online, 'people': _people, 'study': _study, 'feedback': _feedback}[tab](c)
    if not isinstance(out, list):      # CSV
        return out
    return [_tabs(tab)] + out


VIEWS = {'users': users}
