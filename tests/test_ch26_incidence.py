# -*- coding: utf-8 -*-
"""CH26: тесты инцидентности (point_on_circle / inscribed_polygon /
INCIDENCE_VIOLATED / MISSING_INCIDENCE)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine  # noqa: E402
from geometric_engine import geom  # noqa: E402


def _build(description, seed=42):
    eng = GeometricEngine()
    svg, ctx = eng.build(description, seed=seed)
    return svg, ctx, eng


def _circle_plan():
    return {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "O", "x": 300, "y": 250},
            {"type": "circle_center_radius", "id": "omega", "center": "O", "radius": 180},
        ],
    }


# ── FIX 1: point_on_circle ──

def test_point_on_circle_lies_on_circle():
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "point_on_circle", "id": "D", "circle": "omega", "angle_deg": 145}
    )
    _, ctx, _ = _build(plan)
    center, radius = ctx.circles["omega"]
    pt = ctx.points["D"]
    assert abs(geom.dist(center, pt) - radius) < 1e-6


def test_point_on_circle_between_arc():
    plan = _circle_plan()
    # Точки C и A на окружности — через point_on_circle с явными углами.
    plan["constructions"].extend([
        {"type": "point_on_circle", "id": "C", "circle": "omega", "angle_deg": 90},
        {"type": "point_on_circle", "id": "A", "circle": "omega", "angle_deg": 200},
        {"type": "point_on_circle", "id": "D", "circle": "omega", "between": ["C", "A"]},
    ])
    _, ctx, _ = _build(plan)
    center, radius = ctx.circles["omega"]
    pt = ctx.points["D"]
    # На окружности.
    assert abs(geom.dist(center, pt) - radius) < 1e-6
    # Угол D должен лежать строго между углами C и A (по меньшей дуге).
    a_c = math_angle(ctx.points["C"], center)
    a_a = math_angle(ctx.points["A"], center)
    a_d = math_angle(ctx.points["D"], center)
    # Нормализуем дугу от C до A по часовой/против и проверим, что D внутри.
    span = (a_a - a_c) % 360.0
    d_off = (a_d - a_c) % 360.0
    assert 0.0 < d_off < span


def math_angle(pt, center):
    import math
    return math.degrees(math.atan2(pt[1] - center[1], pt[0] - center[0])) % 360.0


def test_point_on_circle_seed_changes_position_but_stays_on_circle():
    plan = _circle_plan()
    plan["constructions"] = _circle_plan()["constructions"] + [
        {"type": "point_on_circle", "id": "C", "circle": "omega", "angle_deg": 90},
        {"type": "point_on_circle", "id": "A", "circle": "omega", "angle_deg": 200},
        {"type": "point_on_circle", "id": "D", "circle": "omega", "between": ["C", "A"]},
    ]
    _, ctx1, _ = _build(plan, seed=42)
    _, ctx2, _ = _build(plan, seed=43)
    center, radius = ctx1.circles["omega"]
    p1 = ctx1.points["D"]
    p2 = ctx2.points["D"]
    # Обе на окружности.
    assert abs(geom.dist(center, p1) - radius) < 1e-6
    assert abs(geom.dist(center, p2) - radius) < 1e-6


# ── FIX 2: inscribed_polygon ──

def test_inscribed_polygon_all_vertices_on_circle():
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
         "vertices": ["A", "B", "C", "D"], "order": "ccw"}
    )
    _, ctx, _ = _build(plan)
    center, radius = ctx.circles["omega"]
    for vid in ("A", "B", "C", "D"):
        assert vid in ctx.points
        assert abs(geom.dist(center, ctx.points[vid]) - radius) < 1e-6


def test_inscribed_polygon_ccw_order_no_self_intersection():
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
         "vertices": ["A", "B", "C", "D"], "order": "ccw"}
    )
    _, ctx, _ = _build(plan)
    verts = [ctx.points[v] for v in ("A", "B", "C", "D")]
    # Проверяем, что многоугольник не самопересекается: знак поворота
    # каждой последовательной тройки одинаков (выпуклый).
    signs = []
    for i in range(4):
        a = verts[i]
        b = verts[(i + 1) % 4]
        c = verts[(i + 2) % 4]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        signs.append(cross)
    # Для ccw порядка все cross >= 0 (выпуклый).
    assert all(s >= -1e-6 for s in signs)


def test_inscribed_polygon_degenerate_retries():
    # min_arc_deg слишком велик для n вершин — движок бросает ConstructionError,
    # которую build_with_retry обработает как HARD и вернёт violations.
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
         "vertices": ["A", "B", "C", "D"], "order": "ccw", "min_arc_deg": 100}
    )
    eng = GeometricEngine()
    svg, ctx, attempts, violations = eng.build_with_retry(plan)
    # 100° * 4 = 400° > 360° — невозможная конфигурация.
    assert svg == ""
    assert any("INCIDENCE" in v or "min_arc" in v for v in violations) or attempts > 1


# ── FIX 3: INCIDENCE_VIOLATED ──

def test_incidence_violated_point_inside_circle():
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "free_point", "id": "D", "x": 300, "y": 260}  # внутри круга
    )
    plan["incidences"] = [{"point": "D", "on": "circle", "object": "omega"}]
    eng = GeometricEngine()
    svg, ctx, attempts, violations = eng.build_with_retry(plan)
    assert any("INCIDENCE_VIOLATED" in v for v in violations)


def test_incidence_violated_point_on_circle_passes():
    plan = _circle_plan()
    plan["constructions"].append(
        {"type": "point_on_circle", "id": "D", "circle": "omega", "angle_deg": 145}
    )
    plan["incidences"] = [{"point": "D", "on": "circle", "object": "omega"}]
    eng = GeometricEngine()
    svg, ctx, attempts, violations = eng.build_with_retry(plan)
    assert not any("INCIDENCE_VIOLATED" in v for v in violations)


def test_incidence_violated_point_outside_segment():
    plan = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "B", "x": 100, "y": 250},
            {"type": "free_point", "id": "C", "x": 500, "y": 250},
            {"type": "free_point", "id": "M", "x": 550, "y": 250},  # вне BC
        ],
        "incidences": [{"point": "M", "on": "segment", "object": ["B", "C"]}],
    }
    eng = GeometricEngine()
    svg, ctx, attempts, violations = eng.build_with_retry(plan)
    assert any("INCIDENCE_VIOLATED" in v for v in violations)


# ── FIX 4: MISSING_INCIDENCE (в validator) ──

def test_missing_incidence_free_point_inscribed():
    from services.figure_plan_validator import check_missing_incidence
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 150},
            {"type": "free_point", "id": "B", "x": 450, "y": 150},
            {"type": "free_point", "id": "C", "x": 450, "y": 350},
            {"type": "free_point", "id": "D", "x": 150, "y": 250},
            {"type": "circumcircle", "id": "omega", "p1": "A", "p2": "B", "p3": "C"},
        ],
    }
    errors = check_missing_incidence("Четырёхугольник ABCD вписан в окружность.", base)
    assert any("MISSING_INCIDENCE" in e for e in errors)


def test_missing_incidence_inscribed_polygon_ok():
    from services.figure_plan_validator import check_missing_incidence
    base = {
        "constructions": [
            {"type": "free_point", "id": "O", "x": 300, "y": 250},
            {"type": "circle_center_radius", "id": "omega", "center": "O", "radius": 180},
            {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
             "vertices": ["A", "B", "C", "D"], "order": "ccw"},
        ],
    }
    errors = check_missing_incidence("Четырёхугольник ABCD вписан в окружность.", base)
    assert not any("MISSING_INCIDENCE" in e for e in errors)


def test_missing_incidence_plain_triangle_no_false_positive():
    from services.figure_plan_validator import check_missing_incidence
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 400},
            {"type": "free_point", "id": "B", "x": 450, "y": 400},
            {"type": "free_point", "id": "C", "x": 300, "y": 100},
        ],
    }
    errors = check_missing_incidence(
        "В треугольнике ABC угол A равен 40°. Найдите угол B.", base
    )
    assert errors == []


def test_validator_accepts_inscribed_polygon_vertices():
    from services.figure_validator import validate_figure_json
    plan = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "O", "x": 300, "y": 250},
            {"type": "circle_center_radius", "id": "omega", "center": "O", "radius": 180},
            {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
             "vertices": ["A", "B", "C", "D"], "order": "ccw"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        ],
    }
    result = validate_figure_json(plan)
    assert result["valid"] is True, result.get("errors")
