import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User

TEST_DB = 'instance/_test_check.db'
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{TEST_DB}'

with app.app_context():
    db.create_all()
    print('OK: tables created')
    u = User(email='test@test.com', name='Test')
    db.session.add(u)
    db.session.commit()
    print('OK: user created, questionnaire_state:', repr(u.questionnaire_state))
    db.session.remove()

if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
print('Done.')
