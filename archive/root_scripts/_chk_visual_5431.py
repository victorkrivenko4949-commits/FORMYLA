# -*- coding: utf-8 -*-
import sqlite3, io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
c = sqlite3.connect('instance/formyla.db')
c.row_factory = sqlite3.Row
r = c.execute("SELECT id,audit_json,aux_plan_json,base_plan_json,aux_svg_path,svg_path FROM figure_build_jobs WHERE id=5431").fetchone()
print('ID:', r['id'])
print('svg_path:', r['svg_path'])
print('aux_svg_path:', r['aux_svg_path'])
print()
print('=== AUDIT_JSON (visual check result) ===')
aj = r['audit_json']
if aj:
    try:
        d = json.loads(aj)
        print(json.dumps(d, ensure_ascii=False, indent=2)[:3000])
    except Exception as e:
        print('parse err', e, aj[:2000])
else:
    print('None')
print()
print('=== AUX_PLAN_JSON ===')
print((r['aux_plan_json'] or '')[:2000])
