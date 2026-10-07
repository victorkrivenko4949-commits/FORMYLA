# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
r = c.execute(
    "SELECT id,status,aux_status,aux_dropped_reason,aux_fail_reason,"
    "solution_json,problem_text FROM figure_build_jobs WHERE id=5429"
).fetchone()

print('ID:', r['id'], '| status:', r['status'], '| aux_status:', r['aux_status'])
print('aux_dropped_reason:', r['aux_dropped_reason'])
print('aux_fail_reason:', r['aux_fail_reason'])
print()
print('=== УСЛОВИЕ ЗАДАЧИ ===')
print(r['problem_text'])
print()

sj = json.loads(r['solution_json'])
print('=== GPT: aux_needed ===')
print(sj.get('aux_needed'))
print()
print('=== GPT: aux_constructions (что GPT просил построить) ===')
for i, a in enumerate(sj.get('aux_constructions', [])):
    print(f"[{i}] op={a.get('op')}")
    print(f"    points={a.get('points')} vertex={a.get('vertex')} rays={a.get('rays')}")
    print(f"    center={a.get('center')} through={a.get('through')} id={a.get('id')} foot_id={a.get('foot_id')}")
    print(f"    line1={a.get('line1')} line2={a.get('line2')}")
    print(f"    quote: {a.get('quote')}")
    print(f"    purpose: {a.get('purpose')}")
    print()
print('=== GPT: steps (текст решения) ===')
for s in sj.get('steps', []):
    print(f"  {s.get('no')}. {s.get('text')}")
