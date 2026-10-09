# -*- coding: utf-8 -*-
import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

for jid in (2138,):
    base = json.loads(c.execute(f'SELECT base_plan_json FROM figure_build_jobs WHERE id={jid}').fetchone()[0])
    sol = json.loads(c.execute(f'SELECT solution_json FROM figure_build_jobs WHERE id={jid}').fetchone()[0])
    from services.aux_compiler import compile_solver_aux
    from services.figure_plan_validator import merge_base_aux
    compiled, issues = compile_solver_aux(sol, base)
    merged = merge_base_aux(base, compiled)
    from geometric_engine.engine import GeometricEngine
    eng = GeometricEngine()
    eng.settings.semantic_colors = True
    eng.settings.auto_fit = True
    svg, ctx = eng.build(merged)
    # collect bbox of points
    xs, ys = [], []
    for name, pt in ctx.points.items():
        m = ctx.meta.get(name, {})
        if m.get('hidden'):
            continue
        xs.append(pt[0]); ys.append(pt[1])
    print(f'job {jid}: points bbox x[{min(xs):.1f},{max(xs):.1f}] y[{min(ys):.1f},{max(ys):.1f}] n={len(xs)}')
    # circle radii
    for cid, cd in ctx.circles.items():
        print('  circle', cid, 'center', cd[0], 'r', round(cd[1],1))
    # print all points
    for name, pt in ctx.points.items():
        m = ctx.meta.get(name, {})
        if not m.get('hidden'):
            print('  pt', name, (round(pt[0],1), round(pt[1],1)), m.get('type'))
