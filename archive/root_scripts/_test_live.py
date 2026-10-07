# -*- coding: utf-8 -*-
"""
Task 4: Live page test v2 - save full HTML and analyze properly.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

def test_live_page():
    app.config['TESTING'] = True
    app.config['SERVER_NAME'] = 'localhost'
    app.config['WTF_CSRF_ENABLED'] = False

    with app.test_client() as client:
        # Step 1: dev_login
        resp = client.get('/dev_login?uid=1', environ_base={'REMOTE_ADDR': '127.0.0.1'})
        print(f"dev_login: {resp.status_code} -> {resp.headers.get('Location')}")

        # Step 2: follow redirect
        resp2 = client.get('/')
        print(f"index: {resp2.status_code}")

        # Step 3: GET /daily_tasks
        resp3 = client.get('/daily_tasks', follow_redirects=True)
        html = resp3.data.decode('utf-8', errors='replace')

        with open('_live_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Saved {len(html)} chars to _live_page.html")

        print(f"STATUS: {resp3.status_code}")
        print(f"HTML length: {len(html)}")

        # Card counting - look for actual task content patterns
        card_patterns = [
            ('dt-task-card', html.count('dt-task-card')),
            ('daily-task-card', html.count('daily-task-card')),
            ('task-card', html.count('task-card')),
            ('dt-item', html.count('dt-item')),
            ('data-item-id', html.count('data-item-id')),
            ('dt-modal-box', html.count('dt-modal-box')),
            ('difficulty_level', html.count('difficulty_level')),
            ('correct_answer', html.count('correct_answer')),
            ('task_text', html.count('task_text')),
        ]
        print("\n=== CARD PATTERNS ===")
        for name, count in card_patterns:
            print(f"  {name}: {count}")

        # Determine source table
        has_daily_task_items = 'daily_task_items' in html or 'daily_set_id' in html
        from_adaptive = 'adaptive_tasks' in html or 'adaptive' in html.lower()
        from_olympiad = 'olympiad_tasks' in html or ('olympiad' in html.lower() and 'olympiad_tasks' not in html)
        print(f"\nSource hints: daily_task_items={has_daily_task_items}, adaptive={from_adaptive}, olympiad={from_olympiad}")

        # Title
        title_match = re.search(r'<title>(.*?)</title>', html)
        print(f"Title: {title_match.group(1) if title_match else 'N/A'}")

        # HTML fragment around main content
        main_idx = html.find('<main')
        if main_idx < 0:
            main_idx = html.find('<body')
        if main_idx > 0:
            fragment = html[main_idx:main_idx + 3000]
            print(f"\n=== HTML BODY FRAGMENT (3000 chars) ===")
            print(fragment)
        else:
            print(f"\n=== HTML (first 2000 chars) ===")
            print(html[:2000])

if __name__ == '__main__':
    test_live_page()
