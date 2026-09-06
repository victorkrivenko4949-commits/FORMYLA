# -*- coding: utf-8 -*-
import sqlite3, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id,status,aux_status,aux_svg_path,aux_plan_json,aux_fail_reason,"
    "aux_usefulness,aux_completeness,aux_dropped_reason,aux_reason "
    "FROM figure_build_jobs WHERE id IN (5427,5426,5425,5424) ORDER BY id DESC"
).fetchall()
for x in rows:
    print('=' * 70)
    print('ID', x['id'], 'status', x['status'], 'aux_status', x['aux_status'])
    print('fail:', x['aux_fail_reason'])
    print('dropped:', x['aux_dropped_reason'])
    for key in ('aux_usefulness', 'aux_completeness', 'aux_reason', 'aux_plan_json'):
        v = x[key]
        if not isinstance(v, str):
            v = str(v)
        print(f'{key}:', v[:1200])
