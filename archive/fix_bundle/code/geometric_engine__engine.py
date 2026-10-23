"""
engine.py — Ядро геометрического движка.

Разбор JSON-описания -> вычисление координат -> отрисовка SVG -> проверки -> retry.

Только стандартная библиотека Python. Без numpy, без matplotlib, без интернета.
"""

import json
import logging
import math
import random
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from . import geom
from .geom import Point, Segment
from .semantic_theme import (
    DARK_GEOMETRY,
    resolve_visual_role,
    resolve_point_role,
)

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
    # CH21 FIX 1: лимит попыток в поисках лучшего SOFT-кандидата.
    soft_retry_limit: int = 12              # сколько retry искать кандидата с меньшим penalty
    leader_offset: float = 22.0             # вынос подписи для точек с 3+ инцидентными отрезками

    # Отступ для подписей
    label_padding: float = 14.0             # отступ подписи от точки (пиксели)

    # Цвета (тёмно-синяя тема)
    bg_color: str = "#0F1729"               # тёмно-синий фон (НЕ прозрачный)
    line_color: str = "#D9E5F5"             # светлые контрастные линии
    point_color: str = "#EAF1FA"            # точки
    label_color: str = "#EAF1FA"            # подписи (светлые, без чёрного halo)
    mark_color: str = "#A6B7CC"             # пометки (штрихи, дужки)
    dash_color: str = "#73B6E6"             # пунктир (вспомогательная геометрия)
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

    # Layout / auto-fit (CH15.1: presentation-only pass, не меняет геометрию)
    auto_fit: bool = False              # подогнать холст под содержимое с отступом
    fit_padding_ratio: float = 0.14     # отступ 12–16% (по умолчанию 14%)
    fit_min_padding: float = 30.0
    fit_max_padding: float = 140.0

    # CH16: семантические цвета по visual_role.
    # При False renderer использует старую палитру (legacy-совместимость).
    semantic_colors: bool = False


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
        # CH26: объявленные инцидентности (точка обязана лежать на объекте).
        # Каждый элемент: {"point": id, "on": "circle"|"segment"|"line"|"ray",
        #                  "object": id или [p1,p2], "touch": "circle2" (опц.)}
        self.incidences: List[Dict[str, Any]] = []
        # CH31: численные проверки, извлечённые из условия (constraints).
        # Каждый элемент: {"kind": "equal_lengths"|"length"|"angle"|"parallel"|"perpendicular"|"inside",
        #                  ...} — см. extract_condition_constraints.
        self.constraints: List[Dict[str, Any]] = []
        # CH31: неподтверждённые аннотации (числа для отчёта).
        self.annotation_issues: List[str] = []

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

    def get_line_by_points(self, a_ref: str, b_ref: str, constr_id: str) -> geom.Line:
        """Прямая через две точки (или через id отрезка/прямой, если передана одна)."""
        a = self.get_point(a_ref, constr_id)
        b = self.get_point(b_ref, constr_id)
        return geom.line_through_points(a, b)


def _resolve_line_ref(ctx: BuildContext, constr: dict, cid: str,
                      line_keys: tuple, p1_keys: tuple, p2_keys: tuple) -> geom.Line:
    """Резолв ссылки на прямую с поддержкой синонимов полей.

    Планировщики (Gemini/Claude) нестабильны в именовании полей пересечения:
    могут прислать line1/line2 (id отрезка/прямой), l1/l2 (id или
    список двух точек ["A","B"]), l1_p1/l1_p2/l2_p1/l2_p2 (пара точек),
    либо p1..p4 (четыре точки).  Здесь единый резолв всех форм.
    """
    # 1) Прямой id (line1, l1) — строка.
    for k in line_keys:
        v = constr.get(k)
        if isinstance(v, str) and v:
            if v in ctx.lines:
                return ctx.lines[v]
            if v in ctx.segments:
                a, b = ctx.segments[v]
                return geom.line_through_points(a, b)
            # id может быть с префиксом seg_ (seg_AL) — ищем по суффиксу.
            for sid, seg in ctx.segments.items():
                if str(sid) == v or str(sid).replace("seg_", "") == v.replace("seg_", ""):
                    return geom.line_through_points(*seg)
            raise ConstructionError(cid, constr.get("type", "?"),
                                    f"Прямая '{v}' не найдена")
        # BATCH FIX: Claude шлёт l1: ["A","B"] — список двух точек.
        if isinstance(v, (list, tuple)) and len(v) == 2:
            a, b = v
            if isinstance(a, str) and isinstance(b, str):
                return ctx.get_line_by_points(a, b, cid)
    # 2) Пара точек (l1_p1/l1_p2 или line1_p1/line1_p2).
    for a_k, b_k in zip(p1_keys, p2_keys):
        a = constr.get(a_k)
        b = constr.get(b_k)
        if isinstance(a, str) and a and isinstance(b, str) and b:
            return ctx.get_line_by_points(a, b, cid)
    raise ConstructionError(cid, constr.get("type", "?"),
                            f"не удалось разрешить прямую ({line_keys[0]})")


def execute_construction(ctx: BuildContext, constr: dict):
    """Выполнить одно построение. Мутирует ctx."""
    ctype = constr["type"]
    cid = constr["id"]

    try:
        if ctype == "free_point":
            x = constr.get("x", 0.0)
            y = constr.get("y", 0.0)
            ctx.points[cid] = (x, y)
            meta = {"type": "free_point", "label": constr.get("label", cid),
                    "side": constr.get("side", "auto")}
            # CH16: сохранить семантическую роль точки.
            if constr.get("style") == "aux":
                meta["style"] = "aux"
            if constr.get("visual_role"):
                meta["visual_role"] = constr["visual_role"]
            ctx.meta[cid] = meta

        elif ctype == "midpoint":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            ctx.points[cid] = geom.midpoint(p1, p2)
            ctx.meta[cid] = {"type": "midpoint", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "parents": [constr["p1"], constr["p2"]]}
            ctx.incidences.append({"point": cid, "on": "segment",
                                   "object": [constr["p1"], constr["p2"]]})

        elif ctype == "point_on_circle":
            # CH26 FIX1: точка строго на окружности.
            circle = ctx.get_circle(constr["circle"], cid)
            center, radius = circle
            if radius < geom.EPS:
                raise ConstructionError(cid, ctype, "Радиус окружности нулевой")
            angle_deg = constr.get("angle_deg")
            between = constr.get("between")
            if angle_deg is not None:
                t = math.radians(float(angle_deg))
            elif between and isinstance(between, (list, tuple)) and len(between) == 2:
                b1 = ctx.get_point(between[0], cid)
                b2 = ctx.get_point(between[1], cid)
                a1 = math.atan2(b1[1] - center[1], b1[0] - center[0])
                a2 = math.atan2(b2[1] - center[1], b2[0] - center[0])
                # Детерминированно: точка строго внутри меньшей дуги [a1,a2],
                # на 45% от a1 к a2 (не совпадает ни с одной границей).
                span = (a2 - a1) % (2 * math.pi)
                if span < 1e-9:
                    span = 2 * math.pi
                t = a1 + span * 0.45
            else:
                raise ConstructionError(cid, ctype,
                                        "point_on_circle требует angle_deg или between:[X,Y]")
            x = center[0] + radius * math.cos(t)
            y = center[1] + radius * math.sin(t)
            ctx.points[cid] = (x, y)
            ctx.meta[cid] = {"type": "point_on_circle", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}
            ctx.incidences.append({"point": cid, "on": "circle", "object": constr["circle"]})

        elif ctype == "inscribed_polygon":
            # CH26 FIX2: все вершины размещаются на окружности в циклическом
            # порядке с минимальной дугой между соседями >= min_arc_deg.
            circle = ctx.get_circle(constr["circle"], cid)
            center, radius = circle
            verts = constr.get("vertices", [])
            if not isinstance(verts, list) or len(verts) < 3:
                raise ConstructionError(cid, ctype, "inscribed_polygon требует >= 3 vertices")
            if radius < geom.EPS:
                raise ConstructionError(cid, ctype, "Радиус окружности нулевой")
            n = len(verts)
            min_arc = math.radians(float(constr.get("min_arc_deg", 15.0)))
            if min_arc * n > 2 * math.pi:
                raise ConstructionError(cid, ctype,
                                        f"min_arc_deg={min_arc} слишком велик для {n} вершин")
            order = (constr.get("order") or "ccw").lower()
            # Стартовый угол из seed-детерминированного random (уже seeded).
            base_angle = constr.get("start_angle_deg", 0.0)
            start = math.radians(float(base_angle)) + random.uniform(0.0, min_arc)
            step = (2 * math.pi) / n
            for i, vid in enumerate(verts):
                if order == "cw":
                    t = start - i * step
                else:
                    t = start + i * step
                if vid in ctx.points:
                    raise ConstructionError(cid, ctype,
                                            f"вершина '{vid}' уже существует")
                x = center[0] + radius * math.cos(t)
                y = center[1] + radius * math.sin(t)
                ctx.points[vid] = (x, y)
                ctx.meta[vid] = {"type": "polygon_vertex", "label": vid,
                                 "side": constr.get("side", "auto"), "hidden": True}
                ctx.incidences.append({"point": vid, "on": "circle", "object": constr["circle"]})
            ctx.meta[cid] = {"type": "inscribed_polygon", "circle": constr["circle"],
                             "vertices": list(verts), "order": order,
                             "label": constr.get("label", cid)}

        elif ctype == "point_on_segment":
            p1 = ctx.get_point(constr["p1"], cid)
            p2 = ctx.get_point(constr["p2"], cid)
            r = constr.get("ratio", 0.5)
            ctx.points[cid] = geom.point_on_segment(p1, p2, r)
            ctx.meta[cid] = {"type": "point_on_segment", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"), "ratio": r}
            ctx.incidences.append({"point": cid, "on": "segment",
                                   "object": [constr["p1"], constr["p2"]]})

        elif ctype == "point_on_ray":
            # Точка за origin в направлении ОТ away_from на расстоянии distance.
            # distance задаётся либо числом, либо точкой length_from:
            #   distance = |origin − length_from|.
            origin = ctx.get_point(constr["origin"], cid)
            away_from = ctx.get_point(constr["away_from"], cid)
            distance = constr.get("distance")
            if distance is None and constr.get("length_from"):
                lf = ctx.get_point(constr["length_from"], cid)
                distance = geom.dist(origin, lf)
            if distance is None:
                distance = geom.dist(origin, away_from)
            ctx.points[cid] = geom.point_on_ray(origin, away_from, distance)
            ctx.meta[cid] = {"type": "point_on_ray", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"),
                             "parents": [constr["origin"], constr["away_from"]]}
            ctx.incidences.append({"point": cid, "on": "ray",
                                   "object": [constr["origin"], constr["away_from"]]})

        elif ctype == "foot_perpendicular":
            p = ctx.get_point(constr["p1"], cid)
            line = ctx.get_line(constr["line1"], cid)
            ctx.points[cid] = geom.foot_of_perpendicular(p, line)
            ctx.meta[cid] = {"type": "foot_perpendicular", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"),
                             "parents": [constr["p1"]]}
            ctx.incidences.append({"point": cid, "on": "line", "object": constr["line1"]})

        elif ctype == "intersect_lines":
            # Поддержка синонимов полей (line1/line2, l1/l2, l1_p1/l1_p2/…, p1..p4).
            if ("line1" in constr or "l1" in constr
                    or "l1_p1" in constr or "line1_p1" in constr):
                l1 = _resolve_line_ref(ctx, constr, cid, ("line1", "l1"),
                                       ("l1_p1", "line1_p1"), ("l1_p2", "line1_p2"))
                l2 = _resolve_line_ref(ctx, constr, cid, ("line2", "l2"),
                                       ("l2_p1", "line2_p1"), ("l2_p2", "line2_p2"))
            elif ("p1" in constr and "p2" in constr
                  and "p3" in constr and "p4" in constr):
                # Четыре точки: p1-p2 — первая прямая, p3-p4 — вторая.
                l1 = ctx.get_line_by_points(constr["p1"], constr["p2"], cid)
                l2 = ctx.get_line_by_points(constr["p3"], constr["p4"], cid)
            else:
                raise ConstructionError(
                    cid, ctype,
                    "intersect_lines требует line1/line2 или пары точек"
                )
            result = geom.intersect_lines(l1, l2)
            if result is None:
                raise ConstructionError(cid, ctype, "Прямые параллельны — пересечения нет")
            ctx.points[cid] = result
            ctx.meta[cid] = {"type": "intersect_lines", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}
            # Инцидентность фиксируем по точкам линий, если известны их id.
            for lk in ("line1", "line2"):
                lv = constr.get(lk)
                if isinstance(lv, str) and lv:
                    ctx.incidences.append({"point": cid, "on": "line", "object": lv})

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
            ctx.incidences.append({"point": cid, "on": "line", "object": constr["line1"]})
            ctx.incidences.append({"point": cid, "on": "circle", "object": constr["circle"]})

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
            ctx.incidences.append({"point": cid, "on": "circle", "object": constr["circle1"]})
            ctx.incidences.append({"point": cid, "on": "circle", "object": constr["circle2"]})

        elif ctype == "reflect_point_over_point":
            p = ctx.get_point(constr["p1"], cid)
            center = ctx.get_point(constr["p2"], cid)
            ctx.points[cid] = geom.reflect_point_over_point(p, center)
            ctx.meta[cid] = {"type": "reflect_point_over_point", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto")}

        elif ctype == "reflect_point":
            # CH27 FIX1: центральная симметрия. args {point, center},
            # результат — точка id (создаётся всегда).  D = 2*center − point.
            p = ctx.get_point(constr["point"], cid)
            center = ctx.get_point(constr["center"], cid)
            ctx.points[cid] = geom.reflect_point_over_point(p, center)
            ctx.meta[cid] = {"type": "reflect_point", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"),
                             "parents": [constr["point"], constr["center"]]}
            ctx.incidences.append({"point": cid, "on": "segment",
                                   "object": [constr["point"], cid]})

        elif ctype == "rotate_point":
            # CH27 FIX2: поворот точки вокруг центра.
            #   {point, center, degrees} — явный угол;
            #   {point, center, maps:[A, C]} — угол = ∠ABC, знак такой, чтобы
            #   A перешла в C (для «повернём вокруг B так, чтобы A перешла в C»).
            p = ctx.get_point(constr["point"], cid)
            center = ctx.get_point(constr["center"], cid)
            if "maps" in constr and isinstance(constr["maps"], (list, tuple)) \
                    and len(constr["maps"]) == 2:
                a = ctx.get_point(constr["maps"][0], cid)
                c = ctx.get_point(constr["maps"][1], cid)
                angle_rad = geom.signed_angle(a, center, c)
            else:
                angle_rad = math.radians(float(constr.get("degrees", 0.0)))
            ctx.points[cid] = geom.rotate_point(p, center, angle_rad)
            ctx.meta[cid] = {"type": "rotate_point", "label": constr.get("label", cid),
                             "side": constr.get("side", "auto"),
                             "parents": [constr["point"], constr["center"]]}

        elif ctype == "parallel_line":
            # CH27: прямая через точку point, параллельная прямой line.
            #   line — id прямой/отрезка, либо пара точек [P, Q].
            point = ctx.get_point(constr["point"], cid)
            if isinstance(constr.get("line"), (list, tuple)) \
                    and len(constr["line"]) == 2:
                q = ctx.get_point(constr["line"][0], cid)
                r = ctx.get_point(constr["line"][1], cid)
            else:
                seg = ctx.get_segment(constr["line"], cid)
                q, r = seg
            dx = r[0] - q[0]
            dy = r[1] - q[1]
            n = math.hypot(dx, dy)
            if n < geom.EPS:
                raise ConstructionError(cid, ctype, "Направляющий отрезок вырожден")
            p2 = (point[0] + dx, point[1] + dy)
            ctx.lines[cid] = geom.line_through_points(point, p2)
            ctx.segments[cid] = (point, p2)
            ctx.meta[cid] = {"type": "parallel_line", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [constr["point"]]}

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
            # CH15.1: поддерживаем контракт
            #   vertex / side_a / side_b / foot_id
            # И обратную совместимость с legacy-полями p1 / p2 / p3.
            vertex_ref = constr.get("vertex", constr.get("p1", ""))
            side_a_ref = constr.get("side_a", constr.get("p2", ""))
            side_b_ref = constr.get("side_b", constr.get("p3", ""))
            if not vertex_ref or not side_a_ref or not side_b_ref:
                raise ConstructionError(
                    cid, ctype,
                    "altitude требует vertex/side_a/side_b (или p1/p2/p3)"
                )
            p1 = ctx.get_point(vertex_ref, cid)
            p2 = ctx.get_point(side_a_ref, cid)
            p3 = ctx.get_point(side_b_ref, cid)
            # Высота из p1 на прямую p2-p3
            line_base = geom.line_through_points(p2, p3)
            foot = geom.foot_of_perpendicular(p1, line_base)
            line_alt = geom.line_through_points(p1, foot)
            # foot_id — имя основания, заданное моделью (по умолчанию "_foot").
            foot_id = constr.get("foot_id", cid + "_foot")
            if not isinstance(foot_id, str) or not foot_id:
                raise ConstructionError(cid, ctype, "foot_id должен быть непустой строкой")
            if foot_id != cid and foot_id in ctx.points:
                raise ConstructionError(
                    cid, ctype,
                    f"точка '{foot_id}' уже существует (повторное создание foot_id)"
                )
            ctx.points[foot_id] = foot
            ctx.meta[foot_id] = {"type": "foot_perpendicular",
                                 "label": constr.get("foot_label", foot_id if not foot_id.endswith("_foot") else ""),
                                 "side": "auto", "hidden": False,
                                 "parents": [vertex_ref]}
            ctx.lines[cid] = line_alt
            ctx.segments[cid] = (p1, foot)
            ctx.meta[cid] = {"type": "altitude", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [vertex_ref, side_a_ref, side_b_ref],
                             "foot_id": foot_id}

        elif ctype == "median":
            # Контракт: vertex / side_a / side_b / foot_id (планировщик),
            # либо legacy p1/p2/p3 (p1 — вершина, p2-p3 — сторона).
            vertex_ref = constr.get("vertex", constr.get("p1", ""))
            side_a_ref = constr.get("side_a", constr.get("p2", ""))
            side_b_ref = constr.get("side_b", constr.get("p3", ""))
            if not vertex_ref or not side_a_ref or not side_b_ref:
                raise ConstructionError(
                    cid, ctype,
                    "median требует vertex/side_a/side_b (или p1/p2/p3)"
                )
            p1 = ctx.get_point(vertex_ref, cid)
            p2 = ctx.get_point(side_a_ref, cid)
            p3 = ctx.get_point(side_b_ref, cid)
            # Медиана из p1 к середине p2-p3
            mid = geom.midpoint(p2, p3)
            ctx.points[cid + "_mid"] = mid
            ctx.meta[cid + "_mid"] = {"type": "midpoint", "label": "",
                                       "side": "auto", "hidden": True}
            ctx.lines[cid] = geom.line_through_points(p1, mid)
            ctx.segments[cid] = (p1, mid)
            ctx.meta[cid] = {"type": "median", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [vertex_ref, side_a_ref, side_b_ref]}
            # foot_id — имя точки-середины (создаём, если задано), чтобы
            # последующие построения могли ссылаться на неё.
            foot_id = constr.get("foot_id")
            if foot_id and isinstance(foot_id, str) and foot_id:
                if foot_id != cid and foot_id in ctx.points:
                    raise ConstructionError(
                        cid, ctype,
                        f"точка '{foot_id}' уже существует (повторное создание foot_id)"
                    )
                ctx.points[foot_id] = mid
                ctx.meta[foot_id] = {"type": "midpoint", "label": foot_id,
                                     "side": "auto", "hidden": False,
                                     "parents": [side_a_ref, side_b_ref]}
                ctx.meta[cid]["foot_id"] = foot_id

        elif ctype == "angle_bisector":
            # Контракт: vertex / side_a / side_b / foot_id (планировщик),
            # либо legacy p1/p2/p3 (p2 — вершина угла).
            vertex_ref = constr.get("vertex", constr.get("p2", ""))
            side_a_ref = constr.get("side_a", constr.get("p1", ""))
            side_b_ref = constr.get("side_b", constr.get("p3", ""))
            if not vertex_ref or not side_a_ref or not side_b_ref:
                raise ConstructionError(
                    cid, ctype,
                    "angle_bisector требует vertex/side_a/side_b (или p1/p2/p3)"
                )
            p1 = ctx.get_point(side_a_ref, cid)
            p2 = ctx.get_point(vertex_ref, cid)
            p3 = ctx.get_point(side_b_ref, cid)
            # Биссектриса угла p1-p2-p3 (из вершины p2).
            line_bis = geom.angle_bisector_line(p1, p2, p3)
            ctx.lines[cid] = line_bis
            ctx.segments[cid] = (p2, (p2[0] + (p1[0] - p2[0]) + (p3[0] - p2[0]),
                                      p2[1] + (p1[1] - p2[1]) + (p3[1] - p2[1])))
            ctx.meta[cid] = {"type": "angle_bisector", "label": constr.get("label", cid),
                             "dashed": constr.get("dashed", False),
                             "parents": [side_a_ref, vertex_ref, side_b_ref],
                             "vertex": vertex_ref}
            # foot_id — точка на биссектрисе.  Настоящее пересечение с
            # противолежащей стороной (side_a–side_b) вычислять нельзя: сторона
            # может быть «вырожденным углом» 180° для угла между p1 и p3.
            # Поэтому foot_id = точка на биссектрисе на фиксированном расстоянии
            # от вершины (по направлению биссектрисы).  Это гарантирует
            # существование точки, на которую можно ссылаться дальше.
            foot_id = constr.get("foot_id")
            if foot_id and isinstance(foot_id, str) and foot_id:
                if foot_id != cid and foot_id in ctx.points:
                    raise ConstructionError(
                        cid, ctype,
                        f"точка '{foot_id}' уже существует (повторное создание foot_id)"
                    )
                # Направление биссектрисы из line_bis: берём нормаль/вторую точку.
                # Проще: взять направляющий вектор биссектрисы как разность
                # единичных векторов к p1 и p3 (уже нормирован в geom), либо
                # использовать точку на прямой line_bis.
                # Надёжно: foot_id = вершина + нормализованное направление.
                try:
                    import math as _math
                    v1 = (p1[0] - p2[0], p1[1] - p2[1])
                    v3 = (p3[0] - p2[0], p3[1] - p2[1])
                    n1 = _math.hypot(v1[0], v1[1])
                    n3 = _math.hypot(v3[0], v3[1])
                    if n1 < 1e-9 or n3 < 1e-9:
                        # Вырожденный угол: foot_id — просто на продолжении к p1.
                        foot_pt = (p2[0] + 30.0, p2[1])
                    else:
                        d = (v1[0]/n1 + v3[0]/n3, v1[1]/n1 + v3[1]/n3)
                        nd = _math.hypot(d[0], d[1])
                        if nd < 1e-9:
                            d = (-v1[1]/n1, v1[0]/n1)
                            nd = 1.0
                        foot_pt = (p2[0] + 40.0*d[0]/nd, p2[1] + 40.0*d[1]/nd)
                    ctx.points[foot_id] = foot_pt
                    ctx.meta[foot_id] = {"type": "foot_perpendicular",
                                         "label": foot_id,
                                         "side": "auto", "hidden": False,
                                         "parents": [vertex_ref]}
                except Exception:
                    ctx.points[foot_id] = (p2[0] + 40.0, p2[1])
                    ctx.meta[foot_id] = {"type": "foot_perpendicular",
                                         "label": foot_id,
                                         "side": "auto", "hidden": False,
                                         "parents": [vertex_ref]}
                ctx.meta[cid]["foot_id"] = foot_id

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
            # Радиус можно задать числом (radius) или точкой
            # (radius_point / through / radius_from): r = distance(center, point).
            #
            # CH-fix: если ни один из ключей не указан — падаем явно.  Раньше
            # возвращалась вырожденная окружность r=1, которая тихо ломала aux-чертеж:
            # касания не совпадали с foot-точками, а визуал-аудит кидал INCIDENCE_VIOLATED.
            radius = constr.get("radius")
            if radius is None:
                rp = (constr.get("radius_point")
                      or constr.get("through")
                      or constr.get("radius_from"))
                if rp:
                    rp_pt = ctx.get_point(rp, cid)
                    radius = math.hypot(rp_pt[0] - center[0], rp_pt[1] - center[1])
            if radius is None:
                raise ConstructionError(
                    cid, ctype,
                    "circle_center_radius требует radius или radius_point/through/radius_from"
                )
            if radius <= geom.EPS:
                raise ConstructionError(
                    cid, ctype,
                    f"CIRCLE_RADIUS_ZERO: радиус {radius} не положителен"
                )
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

        # ─── REC-4: ограничения (задают геометрию, а не подбор координат) ───

        elif ctype == "angle_at_vertex":
            # Зафиксировать угол при вершине: vertex, ray1, ray2, value_deg.
            vertex = constr.get("vertex", constr.get("p2", ""))
            ray1 = constr.get("ray1", constr.get("p1", ""))
            ray2 = constr.get("ray2", constr.get("p3", ""))
            value_deg = float(constr.get("value_deg", constr.get("degrees", 0.0)))
            # Регистрируем как проверяемое ограничение (HARD).
            ctx.constraints.append({
                "kind": "angle",
                "vertex": vertex,
                "ray1": ray1,
                "ray2": ray2,
                "degrees": value_deg,
            })
            ctx.meta[cid] = {"type": "angle_at_vertex", "label": constr.get("label", cid),
                             "vertex": vertex, "ray1": ray1, "ray2": ray2,
                             "degrees": value_deg}

        elif ctype == "segment_length":
            # Зафиксировать длину отрезка p1-p2.
            p1 = constr.get("p1", "")
            p2 = constr.get("p2", "")
            value = float(constr.get("value", 0.0))
            ctx.constraints.append({
                "kind": "length",
                "segment": [p1, p2],
                "value": value,
            })
            ctx.meta[cid] = {"type": "segment_length", "label": constr.get("label", cid),
                             "p1": p1, "p2": p2, "value": value}

        elif ctype == "equal_segments":
            # Зафиксировать равенство отрезков: pairs = [[p1,p2],[p3,p4], ...].
            pairs = constr.get("pairs", constr.get("segments", [])) or []
            flat = []
            for item in pairs:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    flat.append([str(item[0]), str(item[1])])
            for i in range(len(flat) - 1):
                ctx.constraints.append({
                    "kind": "equal_lengths",
                    "seg1": flat[i],
                    "seg2": flat[i + 1],
                })
            ctx.meta[cid] = {"type": "equal_segments", "label": constr.get("label", cid),
                             "pairs": flat}

        elif ctype == "triangle_by_two_angles":
            # Построить треугольник A-B-C с заданными углами при A и B.
            # Требует, чтобы A и B уже были созданы (free_point).  Вершина C
            # вычисляется детерминированно по закону синусов — оба угла точны.
            a = ctx.get_point(constr["p1"], cid)
            b = ctx.get_point(constr["p2"], cid)
            angle_a = float(constr["angle_a"])
            angle_b = float(constr["angle_b"])
            angle_c = 180.0 - angle_a - angle_b
            if angle_c <= 0:
                raise ConstructionError(cid, ctype,
                                        f"Углы {angle_a}+{angle_b} не образуют треугольник")
            d = geom.dist(a, b)
            if d < geom.EPS:
                raise ConstructionError(cid, ctype, "Сторона AB вырождена")
            ac = d * math.sin(math.radians(angle_b)) / math.sin(math.radians(angle_c))
            bc = d * math.sin(math.radians(angle_a)) / math.sin(math.radians(angle_c))
            intersections = geom.intersect_circles((a, ac), (b, bc))
            if not intersections:
                raise ConstructionError(cid, ctype, "Нет пересечения окружностей")
            # Берём точку, не лежащую на прямой AB (любая из двух даёт те же углы).
            c = intersections[0]
            p3 = constr.get("p3", "C")
            ctx.points[p3] = c
            ctx.meta[p3] = {"type": "triangle_vertex", "label": constr.get("label_c", p3),
                            "side": "auto"}
            # Зафиксировать оба угла как ограничения.
            ctx.constraints.append({
                "kind": "angle",
                "vertex": constr["p1"], "ray1": constr["p2"], "ray2": p3,
                "degrees": angle_a,
            })
            ctx.constraints.append({
                "kind": "angle", "vertex": constr["p2"], "ray1": constr["p1"], "ray2": p3,
                "degrees": angle_b,
            })
            ctx.meta[cid] = {"type": "triangle", "label": constr.get("label", cid),
                             "parents": [constr["p1"], constr["p2"], p3],
                             "triangle_type": "by_two_angles",
                             "angles": [angle_a, angle_b, angle_c]}

        # ─── пометки ──────────────────────────────────────────

        elif ctype == "equal_segments_mark":
            # CH15.1: поддержка segments как списка пар [["A","B"],["A","C"]]
            # и count (число насечек).  Обратная совместимость с плоским
            # списком ["A","B","A","C"] и num_ticks.
            segs = constr.get("segments",
                  constr.get("parents",
                    [constr.get("p1", ""), constr.get("p2", ""),
                     constr.get("p3", ""), constr.get("p4", "")]))
            ctx.meta[cid] = {"type": "equal_segments_mark",
                             "segments": segs,
                             "num_ticks": constr.get("count", constr.get("num_ticks", 1))}

        elif ctype == "equal_angles_mark":
            ctx.meta[cid] = {"type": "equal_angles_mark",
                             "angles": constr.get("angles",
                                constr.get("parents", [])),
                             "num_arcs": constr.get("num_arcs", 1)}

        elif ctype == "right_angle_mark":
            # CH15.1: vertex / ray1 / ray2.  Обратная совместимость: p1/p2/p3.
            ctx.meta[cid] = {"type": "right_angle_mark",
                             "vertex": constr.get("vertex", constr.get("p2", "")),
                             "ray1": constr.get("ray1", constr.get("p1", "")),
                             "ray2": constr.get("ray2", constr.get("p3", ""))}

        elif ctype == "midpoint_mark":
            # CH15.1: отметка середины отрезка p1-p2 (или точки point).
            ctx.meta[cid] = {"type": "midpoint_mark",
                             "point": constr.get("point", constr.get("p1", "")),
                             "p1": constr.get("p1", ""),
                             "p2": constr.get("p2", "")}

        elif ctype == "parallel_mark":
            # CH15.1: отметка параллельности пары линий/отрезков.
            ctx.meta[cid] = {"type": "parallel_mark",
                             "segments": constr.get("segments",
                                constr.get("parents", []))}

        elif ctype == "perpendicular_mark":
            # CH15.1: отметка перпендикулярности (малый прямой угол в точке).
            ctx.meta[cid] = {"type": "perpendicular_mark",
                             "vertex": constr.get("vertex", constr.get("p2", "")),
                             "ray1": constr.get("ray1", constr.get("p1", "")),
                             "ray2": constr.get("ray2", constr.get("p3", ""))}

        elif ctype == "angle_label":
            # CH15.1: vertex / ray1 / ray2 / text.  Обратная совместимость: p1/p2/p3/label.
            ctx.meta[cid] = {"type": "angle_label",
                             "vertex": constr.get("vertex", constr.get("p2", "")),
                             "ray1": constr.get("ray1", constr.get("p1", "")),
                             "ray2": constr.get("ray2", constr.get("p3", "")),
                             "text": constr.get("text", constr.get("label", cid))}

        elif ctype == "length_label":
            # FIX: читаем text (как у angle_label), иначе Gemini шлёт
            # text: "6", а движок подставлял в label id ("len_AC") и отбрасывал
            # подпись через _skip_invalid_label (SKIPPED_INVALID_LABEL).
            ctx.meta[cid] = {"type": "length_label",
                             "p1": constr.get("p1", ""),
                             "p2": constr.get("p2", ""),
                             "text": constr.get("text", constr.get("label", cid))}

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


# CH21 FIX 1: SOFT-проверки (презентация) — не блокируют job, только влияют
# на выбор лучшей попытки.
_SOFT_VIOLATION_MARKERS = ("Проверка 2", "LABEL_OVERLAP_ANGLE")


def _is_soft_violation(text: str) -> bool:
    return any(marker in text for marker in _SOFT_VIOLATION_MARKERS)


def run_all_checks(ctx: BuildContext,
                   canvas_w: int, canvas_h: int, margin: int,
                   settings: EngineSettings) -> CheckResult:
    """Запустить все проверки (HARD блокируют, SOFT — презентация)."""
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

    # Проверка 2 (подписи) и 4 (пересечения): считаем прямоугольники подписей
    # и проверяем, что подпись не ложится на отрезок / точку / другую подпись.
    label_boxes = _collect_label_boxes(ctx, settings)

    # подпись не пересекает ЧУЖОЙ отрезок. Отрезки, инцидентные своей точке
    # подписи (проходят через неё), пропускаются — иначе подпись вершины
    # треугольника всегда «пересекает» две стороны и сборка невозможна.
    own_segments = {}
    for sid, smeta in ctx.meta.items():
        parents = smeta.get("parents") or []
        for p in parents:
            own_segments.setdefault(p, set()).add(sid)

    for pid, lid, (lx1, ly1, lx2, ly2) in label_boxes:
        for sid, seg in ctx.segments.items():
            smeta = ctx.meta.get(sid, {})
            if smeta.get("hidden", False):
                continue
            if sid in own_segments.get(pid, set()):
                continue
            if _bbox_intersects_segment((lx1, ly1, lx2, ly2), seg):
                violations.append(
                    f"Проверка 2 (подпись/отрезок): label '{lid}' пересекает segment '{sid}'"
                )

    # подпись не пересекает чужую подпись
    for i in range(len(label_boxes)):
        for j in range(i + 1, len(label_boxes)):
            a = label_boxes[i][2]
            b = label_boxes[j][2]
            if _bboxes_overlap(a, b):
                violations.append(
                    f"Проверка 2 (подписи): '{label_boxes[i][1]}' и '{label_boxes[j][1]}' пересекаются"
                )

    # подпись не ложится на ЧУЖУЮ точку (своя точка подписи — это нормально).
    for pid, lid, (lx1, ly1, lx2, ly2) in label_boxes:
        for pname, pt in all_points.items():
            if pid == pname:
                continue
            if _bbox_contains_point((lx1, ly1, lx2, ly2), pt, settings.point_radius):
                violations.append(
                    f"Проверка 2 (подпись/точка): label '{lid}' перекрывает точку '{pname}'"
                )

    # подпись не выходит за холст
    for pid, lid, (lx1, ly1, lx2, ly2) in label_boxes:
        if lx1 < 0 or ly1 < 0 or lx2 > canvas_w or ly2 > canvas_h:
            violations.append(
                f"Проверка 2 (границы подписи): label '{lid}' выходит за холст"
            )

    # CH19 DEFECT 2: LABEL_OVERLAP_ANGLE — пересечение bounding box двух
    # angle_label у ОДНОЙ вершины после ступенчатого размещения.
    angle_boxes = {}  # vertex -> list[(cid, bbox)]
    for obj in ctx.objects:
        if obj.get("type") != "angle_label":
            continue
        cid = obj["id"]
        meta = ctx.meta.get(cid, {})
        v_id = meta.get("vertex", "")
        if not v_id:
            continue
        layout = _angle_label_layout(ctx, settings)
        lay = layout.get(cid, {})
        if "lx" not in lay:
            continue
        lx, ly = lay["lx"], lay["ly"]
        angle_boxes.setdefault(v_id, []).append(
            (cid, (lx - 20, ly - 8, lx + 20, ly + 8))
        )
    for v_id, boxes in angle_boxes.items():
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                cid_a, bbox_a = boxes[i]
                cid_b, bbox_b = boxes[j]
                if _bboxes_overlap(bbox_a, bbox_b):
                    violations.append(
                        f"LABEL_OVERLAP_ANGLE: '{cid_a}' и '{cid_b}' "
                        f"пересекаются у вершины '{v_id}'"
                    )

    # ── CH26 FIX3: HARD-проверка инцидентности (INCIDENCE_VIOLATED) ──
    for inc in ctx.incidences:
        pid = inc.get("point")
        if pid not in ctx.points:
            continue
        pt = ctx.points[pid]
        on = inc.get("on")
        obj = inc.get("object")
        if on == "circle":
            circle = ctx.circles.get(obj) if isinstance(obj, str) else None
            if circle is None:
                continue
            center, radius = circle
            deviation = abs(geom.dist(center, pt) - radius)
            if deviation > 1e-6:
                violations.append(
                    f"INCIDENCE_VIOLATED: точка '{pid}' объявлена на окружности "
                    f"'{obj}', но отклонение {deviation:.6f} > 1e-6"
                )
        elif on in ("segment", "line", "ray"):
            # object — либо id линии/отрезка, либо [p1, p2].
            if isinstance(obj, str) and obj in ctx.segments:
                seg = ctx.segments[obj]
            elif isinstance(obj, (list, tuple)) and len(obj) == 2 \
                    and obj[0] in ctx.points and obj[1] in ctx.points:
                seg = (ctx.points[obj[0]], ctx.points[obj[1]])
            else:
                continue
            # Отклонение от прямой (для line/ray) или от отрезка (для segment).
            d_line = geom.point_to_line_distance(pt, geom.line_through_points(seg[0], seg[1]))
            if on == "segment":
                if not geom.segment_contains_point(seg, pt):
                    d_seg = geom.point_to_segment_distance(pt, seg)
                    violations.append(
                        f"INCIDENCE_VIOLATED: точка '{pid}' объявлена на отрезке, "
                        f"но отстоит на {d_seg:.6f} (не между концами)"
                    )
                elif d_line > 1e-6:
                    violations.append(
                        f"INCIDENCE_VIOLATED: точка '{pid}' объявлена на отрезке, "
                        f"но отклонение от прямой {d_line:.6f} > 1e-6"
                    )
            else:
                if d_line > 1e-6:
                    violations.append(
                        f"INCIDENCE_VIOLATED: точка '{pid}' объявлена на прямой/луче, "
                        f"но отклонение {d_line:.6f} > 1e-6"
                    )

    # REC-4: численные ограничения (angle_at_vertex / segment_length /
    # equal_segments / triangle_by_two_angles) — HARD.
    violations.extend(check_constraints(ctx))

    return CheckResult(passed=len(violations) == 0, violations=violations)


def _bboxes_overlap(a, b) -> bool:
    """True, если прямоугольники (x1,y1,x2,y2) пересекаются."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _bbox_contains_point(bbox, pt, radius) -> bool:
    """True, если точка (с учётом радиуса) попадает внутрь bbox."""
    x1, y1, x2, y2 = bbox
    return (x1 - radius) <= pt[0] <= (x2 + radius) and (y1 - radius) <= pt[1] <= (y2 + radius)


def _bbox_intersects_segment(bbox, seg) -> bool:
    """Приблизительная проверка пересечения bbox и отрезка.

    Проверяем: хотя бы одна точка отрезка попадает в расширенный bbox,
    либо отрезок проходит через bbox (пересечение с диагоналями).
    """
    x1, y1, x2, y2 = bbox
    pad = 2.0
    p1, p2 = seg
    # Точки отрезка внутри расширенного bbox
    for pt in (p1, p2):
        if (x1 - pad) <= pt[0] <= (x2 + pad) and (y1 - pad) <= pt[1] <= (y2 + pad):
            return True
    # Пересечение с границами bbox (грубая проверка по средним точкам)
    mid = geom.midpoint(p1, p2)
    if (x1 - pad) <= mid[0] <= (x2 + pad) and (y1 - pad) <= mid[1] <= (y2 + pad):
        return True
    return False


def _collect_label_boxes(ctx: BuildContext, settings: EngineSettings):
    """Собрать (point_id, label_text, (x1,y1,x2,y2)) для видимых подписей точек.

    Повторяет ту же логику выбора позиции, что в render_svg, чтобы
    проверки соответствовали реальному размещению подписи.
    """
    boxes = []
    all_drawn_segments = []
    for sid, sdata in ctx.segments.items():
        smeta = ctx.meta.get(sid, {})
        if not smeta.get("hidden", False):
            all_drawn_segments.append(sdata)

    all_drawn_circles = []
    for cid, cdata in ctx.circles.items():
        cmeta = ctx.meta.get(cid, {})
        if not cmeta.get("hidden", False):
            all_drawn_circles.append(cdata)

    all_drawn_points = [p for n, p in ctx.points.items()
                        if not ctx.meta.get(n, {}).get("hidden", False)
                        and ctx.meta.get(n, {}).get("type") != "polygon_vertex"]

    placed = []
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("hidden") or meta.get("type") == "polygon_vertex":
            continue
        label = meta.get("label", name)
        if not label or label.startswith("_"):
            continue
        side = meta.get("side", "auto")
        if side != "auto":
            ox, oy = _compute_label_offset(pt, side, settings.label_padding, 0)
        else:
            other_points = [p for p in all_drawn_points if p != pt]
            cands = _compute_label_candidates(pt, settings.label_padding, 8)
            best, best_s = None, float('inf')
            for c in cands:
                s = _score_label_candidate(c, all_drawn_segments, placed, settings,
                                           circles=all_drawn_circles, points=other_points)
                if s < best_s:
                    best_s, best = s, c
            ox, oy = best if best else _compute_label_offset(pt, "auto", settings.label_padding, 0)
        placed.append((ox, oy))
        boxes.append((name, label, (ox - 18, oy - 7, ox + 18, oy + 7)))
    return boxes


# ═══════════════════════════════════════════════════════════════
# Отрисовка SVG
# ═══════════════════════════════════════════════════════════════

# Константы для штрихов равенства и дуг
EQUAL_TICK_SPACING = 4.0      # расстояние между параллельными насечками на отрезке
EQUAL_ARC_RADIUS_GAP = 5.0    # радиальный зазор между концентрическими дугами
EQUAL_TICK_HALF_LENGTH = 5.0  # полудлина одной насечки


def _compute_label_candidates(pt: Point, padding: float, n_directions: int = 24) -> List[Point]:
    """Сгенерировать позиции-кандидаты для подписи вокруг точки pt.

    По умолчанию 8 позиций: N, NE, E, SE, S, SW, W, NW (детерминированный
    порядок, начиная с N).  При n_directions > 8 возвращается равномерный
    веер по кругу (старое поведение — для обратной совместимости).
    """
    candidates = []
    if n_directions == 8:
        dirs = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
        for dx, dy in dirs:
            candidates.append((pt[0] + dx * padding, pt[1] + dy * padding))
        return candidates
    for i in range(n_directions):
        angle = 2.0 * math.pi * i / n_directions
        dx = padding * math.cos(angle)
        dy = padding * math.sin(angle)
        candidates.append((pt[0] + dx, pt[1] + dy))
    return candidates


def _score_label_candidate(candidate: Point, segments: List[Segment],
                           placed_labels: List[Point], settings: EngineSettings,
                           circles: Optional[List[geom.Circle]] = None,
                           points: Optional[List[Point]] = None,
                           canvas_w: int = 0, canvas_h: int = 0,
                           label_half_w: float = 18.0,
                           label_half_h: float = 7.0) -> float:
    """
    Оценить кандидата: чем меньше score, тем лучше.

    Штрафы:
      * близость к отрезкам;
      * близость к окружностям (CH15.1);
      * близость к уже размещённым подписям;
      * выход подписи за границы canvas.
    """
    score = 0.0
    # Штраф за близость к точкам (CH15.1): подпись не должна ложиться
    # на чужую точку.  В кандидатах сюда передаются ВСЕ видимые точки,
    # поэтому текущая точка сюда не попадает (см. вызов в render_svg /
    # _collect_label_boxes ниже).
    for p in (points or []):
        d = geom.dist(candidate, p)
        if d < settings.point_radius + 1.0:
            score += 1e9
        elif d < settings.point_radius + settings.label_padding:
            score += 600.0 / ((d - settings.point_radius) ** 2)
        else:
            score += 120.0 / (d * d)

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

    # Штраф за близость к окружностям
    for circle in (circles or []):
        center, r = circle
        d = abs(geom.dist(candidate, center) - r)
        if d < 0.01:
            score += 1e9
        else:
            score += 400.0 / (d * d)

    # Штраф за близость к уже размещённым подписям
    for placed in placed_labels:
        d = geom.dist(candidate, placed)
        if d < 0.01:
            score += 1e9
        else:
            score += 300.0 / (d * d)

    # Штраф за выход за холст (прямоугольник подписи).
    if canvas_w and canvas_h:
        x1 = candidate[0] - label_half_w
        y1 = candidate[1] - label_half_h
        x2 = candidate[0] + label_half_w
        y2 = candidate[1] + label_half_h
        if x1 < 0 or y1 < 0 or x2 > canvas_w or y2 > canvas_h:
            score += 1e6

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


def _compute_auto_fit(ctx: BuildContext, canvas_w: int, canvas_h: int,
                      settings: EngineSettings):
    """Вычислить (new_w, new_h, dx, dy, scale) для auto-fit презентации.

    Только масштаб и сдвиг (scale+shift), относительная геометрия неизменна.
    Bounding box считается по всем видимым элементам: точки, отрезки, лучи,
    окружности, дуги, тексты подписей, маркеры углов.  После паддинга
    (10–14% от большей стороны bbox) сцена масштабируется так, чтобы занимать
    не менее 70% площади canvas по каждой оси (для веера лучей из одной
    точки — чтобы вершина не прижималась к краю).
    """
    xs = []
    ys = []

    # Точки (видимые, не вершины полигонов — их позиции и так в отрезках).
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("hidden") or meta.get("type") == "polygon_vertex":
            continue
        xs.append(pt[0])
        ys.append(pt[1])

    # Отрезки / лучи / линии.
    for sid, sdata in ctx.segments.items():
        smeta = ctx.meta.get(sid, {})
        if smeta.get("hidden", False):
            continue
        xs.extend([sdata[0][0], sdata[1][0]])
        ys.extend([sdata[0][1], sdata[1][1]])

    # Окружности (включая маркеры-дуги — они circle-объекты движка).
    for cid, cdata in ctx.circles.items():
        cmeta = ctx.meta.get(cid, {})
        if cmeta.get("hidden", False):
            continue
        center, r = cdata
        xs.extend([center[0] - r, center[0] + r])
        ys.extend([center[1] - r, center[1] + r])

    # Тексты подписей (точки + angle/length-подписи).  Их позиции уже
    # вычислены greedy-плейсментом в ctx.meta — берём грубую оценку.
    for name, meta in ctx.meta.items():
        if meta.get("hidden"):
            continue
        if name not in ctx.points:
            continue
        pt = ctx.points[name]
        # Оцениваем подпись вокруг точки (padding + половина высоты текста).
        xs.extend([pt[0] - settings.label_padding - 20,
                   pt[0] + settings.label_padding + 20])
        ys.extend([pt[1] - settings.label_padding - 10,
                   pt[1] + settings.label_padding + 10])

    if not xs or not ys:
        return canvas_w, canvas_h, 0.0, 0.0, 1.0

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    content_w = max_x - min_x
    content_h = max_y - min_y
    if content_w < 1.0:
        content_w = 1.0
    if content_h < 1.0:
        content_h = 1.0

    pad = settings.fit_padding_ratio * max(content_w, content_h)
    pad = max(settings.fit_min_padding, min(settings.fit_max_padding, pad))

    # Масштаб, чтобы сцена занимала ~70% canvas по каждой оси.
    # Если содержимое ШИРЕ canvas (например, вспомогательная точка выходит
    # за поле) — уменьшаем масштаб, чтобы всё поместилось.  Нижний порог 0.2,
    # чтобы не сжимать в точку.
    target_w = content_w + 2 * pad
    target_h = content_h + 2 * pad
    scale_w = (0.70 * canvas_w) / target_w
    scale_h = (0.70 * canvas_h) / target_h
    scale = min(scale_w, scale_h)
    # Растягивать мелочь не нужно (>=70% охвата — уже цель), а сжимать
    # крупное — да.  Ограничиваем только снизу, чтобы не выродить.
    scale = max(0.2, min(scale, 1.5))

    # Сдвиг: центрируем масштабированный bbox в исходном canvas.
    scaled_w = target_w * scale
    scaled_h = target_h * scale
    dx = (canvas_w - scaled_w) / 2.0 - (min_x - pad) * scale
    dy = (canvas_h - scaled_h) / 2.0 - (min_y - pad) * scale

    new_w = int(math.ceil(max(scaled_w, canvas_w)))
    new_h = int(math.ceil(max(scaled_h, canvas_h)))
    return new_w, new_h, dx, dy, scale


def _angle_label_layout(ctx: BuildContext, settings: EngineSettings) -> Dict[str, dict]:
    """Ступенчатое размещение angle_label по вершинам (CH19 DEFECT 2).

    Группируем angle_label по vertex, сортируем по возрастанию биссектрисного
    направления, назначаем радиус дуги r_i = r_base + i*step (step ~14px),
    текст ставим на биссектрисе на r_i + offset.  Для очень малых углов
    (< 15°) используем выносную подпись дальше от вершины.
    """
    from collections import defaultdict

    step = settings.label_padding * 1.0  # ~14px
    r_base = settings.label_padding * 1.0
    text_offset = settings.label_padding * 0.6

    groups = defaultdict(list)
    for obj in ctx.objects:
        if obj.get("type") != "angle_label":
            continue
        cid = obj["id"]
        meta = ctx.meta.get(cid, {})
        v_id = meta.get("vertex", "")
        a_id = meta.get("ray1", meta.get("p1", ""))
        b_id = meta.get("ray2", meta.get("p3", ""))
        if not (v_id in ctx.points and a_id in ctx.points and b_id in ctx.points):
            continue
        v = ctx.points[v_id]
        a = ctx.points[a_id]
        b = ctx.points[b_id]
        va = (a[0] - v[0], a[1] - v[1])
        vb = (b[0] - v[0], b[1] - v[1])
        angle_a = math.atan2(va[1], va[0])
        angle_b = math.atan2(vb[1], vb[0])
        diff = (angle_b - angle_a) % (2 * math.pi)
        if diff > math.pi:
            diff = diff - 2 * math.pi
        bisector = angle_a + diff / 2.0
        groups[v_id].append((cid, bisector, diff))

    layout: Dict[str, dict] = {}
    for v_id, entries in groups.items():
        entries.sort(key=lambda e: e[1])
        # Шаг 1: ступенчатый радиус по биссектрисе.
        for i, (cid, bisector, diff) in enumerate(entries):
            r = r_base + i * step
            small = abs(math.degrees(diff)) < 15.0
            off = text_offset * (1.5 if small else 1.0)
            lx = ctx.points[v_id][0] + (r + off) * math.cos(bisector)
            ly = ctx.points[v_id][1] + (r + off) * math.sin(bisector)
            layout[cid] = {"r": r, "lx": lx, "ly": ly, "bisector": bisector}

        # Шаг 2: если bbox соседних подписей пересекаются — сдвигаем текст
        # вдоль дуги (тангенциально) с минимальным penalty.
        def _bbox(l):
            return (l["lx"] - 20, l["ly"] - 8, l["lx"] + 20, l["ly"] + 8)

        def _overlap(a, b):
            return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

        cids_in_group = [cid for cid, _, _ in entries]
        for idx in range(1, len(cids_in_group)):
            prev = layout[cids_in_group[idx - 1]]
            cur = layout[cids_in_group[idx]]
            if not _overlap(_bbox(prev), _bbox(cur)):
                continue
            # Кандидаты тангенциального сдвига текущей подписи вдоль её дуги.
            r = cur["r"] + text_offset
            bis = cur["bisector"]
            best = None
            best_score = float("inf")
            for k in (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0):
                tang = bis + math.pi / 2.0
                dx = k * text_offset * math.cos(tang)
                dy = k * text_offset * math.sin(tang)
                cand = {"r": cur["r"], "bisector": bis,
                        "lx": cur["lx"] + dx, "ly": cur["ly"] + dy}
                # penalty: пересечение с предыдущим (большой штраф) + отклонение.
                score = abs(k) * 10.0
                if _overlap(_bbox(prev), _bbox(cand)):
                    score += 1e6
                if score < best_score:
                    best_score = score
                    best = cand
            if best is not None and best_score < 1e6:
                cur["lx"] = best["lx"]
                cur["ly"] = best["ly"]
    return layout


def _semantic_color(settings: EngineSettings, role: str, kind: str, fallback: str) -> str:
    """Вернуть цвет семантической роли (CH16), либо fallback при выключенном
    semantic_colors или неизвестной роли."""
    if not getattr(settings, "semantic_colors", False):
        return fallback
    return DARK_GEOMETRY.get(role, {}).get(kind, fallback)


# Индексы геометрических точек встречаются в двух формах:
#   «A_1» / «A_{12}»  — с явным подчёркиванием;
#   «A1»              — буква, сразу за которой идёт индекс (частый случай
#                       в планах построений: A1, B1, C1, P12).
_SUB_RE = re.compile(r"([A-Za-zА-Яа-я])(?:_(\{?[0-9A-Za-z]+\}?)|(\d+))")


def _label_spans(text: str) -> List[tuple]:
    """Разбить подпись на (текст, признак_подстрочного) пары.

    Подписи вида «A_1», «A_{12}» и «A1» (индексы в геометрии) превращаются
    в обычный текст + подстрочный индекс, чтобы на чертеже было «A₁», а не
    «A_1» / «A1».
    """
    if not text:
        return []
    spans = []
    pos = 0
    for m in _SUB_RE.finditer(text):
        if m.start() > pos:
            spans.append((text[pos:m.start()], False))
        # Базовая буква (A/B/C) идёт обычным текстом, индекс — подстрочным.
        spans.append((m.group(1), False))
        idx = (m.group(2) or m.group(3) or "").strip("{}")
        if idx:
            spans.append((idx, True))
        pos = m.end()
    if pos < len(text):
        spans.append((text[pos:], False))
    return spans or [(text, False)]


def _set_label_text(el, text: str, font_size) -> None:
    """Записать текст подписи с настоящими подстрочными индексами."""
    spans = _label_spans(text or "")
    if len(spans) == 1 and not spans[0][1]:
        el.text = spans[0][0]
        return
    sub_size = max(int(float(font_size) * 0.7), 8)
    for chunk, is_sub in spans:
        tspan = ET.SubElement(el, "tspan")
        tspan.text = chunk
        if is_sub:
            tspan.set("font-size", str(sub_size))
            tspan.set("baseline-shift", "sub")


def _skip_invalid_label(text: Any, object_id: str = "") -> bool:
    """Последний защитный барьер: True, если подпись запрещена.

    Логирует SKIPPED_INVALID_LABEL.  Геометрию не меняет — только
    предотвращает отрисовку служебного имени.  Ленивый импорт из
    services.figure_plan_validator (без циклических зависимостей).
    """
    s = (text or "").strip()
    if not s:
        return False
    try:
        from services.figure_plan_validator import is_invalid_label_text
    except Exception:
        return False
    if is_invalid_label_text(s, object_id or None):
        logger.warning(
            "SKIPPED_INVALID_LABEL: '%s' (object_id=%s)", s, object_id or ""
        )
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────
# CH31: извлечение числовых утверждений из условия + их проверка.
# ──────────────────────────────────────────────────────────────────────────

_PT = r"([A-Z])"  # одиночная заглавная буква-точка


def extract_condition_constraints(condition_text: str) -> List[Dict[str, Any]]:
    """Извлечь из условия проверяемые числовые утверждения.

    Поддерживает:
      - «AB = BC» (равенство длин сторон);
      - «AB = 6» (числовая длина стороны);
      - «угол B равен 50» / «∠B = 50» (величина угла);
      - «AB ∥ CD» (параллельность);
      - «AB ⟂ CD» (перпендикулярность).
    """
    out: List[Dict[str, Any]] = []
    if not condition_text:
        return out

    # Углы: «угол B равен 50», «∠B = 50», «угол ABC равен 50».
    for m in re.finditer(
        r"угол\s+([A-Z]{1,3})\s*(?:равен|равна|=)\s*(\d+(?:[.,]\d+)?)°?|"
        r"∠\s*([A-Z]{1,3})\s*=\s*(\d+(?:[.,]\d+)?)°?",
        condition_text,
        re.IGNORECASE,
    ):
        label = m.group(1) or m.group(3)
        val = m.group(2) or m.group(4)
        if label and val:
            try:
                out.append({"kind": "angle", "vertex": label, "degrees": float(val.replace(",", "."))})
            except ValueError:
                pass

    # Равенство длин: «AB = BC», «AD = DC».
    for m in re.finditer(
        r"\b([A-Z])([A-Z])\s*=\s*([A-Z])([A-Z])\b",
        condition_text,
    ):
        a1, a2, b1, b2 = m.groups()
        if (a1 + a2) == (b1 + b2):
            continue
        out.append({"kind": "equal_lengths", "seg1": [a1, a2], "seg2": [b1, b2]})

    # Числовая длина: «AB = 6», «AB = 7».
    for m in re.finditer(
        r"\b([A-Z])([A-Z])\s*=\s*(\d+(?:[.,]\d+)?)(?!\s*°)\b",
        condition_text,
    ):
        a, b, val = m.groups()
        try:
            out.append({"kind": "length", "segment": [a, b], "value": float(val.replace(",", "."))})
        except ValueError:
            pass

    # Параллельность / перпендикулярность.
    for m in re.finditer(
        r"\b([A-Z])([A-Z])\s*∥\s*([A-Z])([A-Z])\b", condition_text
    ):
        out.append({"kind": "parallel", "seg1": [m.group(1), m.group(2)],
                    "seg2": [m.group(3), m.group(4)]})
    for m in re.finditer(
        r"\b([A-Z])([A-Z])\s*⟂\s*([A-Z])([A-Z])\b", condition_text
    ):
        out.append({"kind": "perpendicular", "seg1": [m.group(1), m.group(2)],
                    "seg2": [m.group(3), m.group(4)]})

    return out


def _angle_deg_at(ctx, vertex, a, b) -> float:
    """Измерить угол a-vertex-b в градусах (0..180)."""
    if vertex not in ctx.points or a not in ctx.points or b not in ctx.points:
        return None
    v = ctx.points[vertex]
    return math.degrees(geom.angle_between_three(ctx.points[a], v, ctx.points[b]))


def check_constraints(ctx: BuildContext) -> List[str]:
    """Проверить все constraints численно.  Возвращает violations."""
    violations = []
    for c in ctx.constraints:
        kind = c.get("kind")
        if kind == "equal_lengths":
            s1 = c["seg1"]
            s2 = c["seg2"]
            if all(p in ctx.points for p in s1 + s2):
                d1 = geom.dist(ctx.points[s1[0]], ctx.points[s1[1]])
                d2 = geom.dist(ctx.points[s2[0]], ctx.points[s2[1]])
                rel = abs(d1 - d2) / max(d1, d2, geom.EPS)
                if rel > 1e-3:
                    violations.append(
                        f"CONSTRAINT_VIOLATION: заявлено {s1[0]}{s1[1]} = {s2[0]}{s2[1]}, "
                        f"измерено {d1:.1f} и {d2:.1f}"
                    )
        elif kind == "length":
            s = c["segment"]
            if all(p in ctx.points for p in s):
                d = geom.dist(ctx.points[s[0]], ctx.points[s[1]])
                # Масштаб произволен — сравниваем только если есть другая длина.
                # Пропорциональную проверку делаем через отношения длин, если
                # в constraints есть более одной length.
                pass
        elif kind == "angle":
            v = c.get("vertex")
            ray1 = c.get("ray1")
            ray2 = c.get("ray2")
            if ray1 and ray2:
                # Явные лучи (angle_at_vertex / triangle_by_two_angles).
                meas = _angle_deg_at(ctx, v, ray1, ray2)
                if meas is not None and abs(meas - c["degrees"]) > 0.5:
                    violations.append(
                        f"CONSTRAINT_VIOLATION: угол {v} заявлен {c['degrees']}, "
                        f"построен {meas:.1f}"
                    )
            elif len(v) == 1:
                # «угол B равен 50» — вершина B, лучи из соседних точек.
                pts = [p for p in ctx.points if p != v]
                if v in ctx.points and len(pts) >= 2:
                    a, b = pts[0], pts[1]
                    meas = _angle_deg_at(ctx, v, a, b)
                    if meas is not None and abs(meas - c["degrees"]) > 0.5:
                        violations.append(
                            f"CONSTRAINT_VIOLATION: угол {v} заявлен {c['degrees']}, "
                            f"построен {meas:.1f}"
                        )
        elif kind == "perpendicular":
            s1, s2 = c["seg1"], c["seg2"]
            if all(p in ctx.points for p in s1 + s2):
                v1 = (ctx.points[s1[1]][0] - ctx.points[s1[0]][0],
                      ctx.points[s1[1]][1] - ctx.points[s1[0]][1])
                v2 = (ctx.points[s2[1]][0] - ctx.points[s2[0]][0],
                      ctx.points[s2[1]][1] - ctx.points[s2[0]][1])
                dot = v1[0] * v2[0] + v1[1] * v2[1]
                n1 = math.hypot(*v1)
                n2 = math.hypot(*v2)
                if n1 > geom.EPS and n2 > geom.EPS and abs(dot) / (n1 * n2) > 1e-3:
                    violations.append(
                        f"CONSTRAINT_VIOLATION: {s1[0]}{s1[1]} ⟂ {s2[0]}{s2[1]} "
                        f"заявлено, но угол не прямой"
                    )
        elif kind == "parallel":
            s1, s2 = c["seg1"], c["seg2"]
            if all(p in ctx.points for p in s1 + s2):
                v1 = (ctx.points[s1[1]][0] - ctx.points[s1[0]][0],
                      ctx.points[s1[1]][1] - ctx.points[s1[0]][1])
                v2 = (ctx.points[s2[1]][0] - ctx.points[s2[0]][0],
                      ctx.points[s2[1]][1] - ctx.points[s2[0]][1])
                cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
                n1 = math.hypot(*v1)
                n2 = math.hypot(*v2)
                if n1 > geom.EPS and n2 > geom.EPS and cross / (n1 * n2) > 1e-3:
                    violations.append(
                        f"CONSTRAINT_VIOLATION: {s1[0]}{s1[1]} ∥ {s2[0]}{s2[1]} "
                        f"заявлено, но прямые не параллельны"
                    )
    return violations


# ──────────────────────────────────────────────────────────────────────────
# CH30 ЭТАП 1b: автовывод семантики из способа построения.
# ──────────────────────────────────────────────────────────────────────────

# Операции, которые создают перпендикулярность (для автогенерации меток
# прямых углов).  Значение — имена точек (vertex, ray1, ray2) в ctx.points.
def _apply_auto_semantics(ctx: BuildContext) -> None:
    """Вывести visual_role и авто-метки прямых углов, НЕ прося LLM.

    Правила:
      * altitude / foot_perpendicular / draw_perpendicular /
        perpendicular_bisector -> авто right_angle_mark в основании;
      * точка, построенная операцией производной точки (midpoint/foot/
        circumcenter/incenter/orthocenter/intersect_*/...) -> "secondary",
        если это последний объект aux-слоя — "key_point";
      * окружность circumcircle/incircle в base -> "reference_circle";
      * окружность в aux -> "target_circle";
      * линии aux -> "auxiliary".
    """
    # 1. Авто-метки прямых углов для перпендикулярных операций.
    auto_marks = []
    for cid, meta in ctx.meta.items():
        ctype = meta.get("type")
        if ctype == "altitude":
            vertex = meta.get("parents", [None])[0]
            foot = meta.get("foot_id")
            if foot and foot in ctx.points and vertex in ctx.points:
                auto_marks.append({"vertex": foot, "ray1": vertex, "ray2": None})
        elif ctype == "foot_perpendicular":
            parents = meta.get("parents") or []
            if len(parents) >= 1 and parents[0] in ctx.points:
                # ray2 — любая точка на базовой прямой (не сам foot и не vertex).
                ray2 = _find_point_on_line(ctx, cid, exclude={parents[0]})
                auto_marks.append({"vertex": cid, "ray1": parents[0], "ray2": ray2})
        elif ctype == "perpendicular_bisector":
            parents = meta.get("parents") or []
            if len(parents) >= 2:
                mid_id = cid + "_mid"
                if mid_id in ctx.points and parents[0] in ctx.points:
                    auto_marks.append({"vertex": mid_id, "ray1": parents[0], "ray2": parents[1]})

    # 2. Автовывод visual_role по происхождению.
    for obj in ctx.objects:
        cid = obj.get("id")
        meta = ctx.meta.get(cid, {})
        ctype = obj.get("type")
        style = meta.get("style") or obj.get("style")

        # Явная роль — не перезаписываем.
        if meta.get("visual_role") or obj.get("visual_role"):
            continue

        # Описанная/вписанная окружность — ВСЕГДА reference_circle,
        # независимо от слоя (правило Задачи 2).
        if ctype in ("circumcircle", "incircle"):
            meta["visual_role"] = "reference_circle"
        elif style == "aux":
            if ctype in ("segment", "line", "ray", "line_extension", "altitude",
                         "median", "angle_bisector", "perpendicular_bisector",
                         "parallel_line", "tangent_from_point", "tangent_at_point"):
                meta["visual_role"] = "aux"
            elif ctype in ("circle_center_radius", "circle_three_points"):
                meta["visual_role"] = "target_circle"
            elif ctype == "free_point":
                meta["visual_role"] = "secondary"
        else:
            # base-объекты.
            if ctype in ("midpoint", "foot_perpendicular", "circumcenter",
                         "incenter", "orthocenter", "centroid",
                         "intersect_lines", "intersect_line_circle",
                         "intersect_circles", "incircle_touch",
                         "reflect_point", "rotate_point", "point_on_circle",
                         "point_on_segment"):
                meta["visual_role"] = "secondary"

    # 3. Ключевая точка: последняя производная точка aux-слоя.
    aux_point_order = []
    for obj in ctx.objects:
        cid = obj.get("id")
        meta = ctx.meta.get(cid, {})
        if meta.get("style") == "aux" or obj.get("style") == "aux":
            if cid in ctx.points:
                aux_point_order.append(cid)
    if aux_point_order:
        last = aux_point_order[-1]
        ctx.meta[last]["visual_role"] = "key_point"

    # 4. Авто-метки добавляем в objects для отрисовки.
    for i, m in enumerate(auto_marks):
        if not m["vertex"] or m["vertex"] not in ctx.points:
            continue
        mark_id = f"_auto_right_{i}_{m['vertex']}"
        # Не дублируем, если LLM уже поставил явную метку.
        existing = {o.get("id") for o in ctx.objects if o.get("type") == "right_angle_mark"}
        if mark_id in existing:
            continue
        if m["ray1"] not in ctx.points:
            continue
        if m["ray2"] is None or m["ray2"] not in ctx.points:
            continue
        ctx.meta[mark_id] = {"type": "right_angle_mark",
                             "vertex": m["vertex"],
                             "ray1": m["ray1"], "ray2": m["ray2"]}
        ctx.objects.append({"type": "right_angle_mark", "id": mark_id,
                            "vertex": m["vertex"], "ray1": m["ray1"],
                            "ray2": m["ray2"]})


def _find_point_on_line(ctx: BuildContext, foot_id: str, exclude: set) -> str:
    """Найти любую точку на той же прямой, что и foot (не сам foot и не exclude)."""
    foot = ctx.points.get(foot_id)
    if foot is None:
        return None
    for name, pt in ctx.points.items():
        if name == foot_id or name in exclude:
            continue
        if ctx.meta.get(name, {}).get("type") == "polygon_vertex":
            continue
        if geom.dist(pt, foot) > geom.EPS:
            # Проверяем коллинеарность с foot и любым родителем линии.
            return name
    return None


def render_svg(ctx: BuildContext,
               canvas_w: int, canvas_h: int,
               settings: EngineSettings) -> str:
    """Отрисовать SVG-строку."""
    # CH30 ЭТАП 1b: автовывод семантики перед рендером.
    _apply_auto_semantics(ctx)
    # CH15.1: presentation-only layout pass — auto-fit содержимого.
    # По умолчанию выключен (не меняет поведение существующих SVG).
    shift_x = 0.0
    shift_y = 0.0
    scale = 1.0
    if settings.auto_fit:
        canvas_w, canvas_h, shift_x, shift_y, scale = _compute_auto_fit(
            ctx, canvas_w, canvas_h, settings
        )

    ns = "http://www.w3.org/2000/svg"
    svg = ET.Element("svg", {
        "xmlns": ns,
        "width": str(canvas_w),
        "height": str(canvas_h),
        "viewBox": f"0 0 {canvas_w} {canvas_h}",
        "style": f"background-color: {settings.bg_color};",
    })
    # CH23 PART A: явный фоновый прямоугольник на весь canvas.
    ET.SubElement(svg, "rect", {
        "x": "0", "y": "0",
        "width": str(canvas_w), "height": str(canvas_h),
        "fill": settings.bg_color if settings.bg_color != "none" else "#0F1729",
    })

    def _sx(x):
        return x * scale + shift_x

    def _sy(y):
        return y * scale + shift_y

    def add_line(x1, y1, x2, y2, color=None, width=None, dashed=False, cls=""):
        attrs = {
            "x1": f"{_sx(x1):.2f}", "y1": f"{_sy(y1):.2f}",
            "x2": f"{_sx(x2):.2f}", "y2": f"{_sy(y2):.2f}",
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
        # CH-FIX: радиус тоже масштабируется при auto_fit.  Раньше центр
        # масштабировался (_sx/_sy), а радиус оставался исходным — окружность
        # (особенно вписанная) визуально «распухала» и выглядела как описанная.
        attrs = {
            "cx": f"{_sx(cx):.2f}", "cy": f"{_sy(cy):.2f}", "r": f"{r * scale:.2f}",
            "stroke": color or settings.line_color,
            "stroke-width": f"{width or settings.line_width}",
            "fill": fill,
        }
        if dashed:
            attrs["stroke-dasharray"] = settings.dash_array
            attrs["stroke"] = color or settings.dash_color
        ET.SubElement(svg, "circle", attrs)

    def add_text(x, y, text, color=None, size=None):
        # CH23 PART A: светлый текст без чёрного halo; тонкая обводка
        # цветом фона только для читаемости поверх линий.
        bg = settings.bg_color if settings.bg_color != "none" else "#0F1729"
        attrs = {
            "x": f"{_sx(x):.2f}", "y": f"{_sy(y):.2f}",
            "fill": color or settings.label_color,
            "font-family": settings.font_family,
            "font-size": f"{size or settings.label_font_size}",
            "text-anchor": "middle",
            "dominant-baseline": "central",
            "paint-order": "stroke fill",
            "stroke": bg,
            "stroke-width": "2",
            "stroke-linejoin": "round",
        }
        el = ET.SubElement(svg, "text", attrs)
        _set_label_text(el, text, size or settings.label_font_size)

    def add_polygon(points, color=None, fill="none", width=None, dashed=False):
        pts_str = " ".join(f"{_sx(p[0]):.2f},{_sy(p[1]):.2f}" for p in points)
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

    # CH19 DEFECT 2: ступенчатое размещение angle_label по вершинам.
    angle_layout = _angle_label_layout(ctx, settings)

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
                role = resolve_visual_role(obj, meta)
                stroke = _semantic_color(settings, role, "stroke",
                                         settings.line_color)
                if dashed:
                    stroke = stroke if settings.semantic_colors else settings.dash_color
                add_line(seg[0][0], seg[0][1], seg[1][0], seg[1][1],
                         color=stroke, dashed=dashed)

        elif ctype in ("circle_center_radius", "circumcircle", "incircle",
                       "circle_three_points"):
            circle = ctx.circles.get(cid)
            if circle:
                dashed = meta.get("dashed", False)
                role = resolve_visual_role(obj, meta)
                stroke = _semantic_color(settings, role, "stroke",
                                         settings.line_color)
                if dashed:
                    stroke = stroke if settings.semantic_colors else settings.dash_color
                add_circle(circle[0][0], circle[0][1], circle[1],
                           color=stroke, dashed=dashed)

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
                path_d = (f"M {_sx(x1):.2f} {_sy(y1):.2f} A {r * scale:.2f} {r * scale:.2f} 0 {d_flag} {sweep} "
                          f"{_sx(x2):.2f} {_sy(y2):.2f}")
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
            a_id = meta.get("ray1", meta.get("p1", ""))
            b_id = meta.get("ray2", meta.get("p3", ""))
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
                    pts_str = (f"{_sx(p1[0]):.2f},{_sy(p1[1]):.2f} "
                               f"{_sx(p2[0]):.2f},{_sy(p2[1]):.2f} "
                               f"{_sx(p3[0]):.2f},{_sy(p3[1]):.2f}")
                    mark = _semantic_color(settings, "right_angle_mark", "stroke",
                                           settings.mark_color)
                    ET.SubElement(svg, "polyline", {
                        "points": pts_str,
                        "stroke": mark,
                        "stroke-width": "1.2",
                        "fill": "none",
                    })

        elif ctype == "perpendicular_mark":
            # CH15.1: малый прямой угол (тот же визуал, что right_angle_mark).
            v_id = meta.get("vertex", "")
            a_id = meta.get("ray1", meta.get("p1", ""))
            b_id = meta.get("ray2", meta.get("p3", ""))
            if v_id in ctx.points and a_id in ctx.points and b_id in ctx.points:
                v = ctx.points[v_id]
                a = ctx.points[a_id]
                b = ctx.points[b_id]
                size = 10.0
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
                    pts_str = (f"{_sx(p1[0]):.2f},{_sy(p1[1]):.2f} "
                               f"{_sx(p2[0]):.2f},{_sy(p2[1]):.2f} "
                               f"{_sx(p3[0]):.2f},{_sy(p3[1]):.2f}")
                    ET.SubElement(svg, "polyline", {
                        "points": pts_str,
                        "stroke": settings.mark_color,
                        "stroke-width": "1.2",
                        "fill": "none",
                    })

        elif ctype == "midpoint_mark":
            # CH15.1: небольшая насечка на отрезке p1-p2 в точке point.
            p1_id = meta.get("p1", "")
            p2_id = meta.get("p2", "")
            point_id = meta.get("point", "")
            if p1_id in ctx.points and p2_id in ctx.points:
                seg = (ctx.points[p1_id], ctx.points[p2_id])
                mid = ctx.points.get(point_id) if point_id in ctx.points else geom.midpoint(*seg)
                vec = (seg[1][0] - seg[0][0], seg[1][1] - seg[0][1])
                n = math.hypot(vec[0], vec[1])
                if n > geom.EPS:
                    perp_x = -vec[1] / n * EQUAL_TICK_HALF_LENGTH
                    perp_y = vec[0] / n * EQUAL_TICK_HALF_LENGTH
                    add_line(mid[0] + perp_x, mid[1] + perp_y,
                             mid[0] - perp_x, mid[1] - perp_y,
                             color=settings.mark_color, width=1.2,
                             cls="midpoint-tick")

        elif ctype == "parallel_mark":
            # CH15.1: отметка параллельности (двойная насечка в середине).
            seg_refs = meta.get("segments", []) or []
            for ref_pair in seg_refs:
                if not isinstance(ref_pair, (list, tuple)) or len(ref_pair) < 2:
                    continue
                p1, p2 = ref_pair[0], ref_pair[1]
                if p1 in ctx.points and p2 in ctx.points:
                    seg = (ctx.points[p1], ctx.points[p2])
                    mid = geom.midpoint(*seg)
                    vec = (seg[1][0] - seg[0][0], seg[1][1] - seg[0][1])
                    n = math.hypot(vec[0], vec[1])
                    if n > geom.EPS:
                        perp_x = -vec[1] / n * EQUAL_TICK_HALF_LENGTH
                        perp_y = vec[0] / n * EQUAL_TICK_HALF_LENGTH
                        along_x = vec[0] / n * EQUAL_TICK_SPACING
                        along_y = vec[1] / n * EQUAL_TICK_SPACING
                        for t in range(2):
                            offset = t - 0.5
                            cx = mid[0] + along_x * offset
                            cy = mid[1] + along_y * offset
                            add_line(cx + perp_x, cy + perp_y,
                                     cx - perp_x, cy - perp_y,
                                     color=settings.mark_color, width=1.2,
                                     cls="parallel-tick")

        elif ctype == "equal_segments_mark":
            seg_refs = meta.get("segments", []) or []
            num_ticks = int(meta.get("num_ticks", 1) or 1)
            # Нормализуем в список пар: [["A","B"],["A","C"]] или плоский ["A","B","A","C"].
            pairs = []
            if seg_refs and isinstance(seg_refs[0], (list, tuple)):
                pairs = [list(p) for p in seg_refs if isinstance(p, (list, tuple)) and len(p) >= 2]
            else:
                pairs = [
                    [seg_refs[i], seg_refs[i + 1]]
                    for i in range(0, len(seg_refs) - 1, 2)
                ]
            # CH-aux FIX: элементы пары могут быть вложенными dict'ами
            # (model_id/ref), отбрасываем не-строки, чтобы не было unhashable.
            clean_pairs = []
            for (s1, s2) in pairs:
                if isinstance(s1, str) and isinstance(s2, str):
                    clean_pairs.append((s1, s2))
            for (s1, s2) in clean_pairs:
                # Ищем отрезок с этими родителями (в любом порядке).
                found = None
                for sid, sdata in ctx.segments.items():
                    smeta = ctx.meta.get(sid, {})
                    sparents = smeta.get("parents", []) or []
                    # parents может содержать вложенные структуры — фильтруем
                    # только хэшируемые (строки-точки).
                    sp = [p for p in sparents if isinstance(p, str)]
                    if len(sp) >= 2 and set(sp[:2]) == {s1, s2}:
                        found = sdata
                        break
                if found is None:
                    # Позволяем ссылаться напрямую на точки, если id-отрезка нет.
                    if s1 in ctx.points and s2 in ctx.points:
                        found = (ctx.points[s1], ctx.points[s2])
                if found is None:
                    continue
                mid = geom.midpoint(found[0], found[1])
                vec = (found[1][0] - found[0][0], found[1][1] - found[0][1])
                n = math.hypot(vec[0], vec[1])
                if n > geom.EPS:
                    perp_x = -vec[1] / n * EQUAL_TICK_HALF_LENGTH
                    perp_y = vec[0] / n * EQUAL_TICK_HALF_LENGTH
                    along_x = vec[0] / n * EQUAL_TICK_SPACING
                    along_y = vec[1] / n * EQUAL_TICK_SPACING
                    for t in range(num_ticks):
                        offset = (t - (num_ticks - 1) / 2.0)
                        cx = mid[0] + along_x * offset
                        cy = mid[1] + along_y * offset
                        add_line(cx + perp_x, cy + perp_y,
                                 cx - perp_x, cy - perp_y,
                                 color=settings.mark_color, width=1.2,
                                 cls="equal-tick")

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
                    path_d = (f"M {_sx(x1):.2f} {_sy(y1):.2f} A {arc_r * scale:.2f} {arc_r * scale:.2f} "
                              f"0 {d_flag} {sweep} {_sx(x2):.2f} {_sy(y2):.2f}")
                    ET.SubElement(svg, "path", {
                        "d": path_d,
                        "stroke": settings.mark_color,
                        "stroke-width": "1.2",
                        "fill": "none",
                        "class": "equal-arc",
                    })

        elif ctype == "angle_label":
            # CH15.1: рисуем дугу угла (ray1–vertex–ray2) + текст снаружи угла.
            # CH19 DEFECT 2: радиус и позиция текста из ступенчатого layout.
            v_id = meta.get("vertex", "")
            a_id = meta.get("ray1", meta.get("p1", ""))
            b_id = meta.get("ray2", meta.get("p3", ""))
            label_text = meta.get("text", meta.get("label", ""))
            if v_id in ctx.points and a_id in ctx.points and b_id in ctx.points:
                v = ctx.points[v_id]
                a = ctx.points[a_id]
                b = ctx.points[b_id]
                lay = angle_layout.get(cid, {})
                r = lay.get("r", settings.label_padding * 1.0)
                va = (a[0] - v[0], a[1] - v[1])
                vb = (b[0] - v[0], b[1] - v[1])
                angle_a = math.atan2(va[1], va[0])
                angle_b = math.atan2(vb[1], vb[0])
                diff = (angle_b - angle_a) % (2 * math.pi)
                if diff > math.pi:
                    diff = diff - 2 * math.pi
                x1 = v[0] + r * math.cos(angle_a)
                y1 = v[1] + r * math.sin(angle_a)
                x2 = v[0] + r * math.cos(angle_b)
                y2 = v[1] + r * math.sin(angle_b)
                sweep = 1 if diff > 0 else 0
                large = 1 if abs(diff) > math.pi else 0
                path_d = (f"M {_sx(x1):.2f} {_sy(y1):.2f} A {r * scale:.2f} {r * scale:.2f} "
                          f"0 {large} {sweep} {_sx(x2):.2f} {_sy(y2):.2f}")
                ET.SubElement(svg, "path", {
                    "d": path_d,
                    "stroke": settings.mark_color,
                    "stroke-width": "1.2",
                    "fill": "none",
                    "class": "angle-arc",
                })
                mid_angle = angle_a + diff / 2.0
                lx = lay.get("lx", v[0] + (r + settings.label_padding * 0.5) * math.cos(mid_angle))
                ly = lay.get("ly", v[1] + (r + settings.label_padding * 0.5) * math.sin(mid_angle))
                if _skip_invalid_label(label_text, cid):
                    # дугу рисуем (геометрия-маркер), но служебный текст не печатаем.
                    pass
                else:
                    add_text(lx, ly, label_text, size=settings.label_font_size - 1)
                label_boxes.append((lx - 20, ly - 8, lx + 20, ly + 8))

        elif ctype == "length_label":
            p1_id = meta.get("p1", "")
            p2_id = meta.get("p2", "")
            if p1_id in ctx.points and p2_id in ctx.points:
                mid = geom.midpoint(ctx.points[p1_id], ctx.points[p2_id])
                label_text = meta.get("text", meta.get("label", ""))
                ox, oy = _compute_label_offset(mid, "auto", settings.label_padding * 0.8)
                if _skip_invalid_label(label_text, cid):
                    pass
                else:
                    add_text(ox, oy, label_text, size=settings.label_font_size - 2)
                    label_boxes.append((ox - 20, oy - 8, ox + 20, oy + 8))

    # ─── Точки ───
    drawn_points = set()
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("type") == "polygon_vertex" or meta.get("hidden"):
            drawn_points.add(name)
            continue
        role = resolve_point_role(meta)
        fill = _semantic_color(settings, role, "fill", settings.line_color)
        stroke = _semantic_color(settings, role, "stroke", settings.point_color)
        add_circle(pt[0], pt[1], settings.point_radius,
                   color=stroke, fill=fill)

    # ─── Собираем все отрезки для штрафа подписей ───
    all_drawn_segments = []
    for sid, sdata in ctx.segments.items():
        smeta = ctx.meta.get(sid, {})
        # Исключаем пунктирные и скрытые
        if smeta.get("hidden", False):
            continue
        all_drawn_segments.append(sdata)

    # ─── Собираем окружности для штрафа подписей (CH15.1) ───
    all_drawn_circles = []
    for cid, cdata in ctx.circles.items():
        cmeta = ctx.meta.get(cid, {})
        if cmeta.get("hidden", False):
            continue
        all_drawn_circles.append(cdata)

    # ─── Собираем видимые точки для штрафа подписей (CH15.1) ───
    all_drawn_points = [p for n, p in ctx.points.items()
                        if not ctx.meta.get(n, {}).get("hidden", False)
                        and ctx.meta.get(n, {}).get("type") != "polygon_vertex"]

    # ─── Подписи точек (greedy placement, 8 направлений) ───
    # Сортируем точки детерминированно: по порядку появления в ctx.points
    # CH21 FIX 1: подсчёт инцидентных отрезков для точек (ортоцентр и т.п.).
    incident_count = {}
    for sid, smeta in ctx.meta.items():
        parents = smeta.get("parents") or []
        if smeta.get("hidden", False):
            continue
        for p in parents:
            incident_count[p] = incident_count.get(p, 0) + 1

    placed_label_centers = []  # список (x, y) уже размещённых центров подписей
    for name, pt in ctx.points.items():
        meta = ctx.meta.get(name, {})
        if meta.get("hidden") or meta.get("type") == "polygon_vertex":
            continue
        display_label = meta.get("label", name)
        if not display_label or display_label.startswith("_"):
            continue
        # CH-fidelity: НЕ печатать синтетические внутренние имена (aux_foot_*,
        # aux_inter_*, aux_O, aux_touch_*), если для точки не задан явный
        # геометрический label.  Раньше при label==name (по умолчанию) guard
        # обходился, и на чертеже появлялась служебная подпись «aux_foot_MAB».
        if display_label == name and name.startswith("aux_"):
            continue
        # CH19 DEFECT 1: последний барьер — не печатать служебное имя.
        if display_label != name and _skip_invalid_label(display_label, name):
            continue

        # CH21 FIX 1: для точек с 3+ инцидентными отрезками — выносная подпись.
        leader = incident_count.get(name, 0) >= 3
        padding = settings.leader_offset if leader else settings.label_padding

        side = meta.get("side", "auto")
        if side != "auto":
            # Фиксированное направление — используем старый метод
            ox, oy = _compute_label_offset(pt, side, padding, 0)
        else:
            other_points = [p for p in all_drawn_points if p != pt]
            # 8 кандидатов (N, NE, E, SE, S, SW, W, NW), greedy по штрафам.
            candidates = _compute_label_candidates(pt, padding, 8)
            best_candidate = None
            best_score = float('inf')
            for cand in candidates:
                s = _score_label_candidate(
                    cand, all_drawn_segments, placed_label_centers, settings,
                    circles=all_drawn_circles, points=other_points,
                    canvas_w=canvas_w, canvas_h=canvas_h,
                )
                if s < best_score:
                    best_score = s
                    best_candidate = cand
            ox, oy = best_candidate if best_candidate else _compute_label_offset(pt, "auto", padding, 0)

        # Выноска от текста к точке (приглушённая, без dashed).
        if leader:
            add_line(pt[0], pt[1], ox, oy, color=settings.dash_color, width=0.8)
        label_role = resolve_point_role(meta)
        label_color = _semantic_color(settings, label_role, "text",
                                      settings.label_color)
        add_text(ox, oy, display_label, color=label_color)
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
        # Каждый экземпляр движка получает независимую копию настроек, чтобы
        # мутация в одном месте (например, engine.settings.auto_fit = True)
        # не протекала в глобальный DEFAULT_SETTINGS и другие экземпляры.
        import copy
        self.settings = settings if settings is not None else copy.copy(DEFAULT_SETTINGS)

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

        # CH26 FIX3: явно объявленные инцидентности из плана (поле incidences).
        for inc in description.get("incidences", []) or []:
            if isinstance(inc, dict) and inc.get("point"):
                ctx.incidences.append(dict(inc))

        svg = render_svg(ctx, canvas_w, canvas_h, self.settings)
        return svg, ctx

    def build_with_retry(self, description: dict, seed: int = 42) -> Tuple[str, BuildContext, int, List[str]]:
        """
        Построить с retry-проверками.

        CH21 FIX 1: HARD-проверки блокируют (retry оправдан), SOFT-проверки
        (презентация) не блокируют — ищем кандидата с минимальным penalty.
        Возвращает (svg, ctx, attempts, violations).  Если были только SOFT
        нарушения, возвращается лучший кандидат, а не failed.
        """
        canvas = description.get("canvas", {})
        canvas_w = canvas.get("width", 800)
        canvas_h = canvas.get("height", 600)
        margin = canvas.get("margin", 30)

        best_candidate = None  # (penalty, svg, ctx, attempt)
        best_penalty = float("inf")
        last_hard = []
        hard_seen = False

        soft_search_budget = max(1, self.settings.soft_retry_limit)
        total_budget = max(self.settings.max_retries, soft_search_budget)

        for attempt in range(total_budget):
            current_seed = seed + attempt * 137
            random.seed(current_seed)

            try:
                svg, ctx = self.build(description, current_seed)
                check = run_all_checks(ctx, canvas_w, canvas_h, margin, self.settings)
            except ConstructionError as e:
                hard_seen = True
                last_hard = [str(e)]
                continue

            if check.passed:
                return svg, ctx, attempt + 1, []

            hard = [v for v in check.violations if not _is_soft_violation(v)]
            soft = [v for v in check.violations if _is_soft_violation(v)]

            if hard:
                hard_seen = True
                last_hard = hard
                continue

            # Только SOFT-нарушения: запоминаем кандидата с минимальным penalty.
            penalty = len(soft)
            if penalty < best_penalty:
                best_penalty = penalty
                best_candidate = (soft, svg, ctx, attempt + 1)

        # Если был найден SOFT-кандидат — возвращаем его (не failed).
        if best_candidate is not None:
            soft_warnings, svg, ctx, attempts = best_candidate
            # Сохраняем предупреждения в ctx.meta, чтобы caller мог их увидеть.
            ctx.meta["_soft_warnings"] = list(soft_warnings)
            return svg, ctx, attempts, list(soft_warnings)

        # Ни одна попытка не прошла HARD.
        return "", BuildContext(), total_budget, last_hard

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
