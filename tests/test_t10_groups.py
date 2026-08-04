# -*- coding: utf-8 -*-
"""
tests/test_t10_groups.py — acceptance tests for T10 parent/teacher/groups.
"""
import pytest
from models import db, User, T10Group, T10GroupMember


class TestGroupCreation:
    """POST /teacher/group/create — group creation with invite code."""

    def test_teacher_creates_group_code_len(self, app, teacher_user):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(teacher_user.id)
            r = c.post(
                '/teacher/group/create',
                data={'name': 'Test Group Alpha'},
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        g = T10Group.query.filter_by(teacher_id=teacher_user.id).first()
        assert g is not None, 'Group not created'
        assert len(g.invite_code) == 6, f'Invite code length != 6: {g.invite_code}'
        bad = {'O', '0', 'I', '1'}
        assert not any(ch in g.invite_code for ch in bad), f'Bad chars in code: {g.invite_code}'


class TestGroupCRUD:
    """Rename and delete group."""

    def test_group_rename_and_delete(self, app, teacher_user, student_users):
        # Create group via DB
        g = T10Group(
            name='To Rename',
            teacher_id=teacher_user.id,
            invite_code='XY3KLM',
        )
        db.session.add(g)
        db.session.commit()

        # Rename
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(teacher_user.id)
            r = c.post(
                f'/teacher/group/{g.id}/rename',
                data={'name': 'Renamed Group'},
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        g2 = T10Group.query.get(g.id)
        assert g2.name == 'Renamed Group'

        # Use the fixture's student
        gm = T10GroupMember(group_id=g.id, user_id=student_users[0].id, role='student')
        db.session.add(gm)
        db.session.commit()

        # Delete
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(teacher_user.id)
            r = c.post(
                f'/teacher/group/{g.id}/delete',
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        assert T10Group.query.get(g.id) is None
        assert T10GroupMember.query.filter_by(group_id=g.id).count() == 0


class TestStudentJoin:
    """Student joins group by invite code."""

    def test_student_joins_by_code(self, app, teacher_user, student_users):
        g = T10Group(
            name='Join Test',
            teacher_id=teacher_user.id,
            invite_code='AB3DEF',
        )
        db.session.add(g)
        db.session.commit()

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(student_users[0].id)
            r = c.post(
                '/profile/join-group',
                data={'invite_code': g.invite_code},
                follow_redirects=False,
            )
            assert r.status_code in (301, 302, 200)

        gm = T10GroupMember.query.filter_by(
            group_id=g.id, user_id=student_users[0].id,
        ).first()
        assert gm is not None
        assert gm.role == 'student'

    def test_wrong_invite_code_not_found(self, app, student_users):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(student_users[0].id)
            r = c.post(
                '/profile/join-group',
                data={'invite_code': 'ZZZZZZ'},
                follow_redirects=False,
            )
            assert r.status_code not in (200, 500), f'Expected non-200/500, got {r.status_code}'

    def test_student_without_group_gets_403_on_teacher(self, app, student_users):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(student_users[0].id)
            r = c.get('/teacher', follow_redirects=False)
            assert r.status_code == 403, f'Expected 403, got {r.status_code}'


class TestShareProgress:
    """Share progress toggle."""

    def test_share_progress_off_blocks_parent(self, app, parent_user):
        child = User.query.filter_by(email=parent_user.child_email).first()
        if child is None:
            pytest.skip('Child not found')
        child.share_progress = False
        db.session.commit()

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(parent_user.id)
            r = c.get('/parent', follow_redirects=False)
            assert r.status_code == 200
            text = r.data.decode('utf-8').lower()
            assert 'закрыл доступ' in text or 'закрыл' in text, (
                f'Expected blocked message, got: {text[:300]}'
            )
