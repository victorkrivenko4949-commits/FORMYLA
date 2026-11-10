# -*- coding: utf-8 -*-
"""
tests/test_seat_limits.py — SEAT_SUBSCRIPTION_V1: лимит мест на ВСЕХ путях
принятия ученика.

Проверяется, что при исчерпанных местах (или отсутствии подписки) ученик
НЕ может стать 'accepted' ни по одному из путей:
* подтверждение приглашения учителя (форма /teacher-link/<id>/respond);
* подтверждение из модального уведомления (/api/link-requests/respond);
* вступление по коду группы (новый участник и апгрейд pending→accepted);
* привязка к родителю (принятие запроса и код родителя).
"""
import json

from models import db, User, T10Group, T10GroupMember, ParentChildLink


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _make_group(teacher, code='S1TCDE'):
    g = T10Group(name='Seat Limit Group', teacher_id=teacher.id, invite_code=code)
    db.session.add(g)
    db.session.commit()
    return g


class TestTeacherSeatLimit:
    """Учитель с подпиской на 1 место: второй ученик не принимается."""

    def test_accept_invite_blocked_when_seats_full(
        self, app, teacher_user, student_users, grant_seats,
    ):
        grant_seats(teacher_user.id, seats=1)
        g = _make_group(teacher_user)
        # Единственное место уже занято первым учеником.
        taken = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(taken)
        # Приглашение второму — отправлялось при свободном месте.
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[1].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                f'/teacher-link/{gm.id}/respond',
                data={'action': 'accept', 'next': '/join'},
                follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'pending', 'Accept must be blocked when seats are full'

    def test_accept_via_api_blocked_when_no_subscription(
        self, app, teacher_user, student_users,
    ):
        """Подписки нет вовсе — принятие тоже невозможно."""
        g = _make_group(teacher_user, code='N0SUBS')
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
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
            assert r.status_code == 400
            assert r.get_json()['ok'] is False

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'pending'

    def test_join_by_code_upgrade_blocked_when_seats_full(
        self, app, teacher_user, student_users, grant_seats,
    ):
        """Апгрейд pending→accepted по коду группы тоже занимает место."""
        grant_seats(teacher_user.id, seats=1)
        g = _make_group(teacher_user, code='UPGRDE')
        taken = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(taken)
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[1].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                '/join', data={'invite_code': 'UPGRDE'}, follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'pending'

    def test_join_by_code_new_member_blocked_when_seats_full(
        self, app, teacher_user, student_users, grant_seats,
    ):
        """Новый участник по коду не вступает при исчерпанных местах."""
        grant_seats(teacher_user.id, seats=1)
        g = _make_group(teacher_user, code='NEWMEM')
        taken = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(taken)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                '/join', data={'invite_code': 'NEWMEM'}, follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        assert T10GroupMember.query.filter_by(
            group_id=g.id, user_id=student_users[1].id,
        ).first() is None, 'New member must not be created when seats are full'

    def test_accept_invite_ok_when_seat_available(
        self, app, teacher_user, student_users, grant_seats,
    ):
        """Место есть — принятие работает как раньше (регресс)."""
        grant_seats(teacher_user.id, seats=2)
        g = _make_group(teacher_user, code='SEATOK')
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            c.post(
                f'/teacher-link/{gm.id}/respond',
                data={'action': 'accept', 'next': '/join'},
                follow_redirects=True,
            )

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'accepted'


class TestParentSeatLimit:
    """Родитель с подпиской на 1 место: второй ребёнок не привязывается."""

    def _make_parent_with_pending(self, parent, child):
        link = ParentChildLink(
            parent_id=parent.id, child_id=child.id, status='pending',
        )
        db.session.add(link)
        db.session.commit()
        return link

    def test_accept_link_blocked_when_seats_full(
        self, app, parent_user, student_users, grant_seats,
    ):
        grant_seats(parent_user.id, seats=1)
        # Место занято первым ребёнком.
        taken = ParentChildLink(
            parent_id=parent_user.id, child_id=student_users[0].id,
            status='accepted',
        )
        db.session.add(taken)
        # Запрос второму ребёнку отправлялся при свободном месте.
        link = self._make_parent_with_pending(parent_user, student_users[1])

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                f'/parent-link/{link.id}/respond',
                data={'action': 'accept', 'next': '/join'},
                follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        link2 = db.session.get(ParentChildLink, link.id)
        assert link2.status == 'pending'

    def test_link_by_code_blocked_when_seats_full(
        self, app, parent_user, student_users, grant_seats,
    ):
        """Код родителя при исчерпанных местах не привязывает нового ребёнка."""
        grant_seats(parent_user.id, seats=1)
        parent_user.parent_invite_code = 'FULL01'
        taken = ParentChildLink(
            parent_id=parent_user.id, child_id=student_users[0].id,
            status='accepted',
        )
        db.session.add(taken)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                '/join', data={'invite_code': 'FULL01'}, follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        assert ParentChildLink.query.filter_by(
            parent_id=parent_user.id, child_id=student_users[1].id,
        ).first() is None

    def test_pending_link_by_code_upgrade_blocked(
        self, app, parent_user, student_users, grant_seats,
    ):
        """Апгрейд pending→accepted по коду родителя тоже проверяет места."""
        grant_seats(parent_user.id, seats=1)
        parent_user.parent_invite_code = 'UPGRD1'
        taken = ParentChildLink(
            parent_id=parent_user.id, child_id=student_users[0].id,
            status='accepted',
        )
        db.session.add(taken)
        link = self._make_parent_with_pending(parent_user, student_users[1])

        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post(
                '/join', data={'invite_code': 'UPGRD1'}, follow_redirects=True,
            )
            assert r.status_code == 200
            assert 'закончились места' in r.get_data(as_text=True)

        link2 = db.session.get(ParentChildLink, link.id)
        assert link2.status == 'pending'


class TestJoinLinkPrefill:
    """INVITE_LINK_V1: ссылка /join?code=... подставляет код в форму."""

    def test_code_prefilled_on_join_page(self, app, teacher_user, student_users):
        g = _make_group(teacher_user, code='PREFIL')
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.get('/join?code=prefil')
            assert r.status_code == 200
            text = r.get_data(as_text=True)
            assert 'PREFIL' in text
            assert 'Seat Limit Group' in text

    def test_invalid_code_ignored(self, app, student_users):
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.get('/join?code=short')
            assert r.status_code == 200
