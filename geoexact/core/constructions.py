"""GeoExact: прямое исполнение конструкций плана (чистая аналитика, без итераций).

execute(plan, coords, free_values) -> dict[str, np.ndarray]

Каждая операция из schema.CONSTRUCTIONS вычисляется в замкнутой форме из уже
построенных точек. Свободные точки берут координаты из free_values (по 2 числа
на точку, в порядке появления free_point в plan.constructions).

Вырожденные конфигурации никогда не дают NaN: бросается PlanError("DEGENERATE").
"""
from __future__ import annotations

import math

import numpy as np

from .schema import (CONSTRUCTIONS, Construction, FigurePlan, PlanError,
                     validate_construction_value)

__all__ = ["execute", "count_free_points", "OPS"]

# абсолютный порог «нуля» и относительный порог вырожденности
_ABS_EPS = 1e-12
_REL_EPS = 1e-12


# ------------------------------------------------------------------ утилиты
def _v(p) -> np.ndarray:
    try:
        a = np.asarray(p, dtype=float)
        if a.shape != (2,):
            raise ValueError("ожидалась пара координат")
    except (TypeError, ValueError, OverflowError) as e:
        raise PlanError("BAD_COORDS", "координаты должны быть парой чисел") from e
    return _finite(a, "input")


def _norm(u: np.ndarray) -> float:
    return float(math.hypot(float(u[0]), float(u[1])))


def _cross(u: np.ndarray, v: np.ndarray) -> float:
    return float(u[0] * v[1] - u[1] * v[0])


def _dot(u: np.ndarray, v: np.ndarray) -> float:
    return float(u[0] * v[0] + u[1] * v[1])


def _perp(u: np.ndarray) -> np.ndarray:
    """Поворот на +90°."""
    return np.array([-u[1], u[0]], dtype=float)


def _unit(u: np.ndarray, what: str) -> np.ndarray:
    n = _norm(u)
    if n <= _ABS_EPS:
        raise PlanError("DEGENERATE", f"нулевой вектор в {what}")
    return u / n


def _need_distinct(a: np.ndarray, b: np.ndarray, what: str) -> None:
    if _norm(b - a) <= _ABS_EPS:
        raise PlanError("DEGENERATE", f"совпадающие точки в {what}")


def _root_index(value, what: str) -> int:
    if value is None or isinstance(value, bool) or value not in (0, 1):
        raise PlanError("BAD_VALUE", f"{what}: требуется value=0 или 1")
    return int(value)


def _finite(p: np.ndarray, op: str) -> np.ndarray:
    if not np.all(np.isfinite(p)):
        raise PlanError("DEGENERATE", f"{op}: получены неконечные координаты")
    return p


# ------------------------------------------------------------------ операции
def _midpoint(A, B, value=None):
    return 0.5 * (A + B)


def _divide_segment(A, B, value=None):
    t = float(value)
    return A + t * (B - A)


def _reflect_point(A, B, value=None):
    return 2.0 * B - A


def _reflect_line(A, B, C, value=None):
    """Reflection of point A in the infinite line BC."""
    return 2.0 * _foot(A, B, C) - A


def _homothety(A, B, value=None):
    return B + float(value) * (A - B)


def _foot(A, B, C, value=None):
    _need_distinct(B, C, "foot (прямая BC)")
    d = C - B
    t = _dot(A - B, d) / _dot(d, d)
    return B + t * d


def _perp_point(A, B, C, value=None):
    _need_distinct(B, C, "perp_point (прямая BC)")
    n = _perp(_unit(C - B, "perp_point"))
    return A + float(value) * n


def _circumcenter(A, B, C, value=None):
    scale = _triangle_scale(A, B, C, "circumcenter")
    # Local, normalized coordinates avoid cancellation under large translations.
    u, v = (B - A) / scale, (C - A) / scale
    d = 2.0 * _cross(u, v)
    su, sv = _dot(u, u), _dot(v, v)
    return A + scale * np.array([(su * v[1] - sv * u[1]) / d,
                                  (sv * u[0] - su * v[0]) / d])


def _triangle_scale(A, B, C, what: str) -> float:
    lengths = (_norm(B - A), _norm(C - A), _norm(C - B))
    scale = max(lengths)
    if min(lengths) <= _ABS_EPS or abs(_cross((B - A) / scale, (C - A) / scale)) <= _REL_EPS:
        raise PlanError("DEGENERATE", f"{what}: точки коллинеарны или совпадают")
    return scale


def _incenter(A, B, C, value=None):
    _triangle_scale(A, B, C, "incenter")
    a, b, c = _norm(C - B), _norm(C - A), _norm(B - A)
    s = a + b + c
    if s <= _ABS_EPS or min(a, b, c) <= _ABS_EPS:
        raise PlanError("DEGENERATE", "incenter: вырожденный треугольник")
    return (a * A + b * B + c * C) / s


def _centroid(A, B, C, value=None):
    return (A + B + C) / 3.0


def _orthocenter(A, B, C, value=None):
    O = _circumcenter(A, B, C)
    return A + B + C - 2.0 * O


def _excenter(A, B, C, value=None):
    """value 0/1/2 selects the excenter opposite A/B/C."""
    _triangle_scale(A, B, C, "excenter")
    weights = np.array([_norm(C - B), _norm(C - A), _norm(B - A)])
    weights[int(value)] *= -1
    denominator = float(weights.sum())
    if abs(denominator) <= _REL_EPS * float(np.abs(weights).sum()):
        raise PlanError("DEGENERATE", "excenter: центр на бесконечности")
    # Weighted local coordinates preserve translation accuracy.
    return A + (weights[1] * (B - A) + weights[2] * (C - A)) / denominator


def _ninepoint_center(A, B, C, value=None):
    O = _circumcenter(A, B, C)
    return A + 0.5 * ((B - A) + (C - A) - (O - A))


def _line_intersect(A, B, C, D, value=None):
    _need_distinct(A, B, "line_intersect (прямая AB)")
    _need_distinct(C, D, "line_intersect (прямая CD)")
    r, s = B - A, D - C
    den = _cross(r, s)
    if abs(den) <= max(_ABS_EPS, _REL_EPS * _norm(r) * _norm(s)):
        raise PlanError("DEGENERATE", "line_intersect: прямые параллельны или совпадают")
    t = _cross(C - A, s) / den
    return A + t * r


def _line_circle(A, B, C, D, value=None):
    """Пересечение прямой AB с окружностью (центр C, радиус |CD|).

    Корни упорядочены по возрастанию параметра t вдоль направления A->B.
    """
    k = _root_index(value, "line_circle")
    _need_distinct(A, B, "line_circle (прямая AB)")
    r = _norm(D - C)
    if r <= _ABS_EPS:
        raise PlanError("DEGENERATE", "line_circle: нулевой радиус")
    d = _unit(B - A, "line_circle")
    f = A - C
    b = _dot(d, f)
    cc = _dot(f, f) - r * r
    disc = b * b - cc
    if disc < -max(_ABS_EPS, _REL_EPS * r * r):
        raise PlanError("DEGENERATE", "line_circle: прямая не пересекает окружность")
    sq = math.sqrt(max(disc, 0.0))
    t = (-b - sq) if k == 0 else (-b + sq)
    return A + t * d


def _circle_circle(A, B, C, D, value=None):
    """Пересечение окружностей (A, |AB|) и (C, |CD|); корни по возрастанию
    проекции на нормаль к линии центров (сначала «минус», потом «плюс»)."""
    k = _root_index(value, "circle_circle")
    r1, r2 = _norm(B - A), _norm(D - C)
    if r1 <= _ABS_EPS or r2 <= _ABS_EPS:
        raise PlanError("DEGENERATE", "circle_circle: нулевой радиус")
    dv = C - A
    d = _norm(dv)
    tol = max(_ABS_EPS, _REL_EPS * max(r1, r2))
    if d <= _ABS_EPS:
        raise PlanError("DEGENERATE", "circle_circle: концентрические окружности")
    if d > r1 + r2 + tol or d < abs(r1 - r2) - tol:
        raise PlanError("DEGENERATE", "circle_circle: окружности не пересекаются")
    u = dv / d
    a = (d * d + r1 * r1 - r2 * r2) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < -max(_ABS_EPS, _REL_EPS * r1 * r1):
        raise PlanError("DEGENERATE", "circle_circle: нет точек пересечения")
    h = math.sqrt(max(h2, 0.0))
    base = A + a * u
    n = _perp(u)
    return base + (-h if k == 0 else h) * n


def _bisector_point(A, B, C, value=None):
    """Пересечение биссектрисы угла A треугольника ABC со стороной BC."""
    _triangle_scale(A, B, C, "bisector_point")
    c, b = _norm(B - A), _norm(C - A)
    if b <= _ABS_EPS or c <= _ABS_EPS:
        raise PlanError("DEGENERATE", "bisector_point: вырожденный угол")
    return B + (c / (c + b)) * (C - B)


def _external_bisector_point(A, B, C, value=None):
    _triangle_scale(A, B, C, "external_bisector_point")
    c, b = _norm(B - A), _norm(C - A)
    if abs(c - b) <= _REL_EPS * max(b, c):
        raise PlanError("DEGENERATE", "external_bisector_point: AB=AC, пересечение на бесконечности")
    return B + (c / (c - b)) * (C - B)


def _invert_point(A, B, C, value=None):
    """Inversion in circle (B, |BC|), so no absolute radius is introduced."""
    _need_distinct(A, B, "invert_point (центр инверсии)")
    _need_distinct(B, C, "invert_point (радиус)")
    d, r = _norm(A - B), _norm(C - B)
    return B + ((r / d) * r) * ((A - B) / d)


def _parallel_point(A, B, C, value=None):
    _need_distinct(B, C, "parallel_point (направление BC)")
    return A + float(value) * (C - B)


def _translate(A, B, C, value=None):
    return A + (C - B)


def _rotate(A, B, value=None):
    th = math.radians(float(value))
    ct, st = math.cos(th), math.sin(th)
    d = A - B
    return B + np.array([ct * d[0] - st * d[1], st * d[0] + ct * d[1]], dtype=float)


def _angle_ray(A, B, value=None):
    """Ray origin A, base direction AB, signed CCW angle in degrees; AP=AB."""
    _need_distinct(A, B, "angle_ray")
    return _rotate(B, A, value=value)


def _regular_polygon_vertex(A, B, value=None):
    """Given consecutive vertices A,B, return the next CCW n-gon vertex.

    value is the INTEGER NUMBER OF SIDES n, not an angle or vertex index.
    Repeated calls with the last pair traverse the polygon.
    """
    _need_distinct(A, B, "regular_polygon_vertex")
    return _rotate(B + (B - A), B, value=360.0 / float(value))


def _radical_axis_point(A, B, C, D, value=None):
    """Intersection of the radical axis with the line of centers A,C.

    Works for intersecting, tangent, nested and disjoint nonconcentric circles.
    """
    _need_distinct(A, B, "radical_axis_point (первый радиус)")
    _need_distinct(C, D, "radical_axis_point (второй радиус)")
    _need_distinct(A, C, "radical_axis_point (концентрические окружности)")
    d, r1, r2 = _norm(C - A), _norm(B - A), _norm(D - C)
    scale = max(d, r1, r2)
    dn, r1n, r2n = d / scale, r1 / scale, r2 / scale
    distance = scale * (dn * dn + (r1n - r2n) * (r1n + r2n)) / (2.0 * dn)
    return A + distance * ((C - A) / d)


def _tangent_point(A, B, C, value=None):
    """Точка касания прямой из A к окружности (центр B, радиус |BC|).

    Корни упорядочены по возрастанию проекции на нормаль к BA.
    """
    k = _root_index(value, "tangent_point")
    r = _norm(C - B)
    if r <= _ABS_EPS:
        raise PlanError("DEGENERATE", "tangent_point: нулевой радиус")
    dv = A - B
    d = _norm(dv)
    if d < r - max(_ABS_EPS, _REL_EPS * r):
        raise PlanError("DEGENERATE", "tangent_point: точка внутри окружности")
    u = dv / d
    cos_a = min(1.0, r / d)
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    n = _perp(u)
    return B + r * (cos_a * u + (-sin_a if k == 0 else sin_a) * n)


# соответствие имён из CONSTRUCTIONS реализациям (free_point обрабатывается отдельно)
OPS = {
    "midpoint": _midpoint,
    "divide_segment": _divide_segment,
    "reflect_point": _reflect_point,
    "foot": _foot,
    "perp_point": _perp_point,
    "circumcenter": _circumcenter,
    "incenter": _incenter,
    "centroid": _centroid,
    "orthocenter": _orthocenter,
    "line_intersect": _line_intersect,
    "line_circle": _line_circle,
    "circle_circle": _circle_circle,
    "bisector_point": _bisector_point,
    "parallel_point": _parallel_point,
    "translate": _translate,
    "rotate": _rotate,
    "tangent_point": _tangent_point,
    "reflect_line": _reflect_line,
    "homothety": _homothety,
    "excenter": _excenter,
    "external_bisector_point": _external_bisector_point,
    "invert_point": _invert_point,
    "angle_ray": _angle_ray,
    "regular_polygon_vertex": _regular_polygon_vertex,
    "ninepoint_center": _ninepoint_center,
    "radical_axis_point": _radical_axis_point,
}

assert set(OPS) | {"free_point"} == set(CONSTRUCTIONS), "реализованы не все конструкции"


# ------------------------------------------------------------------ исполнение
def count_free_points(plan: FigurePlan) -> int:
    return sum(1 for c in plan.constructions
               if (c.op if isinstance(c, Construction) else c.get("op")) == "free_point")


def execute(plan: FigurePlan,
            coords: dict[str, np.ndarray] | None = None,
            free_values: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Исполняет plan.constructions по порядку и возвращает координаты точек."""
    out: dict[str, np.ndarray] = {}
    if coords:
        for k, p in coords.items():
            out[k] = _v(p)

    try:
        fv = np.asarray(free_values, dtype=float).ravel() if free_values is not None else np.empty(0)
    except (TypeError, ValueError, OverflowError) as e:
        raise PlanError("BAD_FREE_VALUES", "координаты должны быть числами") from e
    need = 2 * count_free_points(plan)
    if fv.size < need:
        raise PlanError("BAD_FREE_VALUES",
                        f"нужно {need} чисел на свободные точки, получено {fv.size}")
    if not np.all(np.isfinite(fv)):
        raise PlanError("DEGENERATE", "неконечные координаты свободных точек")

    fi = 0
    for i, c in enumerate(plan.constructions):
        if not isinstance(c, Construction):  # допускаем dict из JSON
            c = Construction(**c)
        spec = CONSTRUCTIONS.get(c.op)
        if spec is None:
            raise PlanError("UNKNOWN_CONSTRUCTION", f"[{i}] неизвестная конструкция {c.op!r}")
        name = c.out
        if not name:
            raise PlanError("NO_OUT", f"[{i}] {c.op} без out")
        validate_construction_value(c.op, c.value)
        if len(c.args) != spec["args"]:
            raise PlanError("ARITY", f"[{i}] {c.op} ждёт {spec['args']} аргументов")

        if c.op == "free_point":
            out[name] = fv[2 * fi:2 * fi + 2].copy()
            fi += 1
            continue

        args = []
        for a in c.args:
            if a not in out:
                raise PlanError("FORWARD_REF", f"[{i}] {c.op}: точка {a!r} ещё не построена")
            args.append(out[a])
        if len(args) != spec["args"]:
            raise PlanError("ARITY", f"[{i}] {c.op} ждёт {spec['args']} аргументов")
        if spec.get("value") and c.value is None:
            raise PlanError("NO_VALUE", f"[{i}] {c.op} требует value")

        p = OPS[c.op](*args, value=c.value)
        out[name] = _finite(np.asarray(p, dtype=float).reshape(2), c.op)

    return out
