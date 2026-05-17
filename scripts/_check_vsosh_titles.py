"""Check actual probnik titles in DB for the vsosh-9-2027 course."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app
from models_olympiad import Probnik

with app.app_context():
    rows = (
        Probnik.query
        .filter(Probnik.code.like('vsosh-9-2027-%'))
        .order_by(Probnik.code)
        .all()
    )
    print(f'Found {len(rows)} probniks in DB')
    print('-' * 100)
    for r in rows:
        print(f'{r.code:30s}  type={r.type:8s}  number={r.number!s:4s}  title={r.title!r}')
