# -*- coding: utf-8 -*-
"""OLYMPIAD_LADDER_V1: лестница пробников под класс.

школьный ВсОШ → (≥50%) муниципальный / (<50%) снова школьный →
(≥50%) перечневые от куратора; 5–8 классы — своя стартовая олимпиада.
"""
from datetime import date

import pytest

from models import db, User, DailyTaskBank, BankIssue
from curator import session_plan
from services import olympiad_ladder as ladder
from services.real_probnik import parse_code


@pytest.fixture
def student(app):
    u = User(email='ladder@test.ru', nickname='ladder')
    db.session.add(u)
    db.session.commit()
    return u


def _set_grade(uid, grade):
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs is None:
        cs = CuratorState(user_id=uid)
        db.session.add(cs)
    cs.grade = grade
    db.session.commit()


def _sit(uid, code, correct, total=None, answered=None):
    """Пробник выдан (curator_lessons) и сдан: correct из total верно."""
    session_plan.ensure_tables()
    seq = max((l['seq'] for l in session_plan._lessons(uid)), default=0) + 1
    db.session.execute(db.text(
        f"INSERT INTO {session_plan.TABLE_NAME} (user_id, seq, lesson_type, "
        "status, probnik_code, assigned_date) VALUES (:u, :s, 'probnik', "
        "'completed', :c, :d)"), {'u': uid, 's': seq, 'c': code,
                                   'd': date.today()})
    total = total or 4
    answered = total if answered is None else answered
    for i in range(total):
        row = DailyTaskBank(subtopic=f'probnik:{code}', section='t', level=1,
                            statement=f'задача {i}', position=i + 1)
        db.session.add(row)
        db.session.flush()
        if i < answered:
            db.session.add(BankIssue(user_id=uid, task_id=row.id,
                                     subtopic=row.subtopic, level=1,
                                     issued_date=date.today(),
                                     user_answer='x', is_correct=i < correct))
    db.session.commit()


def _used(uid):
    return {l['probnik_code'] for l in session_plan._lessons(uid)
            if l['probnik_code']}


def _peek(uid, grade, pref=None):
    return ladder.pick_next(uid, grade, _used(uid), preferred_slug=pref,
                            create=False)


def test_grade9_starts_with_vsosh_school(student):
    p = _peek(student.id, 9)
    info = parse_code(p['code'])
    assert info['slug'] == 'vsosh' and info['stage'] == 'school'


def test_school_fail_repeats_school_pass_goes_municipal(student):
    uid = student.id
    first = _peek(uid, 9)['code']
    _sit(uid, first, correct=1)                  # 25% — не прошёл
    again = _peek(uid, 9)['code']
    assert again != first
    assert parse_code(again)['stage'] == 'school'
    _sit(uid, again, correct=2)                  # 50% — прошёл
    mun = _peek(uid, 9)['code']
    assert parse_code(mun)['stage'] == 'municipal'


def test_incomplete_probnik_gives_no_result(student):
    uid = student.id
    first = _peek(uid, 9)['code']
    _sit(uid, first, correct=3, answered=3)      # 4-я задача без ответа
    nxt = _peek(uid, 9)['code']
    assert parse_code(nxt)['stage'] == 'school'


def test_municipal_fail_stays_pass_goes_perechen(student):
    uid = student.id
    _sit(uid, _peek(uid, 9)['code'], correct=4)  # школьный сдан
    mun = _peek(uid, 9)['code']
    _sit(uid, mun, correct=0)                    # муниципальный не сдан
    mun2 = _peek(uid, 9)['code']
    assert parse_code(mun2)['stage'] == 'municipal' and mun2 != mun
    _sit(uid, mun2, correct=3)                   # сдан
    per = _peek(uid, 9, pref='turnir-gorodov')
    assert per['slug'] == 'turgor'               # выбор ученика — первым
    st = ladder.ladder_state(uid, 9, _used(uid), 'turnir-gorodov')
    assert st['rung'] == 2 and st['perechen'][0] == 'turgor'
    assert 1 < len(st['perechen']) <= ladder.PERECHEN_PICK
    assert all(s in ladder.DEFAULT_PERECHEN[9] for s in st['perechen'])


def test_perechen_rotates_between_offered(student):
    uid = student.id
    _sit(uid, _peek(uid, 9)['code'], correct=4)
    _sit(uid, _peek(uid, 9)['code'], correct=4)
    slugs = []
    for _ in range(3):
        p = _peek(uid, 9)
        slugs.append(p['slug'])
        _sit(uid, p['code'], correct=0)
    assert len(set(slugs)) == 3


@pytest.mark.parametrize('grade,slug', [(5, 'formula-unity'), (6, 'matprazdnik'),
                                        (7, 'matprazdnik'), (8, 'euler')])
def test_junior_grades_entry_olympiad(student, grade, slug):
    p = _peek(student.id, grade)
    assert p and p['slug'] == slug


def test_every_grade_has_a_ladder():
    for g in range(5, 12):
        assert ladder.rungs_for_grade(g), g
        assert ladder.DEFAULT_PERECHEN[g]


def test_pick_probnik_uses_ladder_and_creates(student):
    uid = student.id
    _set_grade(uid, 10)
    p = session_plan._pick_probnik(uid, None, set())
    assert p and parse_code(p['code'])['stage'] == 'school'
    from models_olympiad import Probnik
    assert Probnik.query.filter_by(code=p['code']).first() is not None


def test_rotation_admin_only(student, monkeypatch):
    """Пока только админам: у админа 6-я позиция — пробник, у остальных — практика."""
    monkeypatch.delenv('PROBNIK_IN_ROTATION', raising=False)
    monkeypatch.setattr(User, 'is_admin', property(lambda self: True))
    assert session_plan._lesson_type_for_position(student.id, 5) == 'probnik'
    assert session_plan._lesson_type_for_position(student.id, 0) == 'method'
    monkeypatch.setattr(User, 'is_admin', property(lambda self: False))
    assert session_plan._lesson_type_for_position(student.id, 5) == 'practice'


def test_rotation_flag(student, monkeypatch):
    monkeypatch.delenv('PROBNIK_IN_ROTATION', raising=False)
    monkeypatch.setattr(User, 'is_admin', property(lambda self: False))
    assert session_plan._lesson_type_for_position(student.id, 5) == 'practice'
    monkeypatch.setenv('PROBNIK_IN_ROTATION', '1')
    assert session_plan._lesson_type_for_position(student.id, 5) == 'probnik'
    assert session_plan._lesson_type_for_position(student.id, 0) == 'method'
