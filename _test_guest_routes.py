# -*- coding: utf-8 -*-
"""Test all routes for guest access - record actual HTTP codes."""
import sys, os, io, json
sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'test'

# Suppress startup noise
old_stdout = sys.stdout
sys.stdout = io.StringIO()

from app import app
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'localhost'

sys.stdout = old_stdout

ROUTES = [
    '/', '/health', '/healthz', '/about', '/login', '/logout', '/dev_login', '/welcome',
    '/verify-code', '/yandex_login', '/yandex_receiver', '/topics', '/leaderboard',
    '/problems', '/problem/1', '/probniks', '/secrets', '/secrets/1',
    '/olympiads', '/olympiads/open', '/olympiads/solution/1',
    '/olympiad-test', '/olympiad-test/select-section', '/olympiad-test/select-theme',
    '/olympiad-test/select-level', '/olympiad-test/start',
    '/section/algebra', '/section/algebra/quadratic',
    '/adaptive_test/select_class', '/adaptive_test/select_grade',
    '/adaptive_test/select_topic', '/adaptive_test/start', '/adaptive_test/start_grade',
    '/adaptive_test_simple', '/adaptive_test_simple/finish',
    '/adaptive_test_simple/results',
    '/free_mock/start', '/free_mock/generate',
    '/sql', '/matstat',
    '/admin/tutor_stats', '/admin/needs_review', '/admin/fix_latex_rac',
    '/admin/seed-secrets', '/admin/fix-theory-blocks',
    '/api/migrate/tables', '/api/migrate/export',
    '/api/test/start', '/api/test/active',
    '/api/profile', '/api/set_nickname', '/api/save_test_result',
    '/api/secrets', '/api/report_task/1', '/api/reviews',
    '/api/support', '/api/feedback',
    '/api/check_answer', '/api/check_adaptive_answer',
    '/call', '/conference', '/profile', '/settings',
    '/daily-set', '/daily_tasks/',
    '/debug/routes', '/debug-sentry',
    '/__version', '/__diag/method/some_method',
    '/auth/yandex/login',
]

results = []
with app.test_client() as c:
    for url in ROUTES:
        try:
            r = c.get(url, follow_redirects=False)
            status = r.status_code
            redirect = r.headers.get('Location', '') if status in (301, 302, 303, 307, 308) else ''
            results.append((url, status, redirect))
        except Exception as e:
            results.append((url, f'ERROR: {e.__class__.__name__}', ''))

# Also try POST for POST-only routes
POST_ROUTES = [
    '/api/migrate/push', '/api/test/start',
    '/api/save_test_result', '/api/set_nickname', '/api/support',
    '/api/feedback', '/api/report_task/1',
    '/api/check_answer', '/api/check_adaptive_answer',
    '/olympiads/open',
]
for url in POST_ROUTES:
    try:
        r = c.post(url, follow_redirects=False, data='{}', content_type='application/json')
        status = r.status_code
        redirect = r.headers.get('Location', '') if status in (301, 302, 303, 307, 308) else ''
        results.append((f'POST {url}', status, redirect))
    except Exception as e:
        results.append((f'POST {url}', f'ERROR: {e.__class__.__name__}', ''))

print("url|status|redirect")
for url, status, redirect in results:
    print(f"{url}|{status}|{redirect}")
