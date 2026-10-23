# -*- coding: utf-8 -*-
import io, sys, json, sqlite3, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
base = json.loads(c.execute('SELECT base_plan_json FROM figure_build_jobs WHERE id=2134').fetchone()[0])
sol = json.loads(c.execute('SELECT solution_json FROM figure_build_jobs WHERE id=2134').fetchone()[0])

from services.aux_compiler import compile_solver_aux
from services.figure_plan_validator import merge_base_aux
compiled, issues = compile_solver_aux(sol, base)
print('issues:', issues)
merged = merge_base_aux(base, compiled)

print('MERGED:')
for x in merged.get('constructions', []):
    print('  ', x.get('type'), x.get('id'), x.get('x'), x.get('y'),
          x.get('p1'), x.get('p2'), x.get('vertex'), x.get('side_a'), x.get('side_b'))

from geometric_engine.engine import GeometricEngine
eng = GeometricEngine()
eng.settings.semantic_colors = True
eng.settings.auto_fit = True
try:
    r = eng.build(merged)
    print('OK', len(r[0]))
except Exception as e:
    print('FAIL', type(e).__name__, str(e))
    traceback.print_exc()
