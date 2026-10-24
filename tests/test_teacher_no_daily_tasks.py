# -*- coding: utf-8 -*-
"""Роль teacher: /daily_tasks отдаёт статус teacher, а не подбирает набор.

Логика: задачи дня — практика учеников. Аккаунт учителя (role='teacher')
видит карточку «Задачи дня — для учеников» вместо empty-state/лимитов,
и сервер НЕ создаёт для него DailyTaskSet.

Run: pytest tests/test_teacher_no_daily_tasks.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_teacher_gets_teacher_state_not_daily_set():
    """Учитель открывает /daily_tasks → status='teacher', набор не создаётся."""
    from models import db, User
    from daily_tasks.models import DailyTaskSet
    from daily_tasks.services import today_in_user_tz
    from app import app

    with app.app_context():
        teacher = User(
            email="teacher_dt@test.formyla.local",
            name="TeacherDT",
            is_guest=False,
            role="teacher",
        )
        db.session.add(teacher)
        db.session.commit()
        teacher_id = teacher.id

        today = today_in_user_tz()
        # Чистим возможные наборы этого тестового учителя на сегодня
        DailyTaskSet.query.filter_by(
            user_id=teacher_id, target_date=today,
        ).delete()
        db.session.commit()

    with app.test_client() as c:
        login_rv = c.get(f'/dev_login?uid={teacher_id}')
        assert login_rv.status_code in (302, 200), (
            f"dev_login failed: {login_rv.status_code} "
            f"{login_rv.get_data(as_text=True)[:200]}"
        )

        rv = c.get('/daily_tasks')

    # Страница отдаётся успешно (не 402/403/404)
    assert rv.status_code == 200, (
        f"Got status {rv.status_code} body={rv.get_data(as_text=True)[:300]}"
    )
    html = rv.get_data(as_text=True)

    # Карточка учителя отрендерена видимой
    assert 'dt-teacher-state' in html, "нет карточки учителя в шаблоне"
    assert "Задачи дня — для учеников" in html
    assert "В аккаунте учителя задачи дня не выдаются" in html

    # Init-данные для JS несут статус teacher
    start = html.find('id="dt-init-data"')
    assert start != -1, "нет dt-init-data"
    payload = html[html.find('>', start) + 1:]
    payload = payload[:payload.find('</script>')]
    data = json.loads(payload)
    assert data.get('status') == 'teacher', data.get('status')

    # Сервер не создаёт набор задач дня для учителя
    with app.app_context():
        assert DailyTaskSet.query.filter_by(
            user_id=teacher_id, target_date=today,
        ).first() is None, "для учителя создан DailyTaskSet"

        # Убираем тестового пользователя
        User.query.filter_by(id=teacher_id).delete()
        db.session.commit()
