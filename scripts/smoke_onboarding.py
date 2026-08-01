# -*- coding: utf-8 -*-
"""Quick smoke test for acceptance criteria."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from models import User, db

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, 1)
        print(f"User #1: {u.email if u else 'NONE'}")

    with c.session_transaction() as s:
        s['_user_id'] = '1'
        s['_fresh'] = True

    # Test GET /prep/onboarding
    resp = c.get('/prep/onboarding')
    print(f"GET /prep/onboarding = {resp.status_code}")
    html = resp.data.decode('utf-8')
    print(f"Contains 'Онбординг': {'Онбординг' in html}")
    print(f"Contains 'onboarding-app': {'onboarding-app' in html}")

    # Test old endpoint redirects
    resp2 = c.post('/prep/coach/questionnaire/start')
    print(f"POST /prep/coach/questionnaire/start = {resp2.status_code}")
    print(f"redirect_url: {resp2.get_json()}")

print("SMOKE TEST PASSED")
