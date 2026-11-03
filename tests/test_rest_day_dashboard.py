# -*- coding: utf-8 -*-
"""ВЫХОДНОЙ по расписанию пилота: на дашборде задач дня — НИЧЕГО.

Регрессия (03.11.2026, владелец): у пилота с выбранными днями занятий
в выходной страница «Задачи дня» всё равно показывала карточку
«Сначала — тест» (гейт срез-теста). Владелец: «если выходной, то
ничего не должно быть — ни теста, ни метода».

Проверяем НАСТОЯЩИЙ маршрут /daily_tasks: пилот с подпиской calm,
дни занятий не включают сегодня, цикл куратора активен и заблокирован
срезом — дашборд должен быть пуст (status='rest_day'), без карточки
теста и без задач.

Run: pytest tests/test_rest_day_dashboard.py -v
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DT_INIT_RE = re.compile(
    r'<script id="dt-init-data" type="application/json">(.*?)</script>', re.S,
)


def _dashboard_data(client) -> dict:
    rv = client.get('/daily_tasks', follow_redirects=True)
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    m = _DT_INIT_RE.search(html)
    assert m, 'dt-init-data не найден на странице'
    return json.loads(m.group(1))


def _setup_pilot_on_rest_day(user_id: int, auth=False):
    """Пилот calm с днями занятий, НЕ включающими сегодня.

    Возвращает (user_id, today_weekday). Цикл куратора создаём
    отдельным вызовом — он должен остаться заблокированным срезом,
    чтобы старый код показал карточку «Сначала — тест».
    """
    from models import db, Subscription

    # активная пилотная подписка «Спокойный»
    db.session.add(Subscription(
        user_id=user_id,
        plan='premium_calm',
        status='active',
        started_at=datetime.utcnow() - timedelta(days=3),
        expires_at=datetime.utcnow() + timedelta(days=30),
    ))

    # дни занятий: 3 дня, сегодня в них НЕ входит (→ выходной)
    from services.schedule_days import TABLE_NAME as _SDT
    from sqlalchemy import text
    today_wd = date.today().weekday()
    days = [d for d in range(7) if d != today_wd][:3]
    db.session.execute(text(
        f"CREATE TABLE IF NOT EXISTS {_SDT} ("
        "  user_id INTEGER PRIMARY KEY,"
        "  days TEXT NOT NULL,"
        "  plan VARCHAR(40),"
        "  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
    db.session.execute(text(
        f"INSERT OR REPLACE INTO {_SDT} (user_id, days, plan) "
        "VALUES (:uid, :days, 'premium_calm')"),
        {'uid': user_id, 'days': json.dumps(days)})
    db.session.commit()

    # цикл куратора: анкета пройдена, 9 класс → срез требуется
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id, grade=9)
        db.session.add(cs)
    cs.grade = 9
    cs.prep_state = {'intake': {'completed': True}}
    db.session.commit()

    from curator.monthly_cycle import build_or_get_cycle
    build_or_get_cycle(user_id, 9)
    db.session.commit()

    # убедимся, что гейт среза действительно активен (иначе тест
    # ничего не доказывает: без «blocked» старый код ничего и не
    # показывал бы)
    from curator.monthly_cycle import get_cycle_info
    ci = get_cycle_info(user_id)
    assert ci.get('active'), 'цикл куратора не активен — сетап теста битый'
    assert ci.get('blocked'), 'срез не блокирует — сетап теста битый'

    return user_id


def test_rest_day_shows_nothing(app, client, test_user):
    """Выходной: ни карточки «Сначала — тест», ни метода, ни задач."""
    from models import db, User

    # test_user — id=1, он в PILOT_USER_IDS по умолчанию
    uid = _setup_pilot_on_rest_day(test_user.id)

    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)

    rv = client.get('/daily_tasks', follow_redirects=True)
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)

    data = json.loads(_DT_INIT_RE.search(html).group(1))
    assert data.get('status') == 'rest_day', (
        f"ожидаля rest_day, получили {data.get('status')!r}"
    )
    assert not (data.get('items') or [])
    assert not data.get('blocked')

    # карточки состояний есть в разметке всегда — JS показывает их
    # только по статусу; проверяем, что все скрыты (dt-hidden)
    for _sid in ('dt-blocked-state', 'dt-method-day-state', 'dt-ready-state'):
        m2 = re.search(rf'id="{_sid}" class="([^"]*)"', html)
        assert m2, f'{_sid} не найден на странице'
        assert 'dt-hidden' in m2.group(1), (
            f'{_sid} виден в выходной — должен быть скрыт'
        )
    # баннер плана сверху по-прежнему объясняет, что сегодня выходной
    assert 'Сегодня выходной' in html


def test_lesson_day_still_works(app, client):
    """Контроль: не-пилот без расписания видит обычный дашборд (не rest_day)."""
    from models import db, User

    u = User(id=8811, email='rest_ctrl@test.invalid', nickname='rest_ctrl')
    db.session.add(u)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id)

    data = _dashboard_data(client)
    assert data.get('status') != 'rest_day'
    assert data.get('status') != 'blocked'
