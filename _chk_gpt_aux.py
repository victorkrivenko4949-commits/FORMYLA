# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id,status,generation_mode,aux_status,aux_fail_reason,aux_dropped_reason,"
    "aux_reason,aux_usefulness,aux_completeness,solution_json,aux_plan_json,solver_answer,"
    "aux_source,created_at "
    "FROM figure_build_jobs WHERE id IN (SELECT id FROM figure_build_jobs ORDER BY id DESC LIMIT 6) "
    "ORDER BY id DESC"
).fetchall()
for x in rows:
    print('=' * 80)
    print('ID', x['id'], '| status', x['status'], '| mode', x['generation_mode'], '| aux_status', x['aux_status'])
    print('aux_source:', x['aux_source'])
    print('aux_fail_reason:', x['aux_fail_reason'])
    print('aux_dropped_reason:', x['aux_dropped_reason'])
    print('aux_reason:', x['aux_reason'])
    print('aux_usefulness:', x['aux_usefulness'])
    print('aux_completeness:', x['aux_completeness'])
    print('solver_answer:', (x['solver_answer'] or '')[:500])
    sj = x['solution_json']
    print('--- solution_json (aux_constructions/steps) ---')
    if sj:
        try:
            d = json.loads(sj)
        except Exception as e:
            print('  JSON parse err:', e)
            print('  raw:', sj[:1500])
        else:
            for key in ('aux_needed', 'aux_constructions', 'aux_reason', 'solution_type'):
                if key in d:
                    print(f'  {key}:', json.dumps(d[key], ensure_ascii=False)[:2000])
            steps = d.get('steps')
            if isinstance(steps, list):
                print('  steps:', json.dumps(steps, ensure_ascii=False)[:2500])
    else:
        print('  solution_json is None')
    print('--- aux_plan_json ---')
    print((x['aux_plan_json'] or '')[:1500])
