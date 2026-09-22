"""GeoExact: невязки ограничений и многостартовый решатель свободных координат.

residuals(plan, coords) -> np.ndarray   — по одной нормированной невязке на ограничение
solve(plan, n_seeds, seed) -> list[Solution] — все различные решения, по возрастанию невязки

Все невязки приведены к безразмерному (или одинаково масштабированному) виду:
длины делятся на характерный масштаб фигуры, углы берутся в радианах,
коллинеарность/параллельность/перпендикулярность — через нормированные
векторные/скалярные произведения (синус/косинус угла), а не сырые определители.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from .constructions import count_free_points, execute
from .schema import CONSTRAINTS, Constraint, FigurePlan, PlanError, validate_plan

__all__ = ["Solution", "residuals", "residual_norm", "plan_scale", "normalize_coords", "solve"]

TOL = 1e-7           # порог допустимости невязки (относительно габарита фигуры)
_EPS = 1e-12
_PENALTY = 1e3       # невязка для вырожденных конфигураций при оптимизации


@dataclass
class Solution:
    coords: dict[str, np.ndarray] = field(default_factory=dict)
    residual: float = float("inf")
    ok: bool = False
    reason: str = ""


# ------------------------------------------------------------------ масштаб
def plan_scale(plan: FigurePlan) -> float:
    """Характерный линейный масштаб задачи (из значений ограничений). Всегда > 0."""
    vals: list[float] = []
    for c in plan.constraints:
        c = c if isinstance(c, Constraint) else Constraint(**c)
        if c.value is None:
            continue
        if c.type == "dist":
            vals.append(abs(float(c.value)))
        elif c.type == "area":
            vals.append(math.sqrt(abs(float(c.value))))
    for c in plan.constructions:
        if c.op == "perp_point" and c.value is not None:
            vals.append(abs(float(c.value)))
    # Numeric length annotations assert an absolute measurement as well.
    from .gates import numeric_mark_value
    for mark in plan.draw.length_marks:
        value = numeric_mark_value(mark.get("text", ""), angle=False)
        if value is not None and value > 0:
            vals.append(value)
    vals = [v for v in vals if v > _EPS]
    if not vals:
        return 1.0
    return float(np.median(np.asarray(vals, dtype=float)))


# ------------------------------------------------------------------ геометрия
def _n(u: np.ndarray) -> float:
    return float(math.hypot(float(u[0]), float(u[1])))


def _cross(u: np.ndarray, v: np.ndarray) -> float:
    return float(u[0] * v[1] - u[1] * v[0])


def _dot(u: np.ndarray, v: np.ndarray) -> float:
    return float(u[0] * v[0] + u[1] * v[1])


def _angle(A: np.ndarray, B: np.ndarray, C: np.ndarray) -> float:
    """Угол ABC (при вершине B) в радианах, [0, pi]."""
    u, v = A - B, C - B
    nu, nv = _n(u), _n(v)
    if nu <= _EPS or nv <= _EPS:
        raise PlanError("DEGENERATE", "угол при совпадающих точках")
    return float(math.atan2(abs(_cross(u, v)), _dot(u, v)))


def _get(coords: dict[str, np.ndarray], name: str) -> np.ndarray:
    p = coords.get(name)
    if p is None:
        raise PlanError("UNKNOWN_REF", f"точка {name!r} не построена")
    try:
        a = np.asarray(p, dtype=float)
        if a.shape != (2,) or not np.isfinite(a).all():
            raise ValueError("неверный размер или неконечные координаты")
        return a
    except (TypeError, ValueError, OverflowError) as e:
        raise PlanError("BAD_COORDS", f"точка {name!r}: требуется конечная пара координат") from e


# ------------------------------------------------------------------ невязки
def residuals(plan: FigurePlan, coords: dict[str, np.ndarray]) -> np.ndarray:
    """Нормированная невязка каждого ограничения плана (порядок сохраняется)."""
    for name in coords:
        _get(coords, name)
    S = plan_scale(plan)
    res = np.zeros(len(plan.constraints), dtype=float)

    for i, c in enumerate(plan.constraints):
        c = c if isinstance(c, Constraint) else Constraint(**c)
        spec = CONSTRAINTS.get(c.type)
        if spec is None:
            raise PlanError("UNKNOWN_CONSTRAINT", f"[{i}] неизвестное ограничение {c.type!r}")
        if len(c.args) != spec["pts"]:
            raise PlanError("ARITY", f"[{i}] {c.type} ждёт {spec['pts']} точек")
        if spec["value"] and c.value is None:
            raise PlanError("NO_VALUE", f"[{i}] {c.type} требует value")
        if c.value is not None:
            if isinstance(c.value, bool) or not isinstance(c.value, (int, float)):
                raise PlanError("BAD_VALUE", f"[{i}] value должно быть числом")
            if not math.isfinite(float(c.value)):
                raise PlanError("NON_FINITE_VALUE", f"[{i}] value должно быть конечным")
        P = [_get(coords, a) for a in c.args]
        t = c.type

        if t == "dist":
            A, B = P
            res[i] = (_n(B - A) - float(c.value)) / S

        elif t == "dist_eq":
            A, B, C, D = P
            res[i] = (_n(B - A) - _n(D - C)) / S

        elif t == "dist_ratio":
            A, B, C, D = P
            res[i] = (_n(B - A) - float(c.value) * _n(D - C)) / S

        elif t == "angle":
            A, B, C = P
            res[i] = _angle(A, B, C) - math.radians(float(c.value))

        elif t == "angle_eq":
            A, B, C, D, E, F = P
            res[i] = _angle(A, B, C) - _angle(D, E, F)

        elif t == "collinear":
            A, B, C = P
            u, v = B - A, C - A
            nu, nv = _n(u), _n(v)
            if nu <= _EPS or nv <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] collinear: совпадающие точки")
            res[i] = _cross(u, v) / (nu * nv)          # sin угла между AB и AC

        elif t == "perpendicular":
            A, B, C, D = P
            u, v = B - A, D - C
            nu, nv = _n(u), _n(v)
            if nu <= _EPS or nv <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] perpendicular: нулевой отрезок")
            res[i] = _dot(u, v) / (nu * nv)            # cos угла

        elif t == "parallel":
            A, B, C, D = P
            u, v = B - A, D - C
            nu, nv = _n(u), _n(v)
            if nu <= _EPS or nv <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] parallel: нулевой отрезок")
            res[i] = _cross(u, v) / (nu * nv)          # sin угла

        elif t == "concyclic":
            A, B, C, D = P
            base_scale = max(_n(B - A), _n(C - A), _n(D - A))
            if base_scale <= _EPS or abs(_cross((B - A) / base_scale, (C - A) / base_scale)) <= 1e-12:
                raise PlanError("DEGENERATE", f"[{i}] concyclic: коллинеарные точки не задают окружность")
            det = _concyclic_det(A, B, C, D)
            scale = (_n(B - A) * _n(C - B) * _n(D - C) * _n(A - D))
            if scale <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] concyclic: совпадающие точки")
            res[i] = det / scale                        # безразмерная мера

        elif t == "on_circle":
            A, B, C, D = P
            if _n(D - C) <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] on_circle: нулевой радиус")
            res[i] = (_n(A - B) - _n(D - C)) / S

        elif t == "area":
            A, B, C = P
            ar = 0.5 * abs(_cross(B - A, C - A))
            res[i] = (ar - float(c.value)) / (S * S)

        elif t == "on_segment":
            A, B, C = P
            v = C - B
            length = _n(v)
            if length <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] on_segment: нулевой отрезок")
            u = v / length
            along = float(np.clip(_dot(A - B, u), 0.0, length))
            res[i] = _n(A - (B + along * u)) / length

        elif t in ("same_side", "opposite_side"):
            A, B, C, D = P
            v = D - C
            length = _n(v)
            if length <= _EPS:
                raise PlanError("DEGENERATE", f"[{i}] {t}: нулевая прямая")
            u = v / length
            da, db = _cross(u, (A - C) / length), _cross(u, (B - C) / length)
            product = da * db * (1.0 if t == "same_side" else -1.0)
            # Strict half-planes: a point ON the line never satisfies either
            # relation. The positive jump prevents boundary solutions being
            # silently accepted as "zero residual".
            res[i] = 0.0 if product > 0 else min(abs(da), abs(db)) + 1e-5

        else:  # pragma: no cover — защита от расширения CONSTRAINTS без кода
            raise PlanError("UNKNOWN_CONSTRAINT", f"[{i}] ограничение {t!r} не реализовано")

    if not np.all(np.isfinite(res)):
        raise PlanError("DEGENERATE", "невязка не конечна")
    return res


def _concyclic_det(A, B, C, D) -> float:
    """Определитель |x²+y², x, y, 1| для четырёх точек (0 <=> одна окружность/прямая)."""
    M = np.empty((4, 4), dtype=float)
    # Subtract an origin to avoid cancellation of huge absolute squares.
    for k, P in enumerate((A - A, B - A, C - A, D - A)):
        M[k, 0] = P[0] * P[0] + P[1] * P[1]
        M[k, 1] = P[0]
        M[k, 2] = P[1]
        M[k, 3] = 1.0
    return float(np.linalg.det(M))


def residual_norm(plan: FigurePlan, coords: dict[str, np.ndarray]) -> float:
    r = residuals(plan, coords)
    return float(np.max(np.abs(r))) if r.size else 0.0


# ------------------------------------------------------------------ нормализация
def normalize_coords(plan: FigurePlan, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Центрирует фигуру; при plan.scale_free масштабирует до габарита 1."""
    names = sorted(coords)
    if not names:
        return {}
    P = np.array([_get(coords, k) for k in names], dtype=float)
    lo, hi = P.min(axis=0), P.max(axis=0)
    center = 0.5 * (lo + hi)
    P = P - center
    # Масштабировать можно ТОЛЬКО если в плане нет ни одного ограничения,
    # задающего абсолютный размер. Иначе нормировка ломает уже выполненное
    # ограничение (dist AB = 10 перестаёт держаться), и гейт корректности
    # справедливо отклоняет верную фигуру.
    from .gates import numeric_mark_value
    has_absolute = any(
        c.type in ("dist", "area") and c.value is not None for c in plan.constraints
    ) or any(
        c.op == "perp_point" and c.value is not None
        for c in plan.constructions
    ) or any(
        numeric_mark_value(m.get("text", ""), angle=False) is not None
        for m in plan.draw.length_marks
    )
    if plan.scale_free and not has_absolute:
        span = float(np.max(hi - lo))
        if span > _EPS:
            P = P / span
    return {k: P[i].copy() for i, k in enumerate(names)}


# ------------------------------------------------------------------ калибровка
def _n_vars(n_free: int) -> int:
    """Число свободных переменных после фиксации жёсткого движения."""
    if n_free <= 0:
        return 0
    if n_free == 1:
        return 0                 # точка приклеена в (0,0)
    return 1 + 2 * (n_free - 2)  # вторая точка: только x >= 0 на оси x


def _free_from_vars(x: np.ndarray, n_free: int) -> np.ndarray:
    """vars -> полный вектор координат свободных точек (2 на точку)."""
    fv = np.zeros(2 * n_free, dtype=float)
    if n_free >= 2:
        fv[2] = float(x[0])          # (x1, 0)
        if n_free > 2:
            fv[4:] = np.asarray(x[1:], dtype=float)
    return fv


# ------------------------------------------------------------------ решатель
def solve(plan: FigurePlan, n_seeds: int = 24, seed: int = 0) -> list[Solution]:
    """Многостартовый least_squares по свободным координатам.

    Возвращает список различных решений (дедупликация после нормализации,
    порог 1e-6 по максимальному смещению точки), отсортированный по невязке.
    Детерминирован при фиксированном seed.
    """
    validate_plan(plan)
    n_free = count_free_points(plan)
    nv = _n_vars(n_free)
    S = plan_scale(plan)
    m = len(plan.constraints)

    def coords_of(x: np.ndarray) -> dict[str, np.ndarray]:
        return execute(plan, None, _free_from_vars(np.asarray(x, dtype=float), n_free))

    def fun(x: np.ndarray) -> np.ndarray:
        try:
            return residuals(plan, coords_of(x))
        except PlanError:
            return np.full(m, _PENALTY, dtype=float)

    # --- нет свободных переменных: единственная конфигурация
    if nv == 0:
        try:
            coords = coords_of(np.zeros(0))
        except PlanError as e:
            return [Solution({}, float("inf"), False, e.code)]
        return [_finish(plan, coords)]

    rng = np.random.RandomState(int(seed))
    starts: list[np.ndarray] = []

    # детерминированный «правильный» старт: точки по окружности радиуса S
    x0 = np.zeros(nv, dtype=float)
    x0[0] = S
    for j in range(n_free - 2):
        a = 2.0 * math.pi * (j + 1) / max(1, n_free - 1) + 0.7
        x0[1 + 2 * j] = S * math.cos(a)
        x0[2 + 2 * j] = S * math.sin(a)
    starts.append(x0)

    for _ in range(max(0, int(n_seeds) - 1)):
        x = rng.uniform(-1.5, 1.5, size=nv) * S
        x[0] = abs(x[0]) + 0.2 * S       # вторая точка на положительной полуоси
        starts.append(x)

    found: list[Solution] = []
    norm_cache: list[np.ndarray] = []   # нормализованные координаты для дедупликации
    key_names = sorted(plan.points) if plan.points else None
    best: Solution | None = None

    for x_start in starts:
        if m == 0:
            # No equations: retain deterministic, well-spread sampled geometry
            # rather than passing an empty residual vector to least_squares.
            x = x_start.copy()
        else:
            try:
                sol = least_squares(fun, x_start, method="trf",
                                    xtol=1e-15, ftol=1e-15, gtol=1e-15,
                                    max_nfev=400 * (nv + 1))
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                continue
            x = np.asarray(sol.x, dtype=float)

        # канонизация: разворот на 180°, если вторая свободная точка ушла на x<0
        if n_free >= 2 and x[0] < 0.0:
            x_rot = -x
            try:
                if residual_norm(plan, coords_of(x_rot)) <= max(TOL, residual_norm(plan, coords_of(x)) * 1.0001):
                    x = x_rot
            except PlanError:
                pass

        try:
            coords = coords_of(x)
        except PlanError:
            continue
        cand = _finish(plan, coords)
        if best is None or cand.residual < best.residual:
            best = cand
        if not cand.ok:
            continue

        names = key_names if key_names and all(k in cand.coords for k in key_names) else sorted(cand.coords)
        vec = np.array([cand.coords[k] for k in names], dtype=float)
        dup = False
        for prev in norm_cache:
            if prev.shape == vec.shape and float(np.max(np.linalg.norm(prev - vec, axis=1))) < 1e-6:
                dup = True
                break
        if dup:
            continue
        norm_cache.append(vec)
        found.append(cand)

    if not found:
        if best is None:
            return [Solution({}, float("inf"), False, "DEGENERATE")]
        return [best]

    order = sorted(range(len(found)),
                   key=lambda i: (round(found[i].residual, 15),
                                  tuple(np.round(norm_cache[i].ravel(), 9).tolist())))
    return [found[i] for i in order]


def _finish(plan: FigurePlan, coords: dict[str, np.ndarray]) -> Solution:
    """Считает невязку на решённых координатах и нормализует фигуру."""
    try:
        coords = normalize_coords(plan, coords)
        r = residual_norm(plan, coords)
    except PlanError as e:
        return Solution({}, float("inf"), False, e.code)
    ok = r <= TOL
    return Solution(coords=coords,
                    residual=float(r),
                    ok=bool(ok),
                    reason="" if ok else "RESIDUAL_TOO_HIGH")
