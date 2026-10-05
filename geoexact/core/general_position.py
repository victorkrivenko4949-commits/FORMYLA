"""Общее положение: чертёж не должен случайно получаться равносторонним,
равнобедренным или прямоугольным, если условие этого не требует, а точки не
должны слипаться.

Почему так выходило. Решатель (solver.solve) стартует с точек, расставленных по
окружности через равные углы, — это правильный многоугольник, и least_squares
сходится к ближайшей симметричной конфигурации. Среди нескольких верных решений
(все с невязкой <= TOL) первым оказывалось самое «особое»: равносторонний или
прямоугольный треугольник. Оценка наглядности (gates.readability_score) к тому же
поощряет одинаковые длины (s_uni) — то есть снова равные стороны.

Что делает модуль. Ничего не меняет в ограничениях: любое решение, которое
переставляется, уже удовлетворяет условию задачи. Он только
  1) просит у решателя больше стартов (не меньше GP_SEEDS), чтобы было из чего
     выбирать;
  2) среди верных решений ставит первыми те, где нет случайных совпадений:
     углов около 30/45/60/90/120°, почти равных сторон, точек ближе
     GP_MIN_DIST габарита друг к другу и точек почти на чужой прямой;
  3) в gates.rank_solutions смешивает прежний балл наглядности с баллом общего
     положения, чтобы «красивый, но равносторонний» не выигрывал у разностороннего.

Особенности, которых требует условие (прямой угол, равные стороны), присутствуют
во ВСЕХ кандидатах одинаково и на порядок не влияют — штрафуются только
случайные совпадения. GEOEXACT_GENERAL_POSITION=0 выключает модуль.
"""
from __future__ import annotations

import itertools
import math
import os

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_GENERAL_POSITION") or "1").strip().lower() not in ("0", "no", "off")
GP_SEEDS = int(os.environ.get("GEOEXACT_GP_SEEDS", "48"))      # минимум стартов решателя
GP_MIN_DIST = 0.04          # доля габарита: ближе — точки «слиплись»
GP_LINE_DIST = 0.03         # доля габарита: ближе — точка «почти на прямой»
SPECIAL_ANGLES = (30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0)
ANGLE_TOL = 3.0             # градусов до особого угла, чтобы считать совпадением
RATIO_TOL = 0.03            # относительная разница длин, чтобы считать стороны равными
GP_WEIGHT = 0.5             # доля балла общего положения в итоговом ранге


def _pts(plan, coords) -> list[np.ndarray]:
    names = list(getattr(plan, "points", None) or [])
    names = [n for n in names if n in coords] or sorted(coords)
    out = []
    for n in names:
        p = np.asarray(coords[n], dtype=float)
        if p.shape == (2,) and np.isfinite(p).all():
            out.append(p)
    return out


def _angle_deg(a, b, c) -> float | None:
    u, v = a - b, c - b
    nu, nv = np.hypot(*u), np.hypot(*v)
    if nu < 1e-12 or nv < 1e-12:
        return None
    return math.degrees(math.atan2(abs(u[0] * v[1] - u[1] * v[0]), float(u @ v)))


def score(plan, coords) -> float:
    """Балл общего положения 0..1: 1 — никаких случайных совпадений и слипаний.

    Слагаемые: слипание точек (самое тяжёлое, до 0.6), точка почти на чужой
    прямой (до 0.3), доля троек с особыми углами или почти равными сторонами
    (до 0.4), вытянутость габарита (до 0.2). Особенности, которых требует
    условие, есть у всех кандидатов одинаково и на порядок не влияют.
    """
    P = _pts(plan, coords)
    if len(P) < 3:
        return 1.0
    arr = np.array(P)
    span = float(np.max(arr.max(axis=0) - arr.min(axis=0)))
    if span < 1e-12:
        return 0.0
    n = len(P)
    # 1) слипшиеся точки — худшая пара
    closeness = 0.0
    for i, j in itertools.combinations(range(n), 2):
        d = float(np.hypot(*(P[i] - P[j]))) / span
        if d < GP_MIN_DIST:
            closeness = max(closeness, 1.0 - d / GP_MIN_DIST)
    # 2) особые углы и почти равные стороны — доля «особых» троек
    special, triples = 0.0, 0
    for i, j, k in itertools.combinations(range(n), 3):
        angles = [_angle_deg(P[a], P[b], P[c]) for b, a, c in ((i, j, k), (j, i, k), (k, i, j))]
        if any(x is None or x < 2.0 or x > 178.0 for x in angles):
            continue        # вырожденная тройка (точка на отрезке) — это инцидентность, не форма
        triples += 1
        worst = 0.0
        for ang in angles:
            gap = min(abs(ang - s) for s in SPECIAL_ANGLES)
            if gap < ANGLE_TOL:
                worst = max(worst, 1.0 - gap / ANGLE_TOL)
        sides = sorted(float(np.hypot(*(P[x] - P[y]))) for x, y in ((i, j), (j, k), (i, k)))
        for s1, s2 in ((sides[0], sides[1]), (sides[1], sides[2])):
            rel = (s2 - s1) / s2 if s2 > 1e-12 else 1.0
            if rel < RATIO_TOL:
                worst = max(worst, 1.0 - rel / RATIO_TOL)
        special += worst
    special = special / triples if triples else 0.0
    # 3) точка почти на прямой через две другие (точное попадание — инцидентность
    #    из условия, одинаковая у всех кандидатов, не штрафуется)
    near_line = 0.0
    for i in range(n):
        for j, k in itertools.combinations([x for x in range(n) if x != i], 2):
            a, b, p = P[j], P[k], P[i]
            ab = b - a
            L = float(np.hypot(*ab))
            if L < 1e-12:
                continue
            d = abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / L / span
            if 1e-7 < d < GP_LINE_DIST:
                near_line = max(near_line, 1.0 - d / GP_LINE_DIST)
    # 4) пропорции габарита
    w, h = arr.max(axis=0) - arr.min(axis=0)
    aspect = max(w, h) / max(min(w, h), 1e-12)
    sliver = min(1.0, (aspect - 3.0) / 3.0) if aspect > 3.0 else 0.0
    penalty = 0.6 * closeness + 0.3 * near_line + 0.4 * special + 0.2 * sliver
    return float(max(0.0, 1.0 - penalty))


def _reorder_solutions(plan, solutions):
    """Верные решения — по убыванию общего положения, остальные хвостом как были."""
    good = [s for s in solutions if getattr(s, "ok", False)]
    rest = [s for s in solutions if not getattr(s, "ok", False)]
    if len(good) < 2:
        return list(solutions)
    scored = [(score(plan, s.coords), -i, s) for i, s in enumerate(good)]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [s for _, _, s in scored] + rest


def install(solver_module, gates_module) -> bool:
    """Обернуть solver.solve и gates.rank_solutions. Повторный вызов — no-op."""
    if not ENABLED:
        return False
    done = False
    orig_solve = getattr(solver_module, "solve", None)
    if orig_solve is not None and not getattr(orig_solve, "_general_position", False):
        def solve(plan, n_seeds: int = 24, seed: int = 0, *args, **kwargs):
            sols = orig_solve(plan, max(int(n_seeds), GP_SEEDS), seed, *args, **kwargs)
            try:
                return _reorder_solutions(plan, sols)
            except Exception:  # noqa: BLE001 — эвристика не должна ломать решатель
                return sols
        solve._general_position = True
        solve._original = orig_solve
        solve.__doc__ = orig_solve.__doc__
        solve.__name__ = "solve"
        solver_module.solve = solve
        done = True

    orig_rank = getattr(gates_module, "rank_solutions", None)
    if orig_rank is not None and not getattr(orig_rank, "_general_position", False):
        def rank_solutions(plan, solutions, *args, **kwargs):
            ranked = orig_rank(plan, solutions, *args, **kwargs)
            try:
                if len(ranked) < 2:
                    return ranked
                def key(item):
                    sol, gr = item[0], item[1]
                    base = float(getattr(gr, "score", 0.0) or 0.0)
                    return (1.0 - GP_WEIGHT) * base + GP_WEIGHT * score(plan, sol.coords)
                return sorted(ranked, key=key, reverse=True)
            except Exception:  # noqa: BLE001
                return ranked
        rank_solutions._general_position = True
        rank_solutions._original = orig_rank
        rank_solutions.__doc__ = orig_rank.__doc__
        rank_solutions.__name__ = "rank_solutions"
        gates_module.rank_solutions = rank_solutions
        done = True
    return done
