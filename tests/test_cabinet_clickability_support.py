# -*- coding: utf-8 -*-
"""CLICKABILITY_V1 + SUPPORT_CTA_V1 (09.11.2026).

Кабинеты родителя и учителя: быстрые действия, кликабельные карточки/строки,
кнопки копирования кода и блок «Написать в поддержку» (-> /api/support,
ответ в /my/support).
"""
import os

import pytest

DUMP_DIR = os.environ.get('CABINET_HTML_DUMP')


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


@pytest.fixture
def stub_ctx(app):
    app.context_processor(lambda: {'tg_trial_state': lambda: {'state': 'hidden'}})
    return app


@pytest.fixture
def parent_with_child(app, student_users):
    from models import db, User, ParentChildLink
    parent = User(email='parent_click@example.invalid', nickname='parent_click',
                  role='parent', is_guest=False)
    db.session.add(parent)
    db.session.flush()
    db.session.add(ParentChildLink(parent_id=parent.id, child_id=student_users[0].id,
                               status='accepted'))
    db.session.commit()
    return parent, student_users[0]


def _get(app, user, url, dump_name):
    with app.test_client() as c:
        _login(c, user)
        r = c.get(url)
        html = r.data.decode('utf-8')
        assert r.status_code == 200, html[:2000]
        if DUMP_DIR:
            os.makedirs(DUMP_DIR, exist_ok=True)
            with open(os.path.join(DUMP_DIR, dump_name), 'w', encoding='utf-8') as f:
                f.write(html)
        return html


def _assert_support(html, role_marker):
    assert 'id="support"' in html
    assert 'Написать в поддержку' in html
    assert "fetch('/api/support'" in html
    assert '/my/support' in html
    assert 'href="#support"' in html  # быстрая кнопка в шапке
    assert role_marker in html


def test_parent_dashboard_clickable_and_support(stub_ctx, parent_with_child):
    parent, child = parent_with_child
    html = _get(stub_ctx, parent, '/parent', 'parent.html')
    _assert_support(html, 'привязать ребёнка')
    assert 'class="quick-actions"' in html
    assert 'class="child-name-link"' in html
    assert f'href="/student/{child.id}"' in html
    assert html.count(f'class="stat-item" href="/student/{child.id}"') == 2


def test_teacher_dashboard_clickable_and_support(stub_ctx, teacher_user, group_with_students):
    html = _get(stub_ctx, teacher_user, '/teacher', 'teacher.html')
    _assert_support(html, 'добавить ученика')
    assert 'id="create-group"' in html
    assert 'class="group-link"' in html
    assert 'data-copy="ABCDEF"' in html


def test_teacher_group_rows_clickable_and_support(stub_ctx, teacher_user, group_with_students):
    html = _get(stub_ctx, teacher_user, f'/teacher/group/{group_with_students.id}', 'group.html')
    assert 'id="support"' in html and 'Написать в поддержку' in html
    assert 'clickable" data-href="/student/' in html
    assert 'data-copy="ABCDEF"' in html



@pytest.fixture
def child_with_activity(app, parent_with_child):
    """Ученик с задачами дня за неделю и уровнями по разделам."""
    import json
    from datetime import date, timedelta
    from models import db
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from models_curator import CuratorState
    parent, child = parent_with_child
    today = date.today()
    plan = [(0, 4, 3), (1, 5, 5), (2, 4, 2), (4, 4, 0), (5, 3, 3)]
    for back, total, correct in plan:
        ds = DailyTaskSet(user_id=child.id, target_date=today - timedelta(days=back), status='done')
        db.session.add(ds)
        db.session.flush()
        for k in range(total):
            db.session.add(DailyTaskItem(daily_set_id=ds.id, position=k + 1, task_text='t',
                                         user_answer='1', is_correct=k < correct))
    db.session.add(CuratorState(user_id=child.id, level_mu=2.6, level_sigma=0.9,
                                level_by_section=json.dumps({
                                    'algebra': {'mu': 3.4, 'sigma': 0.6},
                                    'geometry': {'mu': 1.6, 'sigma': 1.4},
                                    'combinatorics': {'mu': 2.7, 'sigma': 0.9},
                                    'logic': {'mu': 2.9, 'sigma': 1.0},
                                    'number_theory': {'mu': 2.2, 'sigma': 1.1},
                                })))
    db.session.commit()
    return parent, child


def test_student_stats_page_is_readable(stub_ctx, child_with_activity):
    parent, child = child_with_activity
    html = _get(stub_ctx, parent, f'/student/{child.id}', 'student.html')
    assert 'class="st-tabs"' in html
    assert 'Коротко' in html and 'За последние 7 дней' in html
    assert 'Сильнее всего — <b>Алгебра</b>' in html
    assert 'подтянуть стоит <b>Геометрия</b>' in html
    assert 'Сегодня уже занимался' in html
    assert 'class="cal-wd"' in html and 'Все цифры' in html
    assert 'из 4' in html
    assert 'id="support"' in html  # родителю доступна поддержка
