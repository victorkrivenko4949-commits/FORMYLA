"""GeoExact: невязки ограничений и многостартовый решатель свободных координат.

residuals(plan, coords) -> np.ndarray   — по одной нормированной невязке на ограничение
solve(plan, n_seeds, seed) -> list[Solution] — все различные решения, по возрастанию невязки

Все невязки приведены к безразмерному (или одинаково масштабированному) виду:
длины делятся на характерный масштаб фигуры, углы берутся в радианах,
коллинеарность/параллельность/перпендикулярность — через нормированные
векторные/скалярные произведения (синус/косинус угла), а не сырые определители.

Поиск решения (см. solve): старты разбросаны по масштабам вокруг ожидаемого
габарита фигуры, каждый старт проходит два этапа — «невязки + мягкие штрафы
общего положения», затем точная полировка только по невязкам. Так
недоопределённая задача (свободный параметр, не влияющий на ответ) получает
читаемый чертёж, а не вырожденный, и быстрее: ранний останов после
достаточного числа различных верных решений и общий лимит времени на поиск.
Вырожденная фигура (схлопнутый нарисованный треугольник, совпавшие точки) верным
решением не считается даже при нулевой невязке (см. degenerate_figure).
"""
from __future__ import annotations

import itertools
import math
import os
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from .constructions import count_free_points, execute
from .schema import CONSTRAINTS, Constraint, FigurePlan, PlanError, validate_plan

__all__ = ["Solution", "residuals", "residual_norm", "plan_scale", "plan_extent",
           "normalize_coords", "degenerate_figure", "solve"]

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

        elif t == "cos_double_angle":
            A, B, C = P
            res[i] = math.cos(2 * _angle(A, B, C)) - float(c.value)

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


# ------------------------------------------------------------------ масштаб габарита
def plan_extent(plan: FigurePlan) -> float:
    """Ожидаемый ГАБАРИТ фигуры (а не характерная длина): максимум заданных длин.

    plan_scale берёт медиану и служит для нормировки невязок. Для стартов
    решателя медиана опасна: при данных AB = 6 и AK = 2 медиана равна 4, а
    фигура обязана быть крупнее 18 — все старты лежали далеко от решений, и
    least_squares уходил по свободному параметру в вырожденные конфигурации
    (слипшиеся точки или «игла»). Габарит — не меньше самой длинной данной.
    """
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
    from .gates import numeric_mark_value
    for mark in plan.draw.length_marks:
        value = numeric_mark_value(mark.get("text", ""), angle=False)
        if value is not None and value > 0:
            vals.append(value)
    vals = [v for v in vals if v > _EPS]
    return float(max(vals)) if vals else plan_scale(plan)


# ------------------------------------------------------------------ вырождение
# Невязка ограничений может быть нулевой и у схлопнутой фигуры: треугольник ABC,
# лёгший на прямую, формально удовлетворяет «AB = 23, AC = 8, M — середина BC,
# MK ∥ ℓ». Раньше такое решение считалось верным и уходило на рендер (видно
# как пять точек на одной прямой). Теперь любая тройка точек, попарно соединённая
# отрезками основного слоя (т.е. нарисованный треугольник), обязана иметь
# ненулевую площадь, а видимые точки — не совпадать. Иначе решение помечается
# DEGENERATE_FIGURE: решатель ищет дальше, а если ничего другого нет, конвейер
# получает отказ и перезапрашивает план у модели.
DEGEN_AREA_FRAC = float(os.environ.get("GEOEXACT_DEGEN_AREA_FRAC", "2e-4") or "2e-4")
DEGEN_POINT_FRAC = float(os.environ.get("GEOEXACT_DEGEN_POINT_FRAC", "0.004") or "0.004")


def _drawn_triangles(plan: FigurePlan) -> list[tuple[str, str, str]]:
    """Тройки точек, попарно соединённые отрезками основного слоя."""
    try:
        segs = [tuple(s) for s in (plan.draw.segments or []) if isinstance(s, (list, tuple)) and len(s) == 2]
    except Exception:  # noqa: BLE001
        return []
    edges = {frozenset(map(str, s)) for s in segs if len(set(s)) == 2}
    names = sorted({str(p) for e in edges for p in e})
    out = []
    for a, b, c in itertools.combinations(names, 3):
        if {frozenset((a, b)), frozenset((b, c)), frozenset((a, c))} <= edges:
            out.append((a, b, c))
    return out


def degenerate_figure(plan: FigurePlan, coords: dict[str, np.ndarray]) -> str:
    """'' если фигура в порядке, иначе краткая причина вырождения."""
    try:
        visible = [n for n in (plan.points or []) if n in coords
                   and n not in set(getattr(plan.draw, "hide_labels", []) or [])]
        if len(visible) < 2:
            return ""
        P = {n: np.asarray(coords[n], dtype=float) for n in visible}
        arr = np.array(list(P.values()))
        span = float(np.max(arr.max(axis=0) - arr.min(axis=0)))
        if span <= _EPS:
            return "все точки совпали"
        for a, b in itertools.combinations(visible, 2):
            if float(np.hypot(*(P[a] - P[b]))) < DEGEN_POINT_FRAC * span:
                return f"точки {a} и {b} совпали"
        for a, b, c in _drawn_triangles(plan):
            if not (a in P and b in P and c in P):
                continue
            area = 0.5 * abs(_cross(P[b] - P[a], P[c] - P[a]))
            if area < DEGEN_AREA_FRAC * span * span:
                return f"треугольник {a}{b}{c} схлопнулся в отрезок"
    except Exception:  # noqa: BLE001 — проверка никогда не ломает решатель
        return ""
    return ""


# ------------------------------------------------------------------ мягкое общее положение
# Этап 1 решателя минимизирует невязки ОГРАНИЧЕНИЙ плюс слабые штрафы за
# «некрасивую» фигуру: слипшиеся точки, габарит много больше данных длин,
# вытянутость. Это не меняет условие — на этапе 2 та же точка дотягивается
# до точного решения уже без штрафов. Штрафы лишь выбирают, в какую сторону
# уходить по свободному параметру недоопределённой задачи.
SOFT_WEIGHT = float(os.environ.get("GEOEXACT_SOFT_POSITION_WEIGHT", "0.05") or "0.05")
SOFT_MIN_FRAC = 0.08       # ближе этой доли габарита точки считаются «слипшимися»
SOFT_MAX_RATIO = 4.0       # габарит больше 4 × максимальной данной длины — штраф
SOFT_MAX_ASPECT = 3.0      # соотношение сторон габарита больше 3 — штраф
# Ранний останов: после EARLY_MIN_STARTS стартов и EARLY_FOUND различных
# верных решений дальнейшие старты не нужны (экономия ~2× времени).
EARLY_FOUND = int(os.environ.get("GEOEXACT_SOLVER_EARLY_FOUND", "8") or "8")
EARLY_MIN_STARTS = int(os.environ.get("GEOEXACT_SOLVER_EARLY_MIN_STARTS", "16") or "16")
# Общий лимит времени на один вызов solve (секунды). Конвейер живёт 170 с на
# всё — классификацию, формализацию, до 3 кругов решения с обратной связью
# модели, гейты и рендер. Без лимита неудачный план (решений нет вовсе) гонял
# все 48 стартов × 2 этапа и съедал время, которого потом не хватало на
# повторную формализацию — пользователь получал эскиз по ключевым словам.
# Когда что-то уже найдено, поиск прекращается после TIME_BUDGET; если не
# найдено ничего — после 2 × TIME_BUDGET (лучшее приближение всё равно
# возвращается). 0 — без лимита.
TIME_BUDGET = float(os.environ.get("GEOEXACT_SOLVER_TIME_BUDGET", "20") or "20")
# Допуски оптимизатора: 1e-15 заставлял least_squares «вылизывать» каждую
# точку до машинного нуля. Невязка проверяется отдельно (TOL), поэтому
# оптимизатору достаточно сойтись заметно ниже TOL.
OPT_TOL_SOFT = 1e-9
OPT_TOL_POLISH = 1e-12


def _soft_position_terms(plan: FigurePlan, coords: dict[str, np.ndarray],
                         extent: float, n_terms: int) -> np.ndarray:
    """Вектор мягких штрафов фиксированной длины n_terms (для least_squares)."""
    out = np.zeros(n_terms, dtype=float)
    if SOFT_WEIGHT <= 0.0:
        return out
    names = [n for n in (plan.points or []) if n in coords] or sorted(coords)
    P = np.array([coords[n] for n in names], dtype=float)
    if len(P) < 2 or not np.isfinite(P).all():
        return out
    lo, hi = P.min(axis=0), P.max(axis=0)
    w, h = hi - lo
    span = float(max(w, h)) + _EPS
    k = 0
    for i in range(len(P)):
        for j in range(i + 1, len(P)):
            if k >= n_terms - 2:
                break
            d = float(math.hypot(*(P[i] - P[j]))) / span
            out[k] = SOFT_WEIGHT * max(0.0, SOFT_MIN_FRAC - d) / SOFT_MIN_FRAC
            k += 1
    out[n_terms - 2] = SOFT_WEIGHT * max(0.0, span / extent - SOFT_MAX_RATIO)
    aspect = span / max(float(min(w, h)), _EPS)
    out[n_terms - 1] = SOFT_WEIGHT * max(0.0, aspect - SOFT_MAX_ASPECT)
    return out


def _soft_term_count(plan: FigurePlan) -> int:
    n = len(plan.points or [])
    return n * (n - 1) // 2 + 2


# ------------------------------------------------------------------ решатель
def solve(plan: FigurePlan, n_seeds: int = 24, seed: int = 0) -> list[Solution]:
    """Многостартовый least_squares по свободным координатам.

    Два этапа на каждый старт: (1) невязки + мягкие штрафы общего положения,
    (2) полировка только по невязкам от найденной точки. Старты разбросаны по
    масштабам 0.5…4 × габарита (plan_extent), а не по одному масштабу.
    Возвращает список различных решений (дедупликация после нормализации,
    порог 1e-6 по максимальному смещению точки), отсортированный по невязке.
    Детерминирован при фиксированном seed. Останавливается раньше, когда
    верных различных решений уже достаточно (EARLY_FOUND) или вышло время
    (TIME_BUDGET). Вырожденные фигуры (degenerate_figure) верными не считаются.
    """
    validate_plan(plan)
    n_free = count_free_points(plan)
    nv = _n_vars(n_free)
    S = plan_scale(plan)
    E = max(plan_extent(plan), S)
    m = len(plan.constraints)
    n_soft = _soft_term_count(plan)

    def coords_of(x: np.ndarray) -> dict[str, np.ndarray]:
        return execute(plan, None, _free_from_vars(np.asarray(x, dtype=float), n_free))

    def fun(x: np.ndarray) -> np.ndarray:
        try:
            return residuals(plan, coords_of(x))
        except PlanError:
            return np.full(m, _PENALTY, dtype=float)

    def fun_soft(x: np.ndarray) -> np.ndarray:
        try:
            coords = coords_of(x)
            r = residuals(plan, coords)
        except PlanError:
            return np.full(m + n_soft, _PENALTY, dtype=float)
        try:
            g = _soft_position_terms(plan, coords, E, n_soft)
        except Exception:  # noqa: BLE001 — штраф никогда не ломает решатель
            g = np.zeros(n_soft, dtype=float)
        return np.concatenate([r, g])

    # --- нет свободных переменных: единственная конфигурация
    if nv == 0:
        try:
            coords = coords_of(np.zeros(0))
        except PlanError as e:
            return [Solution({}, float("inf"), False, e.code)]
        return [_finish(plan, coords)]

    rng = np.random.RandomState(int(seed))
    starts: list[np.ndarray] = []

    # детерминированный «правильный» старт: точки по окружности радиуса E
    x0 = np.zeros(nv, dtype=float)
    x0[0] = E
    for j in range(n_free - 2):
        a = 2.0 * math.pi * (j + 1) / max(1, n_free - 1) + 0.7
        x0[1 + 2 * j] = E * math.cos(a)
        x0[2 + 2 * j] = E * math.sin(a)
    starts.append(x0)

    for _ in range(max(0, int(n_seeds) - 1)):
        # лог-равномерный масштаб старта: фигура может быть и мельче, и крупнее данных
        sc = E * math.exp(rng.uniform(math.log(0.5), math.log(4.0)))
        x = rng.uniform(-1.5, 1.5, size=nv) * sc
        x[0] = abs(x[0]) + 0.2 * sc       # вторая точка на положительной полуоси
        starts.append(x)

    found: list[Solution] = []
    norm_cache: list[np.ndarray] = []   # нормализованные координаты для дедупликации
    key_names = sorted(plan.points) if plan.points else None
    best: Solution | None = None
    max_nfev = 200 * (nv + 1)
    use_soft = SOFT_WEIGHT > 0.0 and m > 0
    t0 = time.monotonic()

    for tried, x_start in enumerate(starts, start=1):
        if TIME_BUDGET > 0 and tried > 1:
            elapsed = time.monotonic() - t0
            if (found and elapsed > TIME_BUDGET) or elapsed > 2.0 * TIME_BUDGET:
                break
        if m == 0:
            # No equations: retain deterministic, well-spread sampled geometry
            # rather than passing an empty residual vector to least_squares.
            x = x_start.copy()
        else:
            try:
                x = x_start
                if use_soft:
                    s1 = least_squares(fun_soft, x, method="trf",
                                       xtol=OPT_TOL_SOFT, ftol=OPT_TOL_SOFT, gtol=OPT_TOL_SOFT,
                                       max_nfev=max_nfev)
                    x = np.asarray(s1.x, dtype=float)
                sol = least_squares(fun, x, method="trf",
                                    xtol=OPT_TOL_POLISH, ftol=OPT_TOL_POLISH, gtol=OPT_TOL_POLISH,
                                    max_nfev=max_nfev)
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
        if EARLY_FOUND > 0 and len(found) >= EARLY_FOUND and tried >= EARLY_MIN_STARTS:
            break

    if not found:
        if best is None:
            return [Solution({}, float("inf"), False, "DEGENERATE")]
        return [best]

    order = sorted(range(len(found)),
                   key=lambda i: (round(found[i].residual, 15),
                                  tuple(np.round(norm_cache[i].ravel(), 9).tolist())))
    return [found[i] for i in order]


def _finish(plan: FigurePlan, coords: dict[str, np.ndarray]) -> Solution:
    """Считает невязку на решённых координатах и нормализует фигуру.

    Решение верно, если невязка ≤ TOL И фигура не вырождена (см. degenerate_figure).
    """
    try:
        coords = normalize_coords(plan, coords)
        r = residual_norm(plan, coords)
    except PlanError as e:
        return Solution({}, float("inf"), False, e.code)
    if r > TOL:
        return Solution(coords=coords, residual=float(r), ok=False, reason="RESIDUAL_TOO_HIGH")
    why = degenerate_figure(plan, coords)
    if why:
        # Невязка нулевая, но рисовать нечего: помечаем, чтобы solve() искал дальше,
        # а конвейер при отсутствии альтернатив получил понятный код отказа.
        return Solution(coords=coords, residual=float(r) + 10.0 * TOL, ok=False,
                        reason="DEGENERATE_FIGURE: " + why)
    return Solution(coords=coords, residual=float(r), ok=True, reason="")
