# -*- coding: utf-8 -*-
"""Test coach chat for 401 and check fallback behavior."""
import json, os, sys, io
sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'test'

_save = sys.stdout
sys.stdout = io.StringIO()
from app import app, db
from models import User
app.config['TESTING'] = True
app.config['SERVER_NAME'] = 'localhost'
sys.stdout = _save

client = app.test_client()

with app.app_context():
    u = User.query.get(1)
    if not u:
        u = User(email='test_coach@t.test', name='CoachTest', is_guest=False,
                 preferred_grade=9)
        db.session.add(u)
        db.session.commit()
    uid = u.id

with client.session_transaction() as sess:
    sess['_user_id'] = str(uid)
    sess['_fresh'] = True

r = client.post('/prep/coach/set_grade', json={'grade': 9})

questions = [
    "какой у меня уровень",
    "что у меня слабое",
    "успею ли я к олимпиаде",
    "сколько мне заниматься",
]

with open('_coach_responses.txt', 'w', encoding='utf-8') as out:
    for q in questions:
        out.write(f'\n--- Q: "{q}" ---\n')
        r = client.post('/prep/coach/chat', json={'message': q})
        out.write(f'Status: {r.status_code}\n')
        d = json.loads(r.data)
        reply = d.get('reply', '')
        out.write(f'Reply: {reply[:500]}\n')
        if 'не могу связаться' in reply:
            out.write('  -> FALLBACK (DeepSeek 401)\n')
        else:
            out.write('  -> ACTUAL DEEPSEEK RESPONSE\n')

print('Responses written to _coach_responses.txt')
for q in questions:
    print(f'Q: {q}')
