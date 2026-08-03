"""P3 acceptance checks - PART 2: Toggle ON counting."""
from dotenv import load_dotenv
load_dotenv()

import services.kimi_review as kr

# ---- CALLS ON (toggle enabled, should be exactly 1 call) ----
calls = {'n': 0}
original = kr.call_kimi_api

def counting_wrapper(*a, **k):
    calls['n'] += 1
    return original(*a, **k)

kr.call_kimi_api = counting_wrapper
kr._kimi_enabled_for = lambda surface: True

try:
    r = kr.review_text(
        task_text='[TEST] test task',
        correct_answer='test answer',
        solution_text='test solution',
        surface='probe',
    )
    print('CALLS_ON', calls['n'])
    print('REVIEW_ERROR', r.get('error', 'no error')[:200])
except Exception as e:
    print('CALLS_ON', calls['n'])
    print('EXCEPTION', str(e)[:300])

print("CALLS_ON_CHECK_DONE")
