"""P2D2 Integration check: test client + pool stats."""
import os, sys
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'
import logging; logging.basicConfig(level=logging.CRITICAL)
for n in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(n).setLevel(logging.CRITICAL)
import warnings; warnings.filterwarnings('ignore')

from app import app

with app.test_client() as c:
    for path, label in [('/login','login'), ('/','home'), ('/daily_tasks','daily'), ('/olympiads','olympiads')]:
        r = c.get(path)
        print(f'{label}: {r.status_code}')

with app.app_context():
    import sqlite3
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    pool = cur.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()[0]
    max_lvl = cur.execute('SELECT MAX(difficulty_level) FROM adaptive_tasks').fetchone()[0]
    min_lvl = cur.execute('SELECT MIN(difficulty_level) FROM adaptive_tasks').fetchone()[0]
    hist = cur.execute('SELECT COUNT(*) FROM task_assignment_history').fetchone()[0]
    conn.close()
    print(f'pool: {pool}, levels: {min_lvl}-{max_lvl}, history: {hist}')
