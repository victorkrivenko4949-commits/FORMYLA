# -*- coding: utf-8 -*-
"""Детерминированная проверка конвейера на фикстуре (без LLM-недетерминизма).
Сверка всех построенных точек с вручную посчитанным ground truth.
"""
import sys, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from services import aux_compiler
from geometric_engine import engine as E, geom

K = 40.0
A = (0.0, 0.0)
B = (13.0 * K, 0.0)
Cx = (15.0**2 + 13.0**2 - 14.0**2) / (2 * 13.0) * K
Cy = (15.0**2 - (99.0/13.0)**2) ** 0.5 * K
C = (Cx, Cy)

GT = {  # unscaled
    "D": (139.0/13.0, 72.0/13.0),
    "E": (52.0/7.0, 0.0),
    "F": (97.0/7.0, 0.0),
    "H": (144.0/13.0, 60.0/13.0),
    "O": (7.0, 4.0),
}
TRUE_R = 4.0
TRUE_PERIM = 18.0

base_plan = {"constructions": [
    {"type": "free_point", "id": "A", "x": A[0], "y": A[1], "label": "A"},
    {"type": "free_point", "id": "B", "x": B[0], "y": B[1], "label": "B"},
    {"type": "free_point", "id": "C", "x": C[0], "y": C[1], "label": "C"},
    {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
    {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
]}

FX = os.path.join(HERE, "fixtures", "solver_fixture.json")
solver_result = json.load(open(FX, encoding="utf-8"))

print("=== compile_solver_aux ===")
aux_plan, issues = aux_compiler.compile_solver_aux(solver_result, base_plan)
print("issues:", issues)
ops_summary = [(c.get("type"), c.get("id")) for c in aux_plan.get("constructions", [])]
for t, i in ops_summary:
    print(f"  {t:22s} {i}")

print("\n=== engine ===")
ctx = E.BuildContext()
for c in base_plan["constructions"]:
    E.execute_construction(ctx, c)
for c in aux_plan.get("constructions", []):
    try:
        E.execute_construction(ctx, c)
    except Exception as e:
        print("  EXEC FAIL:", c.get("id"), c.get("type"), e)

_s = E.EngineSettings()
_s.auto_fit = True
svg = E.render_svg(ctx, 760, 640, _s)
out_svg = os.path.join(HERE, "_artifacts", "figure.svg")
os.makedirs(os.path.dirname(out_svg), exist_ok=True)
open(out_svg, "w", encoding="utf-8").write(svg)
print("SVG:", len(svg), "chars")

print("\n=== сверка с ground truth ===")
checks = []

# окружность
circles = list(ctx.circles.items())
true_I = (GT["O"][0]*K, GT["O"][1]*K)
ok_c = False
if circles:
    for cid, (center, r) in circles:
        dI = geom.dist(center, true_I)/K
        sides = [(A,B),(B,C),(C,A)]
        tang = [abs(geom.point_to_segment_distance(center, s)/K - r/K) for s in sides]
        ok_c = dI < 0.1 and abs(r/K - TRUE_R) < 0.1 and all(t < 0.1 for t in tang)
        print(f"окружность {cid}: центр={tuple(round(x/K,3) for x in center)} r={r/K:.4f} | dI={dI:.4f} касат={[round(t,4) for t in tang]} -> {'OK' if ok_c else 'FAIL'}")
else:
    print("FAIL: окружность не построена")
checks.append(ok_c)

# точки по id (O, D, E, F, H) — ищем в ctx.points
def pt(name):
    p = ctx.get_point(name, name) if False else None
    # ctx.points: id -> (x,y)
    return ctx.points.get(name)

for name, gt in [("O", GT["O"]), ("D", GT["D"]), ("E", GT["E"]), ("F", GT["F"]), ("H", GT["H"])]:
    p = ctx.points.get(name)
    if p is None:
        print(f"FAIL: точка {name} не построена"); checks.append(False); continue
    d = geom.dist(p, (gt[0]*K, gt[1]*K))/K
    ok = d < 0.15
    print(f"точка {name}: построена={tuple(round(x/K,3) for x in p)} ожид={tuple(round(v,3) for v in gt)} | откл={d:.4f} -> {'OK' if ok else 'FAIL'}")
    checks.append(ok)

# геом-проверки
D = ctx.points.get("D"); Ept = ctx.points.get("E")
if D and Ept:
    v1 = (Ept[0]-D[0], Ept[1]-D[1]); v2 = (C[0]-A[0], C[1]-A[1])
    par = abs(v1[0]*v2[1]-v1[1]*v2[0]) < 1.0
    print(f"DE || AC: {par}"); checks.append(par)
H = ctx.points.get("H")
if H:
    dH = geom.point_to_segment_distance(H, (B,C))/K
    print(f"H на BC: расст={dH:.4f} (нужно ~0)"); checks.append(dH < 0.15)
F = ctx.points.get("F")
if F and Ept:
    fx, fy = F[0]/K, F[1]/K; ex, ey = Ept[0]/K, Ept[1]/K
    on_ray = abs(fy) < 0.15 and (fx - ex) > 0
    ef = geom.dist(Ept, F)/K
    ed = geom.dist(Ept, D)/K if D else None
    eq = ed is not None and abs(ef - ed) < 0.15
    print(f"F на луче AE за E: {on_ray} | EF={ef:.4f} ED={ed:.4f} равенство={eq}")
    checks.append(on_ray and eq)

ans = solver_result["answer"]["value"]
ok_ans = abs(ans - TRUE_PERIM) < 0.01
print(f"\nОтвет (периметр EBD): {ans} (нужно {TRUE_PERIM}) -> {'OK' if ok_ans else 'FAIL'}")
checks.append(ok_ans)

passed = sum(1 for c in checks if c)
print(f"\nИТОГ: {passed}/{len(checks)} проверок пройдено")
print("ЧЕРТЕЖ:", "ПРАВИЛЬНЫЙ" if all(checks) else "ЕСТЬ ПРОБЛЕМЫ")
