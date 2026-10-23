# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
c = sqlite3.connect(r'instance/formyla.db')
out = io.StringIO()

r = c.execute("SELECT base_plan_json FROM figure_build_jobs WHERE base_plan_json IS NOT NULL AND user_id=1301 LIMIT 1").fetchone()
if r:
    p = json.loads(r[0])
    out.write(f"BASE_PLAN keys: {list(p.keys())}\n")
    out.write(f"BASE_PLAN sample: {json.dumps(p, ensure_ascii=False)[:400]}\n")

r2 = c.execute("SELECT figure_json FROM adaptive_tasks WHERE figure_json IS NOT NULL LIMIT 1").fetchone()
out.write("\n")
if r2:
    try:
        p2 = json.loads(r2[0])
        out.write(f"ADAPTIVE figure_json keys: {list(p2.keys())}\n")
        out.write(f"ADAPTIVE figure_json sample: {json.dumps(p2, ensure_ascii=False)[:400]}\n")
    except Exception as e:
        out.write(f"adaptive figure_json parse err: {e}, raw[:200]={str(r2[0])[:200]}\n")
else:
    out.write("NO adaptive_tasks with figure_json\n")

# daily_task_items с figure_json
r3 = c.execute("SELECT count(*) FROM daily_task_items WHERE figure_json IS NOT NULL").fetchone()
out.write(f"\ndaily_task_items with figure_json: {r3[0]}\n")

open('_inspect_fig_json.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
