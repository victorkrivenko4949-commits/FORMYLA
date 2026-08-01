# -*- coding: utf-8 -*-
"""TASK 5: Live test via app.test_client()."""
import sys, os, re, sqlite3
BASE = r'c:\Users\Redmi\Desktop\Новая папка (2)'
os.chdir(BASE)
sys.path.insert(0, BASE)
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

from app import app, db

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'localhost'

results = []

with app.app_context():
    client = app.test_client()
    INST = os.path.join(BASE, 'instance', 'formyla.db')
    
    # ── DB stats ──
    conn = sqlite3.connect(INST)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    results.append(f"Users: {cur.fetchone()[0]}")
    
    cur.execute("SELECT id, email FROM users")
    for r in cur.fetchall():
        results.append(f"  id={r[0]} email={r[1]}")
    
    cur.execute("SELECT COUNT(*) FROM task_solutions")
    results.append(f"Task solutions: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM task_assignment_history")
    results.append(f"Task assignment history: {cur.fetchone()[0]}")
    cur.execute("SELECT * FROM task_assignment_history ORDER BY id DESC LIMIT 5")
    results.append("Last 5 history entries:")
    for r in cur.fetchall():
        results.append(f"  {r}")
    
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    results.append(f"Adaptive tasks: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM olympiad_tasks")
    results.append(f"Olympiad tasks: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM olympiad_probniks")
    results.append(f"Olympiad probniks: {cur.fetchone()[0]}")
    conn.close()
    
    # ── HTTP: Login page ──
    resp = client.get('/login', follow_redirects=True)
    results.append(f"\nGET /login: STATUS {resp.status_code}")
    
    # ── HTTP: Home ──
    resp = client.get('/', follow_redirects=True)
    status = resp.status_code
    results.append(f"GET / (home): STATUS {status}")
    
    # ── HTTP: Daily tasks ──
    resp = client.get('/daily_tasks', follow_redirects=True)
    status = resp.status_code
    data = resp.get_data(as_text=True)
    cards = len(re.findall(r'task-card|problem-card|task_item|card', data, re.I))
    results.append(f"GET /daily_tasks: STATUS {status}, task cards ~ {cards}")
    
    # ── HTTP: Olympiads ──
    resp = client.get('/olympiads', follow_redirects=True)
    status = resp.status_code
    results.append(f"GET /olympiads: STATUS {status}")
    
    # ── HTTP: VSOSH specific ──
    resp = client.get('/olympiads/vsosh-9-2027', follow_redirects=True)
    status = resp.status_code
    results.append(f"GET /olympiads/vsosh-9-2027: STATUS {status}")

print('\n'.join(results))
