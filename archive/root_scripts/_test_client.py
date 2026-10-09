"""Test client — проверка регистрации victorkrvnk@gmail.com."""
import sys, os
os.environ['FLASK_ENV'] = 'development'
sys.path.insert(0, '.')
from app import app, db, User

with app.test_client() as client:
    # Шаг 1: POST /login с email
    resp = client.post('/login', data={'email': 'victorkrvnk@gmail.com'}, follow_redirects=False)
    print("=== POST /login (victorkrvnk@gmail.com) ===")
    print(f"Status: {resp.status_code}")
    print(f"Location: {resp.headers.get('Location', 'none')}")
    
    with client.session_transaction() as sess:
        verify_email = sess.get('verify_email')
        print(f"verify_email in session: {verify_email}")
    
    # Check if user exists and has auth_code
    with app.app_context():
        user = User.query.filter_by(email='victorkrvnk@gmail.com').first()
        if user:
            print(f"User: id={user.id}, email={user.email}, auth_code={user.auth_code}")
    
    # Шаг 2: Test with different cases
    print("\n=== Case sensitivity tests ===")
    for test_email in ['victorkrvnk@gmail.com', 'VictorKrvnk@gmail.com', 'VICTORKRVNK@GMAIL.COM']:
        resp2 = client.post('/login', data={'email': test_email}, follow_redirects=False)
        with client.session_transaction() as sess:
            ve = sess.get('verify_email')
        print(f"  {test_email}: status={resp2.status_code}, session_email={ve}")
    
    # Шаг 3: Check yandex-style lookup WITHOUT .lower()
    print("\n=== Yandex-login style lookup (without .lower()) ===")
    with app.app_context():
        for email in ['victorkrvnk@gmail.com', 'VictorKrvnk@gmail.com']:
            user = User.query.filter_by(email=email).first()
            print(f"  filter_by(email='{email}'): found={user is not None}, id={user.id if user else 'N/A'}")
