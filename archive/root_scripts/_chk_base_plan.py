# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
r = c.execute("SELECT base_plan_json FROM figure_build_jobs WHERE id=5429").fetchone()
bp = json.loads(r['base_plan_json'])
print('BASE PLAN top keys:', list(bp.keys()))
for con in bp.get('constructions', []):
    t = con.get('type')
    if t in ('free_point', 'segment', 'line', 'triangle', 'triangle_arbitrary'):
        print(' ', t, con.get('id'), {k: v for k, v in con.items() if k in ('p1','p2','p3','label','vertices')})
