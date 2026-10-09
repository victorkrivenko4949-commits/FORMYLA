"""
Тесты движка: строим то, что должен собрать _recognize_incircle() —
инцентр O, три биссектрисы, три перпендикуляра из O на стороны (foot A1/B1/C1)
и вписанную окружность с центром O и радиусом OA1.

Также проверяем разные типы построений, чтобы поймать регрессы движка.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pkg"))

from geometric_engine.engine import GeometricEngine
from geometric_engine import geom


def base_triangle_plan():
    """Разносторонний треугольник + разметка треугольника."""
    return {
        "canvas": {"width": 620, "height": 620, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 310, "y": 100, "side": "top"},
            {"type": "free_point", "id": "B", "x": 100, "y": 500, "side": "bottom_left"},
            {"type": "free_point", "id": "C", "x": 520, "y": 500, "side": "bottom_right"},
            {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
        ],
    }


def incircle_solver_plan():
    """
    План, эквивалентный тому, что синтезирует _recognize_incircle():
    incenter → 3 биссектрисы → 3 altitude (foot_id = A1/B1/C1) → circle_center_radius.
    """
    plan = base_triangle_plan()
    plan["constructions"] += [
        {"type": "incenter", "id": "O", "p1": "A", "p2": "B", "p3": "C", "side": "auto"},
        # Биссектрисы (визуализация цепочки).
        {"type": "angle_bisector", "id": "b_A", "p1": "B", "p2": "A", "p3": "C"},
        {"type": "angle_bisector", "id": "b_B", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "angle_bisector", "id": "b_C", "p1": "A", "p2": "C", "p3": "B"},
        # Перпендикуляры из O на стороны — altitude с явным foot_id.
        {"type": "altitude", "id": "h_A1", "p1": "O", "p2": "B", "p3": "C", "foot_id": "A1"},
        {"type": "altitude", "id": "h_B1", "p1": "O", "p2": "C", "p3": "A", "foot_id": "B1"},
        {"type": "altitude", "id": "h_C1", "p1": "O", "p2": "A", "p3": "B", "foot_id": "C1"},
        # Радиус до одного из оснований и окружность.
        # radius_point — задокументированный синоним для «радиус до этой точки».
        {"type": "circle_center_radius", "id": "omega_in", "center": "O", "radius_point": "A1"},
    ]
    return plan


def test_base_builds():
    eng = GeometricEngine()
    svg, ctx = eng.build(base_triangle_plan())
    assert "<svg" in svg and "</svg>" in svg
    assert {"A", "B", "C"} <= set(ctx.points)


def test_incircle_full_chain():
    eng = GeometricEngine()
    svg, ctx = eng.build(incircle_solver_plan())
    assert "<svg" in svg
    # 1. O — инцентр — должен быть внутри треугольника.
    O = ctx.points["O"]
    A, B, C = ctx.points["A"], ctx.points["B"], ctx.points["C"]
    # Проверка «O внутри ABC» через знаки cross-product.
    def sign(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    s1 = sign(A, B, O); s2 = sign(B, C, O); s3 = sign(C, A, O)
    assert (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)
    # 2. Основания A1/B1/C1 присутствуют.
    assert {"A1", "B1", "C1"} <= set(ctx.points), \
        f"Foot points missing: got {set(ctx.points)}"
    # 3. Радиусы OA1, OB1, OC1 равны (свойство инцентра).
    r1 = geom.dist(O, ctx.points["A1"])
    r2 = geom.dist(O, ctx.points["B1"])
    r3 = geom.dist(O, ctx.points["C1"])
    assert abs(r1 - r2) < 1e-4 and abs(r1 - r3) < 1e-4, \
        f"Radii mismatch: {r1} {r2} {r3}"
    # 4. Окружность действительно вписана: центр = O, r = r1.
    circle = ctx.circles.get("omega_in")
    assert circle is not None, "Incircle omega_in not created"
    (cx, cy), r = circle
    assert abs(cx - O[0]) < 1e-4 and abs(cy - O[1]) < 1e-4
    assert abs(r - r1) < 1e-4, f"radius drift {r} vs {r1}"
    # 5. SVG содержит и окружность, и основания как ожидаемые метки.
    assert "<circle" in svg
    # 6. Три биссектрисы отрисованы как <line>.
    assert svg.count("<line") >= 3


def test_soft_hard_split_allows_incircle():
    """Даже если ретрай наткнётся на SOFT-нарушения, aux должен уцелеть."""
    from geometric_engine.engine import run_all_checks, DEFAULT_SETTINGS, _is_soft_violation
    eng = GeometricEngine()
    svg, ctx = eng.build(incircle_solver_plan())
    check = run_all_checks(ctx, 620, 620, 40, eng.settings)
    hard = [v for v in check.violations if not _is_soft_violation(v)]
    print("HARD:", hard)
    print("SOFT (первые 3):", [v for v in check.violations if _is_soft_violation(v)][:3])
    assert not hard, f"Hard violations on valid incircle plan: {hard}"


if __name__ == "__main__":
    test_base_builds();               print("test_base_builds: OK")
    test_incircle_full_chain();       print("test_incircle_full_chain: OK")
    test_soft_hard_split_allows_incircle(); print("test_soft_hard_split_allows_incircle: OK")
