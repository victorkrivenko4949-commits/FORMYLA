"""
Расширенные тесты: incircle через синоним radius_from, отказ при отсутствии
радиуса, синхронизация схемы и движка по enum типов.
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pkg"))

from geometric_engine.engine import GeometricEngine, ConstructionError
from geometric_engine import geom

BASE = {
    "canvas": {"width": 620, "height": 620, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 310, "y": 100},
        {"type": "free_point", "id": "B", "x": 100, "y": 500},
        {"type": "free_point", "id": "C", "x": 520, "y": 500},
        {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "incenter", "id": "O", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "altitude", "id": "h_A1", "p1": "O", "p2": "B", "p3": "C", "foot_id": "A1"},
    ],
}


def _plan_with(circle_constr):
    p = dict(BASE); p["constructions"] = list(BASE["constructions"]) + [circle_constr]; return p


def test_radius_from_alias_works():
    plan = _plan_with({"type": "circle_center_radius", "id": "omega",
                       "center": "O", "radius_from": "A1"})
    eng = GeometricEngine()
    svg, ctx = eng.build(plan)
    (cx, cy), r = ctx.circles["omega"]
    expected = geom.dist(ctx.points["O"], ctx.points["A1"])
    assert abs(r - expected) < 1e-6, f"radius_from ignored: {r} vs {expected}"


def test_radius_point_alias_works():
    plan = _plan_with({"type": "circle_center_radius", "id": "omega",
                       "center": "O", "radius_point": "A1"})
    eng = GeometricEngine()
    _, ctx = eng.build(plan)
    (cx, cy), r = ctx.circles["omega"]
    expected = geom.dist(ctx.points["O"], ctx.points["A1"])
    assert abs(r - expected) < 1e-6


def test_missing_radius_now_raises():
    """Раньше молча схлопывалось в r=1. Теперь — ConstructionError."""
    plan = _plan_with({"type": "circle_center_radius", "id": "omega", "center": "O"})
    eng = GeometricEngine()
    try:
        eng.build(plan)
    except ConstructionError as e:
        assert "circle_center_radius" in str(e)
        return
    raise AssertionError("Expected ConstructionError for missing radius")


def test_zero_radius_raises():
    plan = _plan_with({"type": "circle_center_radius", "id": "omega",
                       "center": "O", "radius": 0})
    eng = GeometricEngine()
    try:
        eng.build(plan)
    except ConstructionError as e:
        assert "CIRCLE_RADIUS_ZERO" in str(e)
        return
    raise AssertionError("Expected ConstructionError for zero radius")


def test_schema_engine_sync():
    """Enum схемы должен покрывать все ctype, реализованные в движке."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "fixed", "schema.json")
    engine_path = os.path.join(os.path.dirname(__file__), "..", "fixed", "engine.py")
    schema = json.load(open(schema_path, encoding="utf-8"))
    in_schema = set(schema["properties"]["constructions"]["items"]["properties"]["type"]["enum"])
    engine_text = open(engine_path, encoding="utf-8").read()
    in_engine = set(re.findall(r'if ctype == "([a-z_]+)"', engine_text)) \
              | set(re.findall(r'elif ctype == "([a-z_]+)"', engine_text))
    missing = in_engine - in_schema
    assert not missing, f"Schema missing types supported by engine: {sorted(missing)}"


if __name__ == "__main__":
    test_radius_from_alias_works();  print("test_radius_from_alias_works: OK")
    test_radius_point_alias_works(); print("test_radius_point_alias_works: OK")
    test_missing_radius_now_raises();print("test_missing_radius_now_raises: OK")
    test_zero_radius_raises();       print("test_zero_radius_raises: OK")
    test_schema_engine_sync();       print("test_schema_engine_sync: OK")
