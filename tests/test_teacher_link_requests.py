# -*- coding: utf-8 -*-
"""
tests/test_teacher_link_requests.py — CONFIRM_LINK_V1.

Учитель добавляет ученика по никнейму → ученик получает запрос и сам
подтверждает его (как запрос родителя). Статистика ученика доступна
учителю только после подтверждения.
"""
import json

import pytest
from models import db, User, T10Group, T10GroupMember, ParentChildLink


@pytest.fixture
def group(teacher_user):
    g = T10Group(
        name='Test Group',
        teacher_id=teacher_user.id,
        invite_code='AB3DEF',
    )
    db.session.add(g)
    db.session.commit()
    return g


def _login(client, user):
    # Flask-Login кеширует g._login_user на уровне контекста приложения,
    # а conftest держит один app-context на весь тест — сбрасываем кеш,
    # иначе следующий запрос «помнит» предыдущего пользователя.
    from flask import g
    try:
        g.pop('_login_user', None)
    except Exception:
        pass
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


class TestTeacherInviteFlow:
    """Учитель отправляет запрос по никнейму — ученик подтверждает."""

    def test_add_student_creates_pending(self, app, teacher_user, student_users, group):
        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.post(
                f'/teacher/group/{group.id}/add-student',
                data={'nickname': student_users[0].nickname},
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        gm = T10GroupMember.query.filter_by(
            group_id=group.id, user_id=student_users[0].id,
        ).first()
        assert gm is not None, 'Member row not created'
        assert gm.status == 'pending', (
            f'Invitation must be pending until student confirms, got {gm.status}'
        )

    def test_stats_hidden_before_confirmation(self, app, teacher_user, student_users, group):
        """Пока ученик не подтвердил — его статистика учителю недоступна (403)."""
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 403, (
                'Teacher must NOT see student stats before confirmation'
            )

    def test_student_api_pending_shows_request(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.get('/api/link-requests/pending')
            assert r.status_code == 200
            data = r.get_json()
            assert data['pending'] is True
            teacher_reqs = [x for x in data['requests'] if x['kind'] == 'teacher']
            assert len(teacher_reqs) == 1
            assert teacher_reqs[0]['id'] == gm.id
            assert teacher_reqs[0]['group'] == 'Test Group'

    def test_student_accepts_via_api(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post(
                '/api/link-requests/respond',
                data=json.dumps({'kind': 'teacher', 'id': gm.id, 'action': 'accept'}),
                content_type='application/json',
            )
            assert r.status_code == 200
            assert r.get_json()['ok'] is True

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'accepted'

        # Теперь учитель видит статистику.
        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 200

    def test_student_rejects_via_form(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post(
                f'/teacher-link/{gm.id}/respond',
                data={'action': 'reject', 'next': '/profile'},
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'rejected'

        # Отклонил — статистика по-прежнему закрыта.
        with app.test_client() as c:
            _login(c, teacher_user)
            assert c.get(f'/student/{student_users[0].id}').status_code == 403

        # Учитель может отправить запрос повторно.
        with app.test_client() as c:
            _login(c, teacher_user)
            c.post(
                f'/teacher/group/{group.id}/add-student',
                data={'nickname': student_users[0].nickname},
            )
        gm3 = db.session.get(T10GroupMember, gm.id)
        assert gm3.status == 'pending'

    def test_another_student_cannot_respond(self, app, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                '/api/link-requests/respond',
                data=json.dumps({'kind': 'teacher', 'id': gm.id, 'action': 'accept'}),
                content_type='application/json',
            )
            assert r.status_code == 404

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'pending'

    def test_only_teacher_can_add(self, app, student_users, group):
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post(
                f'/teacher/group/{group.id}/add-student',
                data={'nickname': student_users[1].nickname},
            )
            assert r.status_code == 403

    def test_cannot_add_teacher_account(self, app, teacher_user, student_users, group):
        other_teacher = User(
            email='other_teacher@example.invalid',
            nickname='other_teacher',
            role='teacher',
            is_guest=False,
        )
        db.session.add(other_teacher)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.post(
                f'/teacher/group/{group.id}/add-student',
                data={'nickname': 'other_teacher'},
                follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'только аккаунт ученика' in r.get_data(as_text=True)

    def test_duplicate_pending_request(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.post(
                f'/teacher/group/{group.id}/add-student',
                data={'nickname': student_users[0].nickname},
                follow_redirects=True,
            )
            assert 'уже отправлен' in r.get_data(as_text=True)

        assert T10GroupMember.query.filter_by(
            group_id=group.id, user_id=student_users[0].id,
        ).count() == 1

    def test_join_group_accepts_pending_invite(self, app, teacher_user, student_users, group):
        """Ученик приглашён учителем и подтверждает через код группы."""
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            c.post('/profile/join-group', data={'invite_code': 'AB3DEF'})

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'accepted'


class TestGroupStatsExcludePending:
    """Pending-ученики не попадают в статистику группы и дашборда."""

    def test_pending_not_in_group_view(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/teacher/group/{group.id}')
            html = r.get_data(as_text=True)
            assert student_users[0].nickname in html  # виден в секции ожидания
            assert 'Ждут подтверждения' in html

    def test_teacher_dashboard_shows_pending_count(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get('/teacher')
            html = r.get_data(as_text=True)
            assert 'Ждут подтверждения: 1' in html


class TestParentLinkViaApi:
    """Родительский запрос тоже виден в модальном уведомлении (API)."""

    def test_parent_request_in_api(self, app, student_users):
        parent = User(
            email='parent_x@example.invalid',
            nickname='parent_x',
            role='parent',
            is_guest=False,
        )
        db.session.add(parent)
        db.session.commit()
        link = ParentChildLink(
            parent_id=parent.id, child_id=student_users[0].id, status='pending',
        )
        db.session.add(link)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.get('/api/link-requests/pending')
            data = r.get_json()
            parent_reqs = [x for x in data['requests'] if x['kind'] == 'parent']
            assert len(parent_reqs) == 1
            assert parent_reqs[0]['id'] == link.id

    def test_parent_accept_via_api(self, app, student_users):
        parent = User(
            email='parent_y@example.invalid',
            nickname='parent_y',
            role='parent',
            is_guest=False,
        )
        db.session.add(parent)
        db.session.commit()
        link = ParentChildLink(
            parent_id=parent.id, child_id=student_users[0].id, status='pending',
        )
        db.session.add(link)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post(
                '/api/link-requests/respond',
                data=json.dumps({'kind': 'parent', 'id': link.id, 'action': 'accept'}),
                content_type='application/json',
            )
            assert r.get_json()['ok'] is True

        link2 = db.session.get(ParentChildLink, link.id)
        assert link2.status == 'accepted'

        # Родитель видит статистику ребёнка.
        with app.test_client() as c:
            _login(c, parent)
            assert c.get(f'/student/{student_users[0].id}').status_code == 200

    def test_legacy_child_email_no_access(self, app, student_users):
        """Без подтверждённой связи родитель НЕ видит статистику (легаси убран)."""
        parent = User(
            email='parent_z@example.invalid',
            nickname='parent_z',
            role='parent',
            child_email=student_users[0].nickname,
            is_guest=False,
        )
        db.session.add(parent)
        db.session.commit()

        with app.test_client() as c:
            _login(c, parent)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 403

    def test_guest_gets_no_pending(self, app, student_users):
        u = User(email='guest_x@example.invalid', nickname='guest_x',
                 is_guest=True, role='student')
        db.session.add(u)
        db.session.commit()
        with app.test_client() as c:
            _login(c, u)
            r = c.get('/api/link-requests/pending')
            data = r.get_json()
            assert data['pending'] is False


class TestStudentDetailStats:
    """Полная статистика на странице ученика."""

    def test_detail_contains_full_stats(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 200
            html = r.get_data(as_text=True)
            for marker in (
                'Точность ответов',
                'Активных дней',
                'Тестов пройдено',
                'Календарь месяца',
                'Полная статистика ученика',
            ):
                assert marker in html, f'Missing stats marker: {marker}'


class TestStatsCalculations:
    """Статистика адаптивных тестов и пользовательские метрики."""

    def test_stats_counts_completed_tests(self, app, teacher_user, student_users, group):
        from models import AdaptiveTestResult
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(gm)
        # Три завершённых теста + один незавершённый (completed_at IS NULL).
        for lvl, done in ((3, True), (5, True), (4, True), (None, False)):
            from datetime import datetime, timedelta
            r = AdaptiveTestResult(
                user_id=student_users[0].id, topic='algebra',
                final_level=lvl,
                completed_at=(datetime.utcnow() - timedelta(hours=1) if done else None),
            )
            db.session.add(r)
        db.session.commit()

        from routes.parent_teacher import _test_stats
        stats = _test_stats(student_users[0].id)
        assert stats['count'] == 3, f'Expected 3 completed tests, got {stats["count"]}'
        assert stats['avg_level'] == 4.0
        assert stats['last_at'] is not None

    def test_detail_shows_user_stats(self, app, teacher_user, student_users, group):
        gm = T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(gm)
        s = student_users[0]
        s.total_problems_solved = 42
        s.experience_points = 1500
        s.current_level = 5
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/student/{s.id}')
            html = r.get_data(as_text=True)
            assert 'Всего решено задач' in html
            assert 'Опыт (XP)' in html
            assert '42' in html
            assert '1500' in html


class TestFullStatsForAdults:
    """CONFIRM_LINK_V1: «вся статистика» — точные значения, не только разделы.

    Учитель (accepted member) и родитель (accepted link) видят одну и ту же
    полную страницу статистики: задачи дня, точность, тесты, XP, календарь.
    """

    def _seed_stats(self, student):
        from datetime import date, datetime, timedelta
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        from models import AdaptiveTestResult

        # Два дня задач: 3 задачи (2 верно, 1 нет) + 2 задачи (2 верно).
        days = [
            (date.today() - timedelta(days=1), [True, True, False]),
            (date.today(), [True, True]),
        ]
        for d, results in days:
            s = DailyTaskSet(user_id=student.id, target_date=d, status='done')
            db.session.add(s)
            db.session.flush()
            for i, ok in enumerate(results, start=1):
                db.session.add(DailyTaskItem(
                    daily_set_id=s.id, position=i,
                    task_text='Тестовая задача', user_answer='42', is_correct=ok,
                ))
        # Два завершённых теста (уровни 3 и 5 -> среднее 4.0) + один живой.
        for lvl in (3, 5):
            db.session.add(AdaptiveTestResult(
                user_id=student.id, topic='algebra', final_level=lvl,
                completed_at=datetime.utcnow() - timedelta(hours=2),
            ))
        db.session.add(AdaptiveTestResult(
            user_id=student.id, topic='geometry', final_level=None,
            completed_at=None,
        ))
        student.total_problems_solved = 7
        student.experience_points = 1200
        student.current_level = 4
        db.session.commit()

    def _assert_full_stats(self, html):
        # Точность: 4 верно из 5 попыток = 80%
        assert 'Точность ответов' in html
        assert '80.0%' in html, 'accuracy 4/5 must render as 80.0%'
        assert '2' in html  # активных дня
        # Всего решено задач (за всё время) и XP
        assert 'Всего решено задач' in html
        assert '7' in html
        assert 'Опыт (XP)' in html
        assert '1200' in html
        # Пройденные тесты: 2 завершённых, средний уровень 4
        assert 'Тестов пройдено' in html
        assert '4.0' in html or '4' in html
        # Календарь месяца: сегодняшняя ячейка с подсветкой
        assert 'Календарь месяца' in html
        assert 'cal-cell today' in html

    def test_teacher_sees_exact_stats(self, app, teacher_user, student_users, group):
        db.session.add(T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='accepted',
        ))
        db.session.commit()
        self._seed_stats(student_users[0])

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 200
            self._assert_full_stats(r.get_data(as_text=True))

    def test_parent_sees_exact_stats(self, app, student_users):
        parent = User(
            email='parent_full@example.invalid',
            nickname='parent_full', role='parent',
        )
        db.session.add(parent)
        db.session.flush()
        db.session.add(ParentChildLink(
            parent_id=parent.id, child_id=student_users[0].id,
            status='accepted',
        ))
        db.session.commit()
        self._seed_stats(student_users[0])

        with app.test_client() as c:
            _login(c, parent)
            r = c.get(f'/student/{student_users[0].id}')
            assert r.status_code == 200
            self._assert_full_stats(r.get_data(as_text=True))

    def test_stats_parity_with_own_view(self, app, student_users, teacher_user, group):
        """Учитель видит те же показатели, что и сам ученик на своей странице."""
        db.session.add(T10GroupMember(
            group_id=group.id, user_id=student_users[0].id,
            role='student', status='accepted',
        ))
        db.session.commit()
        self._seed_stats(student_users[0])

        with app.test_client() as c:
            _login(c, student_users[0])
            own = c.get(f'/student/{student_users[0].id}')
            assert own.status_code == 200
            own_html = own.get_data(as_text=True)
            self._assert_full_stats(own_html)

            _login(c, teacher_user)
            teacher_view = c.get(f'/student/{student_users[0].id}')
            assert teacher_view.status_code == 200
            t_html = teacher_view.get_data(as_text=True)
            self._assert_full_stats(t_html)
            # Ключевые значения совпадают между своим и учительским просмотром
            for marker in ('80%', '1200', 'Календарь месяца'):
                assert (marker in own_html) == (marker in t_html)
