"""GeoExact: ДВА НЕЗАВИСИМЫХ ГЕЙТА (этапы 7 и 8 конвейера).

Главная идея: малая невязка решателя НЕ доказывает пригодность чертежа.

* ``gate_correctness`` — геометрическая ИСТИНА: конечность координат, невязка
  КАЖДОГО ограничения по отдельности, инцидентность, невырожденность,
  плюс измерение цели ``plan.target``.
* ``gate_readability`` — НАГЛЯДНОСТЬ: «щепки», пропорции, слипание подписей.
  Правильный, но вырожденно-плоский чертёж проходит первый гейт и валится на втором.

Чистый Python + numpy. Ни сети, ни LLM. ``Solution`` импортируется лениво,
поэтому модуль грузится даже если ``solver.py`` ещё не написан.
"""
from __future__ import annotations

import math
import ast
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Sequence

import numpy as np

from .schema import FigurePlan, PlanError, validate_plan

if TYPE_CHECKING:  # pragma: no cover - только для типов, в рантайме не нужно
    from .solver import Solution

# ---------------------------------------------------------------- пороги
COORD_ABS_MAX = 1e9          # координата больше — считаем расходимостью
CONSTRAINT_TOL = 1e-4        # нормированная невязка КАЖДОГО ограничения
INCIDENCE_TOL = 1e-5         # относительная (к габариту) невязка инцидентности
COINCIDE_TOL = 1e-6          # две точки совпали: dist <= 1e-6 * габарит
ZERO_AREA_TOL = 1e-9         # площадь треугольника / габарит^2
MIN_HULL_ANGLE_DEG = 12.0    # «щепка»: минимальный угол выпуклой оболочки
ASPECT_MIN, ASPECT_MAX = 0.2, 5.0
MIN_POINT_DIST_FRAC = 0.04   # 4 % габарита между любыми двумя точками
MIN_POINT_LINE_FRAC = 0.03   # 3 % габарита от точки до НЕ инцидентной прямой
COINCIDE_VISUAL_FRAC = 0.008  # ниже этого точка визуально сливается с прямой -> жёсткий отказ
EXACT_INCIDENCE_FRAC = 1e-5   # точная инцидентность: геометрия, а не проблема


@dataclass
class GateResult:
    ok: bool
    score: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    measured: float | None = None

    def __bool__(self) -> bool:  # удобство: if gate: ...
        return self.ok


# ---------------------------------------------------------------- геометрия
def _coords(sol: Any) -> dict[str, np.ndarray]:
    raw = getattr(sol, "coords", None) or {}
    out = {}
    for k, v in raw.items():
        try:
            a = np.asarray(v, dtype=float)
            out[k] = a if a.shape == (2,) else np.array([math.nan, math.nan])
        except (TypeError, ValueError, OverflowError):
            out[k] = np.array([math.nan, math.nan])
    return out


def _span(P: dict[str, np.ndarray]) -> float:
    """Габарит чертежа = max(width, height); никогда не ноль."""
    if not P:
        return 1.0
    A = np.array(list(P.values()), dtype=float)
    A = A[np.isfinite(A).all(axis=1)]
    if len(A) == 0:
        return 1.0
    w, h = (A.max(axis=0) - A.min(axis=0)).tolist()
    return max(w, h, 1e-12)


def _d(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.hypot(*(np.asarray(a, float) - np.asarray(b, float))))


def _cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _tri_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return abs(_cross(a, b, c)) / 2.0


def _angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Угол ABC при вершине B, в градусах."""
    u, v = np.asarray(a, float) - b, np.asarray(c, float) - b
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-15 or nv < 1e-15:
        return float("nan")
    cosv = float(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))
    return math.degrees(math.acos(cosv))


def _point_line_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Расстояние от p до бесконечной прямой AB."""
    L = _d(a, b)
    if L < 1e-15:
        return _d(p, a)
    return abs(_cross(a, b, p)) / L


def _point_seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    a, b, p = map(lambda x: np.asarray(x, float), (a, b, p))
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-30:
        return _d(p, a)
    t = float(np.clip(((p - a) @ ab) / L2, 0.0, 1.0))
    return _d(p, a + t * ab)


def _circumcircle(a, b, c):
    """(центр, радиус) описанной окружности или (None, None) для вырожденного случая."""
    d = 2.0 * _cross(a, b, c)
    if abs(d) < 1e-18:
        return None, None
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(c[0]), float(c[1])
    ux = ((ax ** 2 + ay ** 2) * (by - cy) + (bx ** 2 + by ** 2) * (cy - ay)
          + (cx ** 2 + cy ** 2) * (ay - by)) / d
    uy = ((ax ** 2 + ay ** 2) * (cx - bx) + (bx ** 2 + by ** 2) * (ax - cx)
          + (cx ** 2 + cy ** 2) * (bx - ax)) / d
    O = np.array([ux, uy])
    return O, _d(O, a)


def convex_hull(pts: Sequence[np.ndarray]) -> list[np.ndarray]:
    """Обход Эндрю (monotone chain). Возвращает вершины оболочки против ч.с."""
    P = sorted({(round(float(p[0]), 12), round(float(p[1]), 12)) for p in pts})
    if len(P) < 3:
        return [np.array(p) for p in P]
    def build(seq):
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2 and _cross(np.array(out[-2]), np.array(out[-1]), np.array(p)) <= 1e-15:
                out.pop()
            out.append(p)
        return out
    lower, upper = build(P), build(reversed(P))
    hull = lower[:-1] + upper[:-1]
    return [np.array(p) for p in hull] or [np.array(p) for p in P]


def min_hull_angle(pts: Sequence[np.ndarray]) -> float:
    """Минимальный внутренний угол выпуклой оболочки, градусы. Детектор «щепки»."""
    H = convex_hull(pts)
    if len(H) < 3:
        return 0.0
    n = len(H)
    return min(_angle_deg(H[(i - 1) % n], H[i], H[(i + 1) % n]) for i in range(n))


# ---------------------------------------------------------------- невязки ограничений
def constraint_residual(ctype: str, pts: list[np.ndarray], value: float | None,
                        span: float) -> float:
    """Нормированная (безразмерная) невязка одного ограничения."""
    s = max(span, 1e-12)
    v = 0.0 if value is None else float(value)

    if ctype == "dist":
        return abs(_d(pts[0], pts[1]) - v) / max(abs(v), s, 1e-12)
    if ctype == "dist_eq":
        return abs(_d(pts[0], pts[1]) - _d(pts[2], pts[3])) / s
    if ctype == "dist_ratio":
        return abs(_d(pts[0], pts[1]) - v * _d(pts[2], pts[3])) / s
    if ctype == "angle":
        return abs(_angle_deg(pts[0], pts[1], pts[2]) - v) / 180.0
    if ctype == "angle_eq":
        return abs(_angle_deg(pts[0], pts[1], pts[2]) - _angle_deg(pts[3], pts[4], pts[5])) / 180.0
    if ctype == "collinear":
        L1, L2 = _d(pts[0], pts[1]), _d(pts[0], pts[2])
        if L1 < 1e-15 or L2 < 1e-15:
            return 0.0
        return abs(_cross(pts[0], pts[1], pts[2])) / (L1 * L2)
    if ctype == "perpendicular":
        u, w = pts[1] - pts[0], pts[3] - pts[2]
        nu, nw = np.linalg.norm(u), np.linalg.norm(w)
        if nu < 1e-15 or nw < 1e-15:
            return 1.0
        return abs(float(u @ w)) / (nu * nw)
    if ctype == "parallel":
        u, w = pts[1] - pts[0], pts[3] - pts[2]
        nu, nw = np.linalg.norm(u), np.linalg.norm(w)
        if nu < 1e-15 or nw < 1e-15:
            return 1.0
        return abs(float(u[0] * w[1] - u[1] * w[0])) / (nu * nw)
    if ctype == "concyclic":
        O, R = _circumcircle(pts[0], pts[1], pts[2])
        if O is None:
            return 1.0
        return abs(_d(O, pts[3]) - R) / s
    if ctype == "on_circle":
        return abs(_d(pts[0], pts[1]) - _d(pts[2], pts[3])) / s
    if ctype == "area":
        a = _tri_area(pts[0], pts[1], pts[2])
        return abs(a - v) / max(abs(v), s * s, 1e-12)
    if ctype == "on_segment":
        length = _d(pts[1], pts[2])
        if length <= 1e-15:
            return 1.0
        return _point_seg_dist(pts[0], pts[1], pts[2]) / length
    if ctype in ("same_side", "opposite_side"):
        a, b, c, d = pts
        if _d(c, d) <= 1e-15:
            return 1.0
        product = _cross(c, d, a) * _cross(c, d, b)
        satisfied = product > 0 if ctype == "same_side" else product < 0
        return 0.0 if satisfied else 1.0
    return float("inf")


def numeric_mark_value(text: str, *, angle: bool = False) -> float | None:
    """Parse a standalone numeric measurement without executing arbitrary text.

    Supports decimals (including comma), fractions, arithmetic, sqrt/√ and π.
    Conventional unit suffixes are decorative: the plan has one common length
    unit, so this is NOT a physical-unit conversion facility. Symbolic labels
    such as x, a, x+1 remain unverified, not incorrectly interpreted as numbers.
    """
    if not isinstance(text, str) or len(text) > 128:
        return None
    s = text.strip().replace("−", "-").replace(",", ".")
    if angle:
        s = re.sub(r"(?:°|deg|degrees?|град(?:усов|уса)?\.?)\s*$", "", s, flags=re.I)
    else:
        s = re.sub(r"\s*(?:mm|cm|km|m|мм|см|км|м)\s*$", "", s, flags=re.I)
    s = s.replace("π", "pi").replace("^", "**").replace("×", "*").replace("·", "*")
    s = re.sub(r"\\sqrt\{([0-9.]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"√\s*([0-9.]+)", r"sqrt(\1)", s).replace("√(", "sqrt(")
    s = re.sub(r"(?<=[0-9)])(?=sqrt|pi)", "*", s)
    try:
        tree = ast.parse(s.strip(), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 40:
            return None

        def number(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return float(node.value)
            if isinstance(node, ast.Name) and node.id == "pi":
                return math.pi
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return number(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" \
                    and len(node.args) == 1 and not node.keywords:
                return math.sqrt(number(node.args[0]))
            if isinstance(node, ast.BinOp):
                a, b = number(node.left), number(node.right)
                if isinstance(node.op, ast.Add):
                    return a + b
                if isinstance(node.op, ast.Sub):
                    return a - b
                if isinstance(node.op, ast.Mult):
                    return a * b
                if isinstance(node.op, ast.Div):
                    return a / b
                if isinstance(node.op, ast.Pow) and abs(b) <= 16:
                    return a ** b
            raise ValueError("symbolic")

        value = number(tree.body)
        return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def measure_target(plan: FigurePlan, P: dict[str, np.ndarray]) -> float | None:
    """Считает plan.target на построенном чертеже."""
    t = plan.target
    if t.kind == "none":
        return None
    try:
        q = [P[a] for a in t.args]
    except KeyError:
        return None
    if t.kind == "dist":
        return _d(q[0], q[1])
    if t.kind == "angle":
        return _angle_deg(q[0], q[1], q[2])
    if t.kind == "area":
        return _tri_area(q[0], q[1], q[2])
    if t.kind == "ratio":
        den = _d(q[2], q[3])
        return float("inf") if den < 1e-15 else _d(q[0], q[1]) / den
    return None


# ---------------------------------------------------------------- инцидентность
def _incidence_claims(plan: FigurePlan) -> tuple[list[tuple[str, str, str]],
                                                 list[tuple[str, str, float | None, str]]]:
    """Что именно объявлено лежащим на прямой / окружности.

    Возвращает (on_line, on_circle):
      on_line   = [(P, A, B)]                — P на прямой AB
      on_circle = [(P, C, R_ref_or_None, D)] — P на окружности (центр C, радиус |C D|)
    """
    on_line: list[tuple[str, str, str]] = []
    on_circle: list[tuple[str, str, float | None, str]] = []

    for c in plan.constraints:
        a = c.args
        if c.type == "collinear":
            on_line.append((a[2], a[0], a[1]))
        elif c.type == "on_segment":
            on_line.append((a[0], a[1], a[2]))
        # on_circle radius is |CD|, not |BD|. The constraint checker above
        # verifies the actual four-point condition; do not invent incidence
        # with the wrong radius.

    for c in plan.constructions:
        a, out = c.args, c.out
        if not out:
            continue
        if c.op in ("midpoint", "divide_segment"):
            on_line.append((out, a[0], a[1]))
        elif c.op == "foot":
            on_line.append((out, a[1], a[2]))
        elif c.op in ("bisector_point", "external_bisector_point"):
            on_line.append((out, a[1], a[2]))
        elif c.op in ("homothety", "invert_point"):
            on_line.append((out, a[0], a[1]))
        elif c.op == "radical_axis_point":
            on_line.append((out, a[0], a[2]))
        elif c.op == "line_intersect":
            on_line.append((out, a[0], a[1]))
            on_line.append((out, a[2], a[3]))
        elif c.op == "line_circle":
            on_line.append((out, a[0], a[1]))
            on_circle.append((out, a[2], None, a[3]))
        elif c.op == "circle_circle":
            on_circle.append((out, a[0], None, a[1]))
            on_circle.append((out, a[2], None, a[3]))
        elif c.op == "tangent_point":
            on_circle.append((out, a[1], None, a[2]))
    return on_line, on_circle


# ---------------------------------------------------------------- ГЕЙТ 7
def gate_correctness(plan: FigurePlan, sol: Any) -> GateResult:
    """Этап 7: чертёж действительно удовлетворяет условию задачи."""
    fails: list[str] = []
    warns: list[str] = []
    try:
        validate_plan(plan)
    except PlanError as e:
        return GateResult(False, 0.0, [f"INVALID_PLAN: {e}"])
    P = _coords(sol)

    if not getattr(sol, "ok", True):
        fails.append(f"SOLVER_FAILED: {getattr(sol, 'reason', '') or 'решатель не сошёлся'}")

    # 1) полнота набора точек
    missing = [p for p in plan.points if p not in P]
    if missing:
        fails.append(f"MISSING_COORDS: нет координат для {sorted(missing)}")

    # 2) конечность координат
    bad = sorted(n for n, v in P.items()
                 if v.shape[0] < 2 or not np.all(np.isfinite(v))
                 or float(np.max(np.abs(v))) > COORD_ABS_MAX)
    if bad:
        fails.append(f"NON_FINITE_COORDS: {bad}")
        return GateResult(ok=False, score=0.0, failures=fails, warnings=warns, measured=None)
    if missing:
        return GateResult(ok=False, score=0.0, failures=fails, warnings=warns, measured=None)

    span = _span(P)

    # Independent execution proves every analytic construction, not merely
    # line/circle membership (a fake midpoint anywhere on AB is still false).
    from .constructions import execute
    free_names = [c.out for c in plan.constructions if c.op == "free_point"]
    try:
        expected = execute(plan, None, np.array([P[n] for n in free_names]).ravel())
        for c in plan.constructions:
            if c.op == "free_point":
                continue
            local_scale = max([_d(P[c.out], P[n]) for n in c.args] + [1e-12])
            error = _d(P[c.out], expected[c.out]) / local_scale
            if error > INCIDENCE_TOL:
                fails.append(f"CONSTRUCTION_VIOLATED: {c.op}({c.out}) невязка {error:.3e}")
    except PlanError as e:
        fails.append(f"CONSTRUCTION_FAILED: {e}")

    # 3) невязка КАЖДОГО ограничения по отдельности (не сумма!)
    for i, c in enumerate(plan.constraints):
        try:
            pts = [P[a] for a in c.args]
        except KeyError as e:
            fails.append(f"CONSTRAINT[{i}] {c.type}: неизвестная точка {e.args[0]!r}")
            continue
        r = constraint_residual(c.type, pts, c.value, span)
        if not math.isfinite(r) or r > CONSTRAINT_TOL:
            fails.append(f"CONSTRAINT_VIOLATED[{i}] {c.type}{c.args}: невязка {r:.3e} > {CONSTRAINT_TOL:.0e}")

    # 4) инцидентность
    on_line, on_circle = _incidence_claims(plan)
    for p, a, b in on_line:
        if not all(k in P for k in (p, a, b)):
            continue
        if _d(P[a], P[b]) < COINCIDE_TOL * span:
            continue
        dev = _point_line_dist(P[p], P[a], P[b]) / span
        if dev > INCIDENCE_TOL:
            fails.append(f"INCIDENCE_LINE: {p} не на прямой {a}{b} (отклонение {dev:.2e}·габарит)")
    for p, cen, _r, ref in on_circle:
        if not all(k in P for k in (p, cen, ref)):
            continue
        R = _d(P[cen], P[ref])
        dev = abs(_d(P[cen], P[p]) - R) / span
        if dev > INCIDENCE_TOL:
            fails.append(f"INCIDENCE_CIRCLE: {p} не на окружности({cen},r=|{cen}{ref}|) "
                         f"(отклонение {dev:.2e}·габарит)")

    # 5) невырожденность: совпадающие точки
    names = [p for p in plan.points if p in P]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if _d(P[names[i]], P[names[j]]) <= 1e-10 * span:
                a, b = names[i], names[j]
                if a in free_names and b in free_names:
                    fails.append(f"COINCIDENT_POINTS: {a} и {b} совпали")
                else:
                    # E.g. right-triangle orthocenter at its right vertex,
                    # circumcenter at a midpoint, or an inversion fixed point.
                    warns.append(f"CONSTRUCTED_COINCIDENCE: {a} и {b} совпали")

    # 6) невырожденность: треугольники чертежа без нулевой площади
    for tri in _draw_triangles(plan):
        if not all(t in P for t in tri):
            continue
        local = max(_d(P[tri[0]], P[tri[1]]), _d(P[tri[0]], P[tri[2]]),
                    _d(P[tri[1]], P[tri[2]]), 1e-12)
        a = _tri_area(P[tri[0]], P[tri[1]], P[tri[2]]) / (local * local)
        if a <= 1e-12:
            fails.append(f"DEGENERATE_TRIANGLE: {''.join(tri)} имеет нулевую площадь")

    # Marks carry mathematical assertions, unlike ordinary decorative labels.
    _check_marks(plan, P, fails, warns)

    # 7) измерение цели
    measured = measure_target(plan, P)
    if plan.target.kind != "none" and measured is None:
        fails.append(f"TARGET_UNMEASURABLE: цель {plan.target.kind}{plan.target.args} не посчитана")
    elif measured is not None and not math.isfinite(measured):
        fails.append(f"TARGET_NON_FINITE: цель {plan.target.kind} = {measured}")

    res = float(getattr(sol, "residual", 0.0) or 0.0)
    if math.isfinite(res) and res > 1e-6:
        warns.append(f"HIGH_RESIDUAL: суммарная невязка решателя {res:.2e}")

    return GateResult(ok=not fails, score=1.0 if not fails else 0.0,
                      failures=fails, warnings=warns, measured=measured)


def _check_marks(plan: FigurePlan, P: dict[str, np.ndarray],
                 fails: list[str], warns: list[str]) -> None:
    for tri in plan.draw.right_angles:
        value = _angle_deg(*(P[n] for n in tri))
        if not math.isfinite(value) or abs(value - 90) > 0.01:
            fails.append(f"FALSE_RIGHT_ANGLE: {tri} = {value:.6g}°, не 90°")
    for name, marks, is_angle in (("angle_marks", plan.draw.angle_marks, True),
                                  ("length_marks", plan.draw.length_marks, False)):
        for mark in marks:
            pts = [P[n] for n in mark["pts"]]
            actual = _angle_deg(*pts) if is_angle else _d(*pts)
            if is_angle and mark.get("reflex", False):
                actual = 360.0 - actual
            label = mark.get("text", "")
            wanted = numeric_mark_value(label, angle=is_angle)
            if not math.isfinite(actual) or (not is_angle and actual <= 1e-15):
                fails.append(f"DEGENERATE_MARK: {name}{mark['pts']}")
            elif wanted is not None:
                tol = 0.01 if is_angle else max(1e-7, abs(wanted) * 1e-4)
                if abs(actual - wanted) > tol:
                    fails.append(f"MARK_VALUE_MISMATCH: {name}{mark['pts']} "
                                 f"подпись {label!r}, измерено {actual:.8g}")
            elif label:
                warns.append(f"SYMBOLIC_MARK_UNVERIFIED: {name}{mark['pts']} {label!r}")

    for name, marks, is_angle in (("equal_marks", plan.draw.equal_marks, False),
                                  ("angle_marks", [m for m in plan.draw.angle_marks if "count" in m], True)):
        groups: dict[int, list[tuple[list[str], float]]] = {}
        for mark in marks:
            pts = [P[n] for n in mark["pts"]]
            value = _angle_deg(*pts) if is_angle else _d(*pts)
            if is_angle and mark.get("reflex", False):
                value = 360.0 - value
            groups.setdefault(mark.get("count", 1), []).append((mark["pts"], value))
        for count, group in groups.items():
            values = [v for _, v in group]
            if not all(math.isfinite(v) and v > 1e-15 for v in values):
                fails.append(f"DEGENERATE_EQUAL_MARK: {name} count={count}")
                continue
            tol = 0.01 if is_angle else 1e-4 * max(values)
            if max(values) - min(values) > tol:
                fails.append(f"FALSE_EQUAL_MARK: {name} count={count} значения {values}")

    for arc in plan.draw.arcs:
        center, a, b = (P[arc[k]] for k in ("center", "start", "end"))
        r1, r2 = _d(center, a), _d(center, b)
        if min(r1, r2) <= 1e-15 or _d(a, b) <= 1e-15:
            fails.append(f"DEGENERATE_ARC: {arc}")
        elif abs(r1 - r2) > 1e-5 * max(r1, r2):
            fails.append(f"ARC_RADII_MISMATCH: {arc['start']}/{arc['end']} радиусы {r1:.8g}/{r2:.8g}")


def _draw_triangles(plan: FigurePlan) -> list[tuple[str, str, str]]:
    """Треугольники чертежа: 3-циклы графа отрезков + тройки right_angles/angle_marks."""
    adj: dict[str, set[str]] = {}
    for s in plan.draw.segments:
        if len(s) >= 2 and s[0] != s[1]:
            adj.setdefault(s[0], set()).add(s[1])
            adj.setdefault(s[1], set()).add(s[0])
    tris: set[tuple[str, str, str]] = set()
    nodes = sorted(adj)
    for a in nodes:
        for b in sorted(adj[a]):
            for c in sorted(adj[a] & adj.get(b, set())):
                tris.add(tuple(sorted((a, b, c))))  # type: ignore[arg-type]
    for tri in plan.draw.right_angles:
        if len(tri) == 3 and len(set(tri)) == 3:
            tris.add(tuple(sorted(tri)))  # type: ignore[arg-type]
    for m in plan.draw.angle_marks:
        tri = list(m.get("pts") or [])
        if len(tri) == 3 and len(set(tri)) == 3:
            tris.add(tuple(sorted(tri)))  # type: ignore[arg-type]
    # An explicitly subdivided straight segment is not a degenerate triangle.
    on_line, _ = _incidence_claims(plan)
    collinear = {frozenset((p, a, b)) for p, a, b in on_line}
    return sorted(tri for tri in tris if frozenset(tri) not in collinear)


# ---------------------------------------------------------------- ГЕЙТ 8
def _drawn_segments(plan: FigurePlan) -> list[list[str]]:
    return [list(s) for name in ("segments", "aux_segments", "lines", "rays", "aux_lines", "aux_rays")
            for s in getattr(plan.draw, name) if len(s) >= 2]


def _declared_on_line(plan: FigurePlan) -> set[tuple[str, frozenset]]:
    """Пары (точка, {A,B}): точка ОБЪЯВЛЕНА лежащей на прямой AB — такие
    близости законны и не считаются визуальным дефектом."""
    inc: set[tuple[str, frozenset]] = set()
    on_line, _ = _incidence_claims(plan)
    for p, a, b in on_line:
        for pair in ((a, b), (a, p), (b, p)):
            inc.add((p, frozenset(pair)))
            inc.add((a, frozenset((b, p))))
            inc.add((b, frozenset((a, p))))
    for c in plan.constraints:
        if c.type == "collinear" and len(c.args) == 3:
            x, y, z = c.args
            inc.add((x, frozenset((y, z))))
            inc.add((y, frozenset((x, z))))
            inc.add((z, frozenset((x, y))))
    return inc


def _used_points(plan: FigurePlan) -> set[str]:
    used: set[str] = set()
    d = plan.draw
    for group in (d.segments, d.aux_segments, d.lines, d.rays, d.aux_lines, d.aux_rays,
                  d.circles, d.aux_circles, d.right_angles):
        for it in group:
            used.update(it)
    for m in list(d.angle_marks) + list(d.length_marks) + list(d.equal_marks):
        used.update(m.get("pts") or [])
    used.update(d.aux_points)
    for arc in d.arcs:
        used.update(arc[k] for k in ("center", "start", "end"))
    return used


def readability_score(plan: FigurePlan, P: dict[str, np.ndarray]) -> float:
    """Оценка наглядности 0..1 для РАНЖИРОВАНИЯ конфигураций."""
    used = _used_points(plan)
    hidden = set(plan.draw.hide_labels) - used
    pts = [P[p] for p in plan.points if p in P and p not in hidden
           and np.all(np.isfinite(P[p]))]
    if len(pts) < 2:
        return 0.0
    span = _span({str(i): p for i, p in enumerate(pts)})
    A = np.array(pts)
    w = float(A[:, 0].max() - A[:, 0].min())
    h = float(A[:, 1].max() - A[:, 1].min())

    # 1) минимальный угол оболочки: 60° и выше — идеал
    ang = min_hull_angle(pts)
    s_ang = float(np.clip(ang / 60.0, 0.0, 1.0))

    # 2) равномерность распределения точек: min / mean по парам
    dists = [_d(pts[i], pts[j]) for i in range(len(pts)) for j in range(i + 1, len(pts))]
    mean_d = float(np.mean(dists)) if dists else 0.0
    s_uni = float(np.clip((min(dists) / mean_d) / 0.5, 0.0, 1.0)) if mean_d > 1e-15 else 0.0

    # 3) близость отношения габаритов к 1
    if min(w, h) <= 1e-12:
        s_ar = 0.0
    else:
        ar = w / h
        s_ar = float(np.clip(1.0 - abs(math.log(ar)) / math.log(5.0), 0.0, 1.0))

    # 4) мягкий бонус за отсутствие слипаний
    s_gap = float(np.clip((min(dists) / span) / MIN_POINT_DIST_FRAC, 0.0, 1.0)) if dists else 0.0

    return float(np.clip(0.42 * s_ang + 0.18 * s_uni + 0.30 * s_ar + 0.10 * s_gap, 0.0, 1.0))


def gate_readability(plan: FigurePlan, sol: Any, *, strict: bool = True) -> GateResult:
    """Этап 8: визуальные критерии.

    strict=True retains the legacy hard visual gate. Production should use
    strict=False: narrow angles, aspect ratio and crowding become warnings,
    while genuinely undrawable elements still fail.
    """
    fails: list[str] = []
    warns: list[str] = []
    P = _coords(sol)

    used = _used_points(plan)
    hidden = set(plan.draw.hide_labels) - used
    live = {p: P[p] for p in plan.points if p in P and p not in hidden
            and P[p].shape[0] >= 2
            and np.all(np.isfinite(P[p]))}
    if len(live) < 2:
        return GateResult(ok=False, score=0.0,
                          failures=["NOT_RENDERABLE: меньше двух конечных точек"],
                          warnings=warns)

    span = _span(live)
    A = np.array(list(live.values()))
    w = float(A[:, 0].max() - A[:, 0].min())
    h = float(A[:, 1].max() - A[:, 1].min())

    # 1) «щепка»: минимальный угол выпуклой оболочки
    ang = min_hull_angle(list(live.values()))
    if ang < MIN_HULL_ANGLE_DEG:
        fails.append(f"SLIVER: минимальный угол оболочки {ang:.2f}° < {MIN_HULL_ANGLE_DEG:.0f}°")

    # 2) отношение габаритов
    if min(w, h) <= 1e-12:
        fails.append("FLAT_FIGURE: все точки на одной прямой (нулевой габарит по оси)")
    else:
        ar = w / h
        if not (ASPECT_MIN <= ar <= ASPECT_MAX):
            fails.append(f"BAD_ASPECT: width/height = {ar:.3f} вне [{ASPECT_MIN}, {ASPECT_MAX}]")

    # 3) минимальное расстояние между точками
    names = list(live)
    worst = None
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            dij = _d(live[names[i]], live[names[j]]) / span
            if worst is None or dij < worst[0]:
                worst = (dij, names[i], names[j])
    if worst is not None and worst[0] < MIN_POINT_DIST_FRAC:
        fails.append(f"POINTS_TOO_CLOSE: {worst[1]}–{worst[2]} на {worst[0] * 100:.2f}% габарита "
                     f"< {MIN_POINT_DIST_FRAC * 100:.0f}%")

    # 4) точка почти на НЕ инцидентной ей нарисованной прямой
    segs = _drawn_segments(plan)
    declared = _declared_on_line(plan)
    for p, xy in live.items():
        for s in segs:
            a, b = s[0], s[1]
            if p in (a, b) or a not in live or b not in live:
                continue
            if (p, frozenset((a, b))) in declared:
                continue
            if _d(live[a], live[b]) <= COINCIDE_TOL * span:
                continue
            dpl = _point_seg_dist(xy, live[a], live[b]) / span
            if dpl >= MIN_POINT_LINE_FRAC:
                continue
            # ТОЧНОЕ совпадение — это геометрический факт, а не дефект:
            # ортоцентр лежит на высотах, центроид — на медианах, точка
            # пересечения — на обеих прямых. Правило против точки ПОЧТИ на
            # прямой касается только визуальной двусмысленности, не инцидентности.
            if dpl <= EXACT_INCIDENCE_FRAC:
                if not strict:
                    warns.append(f"UNDECLARED_INCIDENCE: {p} лежит на {a}{b}; "
                                 "явно не задано, может следовать из построений")
                continue
            msg = (f"POINT_ON_SEGMENT: {p} в {dpl * 100:.2f}% габарита от отрезка "
                   f"{a}{b} (< {MIN_POINT_LINE_FRAC * 100:.0f}%)")
            # Построенная точка вблизи прямой — косметика (теснота подписей),
            # а не геометрический дефект: конфигурация задана условием.
            # Жёстко отклоняем только полное визуальное слипание.
            if dpl < COINCIDE_VISUAL_FRAC:
                fails.append(msg)
            else:
                warns.append(msg)

    # 5) все отрезки реально отрисовываемы
    for s in list(plan.draw.segments) + list(plan.draw.aux_segments):
        if len(s) < 2 or s[0] == s[1]:
            fails.append(f"BAD_SEGMENT: вырожденный отрезок {s}")
            continue
        a, b = s[0], s[1]
        if a not in live or b not in live:
            fails.append(f"UNDRAWABLE_SEGMENT: {a}{b} — нет координат")
        elif _d(live[a], live[b]) <= COINCIDE_TOL * span:
            fails.append(f"UNDRAWABLE_SEGMENT: {a}{b} — концы совпали")

    # 6) полнота: каждая точка участвует в draw или скрыта (мягко)
    used = _used_points(plan)
    hidden = set(plan.draw.hide_labels)
    for p in plan.points:
        if p not in used and p not in hidden:
            warns.append(f"ORPHAN_POINT: {p} не участвует ни в одном элементе draw")

    score = readability_score(plan, live)
    if not strict:
        # A mathematically correct acute/flat/elongated figure is useful.
        # Keep only genuinely undrawable elements as hard failures.
        cosmetic = ("SLIVER:", "FLAT_FIGURE:", "BAD_ASPECT:", "POINTS_TOO_CLOSE:", "POINT_ON_SEGMENT:")
        warns.extend(f for f in fails if f.startswith(cosmetic))
        fails = [f for f in fails if not f.startswith(cosmetic)]
    return GateResult(ok=not fails, score=score, failures=fails, warnings=warns)


# ---------------------------------------------------------------- ранжирование
def rank_solutions(plan: FigurePlan, solutions: Iterable[Any], *,
                   strict_readability: bool = True) -> list[tuple[Any, GateResult]]:
    """Отбрасывает провалившие gate_correctness, остальные сортирует по score ↓."""
    ranked: list[tuple[Any, GateResult]] = []
    for sol in solutions:
        gc = gate_correctness(plan, sol)
        if not gc.ok:
            continue
        gr = gate_readability(plan, sol, strict=strict_readability)
        gr.warnings = gc.warnings + gr.warnings
        gr.measured = gc.measured
        ranked.append((sol, gr))
    ranked.sort(key=lambda t: (t[1].ok, t[1].score), reverse=True)
    return ranked
