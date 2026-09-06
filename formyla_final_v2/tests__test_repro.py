# -*- coding: utf-8 -*-
"""Тест-харнес: воспроизведение 6 ошибок конвейера solver_aux на текущем коде."""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import aux_compiler
from geometric_engine import geom

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"{'OK ' if cond else 'FAIL'} {name}" + (f"  -- {detail}" if detail else ""))

# Базовый план: треугольник ABC (3-4-5 прямоугольный), вершины-точки.
BASE_PLAN = {"constructions": [
    {"type": "free_point", "id": "A", "x": 0.0, "y": 0.0},
    {"type": "free_point", "id": "B", "x": 4.0, "y": 0.0},
    {"type": "free_point", "id": "C", "x": 0.0, "y": 3.0},
    {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
    {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
]}

def steps_with(text):
    return [{"no": 1, "text": text}]

# ── ОШИБКА 1: incircle_touch порядок аргументов ──────────────────
# geom.incircle_touch_point(opp, end1, end2) должен дать точку на стороне end1-end2.
A, B, C = (0.0, 0.0), (4.0, 0.0), (0.0, 3.0)
t = geom.incircle_touch_point(A, B, C)  # сторона BC, напротив A
on_bc = abs(geom.point_to_segment_distance(t, (B, C))) < 1e-6
r = geom.dist(geom.incenter(A, B, C), t)
check("E1: touch на стороне BC", on_bc, f"dist_to_BC={geom.point_to_segment_distance(t,(B,C)):.2e} r={r:.4f}")

# ── ОШИБКА 2: base-точка касания как point_on_segment с ratio ─────
# base объявил A1 как point_on_segment с произвольным ratio=0.3 (неправильно).
base_with_bad_touch = {"constructions": BASE_PLAN["constructions"] + [
    {"type": "point_on_segment", "id": "A1", "p1": "B", "p2": "C", "ratio": 0.3},
]}
solver_incircle = {
    "steps": steps_with("Проведём биссектрисы углов A и B, их пересечение O — центр вписанной окружности. Опустим перпендикуляры из O на стороны, основания — точки касания. Построим окружность с центром O."),
    "aux_constructions": [
        {"op": "angle_bisector", "points": ["A", "B", "C"], "quote": "Проведём биссектрисы углов A и B", "step_no": 1},
        {"op": "angle_bisector", "points": ["B", "A", "C"], "quote": "Проведём биссектрисы углов A и B", "step_no": 1},
        {"op": "circle_center_radius", "center": "O", "through": "A1", "quote": "Построим окружность с центром O", "step_no": 1},
    ],
}
plan2, iss2 = aux_compiler.compile_solver_aux(solver_incircle, base_with_bad_touch)
cs2 = plan2.get("constructions", [])
# Найдём, какой radius_point использует окружность.
circ = next((c for c in cs2 if c.get("type") == "circle_center_radius"), None)
touch_types = {c.get("type") for c in cs2}
# ОЖИДАНИЕ: компилятор НЕ должен переиспользовать base-точку A1 (point_on_segment) как radius_point.
bad_reuse = circ is not None and circ.get("radius_point") == "A1"
check("E2: не переиспользовать bad base-touch A1", not bad_reuse,
      f"radius_point={circ.get('radius_point') if circ else None} types={touch_types}")

# ── ОШИБКА 3: потеря новой точки (нет id, имя только в quote) ────
# point_on_line без id, имя D только в quote.
solver_pol = {
    "steps": steps_with("Отметим точку D на прямой AB."),
    "aux_constructions": [
        {"op": "point_on_line", "line": ["A", "B"], "quote": "Отметим точку D на прямой AB", "step_no": 1},
        {"op": "segment", "points": ["D", "C"], "quote": "Отметим точку D на прямой AB", "step_no": 1},
    ],
}
plan3, iss3 = aux_compiler.compile_solver_aux(solver_pol, BASE_PLAN)
has_unresolved = any("UNRESOLVED_POINT:D" in i for i in iss3)
d_real = any(c.get("id") == "D" for c in plan3.get("constructions", []))
check("E3a: point_on_line извлекает id D из quote", d_real and not has_unresolved,
      f"issues={iss3} ids={[c.get('id') for c in plan3.get('constructions',[])]}")

# altitude без foot_id, основание K только в quote.
solver_alt = {
    "steps": steps_with("Опустим высоту из вершины A на сторону BC, основание обозначим K."),
    "aux_constructions": [
        {"op": "altitude", "vertex": "A", "to_line": ["B", "C"], "quote": "основание обозначим K", "step_no": 1},
        {"op": "segment", "points": ["K", "A"], "quote": "основание обозначим K", "step_no": 1},
    ],
}
plan3b, iss3b = aux_compiler.compile_solver_aux(solver_alt, BASE_PLAN)
has_unresolved_k = any("UNRESOLVED_POINT:K" in i for i in iss3b)
k_real = any(c.get("foot_id") == "K" for c in plan3b.get("constructions", []))
check("E3b: altitude извлекает foot_id K из quote", k_real and not has_unresolved_k,
      f"issues={iss3b} ids/foot={[ (c.get('id'),c.get('foot_id')) for c in plan3b.get('constructions',[])]}")

# ── ОШИБКА 4: line_intersection с будущей точкой [M,E,A,B] ────────
# Сначала parallel_through через M, потом пересечение [M,E,A,B].
solver_par = {
    "steps": steps_with("Проведём через точку M прямую, параллельную CH, до пересечения с AB в точке E."),
    "aux_constructions": [
        {"op": "parallel_through", "point": "M", "to_line": ["C", "H"], "quote": "Проведём через точку M прямую", "step_no": 1},
        {"op": "line_intersection", "points": ["M", "E", "A", "B"], "quote": "до пересечения с AB в точке E", "step_no": 1},
    ],
}
# M и H должны существовать в base. Добавим.
base_mh = {"constructions": BASE_PLAN["constructions"] + [
    {"type": "free_point", "id": "M", "x": 1.0, "y": 1.0},
    {"type": "free_point", "id": "H", "x": 0.5, "y": 1.5},
]}
plan4, iss4 = aux_compiler.compile_solver_aux(solver_par, base_mh)
e_real = any(c.get("id") == "E" for c in plan4.get("constructions", []))
check("E4: line_intersection резолвит E из [M,E,A,B]", e_real and not any("UNRESOLVED" in i for i in iss4),
      f"issues={iss4} ids={[c.get('id') for c in plan4.get('constructions',[])]}")

# ── ОШИБКА 5: line_extension с равенством AD = AM ────────────────
base_am = {"constructions": BASE_PLAN["constructions"] + [
    {"type": "free_point", "id": "M", "x": 1.0, "y": 0.0},  # |AM| = 1
]}
solver_ext = {
    "steps": steps_with("Продлим BA за точку A до точки D так, что AD = AM."),
    "aux_constructions": [
        {"op": "line_extension", "segment": ["B", "A"], "beyond": "A", "quote": "Продлим BA за точку A до точки D так, что AD = AM", "step_no": 1},
    ],
}
plan5, iss5 = aux_compiler.compile_solver_aux(solver_ext, base_am)
por = next((c for c in plan5.get("constructions", []) if c.get("type") == "point_on_ray"), None)
check("E5a: line_extension AD=AM -> point_on_ray", por is not None, f"issues={iss5}")
# Геометрическая проверка через движок: D на луче из B через A за A, |AD|=|AM|=1 -> D=(-1,0)
if por:
    check("E5b: id=D извлечён из левой части", por.get("id") == "D", f"id={por.get('id')}")
    check("E5b: length_from=пара [A,M]", por.get("length_from") == ["A", "M"], f"length_from={por.get('length_from')}")
    # Исполняем в движке.
    from geometric_engine import engine as E
    ctx = E.BuildContext()
    for c in base_am["constructions"]:
        E.execute_construction(ctx, c)
    for c in plan5["constructions"]:
        E.execute_construction(ctx, c)
    D = ctx.points.get("D")
    check("E5c: движок D=(-1,0) (|AD|=1 за A)", D is not None and abs(D[0]+1.0)<1e-9 and abs(D[1])<1e-9, f"D={D}")

# ── ОШИБКА 6: служебные подписи aux_* (на уровне рендера SVG) ──────
# Точка с синтетическим id aux_* НЕ должна появляться в SVG как <text>.
from geometric_engine import engine as E
base_cd = {"constructions": BASE_PLAN["constructions"] + [
    {"type": "free_point", "id": "D", "x": 2.0, "y": 2.0},
]}
solver_no_id = {
    "steps": steps_with("Найдём точку пересечения прямых AB и CD, обозначим её P."),
    "aux_constructions": [
        {"op": "line_intersection", "line1": ["A", "B"], "line2": ["C", "D"], "quote": "обозначим её P", "step_no": 1},
    ],
}
plan6, iss6 = aux_compiler.compile_solver_aux(solver_no_id, base_cd)
ctx6 = E.BuildContext()
for c in base_cd["constructions"]:
    E.execute_construction(ctx6, c)
for c in plan6.get("constructions", []):
    E.execute_construction(ctx6, c)
svg6 = E.render_svg(ctx6, 400, 400, E.DEFAULT_SETTINGS)
aux_in_svg = "aux_" in svg6
check("E6: в SVG нет служебных aux_* подписей", not aux_in_svg, f"issues={iss6} aux_in_svg={aux_in_svg}")

print(f"\n=== {len(passed)} passed, {len(failed)} failed ===")
if failed:
    print("FAILED:", failed)

# ── РЕГРЕССИЯ: правки не должны ломать существующие случаи ────────
from geometric_engine import engine as E

def run_plan(base_cs, aux_cs, steps_text):
    bp = {"constructions": base_cs}
    sr = {"steps": steps_with(steps_text), "aux_constructions": aux_cs}
    plan, iss = aux_compiler.compile_solver_aux(sr, bp)
    ctx = E.BuildContext()
    for c in base_cs:
        E.execute_construction(ctx, c)
    for c in plan.get("constructions", []):
        E.execute_construction(ctx, c)
    return ctx, plan, iss

# R1: центральная симметрия «продлим AB за B до D так, что B середина AD».
ctx, plan, iss = run_plan(BASE_PLAN["constructions"], [
    {"op": "line_extension", "segment": ["A", "B"], "beyond": "B", "id": "D",
     "quote": "Продлим AB за B до точки D", "step_no": 1},
], "Продлим AB за B до точки D.")
check("R1: central-sym D = 2*B - A", abs(ctx.points["D"][0]-8.0)<1e-9 and abs(ctx.points["D"][1])<1e-9,
      f"D={ctx.points.get('D')} issues={iss}")

# R2: legacy point_on_ray с одноточечным length_from (внутренний контракт движка).
ctx = E.BuildContext()
for c in BASE_PLAN["constructions"] + [{"type":"free_point","id":"M","x":1.0,"y":0.0}]:
    E.execute_construction(ctx, c)
E.execute_construction(ctx, {"type": "point_on_ray", "id": "D", "origin": "A", "away_from": "B", "length_from": "M"})
check("R2: legacy length_from=M -> |AD|=|AM|=1", abs(ctx.points["D"][0]+1.0)<1e-9, f"D={ctx.points.get('D')}")

# R3: midpoint с явным id.
ctx, plan, iss = run_plan(BASE_PLAN["constructions"], [
    {"op": "midpoint", "segment": ["A", "B"], "id": "M", "quote": "отметим середину M", "step_no": 1},
], "отметим середину M отрезка AB.")
check("R3: midpoint M=(2,0)", abs(ctx.points["M"][0]-2.0)<1e-9, f"M={ctx.points.get('M')} issues={iss}")

# R4: altitude с явным foot_id.
ctx, plan, iss = run_plan(BASE_PLAN["constructions"], [
    {"op": "altitude", "vertex": "A", "to_line": ["B", "C"], "foot_id": "H",
     "quote": "опустим высоту AH", "step_no": 1},
], "Опустим высоту AH на сторону BC.")
H = ctx.points.get("H")
check("R4: altitude foot H на BC", H is not None and abs(geom.point_to_segment_distance(H, ((4.0,0.0),(0.0,3.0))))<1e-9, f"H={H} issues={iss}")

# R5: полная вписанная окружность — касательна ко всем трём сторонам.
ctx, plan, iss = run_plan(BASE_PLAN["constructions"], [
    {"op": "angle_bisector", "points": ["A", "B", "C"], "quote": "Проведём биссектрисы", "step_no": 1},
    {"op": "angle_bisector", "points": ["B", "A", "C"], "quote": "Проведём биссектрисы", "step_no": 1},
    {"op": "circle_center_radius", "center": "O", "through": "A1", "quote": "Построим окружность с центром O", "step_no": 1},
], "Проведём биссектрисы углов A и B, их пересечение O. Опустим перпендикуляры из O на стороны, основания — точки касания. Построим окружность с центром O.")
circ = next((c for c in plan.get("constructions", []) if c.get("type")=="circle_center_radius"), None)
inc = ctx.points.get(circ["center"]) if circ else None
touch = ctx.points.get(circ["radius_point"]) if circ else None
r = geom.dist(inc, touch) if inc and touch else None
tangent_all = r is not None and all(abs(geom.point_to_segment_distance(inc, s) - r) < 1e-6 for s in [((0,0),(4,0)),((4,0),(0,3)),((0,3),(0,0))])
check("R5: incircle касательна ко всем 3 сторонам", tangent_all, f"r={r} inc={inc} issues={iss}")

# R6: если base УЖЕ содержит A1 как нативный incircle_touch — переиспользуем его
# (не создаём дубль aux_touch_A).  Регрессия к E2.
base_good_touch = {"constructions": BASE_PLAN["constructions"] + [
    {"type": "incircle_touch", "id": "A1", "p1": "A", "p2": "B", "p3": "C"},
]}
ctx, plan, iss = run_plan(base_good_touch["constructions"], [
    {"op": "angle_bisector", "points": ["A", "B", "C"], "quote": "Проведём биссектрисы", "step_no": 1},
    {"op": "angle_bisector", "points": ["B", "A", "C"], "quote": "Проведём биссектрисы", "step_no": 1},
    {"op": "circle_center_radius", "center": "O", "through": "A1", "quote": "Построим окружность с центром O", "step_no": 1},
], "Проведём биссектрисы углов A и B, пересечение O. Построим окружность с центром O.")
circ = next((c for c in plan.get("constructions", []) if c.get("type")=="circle_center_radius"), None)
aux_touch_created = any(c.get("type")=="incircle_touch" and c.get("id")=="aux_touch_A" for c in plan.get("constructions",[]))
check("R6: переиспользован base incircle_touch A1", circ is not None and circ.get("radius_point")=="A1" and not aux_touch_created,
      f"radius_point={circ.get('radius_point') if circ else None} aux_touch_created={aux_touch_created}")

print(f"\n=== REGRESSION: {len(passed)-10} extra passed, {len(failed)} failed ===")
if failed:
    print("FAILED:", failed)
