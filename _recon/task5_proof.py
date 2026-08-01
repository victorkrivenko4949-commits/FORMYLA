"""Task 5 proof: pytest + test_client route smoke test."""
import subprocess
import sys
import os

BASE = r"c:\Users\Redmi\Desktop\Новая папка (2)"

# 1. pytest -q
print("=" * 60)
print("PYTEST -q")
print("=" * 60)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "-q"],
    capture_output=True, text=True, cwd=BASE, timeout=300,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
)
print(result.stdout)
if result.stderr:
    print(result.stderr[-500:])
print(f"Exit code: {result.returncode}")

# 2. test_client route check
print("\n" + "=" * 60)
print("TEST_CLIENT ROUTE SMOKE")
print("=" * 60)

os.chdir(BASE)
sys.path.insert(0, BASE)

from app import app, db
from models import User

with app.test_client() as c:
    # Create/lookup user 1
    with app.app_context():
        u = db.session.get(User, 1)
        if u is None:
            u = User(id=1, email='test@test.test', name='Test', preferred_grade=9, is_guest=False)
            db.session.add(u)
            db.session.commit()
    
    with c.session_transaction() as s:
        s['_user_id'] = '1'
        s['_fresh'] = True
    
    routes = [
        ('GET', '/', 'home'),
        ('GET', '/login', 'login'),
        ('GET', '/olympiads', 'olympiads'),
        ('GET', '/prep/coach', 'coach'),
        ('GET', '/daily-set', 'daily-set'),
    ]
    
    for method, url, label in routes:
        r = c.get(url) if method == 'GET' else c.post(url)
        # Follow redirects for daily-set
        if r.status_code in (301, 302):
            r2 = c.get(r.headers['Location'])
            cards = r2.data.decode('utf-8', errors='replace').count('task-card')
            print(f"  {label}: {r.status_code} -> {url} -> {r2.status_code} {r.headers['Location']}, cards={cards}")
        else:
            cards = r.data.decode('utf-8', errors='replace').count('task-card')
            print(f"  {label}: {r.status_code} {url}, cards={cards}")

print("\nDONE")
