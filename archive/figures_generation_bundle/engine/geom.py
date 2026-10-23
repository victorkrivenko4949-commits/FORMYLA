"""
geom.py — геометрические вычисления (чистый Python, только stdlib).
Никаких внешних библиотек. Без numpy, без matplotlib.
Все вычисления на math + встроенные типы.

Тип Point: (x: float, y: float) — кортеж из двух float.
Тип Line:  (A, B, C) — коэффициенты прямой Ax + By + C = 0.
Тип Segment: (p1: Point, p2: Point)
Тип Circle: (center: Point, r: float)
"""

import math
from typing import Tuple, List, Optional, Union

# ─── базовые типы ───────────────────────────────────────────────
Point = Tuple[float, float]
Line = Tuple[float, float, float]  # Ax + By + C = 0
Segment = Tuple[Point, Point]
Circle = Tuple[Point, float]

EPS = 1e-9

# ─── вспомогательные функции ────────────────────────────────────

def dist2(a: Point, b: Point) -> float:
    """Квадрат расстояния между двумя точками."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def dist(a: Point, b: Point) -> float:
    """Расстояние между двумя точками."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint(a: Point, b: Point) -> Point:
    """Середина отрезка AB."""
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def point_on_segment(a: Point, b: Point, t: float) -> Point:
    """
    Точка на отрезке AB в заданном отношении:
    t=0 -> A, t=1 -> B, t=0.5 -> середина.
    """
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def line_through_points(p1: Point, p2: Point) -> Line:
    """Прямая через две различные точки. Ax + By + C = 0."""
    A = p1[1] - p2[1]
    B = p2[0] - p1[0]
    C = p1[0] * p2[1] - p2[0] * p1[1]
    # нормализация: первый ненулевой коэффициент > 0
    norm = math.hypot(A, B)
    if norm < EPS:
        raise ValueError("Точки совпадают, прямая не определена")
    return (A / norm, B / norm, C / norm)


def perpendicular_through_point(line: Line, p: Point) -> Line:
    """Прямая, перпендикулярная данной и проходящая через точку p."""
    A, B, _ = line
    # перпендикуляр: Bx - Ay + C' = 0
    C = -B * p[0] + A * p[1]
    norm = math.hypot(B, -A)
    return (B / norm, -A / norm, C / norm)


def intersect_lines(l1: Line, l2: Line) -> Optional[Point]:
    """Пересечение двух прямых. None если параллельны."""
    A1, B1, C1 = l1
    A2, B2, C2 = l2
    det = A1 * B2 - A2 * B1
    if abs(det) < EPS:
        return None
    x = (B1 * C2 - B2 * C1) / det
    y = (C1 * A2 - C2 * A1) / det
    return (x, y)


def foot_of_perpendicular(p: Point, line: Line) -> Point:
    """Основание перпендикуляра из точки p на прямую."""
    perp = perpendicular_through_point(line, p)
    result = intersect_lines(line, perp)
    assert result is not None
    return result


def reflect_point_over_point(p: Point, center: Point) -> Point:
    """Отражение точки p относительно точки center."""
    return (2 * center[0] - p[0], 2 * center[1] - p[1])


def reflect_point_over_line(p: Point, line: Line) -> Point:
    """Отражение точки p относительно прямой."""
    foot = foot_of_perpendicular(p, line)
    return reflect_point_over_point(p, foot)


def intersect_line_circle(line: Line, circle: Circle) -> List[Point]:
    """
    Пересечение прямой и окружности.
    Возвращает 0, 1 или 2 точки.
    """
    A, B, C = line
    cx, cy = circle[0]
    r = circle[1]

    # расстояние от центра до прямой
    d = abs(A * cx + B * cy + C) / math.hypot(A, B)
    if d > r + EPS:
        return []

    # основание перпендикуляра из центра на прямую
    foot = foot_of_perpendicular(circle[0], line)

    if d > r - EPS:
        return [foot]

    # две точки
    h = math.sqrt(max(0, r * r - d * d))
    # направляющий вектор прямой: (-B, A)
    length = math.hypot(A, B)
    dx = -B / length
    dy = A / length
    return [
        (foot[0] + h * dx, foot[1] + h * dy),
        (foot[0] - h * dx, foot[1] - h * dy),
    ]


def intersect_circles(c1: Circle, c2: Circle) -> List[Point]:
    """
    Пересечение двух окружностей.
    Возвращает 0, 1 или 2 точки.
    """
    o1, r1 = c1
    o2, r2 = c2
    d = dist(o1, o2)

    if d < EPS:
        return []  # концентрические

    if d > r1 + r2 + EPS or d < abs(r1 - r2) - EPS:
        return []

    if abs(d - r1 - r2) < EPS or abs(d - abs(r1 - r2)) < EPS:
        # одна точка касания
        t = r1 / (r1 + r2) if abs(d - r1 - r2) < EPS else r1 / (r1 - r2)
        return [(o1[0] + t * (o2[0] - o1[0]), o1[1] + t * (o2[1] - o1[1]))]

    # две точки
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(0, r1 * r1 - a * a))
    mid = (o1[0] + a * (o2[0] - o1[0]) / d, o1[1] + a * (o2[1] - o1[1]) / d)
    rx = -(o2[1] - o1[1]) * h / d
    ry = (o2[0] - o1[0]) * h / d

    return [(mid[0] + rx, mid[1] + ry), (mid[0] - rx, mid[1] - ry)]


def angle_between(v1: Point, v2: Point) -> float:
    """Угол между двумя векторами в радианах (0..pi)."""
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 < EPS or n2 < EPS:
        return 0.0
    cos_a = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.acos(cos_a)


def angle_between_three(a: Point, b: Point, c: Point) -> float:
    """Угол ABC (в точке B)."""
    return angle_between((a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1]))


def circumcenter(a: Point, b: Point, c: Point) -> Optional[Point]:
    """Центр описанной окружности треугольника ABC."""
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < EPS:
        return None
    ux = ((a[0]**2 + a[1]**2) * (b[1] - c[1]) +
          (b[0]**2 + b[1]**2) * (c[1] - a[1]) +
          (c[0]**2 + c[1]**2) * (a[1] - b[1])) / d
    uy = ((a[0]**2 + a[1]**2) * (c[0] - b[0]) +
          (b[0]**2 + b[1]**2) * (a[0] - c[0]) +
          (c[0]**2 + c[1]**2) * (b[0] - a[0])) / d
    return (ux, uy)


def incenter(a: Point, b: Point, c: Point) -> Optional[Point]:
    """Центр вписанной окружности треугольника ABC."""
    ab = dist(a, b)
    bc = dist(b, c)
    ca = dist(c, a)
    perimeter = ab + bc + ca
    if perimeter < EPS:
        return None
    ix = (bc * a[0] + ca * b[0] + ab * c[0]) / perimeter
    iy = (bc * a[1] + ca * b[1] + ab * c[1]) / perimeter
    return (ix, iy)


def centroid(a: Point, b: Point, c: Point) -> Point:
    """Точка пересечения медиан (центроид)."""
    return ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)


def orthocenter(a: Point, b: Point, c: Point) -> Optional[Point]:
    """Ортоцентр треугольника ABC."""
    cent = circumcenter(a, b, c)
    if cent is None:
        return None
    g = centroid(a, b, c)
    # H = 3G - 2O
    return (3 * g[0] - 2 * cent[0], 3 * g[1] - 2 * cent[1])


def incircle_touch_point(a: Point, b: Point, c: Point) -> Point:
    """
    Точка касания вписанной окружности со стороной BC.
    Возвращает точку на отрезке BC.
    """
    ab = dist(a, b)
    ca = dist(c, a)
    # расстояние от B до точки касания на BC
    s = (ab + dist(b, c) + ca) / 2.0
    t = (s - ca) / dist(b, c) if dist(b, c) > EPS else 0.5
    return point_on_segment(b, c, t)


def angle_bisector_line(a: Point, b: Point, c: Point) -> Line:
    """
    Прямая — биссектриса угла ABC (из вершины B).
    Возвращает прямую через B и точку на биссектрисе.
    """
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])
    n_ba = math.hypot(ba[0], ba[1])
    n_bc = math.hypot(bc[0], bc[1])
    if n_ba < EPS or n_bc < EPS:
        # Вырожденный угол (вершина совпадает с одной из сторон).  Не падаем:
        # возвращаем прямую вдоль невырожденного луча (или горизонтальную).
        if n_ba >= EPS:
            return line_through_points(b, a)
        if n_bc >= EPS:
            return line_through_points(b, c)
        return (0.0, 1.0, -b[1])  # горизонталь через вершину
    direction = (ba[0] / n_ba + bc[0] / n_bc, ba[1] / n_ba + bc[1] / n_bc)
    n_dir = math.hypot(direction[0], direction[1])
    if n_dir < EPS:
        # угол 180°, биссектриса — перпендикуляр
        direction = (-ba[1] / n_ba, ba[0] / n_ba)
    else:
        direction = (direction[0] / n_dir, direction[1] / n_dir)
    p2 = (b[0] + direction[0], b[1] + direction[1])
    return line_through_points(b, p2)


def perpendicular_bisector(a: Point, b: Point) -> Line:
    """Серединный перпендикуляр отрезка AB."""
    mid = midpoint(a, b)
    line_ab = line_through_points(a, b)
    return perpendicular_through_point(line_ab, mid)


def circle_from_three_points(a: Point, b: Point, c: Point) -> Optional[Circle]:
    """Окружность по трём точкам."""
    center = circumcenter(a, b, c)
    if center is None:
        return None
    r = dist(center, a)
    return (center, r)


def tangent_from_point_to_circle(p: Point, circle: Circle) -> List[Line]:
    """
    Касательные из точки p к окружности. Возвращает 0, 1 или 2 прямые.
    """
    c, r = circle
    d = dist(p, c)
    if d < r - EPS:
        return []
    if d < r + EPS:
        # точка на окружности
        line_cp = line_through_points(c, p)
        return [perpendicular_through_point(line_cp, p)]

    # две касательные
    # угол между CP и касательной
    alpha = math.asin(r / d)
    cp_vec = (c[0] - p[0], c[1] - p[1])
    cp_angle = math.atan2(cp_vec[1], cp_vec[0])

    lines = []
    for sign in (1.0, -1.0):
        t_angle = cp_angle + sign * alpha
        t_dir = (math.cos(t_angle), math.sin(t_angle))
        t_point = (p[0] + t_dir[0], p[1] + t_dir[1])
        lines.append(line_through_points(p, t_point))
    return lines


def tangent_at_point(p: Point, circle: Circle) -> Optional[Line]:
    """Касательная к окружности в точке, лежащей на ней."""
    c, r = circle
    if abs(dist(p, c) - r) > EPS:
        return None
    line_cp = line_through_points(c, p)
    return perpendicular_through_point(line_cp, p)


def regular_polygon(n: int, center: Point, radius: float, start_angle: float = 0.0) -> List[Point]:
    """
    Вершины правильного n-угольника.
    Центр в center, радиус описанной окружности = radius, начальный угол start_angle.
    """
    vertices = []
    for i in range(n):
        angle = start_angle + 2 * math.pi * i / n
        vertices.append((center[0] + radius * math.cos(angle),
                         center[1] + radius * math.sin(angle)))
    return vertices


def rotate_point(p: Point, center: Point, angle_rad: float) -> Point:
    """Повернуть точку p вокруг center на angle_rad радиан.

    Формула стандартная (x' = x·cos − y·sin, y' = x·sin + y·cos).
    В SVG ось Y направлена вниз, поэтому положительный угол даёт поворот
    ПО ЧАСОВОЙ стрелке (визуально).  Длина от центра сохраняется.
    """
    dx = p[0] - center[0]
    dy = p[1] - center[1]
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (
        center[0] + dx * cos_a - dy * sin_a,
        center[1] + dx * sin_a + dy * cos_a,
    )


def signed_angle(a: Point, center: Point, c: Point) -> float:
    """Ориентированный угол от вектора (center→a) к (center→c), радианы.

    Положительный, если поворот от a к c идёт в том же направлении, что и
    rotate_point с положительным углом (в SVG — по часовой стрелке).
    """
    v1 = (a[0] - center[0], a[1] - center[1])
    v2 = (c[0] - center[0], c[1] - center[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    return math.atan2(cross, dot)


def triangle_area(a: Point, b: Point, c: Point) -> float:
    """Площадь треугольника (по абсолютной величине)."""
    return 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def point_to_line_distance(p: Point, line: Line) -> float:
    """Расстояние от точки до прямой."""
    A, B, C = line
    return abs(A * p[0] + B * p[1] + C) / math.hypot(A, B)


def collinear(a: Point, b: Point, c: Point) -> bool:
    """Проверка: три точки лежат на одной прямой."""
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) < EPS


def points_equal(a: Point, b: Point) -> bool:
    """Проверка совпадения двух точек."""
    return dist(a, b) < EPS


def segment_contains_point(seg: Segment, p: Point) -> bool:
    """Проверяет, лежит ли точка p на отрезке seg."""
    a, b = seg
    if not collinear(a, b, p):
        return False
    d_ab = dist(a, b)
    d_ap = dist(a, p)
    d_pb = dist(p, b)
    return abs(d_ap + d_pb - d_ab) < EPS


def point_to_segment_distance(p: Point, seg: Segment) -> float:
    """
    Минимальное расстояние от точки p до отрезка seg.
    Возвращает расстояние в пикселях.
    """
    a, b = seg
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if abs(dx) < EPS and abs(dy) < EPS:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    proj_x = a[0] + t * dx
    proj_y = a[1] + t * dy
    return dist(p, (proj_x, proj_y))
