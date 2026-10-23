# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
r = c.execute(
    "SELECT id,status,generation_mode,aux_status,aux_dropped_reason,aux_fail_reason,"
    "aux_reason,aux_source,solver_answer,measured_answer,answer_verdict,"
    "solution_json,aux_plan_json,problem_text,solution_text,created_at "
    "FROM figure_build_jobs ORDER BY id DESC LIMIT 1"
).fetchone()
print('ID:', r['id'], '| status:', r['status'], '| mode:', r['generation_mode'])
print('aux_status:', r['aux_status'])
print('aux_dropped_reason:', r['aux_dropped_reason'])
print('aux_fail_reason:', r['aux_fail_reason'])
print('aux_source:', r['aux_source'])
print('aux_reason:', r['aux_reason'])
print('answer_verdict:', r['answer_verdict'])
print('solver_answer:', r['solver_answer'])
print('measured_answer:', r['measured_answer'])
print('created_at:', r['created_at'])
print()
print('=== PROBLEM ===')
print(r['problem_text'])
print()
print('=== SOLUTION_TEXT ===')
print((r['solution_text'] or '')[:3000])
print()
print('=== SOLUTION_JSON ===')
sj = r['solution_json']
if sj:
    try:
        d = json.loads(sj)
    except Exception as e:
        print('parse err', e, sj[:1500])
    else:
        for k in ('aux_needed', 'aux_constructions', 'steps', 'final_answer', 'answer'):
            if k in d:
                print(f'--- {k} ---')
                print(json.dumps(d[k], ensure_ascii=False)[:2500])
else:
    print('None')
print()
print('=== AUX_PLAN_JSON ===')
print((r['aux_plan_json'] or '')[:2000])
