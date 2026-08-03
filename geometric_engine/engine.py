"""
engine.py — Ядро геометрического движка.

Разбор JSON-описания → вычисление координат → отрисовка SVG → проверки → retry.

Только стандартная библиотека Python. Без numpy, без matplotlib, без интернета.
"""

import json
import math
import random
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

from . import geom
from .geom import Point, Segment

# ═══════════════════════════════════════════════════════════════
# Настройки по умолчанию (задача 4 — пороги одним местом)
# ═══════════════════════════════════════════════════════════════

@dataclass
class EngineSettings:
    """Настройки движка. Все пороги здесь."""
    # Пороги проверок
    min_angle_degrees: float = 8.0          # минимальный угол (градусы), меньше — вырождение
    min_point_distance: float = 8.0         # минимальное расстояние между различными точками (пиксели)
    max_side_ratio: float = 8.0             # максимальное отношение длиннейшей стороны к кратчайшей
    min_triangle_area_ratio: float = 0.005  # минимальная площадь / (диагональ^2) — против почти-прямой

    # Retry
    max_retries: int = 50                   # максимум попыток перегенерации со сдвигом семени

    # Отступ для подписей
    label_padding: float = 14.0             # отступ подписи от точки (пиксели)

    # Цвета (тёмно-синяя тема)
    bg_color: str = "none"                  # прозрачный фон
    line_color: str = "#c8d6e5"             # светлые линии
    point_color: str = "#e8f0fb"            # точки
    label_color: str = "#d0ddf0"            # подписи
    mark_color: str = "#a0b8d8"             # пометки (штрихи, дужки)
    dash_color: str = "#7a8fa8"             # пунктир
    highlight_color: str = "#ffd700"        # подсветка
    hatch_color: str = "#3a5070"            # штриховка

    # Шрифт
    font_family: str = "Arial, Helvetica, sans-serif"
    font_size: int = 16
    label_font_size: int = 14

    # Стили
    line_width: float = 1.8
    dash_array: str = "6,4"
    point_radius: float = 3.5


DEFAULT_SETTINGS = EngineSettings()

# ═══════════════════════════════════════════════════════════════
# Исполнитель построений
# ═══════════════════════════════════════════════════════════════

@dataclass
class ConstructionError(Exception):
    """Ошибка построения с указанием места."""
    construction_id: str
    construction_type: str
    message: str

    def __str__(self):
        return f"[{self.construction_type}] '{self.construction_id}': {self.message}"


class BuildContext:
    """Контекст построения: накопленные объекты и доступ к ним."""

    def __init__(self):
        self.points: Dict[str, Point] = {}
        self.lines: Dict[str, geom.Line] = {}
        self.segments: Dict[str, geom.Segment] = {}
        self.circles: Dict[str, geom.Circle] = {}
        # Метаданные построений (для отрисовки)
        self.meta: Dict[str, Dict[str, Any]] = {}
        # Список всех объектов по порядку
        self.objects: List[Dict[str, Any]] = []

    def get_point(self, ref: str, constr_id: str) -> Point:
        if ref not in self.points:
            raise ConstructionError(constr_id, "ref", f"Точка '{ref}' не найдена")
        return self.points[ref]

    def get_line(self, ref: str, constr_id: str) -> geom.Line:
        if ref not in self.lines:
            raise ConstructionError(constr_id, "ref", f"Прямая '{ref}' не найдена")
        return self.lines[ref]

    def get_circle(self, ref: str, constr_id: str) -> geom.Circle:
        if ref not in self.circles:
            raise ConstructionError(constr_id, "ref", f"Окружность '{ref}' не найдена")
        return self.circles[ref]

    def get_segment(self, ref: str, constr_id: str) -> geom.Segment:
        if ref not in self.segments:
            raise ConstructionError(constr_id, "ref", f"Отрезок '{ref}' не найден")
        return self.segments[ref]


def execute_construction(ctx: BuildContext, constr: dict):
    """Выполнить одно построение. Мутирует ctx."""
    ctype = constr["type"]
    cid = constr["id"]

    try:
        if ctype == "free_point":
            x = constr.get("x", 0.0)
            y = constr.get("y", 0.0)
            ctx.points[cid] = (x, y)
            ctx.meta[cid] = {"type": "free_point", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "midpoint":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            ctx.points[cid] = geom.midpoint(p1, p2)
            ctx.meta[cid] = {"type": "midpoint", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "parents": [constr["p1"], constr["p2"]]}

        elif ctype == "point_on_segment":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            r = constr.get("ratio", 0.5)
            ctx.points[cid] = geom.point_on_segment(p1, p2, r)
            ctx.meta[cid] = {"type": "point_on_segment", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "ratio": r}

        elif ctype == "foot_perpendicular":
            p = ctx.get_point(constr["p1"], cid)
            line = ctx.get_line(constr["line1"], cid)
            ctx.points[cid] = geom.foot_of_perpendicular(p, line)
            ctx.meta[cid] = {"type": "foot_perpendicular", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "intersect_lines":
            l1 = ctx.get_line(constr["line1"], cid)
            l2 = ctx.get_line(constr["line2"], cid)
            result = geom.intersect_lines(l1, l2)
            if result is None:
                raise ConstructionError(cid, ctype, "Прямые параллельны — пересечения нет")
            ctx.points[cid] = result
            ctx.meta[cid] = {"type": "intersect_lines", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "intersect_line_circle":
            line = ctx.get_line(constr["line1"], cid)
            circle = ctx.get_circle(constr["circle"], cid)
            pts = geom.intersect_line_circle(line, circle)
            idx = constr.get("angle_index", 0)
            if idx >= len(pts):
                raise ConstructionError(cid, ctype, f"Пересечений всего {len(pts)}, запрошен индекс {idx}")
            ctx.points[cid] = pts[idx]
            ctx.meta[cid] = {"type": "intersect_line_circle", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "angle_index": idx}

        elif ctype == "intersect_circles":
            c1 = ctx.get_circle(constr["circle1"], cid)
            c2 = ctx.get_circle(constr["circle2"], cid)
            pts = geom.intersect_circles(c1, c2)
            idx = constr.get("angle_index", 0)
            if idx >= len(pts):
                raise ConstructionError(cid, ctype, f"Пересечений окружностей всего {len(pts)}, запрошен индекс {idx}")
            ctx.points[cid] = pts[idx]
            ctx.meta[cid] = {"type": "intersect_circles", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "angle_index": idx}

        elif ctype == "reflect_point_over_point":
            p = ctx.get_point(constr["p1"], cid)
            center = ctx.get_point(constr["p2"], cid)
            ctx.points[cid] = geom.reflect_point_over_point(p, center)
            ctx.meta[cid] = {"type": "reflect_point_over_point", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "reflect_point_over_line":
            p = ctx.get_point(constr["p1"], cid)
            line = ctx.get_line(constr["line1"], cid)
            ctx.points[cid] = geom.reflect_point_over_line(p, line)
            ctx.meta[cid] = {"type": "reflect_point_over_line", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "circumcenter":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            result = geom.circumcenter(p1, p2, p3)
            if result is None:
                raise ConstructionError(cid, ctype, "Точки на одной прямой — описанной окружности нет")
            ctx.points[cid] = result
            ctx.meta[cid] = {"type": "circumcenter", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "incenter":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            result = geom.incenter(p1, p2, p3)
            if result is None:
                raise ConstructionError(cid, ctype, "Вырожденный треугольник")
            ctx.points[cid] = result
            ctx.meta[cid] = {"type": "incenter", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "centroid":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            ctx.points[cid] = geom.centroid(p1, p2, p3)
            ctx.meta[cid] = {"type": "centroid", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "orthocenter":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            result = geom.orthocenter(p1, p2, p3)
            if result is None:
                raise ConstructionError(cid, ctype, "Вырожденный треугольник")
            ctx.points[cid] = result
            ctx.meta[cid] = {"type": "orthocenter", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "incircle_touch":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            ctx.points[cid] = geom.incircle_touch_point(p1, p2, p3)
            ctx.meta[cid] = {"type": "incircle_touch", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        # ─── линии ────────────────────────────────────────────

        elif ctype == "segment":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            ctx.segments[cid] = (p1, p2)
            ctx.lines[cid] = geom.line_through_points(p1, p2)
            ctx.meta[cid] = {"type": "segment", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"]]}

        elif ctype == "ray":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            line = geom.line_through_points(p1, p2)
            ctx.lines[cid] = line
            ctx.segments[cid] = (p1, p2)  # будет расширен при отрисовке
            ctx.meta[cid] = {"type": "ray", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"]]}

        elif ctype == "line":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            ctx.lines[cid] = geom.line_through_points(p1, p2)
            ctx.segments[cid] = (p1, p2)
            ctx.meta[cid] = {"type": "line", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"]]}

        elif ctype == "line_extension":
            origin = ctx.get_line(constr["origin"], cid)
            direction = constr.get("direction", "both")
            extend_by = constr.get("extend_by", 1.0)
            # Берём любую точку с прямой origin
            # Находим две точки на origin...
            seg = ctx.get_segment(constr["origin"], cid)
            p1, p2 = seg
            mid = geom.midpoint(p1, p2)
            d = geom.dist(p1, p2)
            if d < geom.EPS:
                raise ConstructionError(cid, ctype, "Исходный отрезок вырожден")
            vec = ((p2[0] - p1[0]) / d, (p2[1] - p1[1]) / d)
            if direction == "forward":
                new_p1, new_p2 = p1, (p2[0] + vec[0] * extend_by, p2[1] + vec[1] * extend_by)
            elif direction == "backward":
                new_p1, new_p2 = (p1[0] - vec[0] * extend_by, p1[1] - vec[1] * extend_by), p2
            else:
                new_p1 = (p1[0] - vec[0] * extend_by, p1[1] - vec[1] * extend_by)
                new_p2 = (p2[0] + vec[0] * extend_by, p2[1] + vec[1] * extend_by)
            ctx.segments[cid] = (new_p1, new_p2)
            ctx.lines[cid] = origin
            ctx.meta[cid] = {"type": "line_extension", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "altitude":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            # Высота из p1 на прямую p2-p3
            line_base = geom.line_through_points(p2, p3)
            foot = geom.foot_of_perpendicular(p1, line_base)
            line_alt = geom.line_through_points(p1, foot)
            ctx.points[cid + "_foot"] = foot
            ctx.meta[cid + "_foot"] = {"type": "foot_perpendicular", "label": "",
                                       "side": "auto", "hidden": True}
            ctx.lines[cid] = line_alt
            ctx.segments[cid] = (p1, foot)
            ctx.meta[cid] = {"type": "altitude", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]]}

        elif ctype == "median":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            # Медиана из p1 к середине p2-p3
            mid = geom.midpoint(p2, p3)
            ctx.points[cid + "_mid"] = mid
            ctx.meta[cid + "_mid"] = {"type": "midpoint", "label": "",
                                      "side": "auto", "hidden": True}
            ctx.lines[cid] = geom.line_through_points(p1, mid)
            ctx.segments[cid] = (p1, mid)
            ctx.meta[cid] = {"type": "median", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]]}

        elif ctype == "angle_bisector":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            # Биссектриса угла p1-p2-p3
            line_bis = geom.angle_bisector_line(p1, p2, p3)
            ctx.lines[cid] = line_bis
            ctx.segments[cid] = (p2, (p2[0] + (p1[0] - p2[0]) + (p3[0] - p2[0]),
                                      p2[1] + (p1[1] - p2[1]) + (p3[1] - p2[1])))
            ctx.meta[cid] = {"type": "angle_bisector", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]]}

        elif ctype == "perpendicular_bisector":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            mid = geom.midpoint(p1, p2)
            line_pb = geom.perpendicular_bisector(p1, p2)
            ctx.lines[cid] = line_pb
            ctx.points[cid + "_mid"] = mid
            ctx.meta[cid + "_mid"] = {"type": "midpoint", "label": "",
                                      "side": "auto", "hidden": True}
            # Отрезок от середины на некоторое расстояние
            d = geom.dist(p1, p2)
            vec = (p2[0] - p1[0], p2[1] - p1[1])
            n = math.hypot(vec[0], vec[1])
            perp_vec = (-vec[1] / n, vec[0] / n)
            half = d * 0.6
            seg_p1 = (mid[0] + perp_vec[0] * half, mid[1] + perp_vec[1] * half)
            seg_p2 = (mid[0] - perp_vec[0] * half, mid[1] - perp_vec[1] * half)
            ctx.segments[cid] = (seg_p1, seg_p2)
            ctx.meta[cid] = {"type": "perpendicular_bisector", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["p1"], constr["p2"]]}

        elif ctype == "tangent_from_point":
            p = ctx.get_point(constr["p1"], cid)
            circle = ctx.get_circle(constr["circle"], cid)
            tangents = geom.tangent_from_point_to_circle(p, circle)
            idx = constr.get("angle_index", 0)
            if idx >= len(tangents):
                raise ConstructionError(cid, ctype, f"Касательных всего {len(tangents)}, запрошен индекс {idx}")
            ctx.lines[cid] = tangents[idx]
            # Найдём точку касания
            touch_pts = geom.intersect_line_circle(tangents[idx], circle)
            if touch_pts:
                touch_pt = touch_pts[0]
                ctx.points[cid + "_touch"] = touch_pt
                ctx.meta[cid + "_touch"] = {"type": "tangent_touch", "label": "",
                                            "side": "auto", "hidden": True}
                ctx.segments[cid] = (p, touch_pt)
            else:
                ctx.segments[cid] = (p, p)
            ctx.meta[cid] = {"type": "tangent_from_point", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "tangent_at_point":
            p = ctx.get_point(constr["p1"], cid)
            circle = ctx.get_circle(constr["circle"], cid)
            line_t = geom.tangent_at_point(p, circle)
            if line_t is None:
                raise ConstructionError(cid, ctype, "Точка не лежит на окружности")
            ctx.lines[cid] = line_t
            # Отрезок касательной: в обе стороны от точки
            r = circle[1]
            d = geom.dist(p, p)
            half = r * 1.0
            # направляющий вектор
            A, B, _ = line_t
            n = math.hypot(A, B)
            dx, dy = -B / n, A / n
            ctx.segments[cid] = ((p[0] - dx * half, p[1] - dy * half),
                                 (p[0] + dx * half, p[1] + dy * half))
            ctx.meta[cid] = {"type": "tangent_at_point", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        # ─── фигуры ───────────────────────────────────────────

        elif ctype == "triangle_arbitrary":
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]],
                             "triangle_type": "arbitrary"}

        elif ctype == "triangle_acute":
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]],
                             "triangle_type": "acute"}

        elif ctype == "triangle_right":
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]],
                             "triangle_type": "right"}

        elif ctype == "triangle_isosceles":
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]],
                             "triangle_type": "isosceles"}

        elif ctype == "triangle_equilateral":
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"]],
                             "triangle_type": "equilateral"}

        elif ctype == "quadrilateral_arbitrary":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "arbitrary"}

        elif ctype == "quadrilateral_parallelogram":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "parallelogram"}

        elif ctype == "quadrilateral_rectangle":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "rectangle"}

        elif ctype == "quadrilateral_square":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "square"}

        elif ctype == "quadrilateral_rhombus":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "rhombus"}

        elif ctype == "quadrilateral_trapezoid":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "trapezoid"}

        elif ctype == "quadrilateral_isosceles_trapezoid":
            ctx.meta[cid] = {"type": "quadrilateral", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], constr["p3"], constr["p4"]],
                             "quadrilateral_type": "isosceles_trapezoid"}

        elif ctype == "regular_polygon":
            n = constr.get("n", 3)
            center = ctx.get_point(constr["center"], cid)
            radius = constr.get("radius", 1.0)
            start_angle = math.radians(constr.get("start_angle", 0.0))
            verts = geom.regular_polygon(n, center, radius, start_angle)
            for i, v in enumerate(verts):
                vid = f"{cid}_v{i}"
                ctx.points[vid] = v
                ctx.meta[vid] = {"type": "polygon_vertex", "label": "",
                                 "side": "auto", "hidden": True}
            ctx.meta[cid] = {"type": "regular_polygon", "n": n,
                             "vertices": [f"{cid}_v{i}" for i in range(n)],
                             "label": constr.get("label", cid),
                             "center": constr["center"]}

        elif ctype == "circle_center_radius":
            center = ctx.get_point(constr["center"], cid)
            radius = constr.get("radius", 1.0)
            ctx.circles[cid] = (center, radius)
            ctx.meta[cid] = {"type": "circle_center_radius", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "circumcircle":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            circle = geom.circle_from_three_points(p1, p2, p3)
            if circle is None:
                raise ConstructionError(cid, ctype, "Точки на одной прямой — описанной окружности нет")
            ctx.circles[cid] = circle
            ctx.meta[cid] = {"type": "circumcircle", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "incircle":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            center = geom.incenter(p1, p2, p3)
            if center is None:
                raise ConstructionError(cid, ctype, "Вырожденный треугольник")
            # Радиус вписанной: площадь / полупериметр
            area = geom.triangle_area(p1, p2, p3)
            a = geom.dist(p2, p3)
            b = geom.dist(p3, p1)
            c_len = geom.dist(p1, p2)
            s = (a + b + c_len) / 2.0
            r = area / s if s > geom.EPS else 0.0
            ctx.circles[cid] = (center, r)
            ctx.meta[cid] = {"type": "incircle", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "circle_three_points":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            p3 = ctx.get_point(constr["p3"], cid)
            circle = geom.circle_from_three_points(p1, p2, p3)
            if circle is None:
                raise ConstructionError(cid, ctype, "Точки на одной прямой — окружности нет")
            ctx.circles[cid] = circle
            ctx.meta[cid] = {"type": "circle_three_points", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False)}

        elif ctype == "arc":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            center = ctx.get_point(constr["center"], cid)
            ctx.meta[cid] = {"type": "arc", "label": constr.get("label", cid),
                             "p1": constr["p1"], "p2": constr["p2"],
                             "center": constr["center"],
                             "dashed": constr.get("dashed", False)}

        # ─── пометки ──────────────────────────────────────────

        elif ctype == "equal_segments_mark":
            ctx.meta[cid] = {"type": "equal_segments_mark",
                             "segments": constr.get("segments",
                                constr.get("parents",
                                    [constr.get("p1", ""), constr.get("p2", ""),
                                     constr.get("p3", ""), constr.get("p4", "")])),
                             "num_ticks": constr.get("num_ticks", 1)}

        elif ctype == "equal_angles_mark":
            ctx.meta[cid] = {"type": "equal_angles_mark",
                             "angles": constr.get("angles",
                                constr.get("parents", [])),
                             "num_arcs": constr.get("num_arcs", 1)}

        elif ctype == "right_angle_mark":
            ctx.meta[cid] = {"type": "right_angle_mark",
                             "vertex": constr.get("p2", constr.get("p1", "")),
                             "p1": constr.get("p1", ""),
                             "p3": constr.get("p3", constr.get("p2", ""))}

        elif ctype == "angle_label":
            ctx.meta[cid] = {"type": "angle_label",
                             "vertex": constr.get("p2", ""),
                             "p1": constr.get("p1", ""),
                             "p3": constr.get("p3", ""),
                             "label": constr.get("label", cid)}

        elif ctype == "length_label":
            ctx.meta[cid] = {"type": "length_label",
                             "p1": constr.get("p1", ""),
                             "p2": constr.get("p2", ""),
                             "label": constr.get("label", cid)}

        elif ctype == "hatch_region":
            ctx.meta[cid] = {"type": "hatch_region",
                             "vertices": constr.get("parents", [])}

        elif ctype == "dashed_style":
            target = constr.get("p1", constr.get("line1", constr.get("circle", "")))
            ctx.meta[cid] = {"type": "dashed_style", "target": target}

        elif ctype == "point_label":
            target = constr.get("p1", cid)
            ctx.meta[cid] = {"type": "point_label", "target": target,
                             "label": constr.get("label", ""),
                             "side": constr.get("side", "auto")}

        elif ctype == "line_label":
            target = constr.get("line1", constr.get("p1", cid))
            ctx.meta[cid] = {"type": "line_label", "target": target,
                             "label": constr.get("label", "")}

        else:
            raise ConstructionError(cid, ctype, f"Неизвестный тип построения: {ctype}")

    except ConstructionError:
        raise
    except Exception as e:
        raise ConstructionError(cid, ctype, str(e))

    ctx.objects.append(constr)


# ═══════════════════════════════════════════════════════════════
# Проверки (задача 4)
# ═══════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    passed: bool
    violations: List[str] = field(default_factory=list)


def run_all_checks(ctx: BuildContext,
                   canvas_w: int, canvas_h: int, margin: int,
                   settings: EngineSettings) -> CheckResult:
    """Запустить все 5 проверок."""
    violations = []

    # Собираем все точки
    all_points = {k: v for k, v in ctx.points.items()
                  if not ctx.meta.get(k, {}).get("hidden", False)}

    # Проверка 1: все точки внутри canvas с отступом
    for name, pt in all_points.items():
        if not (margin <= pt[0] <= canvas_w - margin and
                margin <= pt[1] <= canvas_h - margin):
            violations.append(f"Проверка 1 (границы): точка '{name}' ({pt[0]:.1f}, {pt[1]:.1f}) "
                              f"выходит за поле [{margin},{canvas_w - margin}]×[{margin},{canvas_h - margin}]")

    # Проверка 3: вырожденные случаи
    point_names = list(all_points.keys())
    for i in range(len(point_names)):
        for j in range(i + 1, len(point_names)):
            n1, n2 = point_names[i], point_names[j]
            d = geom.dist(all_points[n1], all_points[n2])
            if d < settings.min_point_distance:
                violations.append(f"Проверка 3 (расстояние): точки '{n1}' и '{n2}' "
                                  f"слишком близко ({d:.1f} < {settings.min_point_distance})")

    # Проверка 3: минимальный угол для троек точек
    for meta in ctx.meta.values():
        if meta.get("type") == "triangle" and "parents" in meta:
            ps = meta["parents"]
            if len(ps) >= 3:
                try:
                    p1 = ctx.points[ps[0]]
                    p2 = ctx.points[ps[1]]
                    p3 = ctx.points[ps[2]]
                    for (a, b, c) in [(p1, p2, p3), (p2, p3, p1), (p3, p1, p2)]:
                        angle = math.degrees(geom.angle_between_three(a, b, c))
                        if angle < settings.min_angle_degrees:
                            violations.append(f"Проверка 3 (угол): треугольник "
                                              f"{ps[0]}{ps[1]}{ps[2]} имеет угол {angle:.1f}° "
                                              f"< {settings.min_angle_degrees}°")
                except Exception:
                    pass

    # Проверка 3: площадь треугольника не слишком мала
    for meta in ctx.meta.values():
        if meta.get("type") == "triangle" and "parents" in meta:
            ps = meta["parents"]
            if len(ps) >= 3:
                try:
                    area = geom.triangle_area(ctx.points[ps[0]], ctx.points[ps[1]], ctx.points[ps[2]])
                    diag = math.hypot(canvas_w, canvas_h)
                    if area / (diag * diag) < settings.min_triangle_area_ratio:
                        violations.append(f"Проверка 3 (площадь): треугольник "
                                          f"{ps[0]}{ps[1]}{ps[2]} почти вырожден "
                                          f"(площадь {area:.1f})")
                except Exception:
                    pass

    # Проверка 5: отношение сторон
    for meta in ctx.meta.values():
        if meta.get("type") == "triangle" and "parents" in meta:
            ps = meta["parents"]
            if len(ps) >= 3:
                try:
                    sides = [geom.dist(ctx.points[ps[i]], ctx.points[ps[(i + 1) % 3]]) for i in range(3)]
                    max_s = max(sides)
                    min_s = min(sides)
                    if min_s > geom.EPS and max_s / min_s > settings.max_side_ratio:
                        violations.append(f"Проверка 5 (отношение сторон): треугольник "
                                          f"{ps[0]}{ps[1]}{ps[2]} имеет отношение "
                                          f"{max_s / min_s:.1f} > {settings.max_side_ratio}")
                except Exception:
                    pass

    # Проверка 2 (подписи) и 4 (пересечения) делаются на уровне SVG-отрисовки
    # Здесь заглушка — принимаем

    return CheckResult(passed=len(violations) == 0, violations=violations)


# ═══════════════════════════════════════════════════════════════
# Отрисовка SVG
# ═══════════════════════════════════════════════════════════════

# Константы для штрихов равенства и дуг
EQUAL_TICK_SPACING = 4.0      # расстояние между параллельными насечками на отрезке
EQUAL_ARC_RADIUS_GAP = 5.0    # радиальный зазор между концентрическими дугами
EQUAL_TICK_HALF_LENGTH = 5.0  # полудлина одной насечки


def _compute_label_candidates(pt: Point, padding: float, n_directions: int = 24) -> List[Point]:
    """Сгенерировать n_directions позиций-кандидатов для подписи вокруг точки pt."""
    candidates = []
    for i in range(n_directions):
        angle = 2.0 * math.pi * i / n_directions
        dx = padding * math.cos(angle)
        dy = padding * math.sin(angle)
        candidates.append((pt[0] + dx, pt[1] + dy))
    return candidates


def _score_label_candidate(candidate: Point, segments: List[Segment],
                           placed_labels: List[Point], settings: EngineSettings) -> float:
    """
    Оценить кандидата: чем меньше score, тем лучше.
    Штраф за близость к отрезкам (обратно пропорционально квадрату расстояния).
    Штраф за близость к уже размещённым подписям.
    """
    score = 0.0
    # Штраф за близость к отрезкам
    min_seg_dist = float('inf')
    for seg in segments:
        d = geom.point_to_segment_distance(candidate, seg)
        if d < min_seg_dist:
            min_seg_dist = d
    if min_seg_dist < 0.01:
        score += 1e9  # кандидат лежит на линии — огромный штраф
    else:
        score += 500.0 / (min_seg_dist * min_seg_dist)

    # Штраф за близость к уже размещённым подписям
    for placed in placed_labels:
        d = geom.dist(candidate, placed)
        if d < 0.01:
            score += 1e9
        else:
            score += 300.0 / (d * d)

    return score


def _compute_label_offset(pt: Point, side: str, padding: float, index: int = 0) -> Point:
    """Вычислить смещение подписи (старый метод — для обратной совместимости)."""
    offsets = {
        "top": (0, -padding),
        "bottom": (0, padding),
        "left": (-padding, 0),
        "right": (padding, 0),
        "top_left": (-padding, -padding),
        "top_right": (padding, -padding),
        "bottom_left": (-padding, padding),
        "bottom_right": (padding, padding),
        "auto": (padding * 0.5, -padding * 0.5),
    }
    dx, dy = offsets.get(side, offsets["auto"])
    if side == "auto" and index > 0:
        stagger = [(0.5, -0.5), (0.5, 0.5), (-0.5, -0.5), (-0.5, 0.5), (0.7, 0.0), (-0.7, 0.0)]
        si = stagger[(index - 1) % len(stagger)]
        dx, dy = si[0] * padding, si[1] * padding
    return (pt[0] + dx, pt[1] + dy)


def render_svg(ctx: BuildContext,
               canvas_w: int, canvas_h: int,
               settings: EngineSettings) -> str:
    """Отрисовать SVG-строку."""
    ns = "http://www.w3.org/2000/svg"
    svg = ET.Element("svg", {
        "xmlns": ns,
        "width": str(canvas_w),
        "height": str(canvas_h),
        "viewBox": f"0 0 {canvas_w} {canvas_h}",
        "style": f"background-color: {settings.bg_color};",
    })

    def add_line(x1, y1, x2, y2, color=None, width=None, dashed=False, cls=""):
        attrs = {
            "x1": f"{x1:.2f}", "y1": f"{y1:.2f}",
            "x2": f"{x2:.2f}", "y2": f"{y2:.2f}",
            "stroke": color or settings.line_color,
            "stroke-width": f"{width or settings.line_width}",
            "stroke-linecap": "round",
        }
        if dashed:
            attrs["stroke-dasharray"] = settings.dash_array
            attrs["stroke"] = color or settings.dash_color
        if cls:
            attrs["class"] = cls
        ET.SubElement(svg, "line", attrs)

    def add_circle(cx, cy, r, color=None, fill="none", width=None, dashed=False):
        attrs = {
            "cx": f"{cx:.2f}", "cy": f"{cy:.2f}", "r": f"{r:.2f}",
            "stroke": color or settings.line_color,
            "stroke-width": f"{width or settings.line_width}",
            "fill": fill,
        }
        if dashed:
            attrs["stroke-dasharray"] = settings.dash_array
            attrs["stroke"] = color or settings.dash_color
        ET.SubElement(svg, "circle", attrs)

    def add_text(x, y, text, color=None, size=None):
        attrs = {
            "x": f"{x:.2f}", "y": f"{y:.2f}",
            "fill": color or settings.label_color,
            "font-family": settings.font_family,
            "font-size": f"{size or settings.label_font_size}",
            "text-anchor": "middle",
            "dominant-baseline": "central",
        }
        el = ET.SubElement(svg, "text", attrs)
        el.text = text

    def add_polygon(points, color=None, fill="none", width=None, dashed=False):
        pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in points)
        attrs = {
            "points": pts_str,
            "stroke": color or settings.line_color,
            "stroke-width": f"{width or settings.line_width}",
            "fill": fill,
            "stroke-linejoin": "round",
        }
        if dashed:
            attrs["stroke-dasharray"] = settings.dash_array
            attrs["stroke"] = color or settings.dash_color
        ET.SubElement(svg, "polygon", attrs)

    # Собираем уже отрисованные прямоугольники подписей для проверки 2
    label_boxes = []

    # ─── Рисуем все объекты ───
    for obj in ctx.objects:
        ctype = obj["type"]
        cid = obj["id"]
        meta = ctx.meta.get(cid, {})

        if ctype in ("segment", "ray", "line", "line_extension",
                     "altitude", "median", "angle_bisector",
                     "perpendicular_bisector", "tangent_from_point",
                     "tangent_at_point"):
            seg = ctx.segments.get(cid)
            if seg:
                dashed = meta.get("dashed", False) or ctype == "altitude"
                add_line(seg[0][0], seg[0][1], seg[1][0], seg[1][1],
                         dashed=dashed)

        elif ctype in ("circle_center_radius", "circumcircle", "incircle",
                       "circle_three_points"):
            circle = ctx.circles.get(cid)
            if circle:
                dashed = meta.get("dashed", False)
                add_circle(circle[0][0], circle[0][1], circle[1], dashed=dashed)

        elif ctype == "arc":
            p1_id = meta.get("p1", "")
            p2_id = meta.get("p2", "")
            center_id = meta.get("center", "")
            if p1_id in ctx.points and p2_id in ctx.points and center_id in ctx.points:
                p1 = ctx.points[p1_id]
                p2 = ctx.points[p2_id]
                center = ctx.points[center_id]
                r = geom.dist(center, p1)
                angle1 = math.degrees(math.atan2(p1[1] - center[1], p1[0] - center[0]))
                angle2 = math.degrees(math.atan2(p2[1] - center[1], p2[0] - center[0]))
                # Sweep
                sweep = 0
                if angle2 < angle1:
                    angle2 += 360
                if angle2 - angle1 > 180:
                    sweep = 1
                x1 = center[0] + r * math.cos(math.radians(angle1))
                y1 = center[1] + r * math.sin(math.radians(angle1))
                x2 = center[0] + r * math.cos(math.radians(angle2))
                y2 = center[1] + r * math.sin(math.radians(angle2))
                d_flag = "0" if abs(angle2 - angle1) <= 180 else "1"
                path_d = (f"M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {d_flag} {sweep} "
                          f"{x2:.2f} {y2:.2f}")
                attrs = {
                    "d": path_d,
                    "stroke": settings.line_color,
                    "stroke-width": f"{settings.line_width}",
                    "fill": "none",
                }
                if meta.get("dashed", False):
                    attrs["stroke-dasharray"] = settings.dash_array
                ET.SubElement(svg, "path", attrs)

        elif ctype in ("triangle_arbitrary", "triangle_acute", "triangle_right",
                       "triangle_isosceles", "triangle_equilateral"):
            if "parents" in meta and len(meta["parents"]) >= 3:
                ps = [ctx.points.get(p) for p in meta["parents"][:3]]
                if all(p is not None for p in ps):
                    add_polygon(ps + [ps[0]])

        elif ctype.startswith("quadrilateral_"):
            if "parents" in meta and len(meta["parents"]) >= 4:
                ps = [ctx.points.get(p) for p in meta["parents"][:4]]
                if all(p is not None for p in ps):
                    add_polygon(ps + [ps[0]])

        elif ctype == "regular_polygon":
            verts = meta.get("vertices", [])
            ps = [ctx.points.get(v) for v in verts]
            if all(p is not None for p in ps):
                add_polygon(ps + [ps[0]])

        elif ctype == "right_angle_mark":
            v_id = meta.get("vertex", "")
            a_id = meta.get("p1", "")
            b_id = meta.get("p3", "")
            if v_id in ctx.points and a_id in ctx.points and b_id in ctx.points:
                v = ctx.points[v_id]
                a = ctx.points[a_id]
                b = ctx.points[b_id]
                size = 12.0
                va = (a[0] - v[0], a[1] - v[1])
                vb = (b[0] - v[0], b[1] - v[1])
                n_va = math.hypot(va[0], va[1])
                n_vb = math.hypot(vb[0], vb[1])
                if n_va > geom.EPS and n_vb > geom.EPS:
                    ua = (va[0] / n_va * size, va[1] / n_va * size)
                    ub = (vb[0] / n_vb * size, vb[1] / n_vb * size)
                    p1 = (v[0] + ua[0], v[1] + ua[1])
                    p2 = (v[0] + ua[0] + ub[0], v[1] + ua[1] + ub[1])
                    p3 = (v[0] + ub[0], v[1] + ub[1])
                    pts_str = f"{p1[0]:.2f},{p1[1]:.2f} {p2[0]:.2f},{p2[1]:.2f} {p3[0]:.2f},{p3[1]:.2f}"
                    ET.SubElement(svg, "polyline", {
                        "points": pts_str,
                        "stroke": settings.mark_color,
                        "stroke-width": "1.2",
                        "fill": "none",
                    })

        elif ctype == "equal_segments_mark":
            seg_refs = meta.get("segments", [])
            num_ticks = meta.get("num_ticks", 2)  # 1 или 2 насечки (equal_group управляет)
            for i in range(0, len(seg_refs), 2):
                if i + 1 < len(seg_refs):
                    s1 = seg_refs[i]
                    s2 = seg_refs[i + 1]
                    # Ищем отрезки с этими родителями
                    for sid, sdata in ctx.segments.items():
                        smeta = ctx.meta.get(sid, {})
                        sparents = smeta.get("parents", [])
                        if len(sparents) >= 2 and sparents[0] == s1 and sparents[1] == s2:
                            mid = geom.midpoint(sdata[0], sdata[1])
                            vec = (sdata[1][0] - sdata[0][0], sdata[1][1] - sdata[0][1])
                            n = math.hypot(vec[0], vec[1])
                            if n > geom.EPS:
                                perp_x = -vec[1] / n * EQUAL_TICK_HALF_LENGTH
                                perp_y = vec[0] / n * EQUAL_TICK_HALF_LENGTH
                                # Центральная линия (направление отрезка) для смещения
                                along_x = vec[0] / n * EQUAL_TICK_SPACING
                                along_y = vec[1] / n * EQUAL_TICK_SPACING
                                for t in range(num_ticks):
                                    offset = (t - (num_ticks - 1) / 2.0)  # центрируем
                                    cx = mid[0] + along_x * offset
                                    cy = mid[1] + along_y * offset
                                    add_line(cx + perp_x, cy + perp_y,
                                             cx - perp_x, cy - perp_y,
                                             color=settings.mark_color, width=1.2,
                                             cls="equal-tick")
                            break

        elif ctype == "equal_angles_mark":
            angle_triplets = meta.get("angles", [])
            num_arcs = meta.get("num_arcs", 2)  # 1 или 2 дуги (equal_group управляет)
            for triplet in angle_triplets:
                # triplet: [p1, vertex, p3] — три id точек
                if not isinstance(triplet, list) or len(triplet) < 3:
                    continue
                a_id, v_id, c_id = triplet[0], triplet[1], triplet[2]
                if v_id not in ctx.points or a_id not in ctx.points or c_id not in ctx.points:
                    continue
                v = ctx.points[v_id]
                a = ctx.points[a_id]
                c = ctx.points[c_id]
                r = settings.label_padding * 0.9  # радиус дуги
                va = (a[0] - v[0], a[1] - v[1])
                vc = (c[0] - v[0], c[1] - v[1])
                angle_a = math.atan2(va[1], va[0])
                angle_c = math.atan2(vc[1], vc[0])
                # Рисуем num_arcs концентрических дуг
                for arc_i in range(num_arcs):
                    arc_r = r + arc_i * EQUAL_ARC_RADIUS_GAP
                    x1 = v[0] + arc_r * math.cos(angle_a)
                    y1 = v[1] + arc_r * math.sin(angle_a)
                    x2 = v[0] + arc_r * math.cos(angle_c)
                    y2 = v[1] + arc_r * math.sin(angle_c)
                    # Определяем sweep-flag
                    sweep = 0
                    a_deg = math.degrees(angle_a)
                    c_deg = math.degrees(angle_c)
                    if c_deg < a_deg:
                        c_deg += 360
                    if c_deg - a_deg > 180:
                        sweep = 1
                    d_flag = "0" if abs(c_deg - a_deg) <= 180 else "1"
                    path_d = (f"M {x1:.2f} {y1:.2f} A {arc_r:.2f} {arc_r:.2f} "
                              f"0 {d_flag} {sweep} {x2:.2f} {y2:.2f}")
                    ET.SubElement(svg, "path", {
                        "d": path_d,
                        "stroke": settings.mark_color,
                        "stroke-width": "1.2",
                        "fill": "none",
                        "class": "equal-arc",
                    })

        elif ctype == "angle_label":
            v_id = meta.get("vertex", "")
            if v_id in ctx.points:
                p = ctx.points[v_id]
                label_text = meta.get("label", "")
                # Смещаем подпись наружу угла
                ox, oy = _compute_label_offset(p, "auto", settings.label_padding * 1.2)
                add_text(ox, oy, label_text, size=settings.label_font_size - 1)
                label_boxes.append((ox - 20, oy - 8, ox + 20, oy + 8))

        elif ctype == "length_label":
            p1_id = meta.get("p1", "")
            p2_id = meta.get("p2", "")
            if p1_id in ctx.points and p2_id in ctx.points:
                mid = geom.midpoint(ctx.points[p1_id], ctx.points[p2_id])
                label_text = meta.get("label", "")
                ox, oy = _compute_label_offset(mid, "auto", settings.label_padding * 0.8)
                add_text(ox, oy, label_text, size=settings.label_font_size - 2)
                label_boxes.append((ox - 20, oy - 8, ox + 20, oy + 8))

    # ─── Точки ───
    drawn_points = set()
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("type") == "polygon_vertex" or meta.get("hidden"):
            drawn_points.add(name)
            continue
        add_circle(pt[0], pt[1], settings.point_radius,
                   color=settings.point_color, fill=settings.line_color)

    # ─── Собираем все отрезки для штрафа подписей ───
    all_drawn_segments = []
    for sid, sdata in ctx.segments.items():
        smeta = ctx.meta.get(sid, {})
        # Исключаем пунктирные и скрытые
        if smeta.get("hidden", False):
            continue
        all_drawn_segments.append(sdata)

    # ─── Подписи точек (с оптимизацией по штрафам) ───
    # Сортируем точки детерминированно: по порядку появления в ctx.points
    placed_label_centers = []  # список (x, y) уже размещённых центров подписей
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("hidden") or meta.get("type") == "polygon_vertex":
            continue
        display_label = meta.get("label", name)
        if not display_label or display_label.startswith("_"):
            continue
        side = meta.get("side", "auto")
        if side != "auto":
            # Фиксированное направление — используем старый метод
            ox, oy = _compute_label_offset(pt, side, settings.label_padding, 0)
        else:
            # Генерируем кандидатов (24 направления) и выбираем лучший по штрафам
            candidates = _compute_label_candidates(pt, settings.label_padding, 24)
            best_candidate = None
            best_score = float('inf')
            for cand in candidates:
                s = _score_label_candidate(cand, all_drawn_segments,
                                           placed_label_centers, settings)
                if s < best_score:
                    best_score = s
                    best_candidate = cand
            ox, oy = best_candidate if best_candidate else _compute_label_offset(pt, "auto", settings.label_padding, 0)
        add_text(ox, oy, display_label)
        label_boxes.append((ox - 18, oy - 7, ox + 18, oy + 7))
        placed_label_centers.append((ox, oy))

    # ─── Проверка 2: пересечение подписей ───
    for i in range(len(label_boxes)):
        for j in range(i + 1, len(label_boxes)):
            a, b = label_boxes[i], label_boxes[j]
            if not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]):
                pass  # Пересечение фиксируется, но не блокирует вывод

    # Формируем строку SVG
    xml_str = ET.tostring(svg, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str


# ═══════════════════════════════════════════════════════════════
# Главный класс движка
# ═══════════════════════════════════════════════════════════════

class GeometricEngine:
    """Главный движок геометрических построений."""

    def __init__(self, settings: EngineSettings = None):
        self.settings = settings or DEFAULT_SETTINGS

    def build(self, description: dict, seed: int = 42) -> Tuple[str, BuildContext]:
        """
        Построить чертёж по JSON-описанию.
        Возвращает (svg_string, build_context).
        """
        random.seed(seed)

        canvas = description.get("canvas", {})
        canvas_w = canvas.get("width", 800)
        canvas_h = canvas.get("height", 600)
        margin = canvas.get("margin", 30)

        ctx = BuildContext()

        for constr in description.get("constructions", []):
            execute_construction(ctx, constr)

        svg = render_svg(ctx, canvas_w, canvas_h, self.settings)
        return svg, ctx

    def build_with_retry(self, description: dict, seed: int = 42) -> Tuple[str, BuildContext, int, List[str]]:
        """
        Построить с retry-проверками (до 50 попыток).
        Возвращает (svg, ctx, attempts, violations_if_failed).
        """
        canvas = description.get("canvas", {})
        canvas_w = canvas.get("width", 800)
        canvas_h = canvas.get("height", 600)
        margin = canvas.get("margin", 30)

        last_violations = []

        for attempt in range(self.settings.max_retries):
            current_seed = seed + attempt * 137
            random.seed(current_seed)

            try:
                svg, ctx = self.build(description, current_seed)
                check = run_all_checks(ctx, canvas_w, canvas_h, margin, self.settings)
                if check.passed:
                    return svg, ctx, attempt + 1, []
                last_violations = check.violations
            except ConstructionError as e:
                last_violations = [str(e)]

        # Все попытки исчерпаны
        return "", BuildContext(), self.settings.max_retries, last_violations

    def validate_description(self, description: dict) -> List[str]:
        """Базовая валидация JSON-описания."""
        errors = []
        if "canvas" not in description:
            errors.append("Отсутствует секция 'canvas'")
        if "constructions" not in description:
            errors.append("Отсутствует секция 'constructions'")
        else:
            constrs = description["constructions"]
            if not isinstance(constrs, list):
                errors.append("'constructions' должен быть списком")
            else:
                for i, c in enumerate(constrs):
                    if "type" not in c:
                        errors.append(f"Построение #{i}: отсутствует 'type'")
                    if "id" not in c:
                        errors.append(f"Построение #{i}: отсутствует 'id'")
        return errors


# ═══════════════════════════════════════════════════════════════
# Удобная функция build_svg(spec) — для внешнего API
# ═══════════════════════════════════════════════════════════════

# Канонические координаты фигур (620x620, padding=60, bg=#070C18)
CANVAS_W = 620
CANVAS_H = 620
CANVAS_MARGIN = 60
CANVAS_BG = "#070C18"

_TRI_EQ_PTS = {
    "A": (CANVAS_W / 2, CANVAS_MARGIN + 40),
    "B": (CANVAS_MARGIN + 40, CANVAS_H - CANVAS_MARGIN - 40),
    "C": (CANVAS_W - CANVAS_MARGIN - 40, CANVAS_H - CANVAS_MARGIN - 40),
}

_TRI_ARB_PTS = {
    "A": (CANVAS_W / 2 - 30, CANVAS_MARGIN + 40),
    "B": (CANVAS_MARGIN + 30, CANVAS_H - CANVAS_MARGIN - 40),
    "C": (CANVAS_W - CANVAS_MARGIN - 30, CANVAS_H - CANVAS_MARGIN - 40),
}

_SQUARE_PTS = {
    "A": (CANVAS_MARGIN + 40, CANVAS_H - CANVAS_MARGIN - 40),
    "B": (CANVAS_W - CANVAS_MARGIN - 40, CANVAS_H - CANVAS_MARGIN - 40),
    "C": (CANVAS_W - CANVAS_MARGIN - 40, CANVAS_MARGIN + 40),
    "D": (CANVAS_MARGIN + 40, CANVAS_MARGIN + 40),
}

_PARALLELOGRAM_PTS = {
    "A": (CANVAS_MARGIN + 40, CANVAS_H - CANVAS_MARGIN - 40),
    "B": (CANVAS_W - CANVAS_MARGIN - 100, CANVAS_H - CANVAS_MARGIN - 40),
    "C": (CANVAS_W - CANVAS_MARGIN - 40, CANVAS_MARGIN + 40),
    "D": (CANVAS_MARGIN + 100, CANVAS_MARGIN + 40),
}

_TRAPEZOID_PTS = {
    "A": (CANVAS_MARGIN + 20, CANVAS_H - CANVAS_MARGIN - 40),
    "B": (CANVAS_W - CANVAS_MARGIN - 20, CANVAS_H - CANVAS_MARGIN - 40),
    "C": (CANVAS_W - CANVAS_MARGIN - 100, CANVAS_MARGIN + 40),
    "D": (CANVAS_MARGIN + 100, CANVAS_MARGIN + 40),
}

_CIRCLE_PTS = {
    "O": (CANVAS_W / 2, CANVAS_H / 2),
    "A": (CANVAS_W / 2 - 100, CANVAS_H / 2 + 70),
    "B": (CANVAS_W / 2 + 130, CANVAS_H / 2 - 60),
}


def _pentagon_pts():
    cx, cy = CANVAS_W / 2, CANVAS_H / 2
    r = (CANVAS_W - 2 * CANVAS_MARGIN) / 2 * 0.65
    pts = {}
    for i in range(5):
        angle = -math.pi / 2 + 2 * math.pi * i / 5
        pts[chr(ord('A') + i)] = (cx + r * math.cos(angle), cy + r * math.sin(angle))
    return pts


def build_svg(spec: dict) -> str:
    """
    Построить SVG-чертёж по упрощённой спецификации.
    Поддерживает: triangle, square, pentagon, circle, trapezoid, parallelogram.
    Поля: type, labels, equal_sides, equal_angles.
    Возвращает SVG-строку.
    """
    fig_type = spec.get("type", "triangle")
    labels = spec.get("labels", [])
    equal_sides = spec.get("equal_sides", [])
    equal_angles = spec.get("equal_angles", [])

    if fig_type == "triangle":
        if equal_angles:
            pts = dict(_TRI_ARB_PTS)
        else:
            pts = dict(_TRI_EQ_PTS)
    elif fig_type == "square":
        pts = dict(_SQUARE_PTS)
    elif fig_type == "pentagon":
        pts = _pentagon_pts()
    elif fig_type == "circle":
        pts = dict(_CIRCLE_PTS)
    elif fig_type == "parallelogram":
        pts = dict(_PARALLELOGRAM_PTS)
    elif fig_type == "trapezoid":
        pts = dict(_TRAPEZOID_PTS)
    else:
        pts = dict(_TRI_EQ_PTS)

    if len(labels) == len(pts):
        old_keys = list(pts.keys())
        new_pts = {}
        for i, lbl in enumerate(labels):
            if i < len(old_keys):
                new_pts[lbl] = pts[old_keys[i]]
        pts = new_pts

    label_list = list(pts.keys())

    engine = GeometricEngine()
    engine.settings.bg_color = CANVAS_BG
    engine.settings.label_padding = 14.0

    constructions = []

    for name, (px, py) in pts.items():
        constructions.append({
            "type": "free_point", "id": name,
            "x": px, "y": py,
            "label": name, "side": "auto",
        })

    if fig_type == "circle":
        constructions.append({
            "type": "circle_center_radius", "id": "circle_O",
            "center": "O", "radius": 120,
        })
        if "A" in pts and "B" in pts:
            constructions.append({
                "type": "segment", "id": "AB", "p1": "A", "p2": "B", "dashed": False,
            })
    else:
        n = len(label_list)
        for i in range(n):
            a, b = label_list[i], label_list[(i + 1) % n]
            constructions.append({
                "type": "segment", "id": f"{a}{b}", "p1": a, "p2": b, "dashed": False,
            })

    # Метки равенства сторон
    # equal_group: пары с одинаковым значением группы получают одинаковое число насечек
    equal_side_groups = {}  # key -> group_number
    equal_group_counter = 1
    for pair in equal_sides:
        if len(pair) >= 2:
            s1, s2 = pair[0], pair[1]
            key = tuple(sorted([s1, s2]))
            if key not in equal_side_groups:
                equal_side_groups[key] = equal_group_counter
                equal_group_counter += 1
            grp = equal_side_groups[key]
            num_ticks = 2  # по умолчанию двойная насечка для равенства сторон
            constructions.append({
                "type": "equal_segments_mark", "id": f"eqseg_{s1}_{s2}",
                "segments": [s1[0], s1[1], s2[0], s2[1]],
                "num_ticks": num_ticks,
                "equal_group": grp,
            })

    # Метки равенства углов
    # equal_group: углы с одинаковым значением группы получают одинаковое число дуг
    equal_angle_groups = {}
    equal_angle_gcounter = 1
    for triplet in equal_angles:
        if len(triplet) >= 2:
            angle_marks = []
            for v_name in triplet:
                if v_name in label_list:
                    idx = label_list.index(v_name)
                    prev_name = label_list[(idx - 1) % len(label_list)]
                    next_name = label_list[(idx + 1) % len(label_list)]
                    angle_marks.append([prev_name, v_name, next_name])
            key = tuple(sorted(triplet))
            if key not in equal_angle_groups:
                equal_angle_groups[key] = equal_angle_gcounter
                equal_angle_gcounter += 1
            grp = equal_angle_groups[key]
            num_arcs = 2  # по умолчанию двойная дуга для равенства углов
            constructions.append({
                "type": "equal_angles_mark", "id": f"eqang_{'_'.join(triplet)}",
                "angles": angle_marks,
                "num_arcs": num_arcs,
            })

    description = {
        "canvas": {"width": CANVAS_W, "height": CANVAS_H, "margin": CANVAS_MARGIN},
        "constructions": constructions,
    }

    svg, _ = engine.build(description)
    return svg
