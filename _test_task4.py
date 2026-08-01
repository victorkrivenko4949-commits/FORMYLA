# -*- coding: utf-8 -*-
"""TASK 4: Cross-user data access using existing users from DB."""
import sys, os, io, json

sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'test'

old = sys.stdout
sys.stdout = io.StringIO()
from app import app, db
from models import User
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'localhost'
sys.stdout = old

results = []

with app.app_context():
    users = User.query.order_by(User.id.desc()).limit(3).all()
    uid_a = users[0].id if len(users) > 0 else None
    uid_b = users[1].id if len(users) > 1 else None
    if not uid_a or not uid_b:
        print("Need at least 2 users in DB")
        sys.exit(1)

with app.test_client() as c:
    # Login as user A using dev_login
    r = c.get(f'/dev_login?user_id={uid_a}', follow_redirects=False)
    print(f'Login A ({uid_a}): {r.status_code}')
    
    r = c.get('/profile', follow_redirects=False)
    print(f'Profile own: {r.status_code}')

    print(f'\n=== CROSS-USER TESTS (as user {uid_a}, targeting user {uid_b}) ===')
    print(f'{"Test":<45s} {"Status":>6s} {"Result":<10s}')
    print(f'{"-"*65}')
    
    tests = [
        ('GET', f'/user/{uid_b}', 'Other user page'),
        ('GET', f'/api/profile/{uid_b}', 'Other profile API'),
        ('GET', f'/student/{uid_b}', 'Student page'),
        ('GET', f'/api/progress/{uid_b}', 'Other progress'),
        ('GET', f'/api/chat/{uid_b}/messages', 'Other chat messages'),
    ]
    
    for method, url, desc in tests:
        r = c.get(url, follow_redirects=False) if method == 'GET' else c.post(url, follow_redirects=False)
        s = r.status_code
        loc = (r.headers.get('Location') or '').lower()
        leak = 'LEAK' if (s == 200 and 'login' not in loc) else 'OK' if s in (302, 303) and 'login' in loc else 'OK' if s == 403 else 'OK' if s == 404 else 'CHECK'
        print(f'{desc:<45s} {s:>6d} {leak:<10s}')
    
    # Try accessing specific daily task items of user B
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    with app.app_context():
        ds_b = DailyTaskSet.query.filter_by(user_id=uid_b).first()
        if ds_b:
            items = DailyTaskItem.query.filter_by(daily_set_id=ds_b.id).limit(2).all()
            for it in items:
                r = c.get(f'/daily_tasks/{it.id}/submit', follow_redirects=False)
                print(f'Daily task {it.id} submit: {r.status_code} {"LEAK" if r.status_code==200 else "OK"}')
                r = c.get(f'/daily_tasks/{it.id}/hint', follow_redirects=False)
                print(f'Daily task {it.id} hint:   {r.status_code} {"LEAK" if r.status_code==200 else "OK"}')
        else:
            print(f'User {uid_b} has no daily tasks')
    
    # Check debt API
    try:
        from services.daily_debt import get_debt_items, get_debt_count
        with app.app_context():
            debt = get_debt_items(uid_b)
            print(f'DEBT access for user {uid_b}: {len(debt)} items (direct call, not via HTTP)')
    except Exception as e:
        print(f'DEBT error: {e}')

print('\n=== TASK 4 DONE ===')
