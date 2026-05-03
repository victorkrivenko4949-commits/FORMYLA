import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from olympiads import OLYMPIADS_DB
from services.olympiad_3stage import stage1_find_task

results = []
try:
    t = stage1_find_task('vsosh', 'school', 5, OLYMPIADS_DB)
    results.append(f"PASS vsosh/school/5: year={t['year']} num={t['problem_num']}")
    results.append(f"  text={t['task_text'][:100]}")
except Exception as e:
    results.append(f"FAIL vsosh/school/5: {e}")

try:
    t2 = stage1_find_task('euler', '', 7, OLYMPIADS_DB)
    results.append(f"PASS euler/any/7: year={t2['year']} num={t2['problem_num']}")
    results.append(f"  text={t2['task_text'][:100]}")
except Exception as e:
    results.append(f{