# -*- coding: utf-8 -*-
"""Регрессионные тесты фиксов E8/E9/E10 конвейера ФОРМУЛА.

Запуск:
  cd <проект>
  python -m pytest tests/test_solver_aux_regressions.py -v
  # или без pytest:
  python tests/test_solver_aux_regressions.py
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from services.aux_compiler import compile_solver_aux
from services.base_normalizer import normalize_base_plan
from verify.invariant_checker import check_invariants

FX = os.path.join(HERE, "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


# --- E10: base-стиль нормализован (всё данное = solid) ---

def test_e10_base_style_normalized():
    """normalize_base_plan делает все base-объекты solid (style=base, dashed=False)."""
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    bad = [c for c in base["constructions"] if c.get("style") == "aux" or c.get("dashed")]
    bm = next((c for c in base["constructions"] if c.get("id") == "BM"), None)
    assert len(bad) == 0, f"base-объекты не должны быть style=aux/dashed: {bad}"
    assert bm is not None and bm.get("style") == "base" and not bm.get("dashed"), \
        f"медиана BM должна быть solid, получено: {bm}"


# --- E8: solver пере-диктует данное → пропускается, без краша ---

def test_e8_duplicate_median_skipped():
    """solver продиктовал медиану BM как aux; foot_id M уже в base —
    компилятор пропускает её (FULFILLED_BY_BASE), не падая."""
    solver = _load("solver_parallelogram.json")
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    aux, issues = compile_solver_aux(solver, base)
    assert any("FULFILLED_BY_BASE" in str(i) and "median:M" in str(i) for i in issues), \
        f"должно быть FULFILLED_BY_BASE:median:M, issues={issues}"
    assert aux.get("has_aux") is True, "aux не пустой (есть point K)"
    assert all("уже существует" not in str(i) for i in issues), \
        f"не должно быть 'уже существует': {issues}"


# --- E9: line_extension эмитит видимый отрезок продления ---

def test_e9_line_extension_emits_segment():
    """line_extension → reflect_point эмитит видимый отрезок продления
    (center→id), иначе точка K повисает без линии."""
    solver = _load("solver_parallelogram.json")
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    aux, _ = compile_solver_aux(solver, base)
    ext = [c for c in aux.get("constructions", []) if c.get("id", "").startswith("aux_ext_")]
    assert len(ext) >= 1, f"должен эмитить >=1 отрезок продления, constructions={aux.get('constructions')}"
    assert any(c.get("p1") == "M" and c.get("p2") == "K" for c in ext), \
        f"отрезок продления должен быть M-K: {ext}"
    assert all(c.get("style") == "aux" and c.get("dashed") for c in ext), \
        f"отрезок продления должен быть aux/dashed: {ext}"


# --- Регресс: ложное утверждение → нет aux ---

def test_false_statement_no_aux():
    """Ложное утверждение (CH=AM ⇒ A=2B): solver solvable=false,
    aux пустой, base нормализован (стиль solid)."""
    solver = _load("solver_cham_false.json")
    base_raw = {"constructions": [
        {"type": "free_point", "id": "A", "x": 150, "y": 100, "label": "A"},
        {"type": "free_point", "id": "B", "x": 430, "y": 110, "label": "B"},
        {"type": "free_point", "id": "C", "x": 300, "y": 420, "label": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B", "style": "aux", "dashed": True},
        {"type": "altitude", "id": "alt_CH", "vertex": "C", "side_a": "A", "side_b": "B", "foot_id": "H"},
        {"type": "segment", "id": "CH", "p1": "C", "p2": "H", "style": "aux", "dashed": True},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M", "style": "aux", "dashed": True},
    ]}
    base = normalize_base_plan(base_raw)
    aux, issues = compile_solver_aux(solver, base)
    bad = [c for c in base["constructions"] if c.get("style") == "aux" or c.get("dashed")]
    assert solver.get("solvable") is False, "утверждение должно быть solvable=false"
    assert aux.get("has_aux") is False, "для ложного утверждения aux должен быть пустым"
    assert len(bad) == 0, f"base должен быть нормализован (0 aux-styled): {bad}"


def test_e11_segment_duplicate_skipped():
    """solver пере-диктовал данное (медиану AM) как segment aux —
    компилятор пропускает его (FULFILLED_BY_BASE:segment:AM),
    не кладя пунктирную aux-копию поверх сплошного данного."""
    base_raw = {"constructions": [
        {"type": "free_point", "id": "A", "x": 150, "y": 150, "label": "A"},
        {"type": "free_point", "id": "B", "x": 150, "y": 400, "label": "B"},
        {"type": "free_point", "id": "C", "x": 400, "y": 150, "label": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},  # данное
    ]}
    base = normalize_base_plan(base_raw)
    solver = {
        "solvable": True, "aux_needed": True, "confidence": 0.9,
        "aux_constructions": [
            {"op": "segment", "points": ["A", "M"], "step_no": 1,
             "purpose": "провести медиану", "quote": "Проведём медиану AM."},
        ],
    }
    aux, issues = compile_solver_aux(solver, base)
    assert any("FULFILLED_BY_BASE:segment:AM" in str(i) for i in issues), \
        f"должно быть FULFILLED_BY_BASE:segment:AM, issues={issues}"
    assert not any(c.get("type") == "segment" and c.get("id", "").startswith("aux_")
                  and {c.get("p1"), c.get("p2")} == {"A", "M"}
                  for c in aux.get("constructions", [])), \
        f"aux-сегмент AM не должен дублироваться: {aux.get('constructions')}"


def test_e13_constraint_without_id_no_crash():
    """E12: ограничение angle_at_vertex без поля id не должно крашить рендер.
    base_planner (v5) эмитит angle_at_vertex(vertex, ray1, ray2, value_deg)
    без id. Движок падал с KeyError 'id' и в execute_construction, и в render_svg.
    Фикс: cid = constr.get("id") + служебный id если None; render пропускает
    объекты без id."""
    from geometric_engine import engine as E
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "B", "x": 120, "y": 440, "label": "B"},
        {"type": "free_point", "id": "C", "x": 480, "y": 440, "label": "C"},
        {"type": "free_point", "id": "A", "x": 172.7, "y": 312.7, "label": "A"},
        # ограничение БЕЗ id — не должно крашить
        {"type": "angle_at_vertex", "vertex": "A", "ray1": "B", "ray2": "C", "value_deg": 90},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},
    ]})
    ctx = E.BuildContext()
    fails = []
    for c in base["constructions"]:
        try: E.execute_construction(ctx, c)
        except Exception as e:
            fails.append((c.get("type"), str(e)))
    assert not fails, f"execute_construction не должен падать на angle_at_vertex без id: {fails}"
    # render_svg тоже не должен падать
    _s = E.EngineSettings(); _s.auto_fit = True
    svg = E.render_svg(ctx, 620, 500, _s)
    assert "<svg" in svg, "render_svg должен выдать SVG"


def test_right_angle_circle_through_vertices():
    """End-to-end: base (прямоугольный треугольник, A=90) + solver (окружность
    с центром M радиусом MB) → окружность проходит через A, B, C; BC — диаметр."""
    import math
    from geometric_engine import engine as E
    base = normalize_base_plan(_load("base_plan_right_angle.json"))
    solver = _load("solver_right_angle.json")
    aux, issues = compile_solver_aux(solver, base)
    assert aux.get("has_aux") is True, f"aux должен содержать окружность: {aux}"
    merged = {"constructions": base["constructions"] + aux.get("constructions", [])}
    ctx = E.BuildContext()
    for c in merged["constructions"]:
        try: E.execute_construction(ctx, c)
        except Exception as e:
            if "уже существует" in str(e): continue
    assert "aux_circle_center_radius_0" in ctx.circles, "окружность должна отрендериться"
    center, r = ctx.circles["aux_circle_center_radius_0"]
    A, B, C = ctx.points["A"], ctx.points["B"], ctx.points["C"]
    dA = math.hypot(A[0]-center[0], A[1]-center[1])
    dB = math.hypot(B[0]-center[0], B[1]-center[1])
    dC = math.hypot(C[0]-center[0], C[1]-center[1])
    assert abs(dA - r) < 1.0, f"A должна лежать на окружности: dA={dA:.2f} r={r:.2f}"
    assert abs(dB - r) < 1.0, f"B должна лежать на окружности: dB={dB:.2f} r={r:.2f}"
    assert abs(dC - r) < 1.0, f"C должна лежать на окружности: dC={dC:.2f} r={r:.2f}"


def test_mark_equal_segments_compiled_and_rendered():
    """solver-v5: solver диктует mark_equal_segments segments:[B,M,C,M,A,M] →
    компилятор переводит в equal_segments_mark, движок рисует насечки."""
    from geometric_engine import engine as E
    solver = {
        "solvable": True, "steps": [{"no": 1, "text": "Отметим равные отрезки BM, CM и AM."}],
        "aux_needed": True,
        "aux_constructions": [
            {"op": "circle_center_radius", "center": "M", "through": "B",
             "quote": "Построим окружность с центром M радиуса MB.", "step_no": 1},
            {"op": "mark_equal_segments", "segments": ["B", "M", "C", "M", "A", "M"],
             "count": 1, "quote": "Отметим равные отрезки BM, CM и AM.", "step_no": 1},
        ],
    }
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "B", "x": 120, "y": 440, "label": "B"},
        {"type": "free_point", "id": "C", "x": 480, "y": 440, "label": "C"},
        {"type": "free_point", "id": "A", "x": 172.7, "y": 312.7, "label": "A"},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},
    ]})
    aux, issues = compile_solver_aux(solver, base)
    assert not any("UNKNOWN_AUX_OP" in i for i in issues), f"mark_equal_segments не должен быть UNKNOWN: {issues}"
    eq = [c for c in aux.get("constructions", []) if c.get("type") == "equal_segments_mark"]
    assert len(eq) == 1, f"должна быть одна equal_segments_mark: {aux.get('constructions')}"
    assert eq[0]["segments"] == ["B", "M", "C", "M", "A", "M"], f"segments: {eq[0]['segments']}"
    assert eq[0]["count"] == 1, f"count: {eq[0]['count']}"
    # рендер не падает
    merged = {"constructions": base["constructions"] + aux.get("constructions", [])}
    ctx = E.BuildContext()
    for c in merged["constructions"]:
        try: E.execute_construction(ctx, c)
        except Exception as e:
            if "уже существует" in str(e): continue
    _s = E.EngineSettings(); _s.auto_fit = True
    svg = E.render_svg(ctx, 620, 500, _s)
    assert "equal-tick" in svg, "насечки равенства должны отрендериться (class equal-tick)"


def test_e15_line_intersection_helper_lines_hidden():
    """E15: вспомогательные прямые для line_intersection (когда line1/line2
    заданы парами точек) создаются как hidden — не рисуются, но линия хранится
    для вычисления пересечения."""
    from geometric_engine import engine as E
    solver = {
        "solvable": True, "steps": [{"no": 1, "text": "Найдём точку E — пересечение AB и CD."}],
        "aux_needed": True,
        "aux_constructions": [
            {"op": "line_intersection", "line1": ["A", "B"], "line2": ["C", "D"],
             "id": "E", "quote": "пересечение AB и CD", "step_no": 1},
        ],
    }
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "A", "x": 100, "y": 100, "label": "A"},
        {"type": "free_point", "id": "B", "x": 400, "y": 300, "label": "B"},
        {"type": "free_point", "id": "C", "x": 100, "y": 300, "label": "C"},
        {"type": "free_point", "id": "D", "x": 400, "y": 100, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
    ]})
    aux, issues = compile_solver_aux(solver, base)
    helpers = [c for c in aux.get("constructions", []) if c.get("type") == "line"]
    assert helpers, f"должны быть helper-линии: {aux.get('constructions')}"
    for h in helpers:
        assert h.get("hidden") is True, f"helper-линия {h.get('id')} должна быть hidden"
    # рендер: helper-линии не должны давать видимых <line> для aux_line_AB/CD
    merged = {"constructions": base["constructions"] + aux.get("constructions", [])}
    ctx = E.BuildContext()
    for c in merged["constructions"]:
        try: E.execute_construction(ctx, c)
        except Exception as e:
            if "уже существует" in str(e): continue
    _s = E.EngineSettings(); _s.auto_fit = True
    svg = E.render_svg(ctx, 500, 400, _s)
    # точка пересечения E создана
    assert "E" in ctx.points, "точка E (пересечение) должна быть создана"


def test_e16_redundant_parallel_line_hidden():
    """E16: parallel_line через D параллельно AB избыточна, если в базе уже есть
    отрезок из D, параллельный AB (напр. DE || AB). Тогда parallel_line
    помечается hidden (линия хранится, но не рисуется)."""
    from geometric_engine import engine as E
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "A", "x": 100, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "free_point", "id": "D", "x": 298, "y": 216, "label": "D"},
        {"type": "free_point", "id": "E", "x": 298, "y": 420, "label": "E"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "DE", "p1": "D", "p2": "E"},
    ]})
    solver = {
        "solvable": True, "steps": [{"no": 1, "text": "Прямая через D параллельно AB."}],
        "aux_needed": True,
        "aux_constructions": [
            {"op": "parallel_through", "point": "D", "to_line": ["A", "B"],
             "quote": "Прямая через D параллельно AB", "step_no": 1},
        ],
    }
    aux, issues = compile_solver_aux(solver, base)
    merged = {"constructions": base["constructions"] + aux.get("constructions", [])}
    ctx = E.BuildContext()
    for c in merged["constructions"]:
        try: E.execute_construction(ctx, c)
        except Exception as e:
            if "уже существует" in str(e): continue
    pl = [k for k, m in ctx.meta.items() if m.get("type") == "parallel_line"]
    assert pl, "parallel_line должна быть в ctx"
    assert ctx.meta[pl[0]].get("hidden") is True, "избыточная parallel_line должна быть hidden"
    # линия всё ещё хранится (для возможных пересечений)
    assert pl[0] in ctx.lines, "линия parallel_line должна храниться в ctx.lines"


def test_e18_redundant_given_mark_suppressed():
    """E18: mark_equal_segments, где ALL пары — данные равенства (N — середина
    AC в базе), подавляется (FULFILLED_BY_BASE), не дублирует midpoint_mark."""
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 500, "y": 420, "label": "C"},
        {"type": "midpoint", "id": "N", "p1": "A", "p2": "C", "label": "N"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ]})
    solver = {"solvable": True,
              "steps": [{"no": 1, "text": "Отметим AN=CN, так как N — середина AC."}],
              "aux_needed": True,
              "aux_constructions": [
                  {"op": "mark_equal_segments", "segments": ["A", "N", "C", "N"],
                   "count": 2, "quote": "Отметим AN=CN, так как N — середина AC.",
                   "step_no": 1},
              ]}
    aux, issues = compile_solver_aux(solver, base)
    assert any("FULFILLED_BY_BASE:mark_equal_segments" in i for i in issues), \
        f"данное равенство AN=CN должно подавиться (FULFILLED_BY_BASE): {issues}"
    assert not any(c.get("type") == "equal_segments_mark"
                  for c in aux.get("constructions", [])), \
        "mark_equal_segments для данного равенства не должен попасть в aux"


def test_e17_tick_not_on_vertex():
    """E17: если середина отмеченного отрезка — подписанная точка-вершина
    (N — середина MD), насечки разносятся на дробную позицию (0.3/0.7),
    а не налезают на вершину N."""
    from geometric_engine import engine as E
    import re
    base = normalize_base_plan({"constructions": [
        {"type": "free_point", "id": "M", "x": 100, "y": 240, "label": "M"},
        {"type": "free_point", "id": "D", "x": 500, "y": 240, "label": "D"},
        {"type": "free_point", "id": "N", "x": 300, "y": 240, "label": "N"},
        {"type": "free_point", "id": "B", "x": 100, "y": 440, "label": "B"},
        {"type": "free_point", "id": "C", "x": 500, "y": 440, "label": "C"},
        {"type": "segment", "id": "MD", "p1": "M", "p2": "D"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ]})
    solver = {"solvable": True,
              "steps": [{"no": 1, "text": "Отметим MD=BC."}],
              "aux_needed": True,
              "aux_constructions": [
                  {"op": "mark_equal_segments", "segments": ["M", "D", "B", "C"],
                   "count": 4, "quote": "Отметим MD=BC.", "step_no": 1},
              ]}
    aux, issues = compile_solver_aux(solver, base)
    merged = {"constructions": base["constructions"] + aux.get("constructions", [])}
    ctx = E.BuildContext()
    for c in merged["constructions"]:
        try:
            E.execute_construction(ctx, c)
        except Exception as e:
            if "уже существует" in str(e):
                continue
    _s = E.EngineSettings()
    _s.auto_fit = False
    svg = E.render_svg(ctx, 620, 500, _s)
    # SVG использует namespace, поэтому парсим регулярками.
    tick_lines = re.findall(r'<line\b[^>]*class="equal-tick"[^>]*/>', svg)
    centers = []
    for t in tick_lines:
        x1 = float(re.search(r'x1="([\d.-]+)"', t).group(1))
        x2 = float(re.search(r'x2="([\d.-]+)"', t).group(1))
        y1 = float(re.search(r'y1="([\d.-]+)"', t).group(1))
        y2 = float(re.search(r'y2="([\d.-]+)"', t).group(1))
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    assert centers, "насечки равенства должны отрендериться"
    # N = (300, 240). Ни одна группа насечек не должна быть в радиусе 12px от N.
    bad = [(x, y) for (x, y) in centers
           if abs(x - 300.0) < 12.0 and abs(y - 240.0) < 12.0]
    assert not bad, f"насечки налезают на вершину N (300,240): {bad}"




def test_verifier_catches_false_equal_segments():
    """E20-верификатор: base-план с equal_segments_mark на НЕравных отрезках
    (AD:DB=2:1) должен быть пойман как INEQUAL_SEGMENTS."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "D", "x": 200, "y": 313, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "equal_segments_mark", "id": "mark_AD_DB",
         "pairs": [["A", "D"], ["D", "B"]]},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "AD:DB=2:1."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    errs = " ".join(rep["errors"])
    assert "INEQUAL_SEGMENTS" in errs, \
        f"верификатор не поймал ложное equal_segments_mark: {rep['errors']}"


def test_verifier_passes_true_equal_segments_pairs_field():
    """E20: верификатор читает поле `pairs` (а не только `segments`), и
    корректные равные отрезки проходят без ошибок."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 200, "y": 100, "label": "A"},
        {"type": "free_point", "id": "B", "x": 400, "y": 100, "label": "B"},
        {"type": "free_point", "id": "C", "x": 400, "y": 300, "label": "C"},
        {"type": "free_point", "id": "D", "x": 200, "y": 300, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
        {"type": "equal_segments_mark", "id": "mark_AB_CD",
         "pairs": [["A", "B"], ["C", "D"]]},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "AB=CD."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    assert not rep["errors"], \
        f"верификатор ошибочно забраковал верные равные отрезки: {rep['errors']}"


def test_verifier_catches_false_parallel_p1p2p3p4():
    """E20: parallel_mark с p1/p2/p3/p4 на непараллельных отрезках → поймать."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "free_point", "id": "D", "x": 300, "y": 250, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
        {"type": "parallel_mark", "id": "par_false",
         "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "AB||CD."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    errs = " ".join(rep["errors"])
    assert "NOT_PARALLEL" in errs, \
        f"верификатор не поймал ложную параллельность (p1/p2/p3/p4): {rep['errors']}"


def test_verifier_catches_duplicate_point():
    """E20-верификатор: solver создал точку O=line_intersection(AD,BE), совпадающую
    с уже существующей точкой I (incenter) → должен предупредить DUPLICATE_POINT."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "free_point", "id": "I", "x": 300, "y": 300, "label": "I"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "O — пересечение AD и BE."}],
              "aux_needed": True,
              "aux_constructions": [
                  {"op": "line_intersection", "line1": ["A", "I"],
                   "line2": ["B", "I"], "id": "O",
                   "quote": "O — пересечение AD и BE.", "step_no": 1},
              ]}
    rep = check_invariants(base, solver)
    warns = " ".join(rep["warnings"])
    assert "DUPLICATE_POINT" in warns and "I" in warns and "O" in warns, \
        f"верификатор не поймал дубликат-точку I≈O: {rep['warnings']}"


def test_dedup_coincident_points_hides_duplicate():
    """E20: dedup_coincident_points помечает дубликат (та же координата) как
    hidden=True, оставляя оригинал видимым. Геометрия (ctx.points) не трогается."""
    import geometric_engine.engine as E
    ctx = E.BuildContext()
    # base incenter I
    E.execute_construction(ctx, {"type": "free_point", "id": "I",
                                 "x": 300, "y": 300, "label": "I"})
    # solver пере-создал O в той же точке (симулируем: движок уже посчитал
    # координаты пересечения, совпадающие с I).
    ctx.points["O"] = (300.0, 300.0)
    ctx.meta["O"] = {"type": "intersect_lines", "label": "O"}
    n = E.dedup_coincident_points(ctx)
    assert n >= 1, "дедуп не нашёл дубликат"
    assert ctx.meta["O"].get("hidden") is True, \
        f"дубликат O не скрыт: {ctx.meta.get('O')}"
    assert ctx.meta["I"].get("hidden") is not True, \
        "оригинал I ошибочно скрыт"
    assert ctx.points["O"] == (300.0, 300.0), \
        "координаты дубликата не должны меняться при дедупе"


def test_e21_verifier_catches_false_equal_angles():
    """E21: верификатор ловит ложное равенство углов (BAD=DAC, но углы не равны)."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        # D намеренно не на биссектрисе — ближе к AB.
        {"type": "free_point", "id": "D", "x": 230, "y": 380, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
        {"type": "equal_angles_mark", "id": "ea_false",
         "angles": [["B", "A", "D"], ["D", "A", "C"]]},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "Углы BAD и DAC равны."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    assert any("INEQUAL_ANGLES" in e for e in rep["errors"]), \
        f"верификатор не поймал ложное равенство углов: {rep['errors']}"


def test_e21_verifier_passes_true_equal_angles():
    """E21: верификатор подтверждает истинное равенство углов (D на биссектрисе)."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        # D на биссектрисе угла A (равноудалена по углу). Биссектриса из (300,80)
        # в равнобедренном (B,C симметричны) — вертикальная прямая x=300.
        {"type": "free_point", "id": "D", "x": 300, "y": 380, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
        {"type": "equal_angles_mark", "id": "ea_true",
         "angles": [["B", "A", "D"], ["D", "A", "C"]]},
    ]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "Углы BAD и DAC равны."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    assert any("equal_angles" in c for c in rep["checks"]), \
        f"верификатор не подтвердил истинное равенство углов: {rep['checks']}"
    assert not any("INEQUAL_ANGLES" in e for e in rep["errors"]), \
        f"ложная тревога по углам: {rep['errors']}"


def test_e21_verifier_catches_point_off_circle():
    """E21: верификатор ловит точку вне заявленной окружности (через incidences)."""
    base = {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "circumcircle", "id": "omega", "p1": "A", "p2": "B", "p3": "C"},
        # D намеренно не на окружности.
        {"type": "free_point", "id": "D", "x": 300, "y": 250, "label": "D"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
    ], "incidences": [{"point": "D", "on": "circle", "object": "omega"}]}
    solver = {"solvable": True, "steps": [{"no": 1, "text": "D лежит на окружности."}],
              "aux_needed": False, "aux_constructions": []}
    rep = check_invariants(base, solver)
    assert any("POINT_NOT_ON_CIRCLE" in e for e in rep["errors"]), \
        f"верификатор не поймал точку вне окружности: {rep['errors']}"


if __name__ == "__main__":
    tests = [
        ("E10 base_style_normalized", test_e10_base_style_normalized),
        ("E8 duplicate_median_skipped", test_e8_duplicate_median_skipped),
        ("E9 line_extension_emits_segment", test_e9_line_extension_emits_segment),
        ("E11 segment_duplicate_skipped", test_e11_segment_duplicate_skipped),
        ("E13 constraint_without_id_no_crash", test_e13_constraint_without_id_no_crash),
        ("right_angle circle_through_vertices", test_right_angle_circle_through_vertices),
        ("mark_equal_segments compiled and rendered", test_mark_equal_segments_compiled_and_rendered),
        ("E15 line_intersection helpers hidden", test_e15_line_intersection_helper_lines_hidden),
        ("E16 redundant parallel_line hidden", test_e16_redundant_parallel_line_hidden),
        ("E18 redundant given-mark suppressed", test_e18_redundant_given_mark_suppressed),
        ("E17 tick not on vertex", test_e17_tick_not_on_vertex),
        ("false_statement_no_aux", test_false_statement_no_aux),
        ("E20 verifier catches false equal_segments (pairs)", test_verifier_catches_false_equal_segments),
        ("E20 verifier passes true equal_segments (pairs)", test_verifier_passes_true_equal_segments_pairs_field),
        ("E20 verifier catches false parallel (p1/p2/p3/p4)", test_verifier_catches_false_parallel_p1p2p3p4),
        ("E20 verifier catches duplicate point I≈O", test_verifier_catches_duplicate_point),
        ("E20 dedup hides coincident duplicate", test_dedup_coincident_points_hides_duplicate),
        ("E21 verifier catches false equal_angles", test_e21_verifier_catches_false_equal_angles),
        ("E21 verifier passes true equal_angles", test_e21_verifier_passes_true_equal_angles),
        ("E21 verifier catches point off circle", test_e21_verifier_catches_point_off_circle),
    ]
    npass = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            npass += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
    print(f"\n{npass}/{len(tests)} passed")
    sys.exit(0 if npass == len(tests) else 1)

