from datetime import date

from flask import g
from sqlalchemy import text

from method_week.models import MethodWeekAnswer, MethodWeekSet
from models import User, db


def test_delete_account_clears_weekly_method_foreign_keys(app, client, student_users):
    if db.engine.dialect.name == 'sqlite':
        db.session.execute(text('PRAGMA foreign_keys=ON'))
    student_id, other_id = [user.id for user in student_users[:2]]
    sets = [
        MethodWeekSet(user_id=uid, week_start=date(2026, 11, 16),
                      method_code='G1', method_name='Метод', status='ready')
        for uid in (student_id, other_id)
    ]
    db.session.add_all(sets)
    db.session.flush()
    db.session.add_all([
        MethodWeekAnswer(set_id=week.id, user_id=week.user_id, position=1, user_answer='1')
        for week in sets
    ])
    db.session.commit()
    g.pop('_login_user', None)
    with client.session_transaction() as session:
        session['_user_id'] = str(student_id)

    response = client.post('/account/delete', json={'confirm': 'DELETE'})
    assert response.status_code == 200
    assert response.json['status'] == 'deleted'
    assert db.session.get(User, student_id) is None
    assert [row.user_id for row in MethodWeekSet.query.all()] == [other_id]
    assert [row.user_id for row in MethodWeekAnswer.query.all()] == [other_id]
