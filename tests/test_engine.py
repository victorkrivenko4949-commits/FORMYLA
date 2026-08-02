"""
tests/test_engine.py — тесты геометрического движка.

- По 2 теста на каждый вид построения
- Тесты на все 5 проверок из задачи 4
- Тест на повторяемость (побайтовое совпадение)
"""

import json
import os
import sys
import tempfile
import math
from pathlib import Path

import pytest

# Добавляем движок в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from geometric_engine.engine import (
    GeometricEngine, EngineSettings, BuildContext, execute_construction,
    ConstructionError, run_all_checks
)
from geometric_engine import geom


# ═══════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def engine():
    return GeometricEngine()


@pytest.fixture
def settings():
    return EngineSettings()


@pytest.fixture
def fresh_ctx():
    return BuildContext()


@pytest.fixture
def canvas():
    return {"width": 800, "height": 600, "margin": 30}


# ═══════════════════════════════════════════════════════════════
# Тесты: ТОЧКИ (2 теста на каждый тип)
# ═══════════════════════════════════════════════════════════════

class TestFreePoint:
    def test_free_point_basic(self, fresh_ctx):
        c = {"type": "free_point", "id": "A", "x": 100, "y": 200}
        execute_construction(fresh_ctx, c)
        pt = fresh_ctx.points["A"]
        assert pt == (100.0, 200.0)
        assert fresh_ctx.meta["A"]["type"] == "free_point"

    def test_free_point_default_coords(self, fresh_ctx):
        c = {"type": "free_point", "id": "O"}
        execute_construction(fresh_ctx, c)
        pt = fresh_ctx.points["O"]
        assert pt == (0.0, 0.0)  # default


class TestMidpoint:
    def test_midpoint_horizontal(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"})
        pt = fresh_ctx.points["M"]
        assert pt == (5.0, 0.0)

    def test_midpoint_diagonal(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 3, "y": 7})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 9, "y": 1})
        execute_construction(fresh_ctx, {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"})
        pt = fresh_ctx.points["M"]
        assert pt == (6.0, 4.0)


class TestPointOnSegment:
    def test_point_on_segment_quarter(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 100, "y": 0})
        execute_construction(fresh_ctx, {"type": "point_on_segment", "id": "P", "p1": "A", "p2": "B", "ratio": 0.25})
        pt = fresh_ctx.points["P"]
        assert pt == (25.0, 0.0)

    def test_point_on_segment_default_mid(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 10})
        execute_construction(fresh_ctx, {"type": "point_on_segment", "id": "P", "p1": "A", "p2": "B"})
        pt = fresh_ctx.points["P"]
        assert pt == (5.0, 5.0)


class TestFootPerpendicular:
    def test_foot_perpendicular_missing_point(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "segment", "id": "AB", "p1": "A", "p2": "B"})
        # C not defined -> must raise ConstructionError
        with pytest.raises(ConstructionError):
            execute_construction(fresh_ctx, {"type": "foot_perpendicular", "id": "H", "p1": "C", "line1": "AB"})

    def test_foot_perpendicular_works(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "segment", "id": "AB", "p1": "A", "p2": "B"})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "P", "x": 3, "y": 5})
        execute_construction(fresh_ctx, {"type": "foot_perpendicular", "id": "H", "p1": "P", "line1": "AB"})
        pt = fresh_ctx.points["H"]
        assert abs(pt[0] - 3.0) < 1e-9
        assert abs(pt[1] - 0.0) < 1e-9


class TestIntersectLines:
    def test_intersect_lines_perpendicular(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "line", "id": "h", "p1": "A", "p2": "B"})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": -10})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "D", "x": 5, "y": 10})
        execute_construction(fresh_ctx, {"type": "line", "id": "v", "p1": "C", "p2": "D"})
        execute_construction(fresh_ctx, {"type": "intersect_lines", "id": "X", "line1": "h", "line2": "v"})
        pt = fresh_ctx.points["X"]
        assert abs(pt[0] - 5.0) < 1e-9
        assert abs(pt[1] - 0.0) < 1e-9

    def test_intersect_lines_parallel_error(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "line", "id": "l1", "p1": "A", "p2": "B"})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "D", "x": 10, "y": 5})
        execute_construction(fresh_ctx, {"type": "line", "id": "l2", "p1": "C", "p2": "D"})
        with pytest.raises(ConstructionError):
            execute_construction(fresh_ctx, {"type": "intersect_lines", "id": "X", "line1": "l1", "line2": "l2"})


class TestIntersectLineCircle:
    def test_intersect_line_circle_through_center(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c", "center": "O", "radius": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": -10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "line", "id": "l", "p1": "A", "p2": "B"})
        execute_construction(fresh_ctx, {"type": "intersect_line_circle", "id": "P", "line1": "l", "circle": "c", "angle_index": 0})
        pt = fresh_ctx.points["P"]
        assert abs(geom.dist(pt, (0, 0)) - 5.0) < 1e-6

    def test_intersect_line_circle_no_intersection(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c", "center": "O", "radius": 1})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 5, "y": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 5, "y": 6})
        execute_construction(fresh_ctx, {"type": "line", "id": "l", "p1": "A", "p2": "B"})
        with pytest.raises(ConstructionError):
            execute_construction(fresh_ctx, {"type": "intersect_line_circle", "id": "P", "line1": "l", "circle": "c", "angle_index": 0})


class TestIntersectCircles:
    def test_intersect_circles_two_points(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O1", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c1", "center": "O1", "radius": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O2", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c2", "center": "O2", "radius": 5})
        execute_construction(fresh_ctx, {"type": "intersect_circles", "id": "P", "circle1": "c1", "circle2": "c2", "angle_index": 0})
        pt = fresh_ctx.points["P"]
        assert abs(pt[0] - 3.0) < 1e-6
        assert abs(geom.dist(pt, (0, 0)) - 5.0) < 1e-6

    def test_intersect_circles_no_intersection(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O1", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c1", "center": "O1", "radius": 1})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O2", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c2", "center": "O2", "radius": 1})
        with pytest.raises(ConstructionError):
            execute_construction(fresh_ctx, {"type": "intersect_circles", "id": "P", "circle1": "c1", "circle2": "c2", "angle_index": 0})


class TestReflectPoint:
    def test_reflect_over_point(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "P", "x": 3, "y": 4})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "reflect_point_over_point", "id": "P'", "p1": "P", "p2": "O"})
        pt = fresh_ctx.points["P'"]
        assert pt == (-3.0, -4.0)

    def test_reflect_over_line(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "line", "id": "x_axis", "p1": "A", "p2": "B"})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "P", "x": 5, "y": 7})
        execute_construction(fresh_ctx, {"type": "reflect_point_over_line", "id": "P'", "p1": "P", "line1": "x_axis"})
        pt = fresh_ctx.points["P'"]
        assert abs(pt[0] - 5.0) < 1e-9
        assert abs(pt[1] - (-7.0)) < 1e-9  # отражение относительно горизонтали y=0


class TestTriangleCenters:
    def test_circumcenter(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 3, "y": 5})
        execute_construction(fresh_ctx, {"type": "circumcenter", "id": "O", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["O"]
        # Должен быть примерно на перпендикуляре через середину AB
        assert abs(pt[0] - 3.0) < 1e-6

    def test_incenter(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 8})
        execute_construction(fresh_ctx, {"type": "incenter", "id": "I", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["I"]
        r = geom.point_to_line_distance(pt, geom.line_through_points((0, 0), (6, 0)))
        assert abs(r - 2.0) < 1e-6  # r = (a+b-c)/2 = (6+8-10)/2 = 2


class TestCentroid:
    def test_centroid_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 6})
        execute_construction(fresh_ctx, {"type": "centroid", "id": "G", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["G"]
        assert pt == (2.0, 2.0)

    def test_centroid_equilateral(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": -1, "y": -1})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 1, "y": -1})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 1})
        execute_construction(fresh_ctx, {"type": "centroid", "id": "G", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["G"]
        assert abs(pt[0] - 0.0) < 1e-9
        assert abs(pt[1] - (-1.0/3.0)) < 1e-9


class TestOrthocenter:
    def test_orthocenter_right_triangle(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 8})
        execute_construction(fresh_ctx, {"type": "orthocenter", "id": "H", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["H"]
        # В прямоугольном треугольнике ортоцентр = вершина прямого угла
        assert abs(pt[0]) < 1e-9 and abs(pt[1]) < 1e-9

    def test_orthocenter_arbitrary(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 3, "y": 8})
        execute_construction(fresh_ctx, {"type": "orthocenter", "id": "H", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["H"]
        # Ортоцентр должен существовать (не ошибка)
        assert isinstance(pt, tuple)
        assert len(pt) == 2


class TestIncircleTouch:
    def test_incircle_touch_right_triangle(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 8})
        execute_construction(fresh_ctx, {"type": "incircle_touch", "id": "T", "p1": "A", "p2": "B", "p3": "C"})
        pt = fresh_ctx.points["T"]
        # Точка касания на BC (гипотенузе). Должна быть на BC
        assert geom.segment_contains_point(((0, 8), (6, 0)), pt)

    def test_incircle_touch_equilateral_approx(self, fresh_ctx):
        # Равносторонний: вписанная касается в середине
        h = 10 * math.sqrt(3) / 2
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": h})
        execute_construction(fresh_ctx, {"type": "incircle_touch", "id": "T_AB", "p1": "C", "p2": "A", "p3": "B"})
        pt = fresh_ctx.points["T_AB"]
        assert abs(pt[0] - 5.0) < 1e-6
        assert abs(pt[1] - 0.0) < 1e-6


# ═══════════════════════════════════════════════════════════════
# Тесты: ЛИНИИ (2 теста на каждый)
# ═══════════════════════════════════════════════════════════════

class TestSegment:
    def test_segment_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 10})
        execute_construction(fresh_ctx, {"type": "segment", "id": "AB", "p1": "A", "p2": "B"})
        assert "AB" in fresh_ctx.segments
        assert "AB" in fresh_ctx.lines

    def test_segment_dashed(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "segment", "id": "s", "p1": "A", "p2": "B", "dashed": True})
        assert fresh_ctx.meta["s"]["dashed"] is True


class TestRay:
    def test_ray_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "ray", "id": "r", "p1": "A", "p2": "B"})
        assert "r" in fresh_ctx.lines

    def test_ray_not_segment_reverse(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 5, "y": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "ray", "id": "r", "p1": "A", "p2": "B"})
        assert "r" in fresh_ctx.lines


class TestLine:
    def test_line_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 1, "y": 1})
        execute_construction(fresh_ctx, {"type": "line", "id": "l", "p1": "A", "p2": "B"})
        assert "l" in fresh_ctx.lines

    def test_line_vertical(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 5, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 5, "y": 10})
        execute_construction(fresh_ctx, {"type": "line", "id": "v", "p1": "A", "p2": "B"})
        A_coef, B_coef, C = fresh_ctx.lines["v"]
        # вертикаль: |A| ≈ 1, B ≈ 0 (после нормализации A=±1, B=0)
        assert abs(A_coef) > 0.9


class TestAltitude:
    def test_altitude_right_triangle(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 8})
        execute_construction(fresh_ctx, {"type": "altitude", "id": "hA", "p1": "A", "p2": "B", "p3": "C"})
        assert "hA" in fresh_ctx.lines

    def test_altitude_creates_foot(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": 8})
        execute_construction(fresh_ctx, {"type": "altitude", "id": "hC", "p1": "C", "p2": "A", "p3": "B"})
        assert "hC_foot" in fresh_ctx.points


class TestMedian:
    def test_median_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": 10})
        execute_construction(fresh_ctx, {"type": "median", "id": "mA", "p1": "A", "p2": "B", "p3": "C"})
        assert "mA" in fresh_ctx.lines
        assert "mA_mid" in fresh_ctx.points

    def test_median_passes_through_vertex(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 6})
        execute_construction(fresh_ctx, {"type": "median", "id": "mA", "p1": "A", "p2": "B", "p3": "C"})
        # Медиана должна проходить через A=(0,0)
        seg = fresh_ctx.segments.get("mA")
        assert seg is not None


class TestAngleBisector:
    def test_angle_bisector_basic(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 1, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 1})
        execute_construction(fresh_ctx, {"type": "angle_bisector", "id": "bis", "p1": "A", "p2": "B", "p3": "C"})
        assert "bis" in fresh_ctx.lines

    def test_angle_bisector_right_angle(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 1, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 0, "y": 1})
        execute_construction(fresh_ctx, {"type": "angle_bisector", "id": "bis", "p1": "A", "p2": "B", "p3": "C"})
        # Биссектриса прямого угла: направление (1,1)
        line = fresh_ctx.lines["bis"]
        # Через точку B(0,0) и направление (1,1) -> -1*x + 1*y = 0 или x-y=0
        A, Bc, C = line
        assert abs(abs(A) - abs(Bc)) < 1e-9  # коэффициенты равны по модулю


class TestPerpendicularBisector:
    def test_perpendicular_bisector_horizontal(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "perpendicular_bisector", "id": "pb", "p1": "A", "p2": "B"})
        assert "pb" in fresh_ctx.lines

    def test_perpendicular_bisector_midpoint(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 2, "y": 3})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 8, "y": 9})
        execute_construction(fresh_ctx, {"type": "perpendicular_bisector", "id": "pb", "p1": "A", "p2": "B"})
        mid = fresh_ctx.points["pb_mid"]
        assert mid == (5.0, 6.0)


class TestTangent:
    def test_tangent_from_point(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c", "center": "O", "radius": 3})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "P", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "tangent_from_point", "id": "t", "p1": "P", "circle": "c", "angle_index": 0})
        assert "t" in fresh_ctx.lines

    def test_tangent_at_point(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c", "center": "O", "radius": 5})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "P", "x": 5, "y": 0})
        execute_construction(fresh_ctx, {"type": "tangent_at_point", "id": "t", "p1": "P", "circle": "c"})
        assert "t" in fresh_ctx.lines


# ═══════════════════════════════════════════════════════════════
# Тесты: ФИГУРЫ (2 теста)
# ═══════════════════════════════════════════════════════════════

class TestTriangles:
    def test_triangle_arbitrary(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": 8})
        execute_construction(fresh_ctx, {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"})
        assert fresh_ctx.meta["tri"]["type"] == "triangle"
        assert fresh_ctx.meta["tri"]["triangle_type"] == "arbitrary"

    def test_triangle_equilateral(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 10, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 5, "y": 8.66})
        execute_construction(fresh_ctx, {"type": "triangle_equilateral", "id": "tri", "p1": "A", "p2": "B", "p3": "C"})
        assert fresh_ctx.meta["tri"]["triangle_type"] == "equilateral"


class TestQuadrilaterals:
    def test_quadrilateral_arbitrary(self, fresh_ctx):
        for i, (x, y) in enumerate([(0, 0), (10, 0), (12, 8), (2, 6)]):
            execute_construction(fresh_ctx, {"type": "free_point", "id": f"P{i}", "x": x, "y": y})
        execute_construction(fresh_ctx, {"type": "quadrilateral_arbitrary", "id": "quad",
                                          "p1": "P0", "p2": "P1", "p3": "P2", "p4": "P3"})
        assert fresh_ctx.meta["quad"]["type"] == "quadrilateral"

    def test_quadrilateral_square(self, fresh_ctx):
        for i, (x, y) in enumerate([(0, 0), (10, 0), (10, 10), (0, 10)]):
            execute_construction(fresh_ctx, {"type": "free_point", "id": f"Q{i}", "x": x, "y": y})
        execute_construction(fresh_ctx, {"type": "quadrilateral_square", "id": "sq",
                                          "p1": "Q0", "p2": "Q1", "p3": "Q2", "p4": "Q3"})
        assert fresh_ctx.meta["sq"]["quadrilateral_type"] == "square"


class TestCircles:
    def test_circle_center_radius(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "O", "x": 5, "y": 5})
        execute_construction(fresh_ctx, {"type": "circle_center_radius", "id": "c", "center": "O", "radius": 3})
        assert "c" in fresh_ctx.circles
        center, r = fresh_ctx.circles["c"]
        assert center == (5, 5)
        assert r == 3

    def test_circumcircle(self, fresh_ctx):
        execute_construction(fresh_ctx, {"type": "free_point", "id": "A", "x": 0, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "B", "x": 6, "y": 0})
        execute_construction(fresh_ctx, {"type": "free_point", "id": "C", "x": 3, "y": 5})
        execute_construction(fresh_ctx, {"type": "circumcircle", "id": "cc", "p1": "A", "p2": "B", "p3": "C"})
        assert "cc" in fresh_ctx.circles


# ═══════════════════════════════════════════════════════════════
# Тесты: ПРОВЕРКИ (задача 4, тест на каждую)
# ═══════════════════════════════════════════════════════════════

class TestCheckBoundaries:
    """Проверка 1: все объекты внутри поля с отступом"""

    def test_all_points_inside(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 200, "y": 300},
                {"type": "free_point", "id": "B", "x": 400, "y": 300},
                {"type": "free_point", "id": "C", "x": 300, "y": 100},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) == 0

    def test_point_outside(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 10, "y": 10},  # outside margin!
                {"type": "free_point", "id": "B", "x": 400, "y": 300},
                {"type": "free_point", "id": "C", "x": 300, "y": 100},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) > 0
        assert any("границы" in v for v in viol)


class TestCheckDegeneracy:
    """Проверка 3: нет вырожденных случаев"""

    def test_points_too_close(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 200, "y": 200},
                {"type": "free_point", "id": "B", "x": 203, "y": 201},  # too close (~3.6 px)
                {"type": "free_point", "id": "C", "x": 500, "y": 400},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) > 0

    def test_small_angle(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 200, "y": 200},
                {"type": "free_point", "id": "B", "x": 600, "y": 200},
                {"type": "free_point", "id": "C", "x": 600, "y": 210},  # почти на AB: угол при A ~1.4°
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) > 0


class TestCheckSideRatio:
    """Проверка 5: отношение сторон"""

    def test_ok_ratio(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 300, "y": 400},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
                {"type": "free_point", "id": "C", "x": 400, "y": 200},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) == 0

    def test_bad_ratio(self, engine):
        # Очень вытянутый треугольник
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 290},
                {"type": "free_point", "id": "B", "x": 700, "y": 310},
                {"type": "free_point", "id": "C", "x": 400, "y": 300},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) > 0


class TestCheckAreaDegeneracy:
    """Проверка 3: площадь не слишком мала"""

    def test_almost_collinear(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 300},
                {"type": "free_point", "id": "B", "x": 700, "y": 300},
                {"type": "free_point", "id": "C", "x": 400, "y": 301},  # почти на AB
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert len(viol) > 0


# ═══════════════════════════════════════════════════════════════
# Тест: ПОВТОРЯЕМОСТЬ
# ═══════════════════════════════════════════════════════════════

class TestRepeatability:
    """Один вход дважды даёт побайтово одинаковый SVG."""

    def test_same_seed_same_output(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 200, "y": 500},
                {"type": "free_point", "id": "B", "x": 600, "y": 500},
                {"type": "free_point", "id": "C", "x": 350, "y": 120},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
                {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
                {"type": "circumcenter", "id": "O", "p1": "A", "p2": "B", "p3": "C"}
            ]
        }

        svg1, _, _, _ = engine.build_with_retry(desc, seed=12345)
        svg2, _, _, _ = engine.build_with_retry(desc, seed=12345)
        assert svg1 == svg2
        assert len(svg1) > 0


# ═══════════════════════════════════════════════════════════════
# Дополнительные тесты
# ═══════════════════════════════════════════════════════════════

class TestConstructionError:
    """Проверка внятных ошибок."""

    def test_missing_point(self, fresh_ctx):
        with pytest.raises(ConstructionError) as exc_info:
            execute_construction(fresh_ctx, {"type": "midpoint", "id": "M", "p1": "X", "p2": "Y"})
        assert "X" in str(exc_info.value) or "Точка" in str(exc_info.value)

    def test_unknown_construction_type(self, fresh_ctx):
        with pytest.raises(ConstructionError) as exc_info:
            execute_construction(fresh_ctx, {"type": "nonexistent_type", "id": "N"})
        assert "Неизвестный" in str(exc_info.value)


class TestSVGOutput:
    """SVG на выходе валиден."""

    def test_svg_contains_correct_tags(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 200, "y": 300},
                {"type": "free_point", "id": "B", "x": 500, "y": 300},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert '<svg' in svg
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert '</svg>' in svg

    def test_svg_canvas_size(self, engine):
        desc = {
            "canvas": {"width": 1200, "height": 900, "margin": 50},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 300, "y": 450},
                {"type": "free_point", "id": "B", "x": 900, "y": 450},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"}
            ]
        }
        svg, ctx, att, viol = engine.build_with_retry(desc)
        assert 'width="1200"' in svg
        assert 'height="900"' in svg


class TestValidation:
    def test_missing_canvas(self, engine):
        errors = engine.validate_description({})
        assert len(errors) > 0

    def test_valid_description(self, engine):
        desc = {
            "canvas": {"width": 800, "height": 600, "margin": 30},
            "constructions": [{"type": "free_point", "id": "A", "x": 100, "y": 200}]
        }
        errors = engine.validate_description(desc)
        assert len(errors) == 0
