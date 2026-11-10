# -*- coding: utf-8 -*-
"""
tests/test_join_by_code.py — JOIN_CODE_V1: единая страница /join.

Покрывает:
* GET /join (аноним → login, ученик → 200)
* вступление в группу учителя по коду через POST /join
* привязку к родителю по коду через POST /join
* ошибки: неверный формат, несуществующий код, повторное вступление,
  ограничения по роли (teacher/parent), блокировка.
"""
import pytest

from models import db, User, T10Group, T10GroupMember, ParentChildLink


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


class TestJoinPage:
    """GET /join — доступность страницы."""

    def test_anonymous_redirected_to_login(self, app):
        with app.test_client() as c:
            r = c.get('/join', follow_redirects=False)
            # 302 — редирект на /login; 401 — unauthorized-ответ flask-login
            # в тестовом приложении без login-страницы.
            assert r.status_code in (301, 302, 401), 'Anonymous must be rejected'

    def test_student_gets_page(self, app, student_users):
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.get('/join')
            assert r.status_code == 200
            assert 'invite_code' in r.get_data(as_text=True)

    def test_guest_redirected(self, app, test_user):
        test_user.is_guest = True
        db.session.commit()
        with app.test_client() as c:
            _login(c, test_user)
            r = c.get('/join', follow_redirects=False)
            assert r.status_code in (301, 302), 'Guest must be redirected'


class TestJoinTeacherGroup:
    """POST /join — вступление в группу учителя по коду."""

    def _make_group(self, teacher, code='J2NCDE'):
        g = T10Group(name='Join Group', teacher_id=teacher.id, invite_code=code)
        db.session.add(g)
        db.session.commit()
        return g

    def test_student_joins_group(self, app, teacher_user, student_users):
        g = self._make_group(teacher_user)
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': g.invite_code.lower()}, follow_redirects=True)
            assert r.status_code == 200

        gm = T10GroupMember.query.filter_by(
            group_id=g.id, user_id=student_users[0].id
        ).first()
        assert gm is not None, 'Member not created'
        assert gm.status == 'accepted'
        assert gm.role == 'student'

    def test_teacher_notified(self, app, teacher_user, student_users):
        from models import Notification
        g = self._make_group(teacher_user, code='N0TF12')
        with app.test_client() as c:
            _login(c, student_users[1])
            c.post('/join', data={'invite_code': 'N0TF12'}, follow_redirects=True)

        n = Notification.query.filter_by(
            user_id=teacher_user.id, type='group_join',
        ).first()
        assert n is not None, 'Teacher not notified about join by code'

    def test_already_member_flash(self, app, teacher_user, student_users):
        g = self._make_group(teacher_user)
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[0].id,
            role='student', status='accepted',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': g.invite_code}, follow_redirects=True)
            assert r.status_code == 200
            assert 'уже состоите' in r.get_data(as_text=True)

    def test_pending_invite_accepted_by_code(self, app, teacher_user, student_users,
                                             grant_seats):
        # SEAT_SUBSCRIPTION_V1: апгрейд pending→accepted тоже занимает место —
        # у учителя должна быть активная подписка с местами.
        grant_seats(teacher_user.id)
        g = self._make_group(teacher_user)
        gm = T10GroupMember(
            group_id=g.id, user_id=student_users[2].id,
            role='student', status='pending',
        )
        db.session.add(gm)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[2])
            c.post('/join', data={'invite_code': g.invite_code}, follow_redirects=True)

        gm2 = db.session.get(T10GroupMember, gm.id)
        assert gm2.status == 'accepted'

    def test_wrong_code_error(self, app, student_users):
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': 'ZZZZZZ'}, follow_redirects=True)
            assert r.status_code == 200
            assert 'не найден' in r.get_data(as_text=True)

    def test_bad_format_rejected(self, app, student_users):
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': 'SHORT'}, follow_redirects=True)
            assert r.status_code == 200
            assert 'формат' in r.get_data(as_text=True)
        # ничего не создано
        assert T10GroupMember.query.count() == 0

    def test_teacher_account_cannot_join(self, app, teacher_user):
        g = T10Group(name='T', teacher_id=teacher_user.id, invite_code='TTTTTT')
        db.session.add(g)
        db.session.commit()

        with app.test_client() as c:
            _login(c, teacher_user)
            r = c.post('/join', data={'invite_code': 'TTTTTT'}, follow_redirects=True)
            assert 'только ученические' in r.get_data(as_text=True)

    def test_parent_account_cannot_join(self, app, parent_user):
        with app.test_client() as c:
            _login(c, parent_user)
            r = c.post('/join', data={'invite_code': 'ABCDEF'}, follow_redirects=True)
            assert 'только ученические' in r.get_data(as_text=True)


class TestJoinParent:
    """POST /join — привязка к родителю по коду."""

    def _give_parent_code(self, parent, code='P4RENT'):
        parent.parent_invite_code = code
        db.session.commit()
        return code

    def test_student_links_parent(self, app, parent_user, student_users):
        code = self._give_parent_code(parent_user)
        with app.test_client() as c:
            _login(c, student_users[1])
            r = c.post('/join', data={'invite_code': code}, follow_redirects=True)
            assert r.status_code == 200
            assert 'привязаны' in r.get_data(as_text=True)

        link = ParentChildLink.query.filter_by(
            parent_id=parent_user.id, child_id=student_users[1].id,
        ).first()
        assert link is not None, 'ParentChildLink not created'
        assert link.status == 'accepted'

    def test_pending_link_accepted_by_code(self, app, parent_user, student_users,
                                          grant_seats):
        # SEAT_SUBSCRIPTION_V1: апгрейд pending→accepted занимает место родителя.
        grant_seats(parent_user.id)
        code = self._give_parent_code(parent_user)
        link = ParentChildLink(
            parent_id=parent_user.id, child_id=student_users[2].id,
            status='pending',
        )
        db.session.add(link)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[2])
            c.post('/join', data={'invite_code': code}, follow_redirects=True)

        link2 = db.session.get(ParentChildLink, link.id)
        assert link2.status == 'accepted'

    def test_blocked_link_stays_blocked(self, app, parent_user, student_users):
        code = self._give_parent_code(parent_user)
        link = ParentChildLink(
            parent_id=parent_user.id, child_id=student_users[0].id,
            status='blocked',
        )
        db.session.add(link)
        db.session.commit()

        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': code}, follow_redirects=True)
            assert 'заблокирована' in r.get_data(as_text=True)

        link2 = db.session.get(ParentChildLink, link.id)
        assert link2.status == 'blocked'

    def test_wrong_parent_code(self, app, parent_user, student_users):
        self._give_parent_code(parent_user, code='P4RENT')
        with app.test_client() as c:
            _login(c, student_users[0])
            r = c.post('/join', data={'invite_code': 'QQQQQQ'}, follow_redirects=True)
            assert 'не найден' in r.get_data(as_text=True)
        assert ParentChildLink.query.count() == 0


class TestParentCodeLifecycle:
    """Выдача и обновление кода родителя."""

    def test_dashboard_assigns_code(self, app, parent_user):
        assert not parent_user.parent_invite_code
        with app.test_client() as c:
            _login(c, parent_user)
            r = c.get('/parent')
            assert r.status_code == 200
        parent2 = db.session.get(User, parent_user.id)
        assert parent2.parent_invite_code
        assert len(parent2.parent_invite_code) == 6
        bad = {'O', '0', 'I', '1'}
        assert not any(ch in parent2.parent_invite_code for ch in bad)
        assert parent2.parent_invite_code in r.get_data(as_text=True)

    def test_regenerate_changes_code(self, app, parent_user):
        with app.test_client() as c:
            _login(c, parent_user)
            c.get('/parent')  # выдаёт первый код
            old = db.session.get(User, parent_user.id).parent_invite_code
            r = c.post('/parent/invite-code/regenerate')
            assert r.status_code in (200, 302)
        new = db.session.get(User, parent_user.id).parent_invite_code
        assert new and new != old

    def test_code_unique_vs_groups(self, app, teacher_user):
        from services.parent_teacher_helpers import generate_parent_invite_code
        g = T10Group(name='X', teacher_id=teacher_user.id, invite_code='GRPCDE')
        db.session.add(g)
        db.session.commit()
        for _ in range(5):
            code = generate_parent_invite_code()
            assert code != 'GRPCDE'
