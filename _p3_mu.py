"""P3: mu/sigma comparison script."""
from dotenv import load_dotenv
load_dotenv()

import sqlite3

conn = sqlite3.connect('instance/formyla.db')

# BEFORE snapshot
conn.execute("UPDATE users SET kimi_review_probe=0 WHERE id=1")
conn.commit()
before = [r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')]
with open('_recon/p3_before.txt', 'w') as f:
    f.write(str(before))
print('BEFORE', before)

# Run review_text with OFF toggle (no patch = uses real _kimi_enabled_for which returns False outside Flask)
import services.kimi_review as kr

try:
    result_off = kr.review_text(
        task_text='[TEST] task',
        correct_answer='ans',
        solution_text='sol',
        surface='probe',
    )
    print('OFF_RESULT', result_off.get('error', 'no error')[:100])
except Exception as e:
    print('OFF_EXCEPTION', str(e)[:200])

after_off = [r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')]
with open('_recon/p3_after_off.txt', 'w') as f:
    f.write(str(after_off))
print('AFTER_OFF', after_off)

# Run review_text with ON toggle (patch to True)
orig_enabled = kr._kimi_enabled_for
kr._kimi_enabled_for = lambda surface: True

orig_call = kr.call_kimi_api
calls = {'n': 0}
def cw(*a, **k):
    calls['n'] += 1
    return orig_call(*a, **k)
kr.call_kimi_api = cw

try:
    result_on = kr.review_text(
        task_text='[TEST] task',
        correct_answer='ans',
        solution_text='sol',
        surface='probe',
    )
    print('ON_CALLS', calls['n'])
    print('ON_RESULT', result_on.get('error', 'no error')[:100])
except Exception as e:
    print('ON_EXCEPTION', str(e)[:200])

after_on = [r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')]
with open('_recon/p3_after_on.txt', 'w') as f:
    f.write(str(after_on))
print('AFTER_ON', after_on)

conn.close()
print('ALL_SNAPSHOTS_SAVED')
