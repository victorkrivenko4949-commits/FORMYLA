# -*- coding: utf-8 -*-
"""ADMIN_STATS_APP_V1 (05.11.2026) — раздел «Приложение» в /admin/stats.

Сколько людей поставили сайт как приложение (PWA), на каких устройствах,
кому сейчас показывается кнопка «Скачать приложение». Данные — таблица
pwa_installs (routes/pwa.py). Тестовые установки (is_test) в «реальные»
цифры не входят и показываются отдельно.
"""
from __future__ import annotations

import logging
from datetime import date

from routes.admin_stats_sections import _day_expr, _fmt_pct, _has_column, _has_table, _pct, _q, _utc_bounds

logger = logging.getLogger(__name__)

PLATFORMS = (
    ('android', 'Android'),
    ('desktop', 'Компьютер'),
    ('ios', 'iPhone / iPad'),
    ('other', 'Другое'),
)

PLATFORM_NOTE = (
    'Приложение открыто всем, но только на Android: кнопка «📲 Скачать приложение для Android» '
    'показывается на Android-телефонах (Chrome, Яндекс Браузер, Samsung Internet) и ставит его в один клик. '
    'На iPhone и компьютере кнопки нет (PWA_PLATFORMS=android). Тестовые аккаунты видят её везде, поэтому '
    'в «Последних установках» могут быть компьютер и iPhone — это тесты. Чтобы открыть другие устройства: '
    'PWA_PLATFORMS=android,desktop,ios или PWA_PLATFORMS=*.'
)

PLATFORM_TITLES = {'android': 'Android', 'desktop': 'компьютер', 'ios': 'iPhone / iPad', 'other': 'другое'}


def _access():
    """(текст «кому доступно», подсказка)."""
    try:
        from routes import pwa
        allowed, platforms = pwa._ALLOWED_USERS, getattr(pwa, '_PLATFORMS', {'*'})
    except Exception:  # noqa: BLE001
        return 'неизвестно (routes/pwa.py не загружен)', ''
    who = 'Всем' if (not allowed or '*' in allowed) else 'Только: ' + ', '.join(sorted(allowed))
    if not platforms or '*' in platforms:
        where = 'на всех устройствах'
    else:
        where = 'только ' + ', '.join(PLATFORM_TITLES.get(x, x) for x in sorted(platforms))
    hint = f"PWA_ALLOWED_USERS={','.join(sorted(allowed)) or '*'} · PWA_PLATFORMS={','.join(sorted(platforms)) or '*'}"
    return f'{who}, {where}', hint


def app_installs(d_from: date, d_to: date):
    access_text, hint = _access()
    access_card = {'title': 'Кому видна кнопка', 'value': access_text, 'small': True, 'sub': hint}
    if not _has_table('pwa_installs'):
        return [
            {'type': 'cards', 'items': [{'title': 'Людей с приложением', 'value': 0, 'sub': 'установок ещё не было'},
                                        access_card]},
            {'type': 'note', 'text': PLATFORM_NOTE},
        ]

    start, end = _utc_bounds(d_from, d_to)
    real = 'is_test = :f'
    p = {'f': False, 's': start, 'e': end}

    def one(sql, **extra):
        rows = _q(sql, **{**p, **extra})
        return int(rows[0][0] or 0) if rows else 0

    people = one(f'SELECT COUNT(DISTINCT user_id) FROM pwa_installs WHERE {real} AND user_id IS NOT NULL')
    anon = one(f'SELECT COUNT(*) FROM pwa_installs WHERE {real} AND user_id IS NULL')
    people_period = one(f'SELECT COUNT(DISTINCT user_id) FROM pwa_installs WHERE {real} AND user_id IS NOT NULL '
                        'AND created_at >= :s AND created_at < :e')
    # «новые» — первая установка человека попала в период
    new_people = one(f'SELECT COUNT(*) FROM (SELECT user_id, MIN(created_at) AS first_at FROM pwa_installs '
                     f'WHERE {real} AND user_id IS NOT NULL GROUP BY user_id) t '
                     'WHERE first_at >= :s AND first_at < :e')
    tests = one('SELECT COUNT(*) FROM pwa_installs WHERE is_test <> :f')
    guest_filter = ' WHERE COALESCE(is_guest, :f) = :f' if _has_column('users', 'is_guest') else ''
    registered = one(f'SELECT COUNT(*) FROM users{guest_filter}')

    by_all = {str(r[0] or 'other'): int(r[1]) for r in (_q(
        f'SELECT platform, COUNT(DISTINCT user_id) FROM pwa_installs WHERE {real} AND user_id IS NOT NULL '
        'GROUP BY platform', **p) or [])}
    by_period = {str(r[0] or 'other'): int(r[1]) for r in (_q(
        f'SELECT platform, COUNT(DISTINCT user_id) FROM pwa_installs WHERE {real} AND user_id IS NOT NULL '
        'AND created_at >= :s AND created_at < :e GROUP BY platform', **p) or [])}
    known = {k for k, _ in PLATFORMS}
    for src in (by_all, by_period):
        for k in [k for k in src if k not in known]:
            src['other'] = src.get('other', 0) + src.pop(k)

    cards = [
        {'title': 'Людей с приложением', 'value': people,
         'sub': f'за всё время{f" · ещё {anon} установок без входа" if anon else ""}'},
        {'title': 'Доля от зарегистрированных', 'value': _fmt_pct(_pct(people, registered)),
         'sub': f'{people} из {registered}'},
        {'title': 'Новых за период', 'value': new_people, 'sub': f'поставили впервые · всего за период: {people_period}'},
        {'title': 'На Android', 'value': by_all.get('android', 0),
         'sub': f'{_fmt_pct(_pct(by_all.get("android", 0), people))} от людей с приложением'},
        access_card,
    ]
    total_all = sum(by_all.values()) or 1
    bar = [{'label': title, 'value': by_all.get(k, 0), 'pct': round(100 * by_all.get(k, 0) / total_all)}
           for k, title in PLATFORMS if by_all.get(k, 0) or k != 'other']
    plat_rows = [[title, by_all.get(k, 0), by_period.get(k, 0)] for k, title in PLATFORMS
                 if by_all.get(k, 0) or by_period.get(k, 0) or k != 'other']

    day = _day_expr('created_at')
    day_rows = [[str(r[0]), int(r[1]), int(r[2])] for r in (_q(
        f'SELECT {day}, COUNT(DISTINCT user_id), '
        "COUNT(DISTINCT CASE WHEN platform = 'android' THEN user_id END) "
        f'FROM pwa_installs WHERE {real} AND user_id IS NOT NULL AND created_at >= :s AND created_at < :e '
        'GROUP BY 1 ORDER BY 1 DESC', **p) or [])]

    titles = dict(PLATFORMS)
    recent = []
    for r in (_q('SELECT i.user_id, i.username, i.platform, i.source, i.is_test, i.created_at '
                 'FROM pwa_installs i ORDER BY i.created_at DESC LIMIT 50') or []):
        uid, uname, plat, source, is_test, created = r
        who = {'text': uname or f'id {uid}', 'href': f'/admin/stats/person?id={uid}'} if uid else 'без входа'
        when = created.strftime('%d.%m.%Y %H:%M') if hasattr(created, 'strftime') else str(created or '')[:16]
        recent.append([who, titles.get(plat, plat or '—'), source or '—', 'тест' if is_test else '', when])

    blocks = [
        {'type': 'cards', 'items': cards},
        {'type': 'note', 'text': PLATFORM_NOTE},
        {'type': 'bar', 'title': 'Люди с приложением по устройствам (за всё время)', 'items': bar},
        {'type': 'table', 'title': 'По устройствам', 'header': ['Устройство', 'Людей всего', 'Людей за период'],
         'rows': plat_rows},
        {'type': 'table', 'title': 'По дням (МСК)', 'header': ['День', 'Людей', 'Из них на Android'],
         'rows': day_rows[:120], 'empty': 'За период установок не было.'},
        {'type': 'table', 'left': True, 'title': 'Последние установки (до 50, вместе с тестовыми)',
         'header': ['Кто', 'Устройство', 'Как засчитали', 'Тест', 'Когда (UTC)'], 'rows': recent},
        {'type': 'note', 'text': (
            f'Тестовых установок (аккаунты из PWA_STATS_EXCLUDE_USERS и тестеры до открытия): {tests} — в цифры выше '
            'не входят. Один человек считается один раз, даже если поставил на несколько устройств; в «По '
            'устройствам» он попадает в каждую свою платформу. Удаление приложения сайт не видит, поэтому это '
            '«ставили когда-либо», а не «стоит сейчас». Сырые данные — /admin/pwa/stats.')},
    ]
    return blocks


VIEWS = {'pwa': app_installs}
