# -*- coding: utf-8 -*-
"""Внешние построения (квадраты/правильные треугольники на сторонах):
правило 46 + семантическая проверка стороны.

Прод-ошибка (баг-хант 26.10.2026): «На сторонах AB и AC треугольника ABC во
внешнюю сторону построены квадраты ABDE и ACFG. Докажите, что BG = CE и
BG перпендикулярно CE.» — формализатор строил ОБА квадрата поворотами
одного знака вокруг общей вершины A. Но внешность обоих квадратов
математически требует ПРОТИВОПОЛОЖНЫХ знаков (внешняя сторона AB — это
сторона, противоположная C; внешняя сторона AC — противоположная B; для
обхода треугольника эти условия означают разные направления поворота).
Система с двумя opposite_side не решалась вовсе — конвейер ушёл в
приближённый фолбэк (APPROXIMATE: условия выполнены лишь приближённо),
хотя конфигурация допускает точное решение (15 решений).

Вторая опасность, которую ловит проверка: формализатор вовсе не добавляет
opposite_side — решатель тогда выбирает произвольную ориентацию, и квадрат
может оказаться ВНУТРИ треугольника, а чертёж всё равно покажется точным.

Здесь:
  1) правило 46 формализатора: циклическое кодирование квадрата на
     стороне, opposite_side для внешности, ПРОТИВОПОЛОЖНЫЕ знаки для двух
     внешних фигур на сторонах, выходящих из одной вершины;
  2) семантическая проверка: «внешним образом» в тексте + квадрат на
     стороне треугольника нарисован с внутренней стороны — отказ.

GEOEXACT_EXTERNAL_FIGURES=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_EXTERNAL_FIGURES") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: спец-план и проверка меняют приёмку чертежей.
CACHE_SUFFIX = "+extFig2"

EXTRA_RULES = """
46. EXTERNAL_FIGURE_RULE («на стороне AB построен квадрат ABDE (внешним
    образом)»): квадрат на стороне AB кодируй ЦИКЛИЧЕСКИ: E = rotate([B, A],
    -90) (вершина при A), D = rotate([A, B], +90) (вершина при B).
    «Внешним образом / во внешнюю сторону / вне треугольника» — добавь
    ОБЯЗАТЕЛЬНО opposite_side([D, C, A, B]) И opposite_side([E, C, A, B])
    (C — третья вершина треугольника), иначе решатель нарисует квадрат
    внутри. Для ДВУХ внешних фигур на сторонах AB и AC, выходящих из
    одной вершины A, знаки поворотов ПРОТИВОПОЛОЖНЫ: E = rotate([B, A],
    -90), D = rotate([A, B], +90), но G = rotate([C, A], +90), F =
    rotate([A, C], -90). Одинаковые знаки делают внешность ОБЕИХ фигур
    математически невозможной — система ограничений не решается. Если
    текст не требует внешности — opposite_side не добавляй.
"""

_L = r"[A-Z](?:_?\d{1,2})?"

# «треугольника ABC» — опорный треугольник для стороны
_TRI = re.compile(rf"треугольник\w*\s+({_L})({_L})({_L})", re.I)

# «квадрат ABDE» / «равносторонний треугольник ABE»
_SQUARE = re.compile(rf"квадрат\w*\s+({_L})({_L})({_L})({_L})(?![A-Za-z0-9_])", re.I)
_EQUILATERAL = re.compile(
    rf"равносторонн\w*\s+треугольник\w*\s+({_L})({_L})({_L})(?![A-Za-z0-9_])", re.I)
# «квадраты ABDE и ACFG» — второе имя без слова «квадрат».
_SQUARE_PAIR = re.compile(
    rf"квадрат\w*\s+({_L})({_L})({_L})({_L})\s*(?:,|\sи\s)\s*"
    rf"(?:квадрат\w*\s+)?({_L})({_L})({_L})({_L})(?![A-Za-z0-9_])", re.I)


def _collect_squares(statement: str) -> list[tuple[str, str, str, str]]:
    """Все имена квадратов текста (без повторов), включая пары «ABDE и ACFG»."""
    names: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for m in _SQUARE_PAIR.finditer(statement):
        for v in (tuple(m[i].upper() for i in range(1, 5)),
                  tuple(m[i].upper() for i in range(5, 9))):
            if v not in seen:
                seen.add(v)
                names.append(v)
    for m in _SQUARE.finditer(statement):
        v = tuple(m[i].upper() for i in range(1, 5))
        if v not in seen:
            seen.add(v)
            names.append(v)
    return names

_EXTERNAL = re.compile(r"внешн\w*\s+(?:образом|сторону|стороне)|вне\s+треугольник", re.I)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text or "")
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _cross(o, a, b) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _pt(coords, name):
    v = coords[name]
    return (float(v[0]), float(v[1]))


def external_figure_failures(text: str, coords) -> list[str]:
    """«внешним образом» + фигура на стороне треугольника нарисована
    изнутри — отказ: чертёж противоречит условию."""
    fails: list[str] = []
    if not coords or not _EXTERNAL.search(_plain(text or "")):
        return fails
    statement = _plain(text or "")
    m_tri = _TRI.search(statement)
    if m_tri is None:
        return fails
    tri = {m_tri[i].upper() for i in range(1, 4)}
    if len(tri) != 3:
        return fails

    def check_figure(side_a: str, side_b: str, far: list[str], kind: str):
        if side_a.upper() not in tri or side_b.upper() not in tri:
            return
        ref = (tri - {side_a.upper(), side_b.upper()})
        ref = next(iter(ref)) if ref else None
        if ref is None:
            return
        names = [side_a, side_b, ref, *far]
        if not all(n in coords for n in names):
            return
        A, B, R = _pt(coords, side_a), _pt(coords, side_b), _pt(coords, ref)
        if _cross(A, B, R) == 0.0:
            return  # вырожденный чертёж — не ориентация
        ref_sign = 1.0 if _cross(A, B, R) > 0 else -1.0
        for f in far:
            if f not in coords:
                continue
            fs = _cross(A, B, _pt(coords, f))
            if fs == 0.0:
                continue
            if (fs > 0) == (ref_sign > 0):
                fails.append(
                    f"EXTERNAL_FIGURE: {kind} {''.join([side_a, side_b, *far])} "
                    f"построен с внутренней стороны прямой {side_a}{side_b} — "
                    f"в условии сказано «внешним образом»")

    for v in _collect_squares(statement):
        check_figure(v[0], v[1], [v[2], v[3]], "квадрат")
    for m in _EQUILATERAL.finditer(statement):
        check_figure(m[1], m[2], [m[3]], "равносторонний треугольник")
    return list(dict.fromkeys(fails))


# ---------------------------------------------------------------------
# Спец-план: внешние квадраты на сторонах треугольника, без LLM.

# «треугольника ABC» — цикл вершин задаёт знак поворота внешности.
_TRI_STRICT = re.compile(rf"треугольник\w*\s+({_L})({_L})({_L})(?![A-Za-z0-9_])", re.I)

# «BG = CE» — заявленные равенства отрезков.
_EQ_CLAIM = re.compile(rf"({_L})({_L})\s*=\s*({_L})({_L})(?![A-Za-z0-9_])")
# «BG перпендикулярно CE» / «BG и CE перпендикулярны».
_PERP_CLAIM = re.compile(
    rf"({_L})({_L})\s+(?:и\s+)?перпендикулярн\w*\s+(?:и\s+)?({_L})({_L})(?![A-Za-z0-9_])", re.I)

# Данные, которые спец-план не умеет учитывать: длины/углы и дополнительные
# условия. Классическая формулировка теоремы о двух квадратах — без них.
_EXTRA_DATA = re.compile(
    r"\d|равнобедренн|равносторонн|медиан|биссектрис|высот|середин|\bугл|∠", re.I)


def _parse_claims(statement: str, known: set) -> list[tuple[str, dict]]:
    """Заявленные равенства/перпендикулярности между ИЗВЕСТНЫМИ точками."""
    out: list[tuple[str, dict]] = []
    for m in _EQ_CLAIM.finditer(statement):
        a, b, c, d = (m[i].upper() for i in range(1, 5))
        if {a, b, c, d} <= known:
            out.append(("dist_eq", {"type": "dist_eq", "args": [a, b, c, d]}))
    for m in _PERP_CLAIM.finditer(statement):
        a, b, c, d = (m[i].upper() for i in range(1, 5))
        if {a, b, c, d} <= known:
            out.append(("perp", {"type": "perpendicular", "args": [a, b, c, d]}))
    return out


def external_squares_plan(text: str, with_aux: bool) -> "FigurePlan | None":  # noqa: F821
    """Канонический план внешних квадратов на сторонах треугольника.

    Спец-план узкий и берёт только разобранную классическую конфигурацию:
      • «внешнюю сторону / внешним образом» (заявлена внешность);
      • «треугольника ABC»;
      • РОВНО два квадрата на двух сторонах треугольника, выходящих из
        одной общей вершины (как ABDE и ACFG из A);
      • без данных, которых план не умеет учитывать: длин/углов (цифр),
        медиан, биссектрис, середин и т. п.;
      • все упомянутые в тексте точки принадлежат плану;
      • заявленные равенства/перпендикулярности — следствия построения
        (проверяется численно на свободном семействе): ложное «докажите»
        (навязывающее частное положение) даёт отказ плана — задача уходит
        обычным путём к формализатору.

    Вершины строятся поворотами: для стороны XY, записанной в порядке
    обхода треугольника, вершина при X — rotate([Y, X], -90), при Y —
    rotate([X, Y], +90); если сторона записана против обхода — знаки
    меняются. Внешность фиксируется ограничениями opposite_side.
    """
    statement = _plain(text or "")
    if not _EXTERNAL.search(statement):
        return None
    if _EXTRA_DATA.search(statement):
        return None                           # длины/углы/доп.условия — LLM
    m_tri = _TRI_STRICT.search(statement)
    if m_tri is None:
        return None
    tri = [m_tri[i].upper() for i in range(1, 4)]
    if len(set(tri)) != 3:
        return None
    tri_sides = {frozenset((tri[0], tri[1])), frozenset((tri[1], tri[2])),
                 frozenset((tri[2], tri[0]))}
    # циклический порядок: AB, BC, CA — «по обходу»
    cyclic = {(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])}

    squares = []
    for v in _collect_squares(statement):
        if len(set(v)) != 4:
            return None                      # не квадрат — не берёмся
        if frozenset((v[0], v[1])) not in tri_sides:
            return None                      # сторона не треугольника — LLM
        squares.append(v)
    if len(squares) != 2:
        return None                          # только классическая пара
    s1, s2 = (frozenset((v[0], v[1])) for v in squares)
    if s1 == s2:
        return None                          # два квадрата на одной стороне
    if len(s1 & s2) != 1:
        return None                          # стороны не из общей вершины
    new_pts = [p for v in squares for p in (v[2], v[3])]
    if any(p in tri for p in new_pts) or len(set(new_pts)) != 4:
        return None                          # имена вершин конфликтуют

    from .schema import FigurePlan
    points = list(tri)
    constructions = [{"op": "free_point", "out": t} for t in tri]
    constraints: list[dict] = []
    segments = [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]]
    for v in squares:
        x, y, adj_y, adj_x = v          # PQRS: R при Q, S при P
        z = next(t for t in tri if t not in (x, y))
        s = -90 if (x, y) in cyclic else 90
        constructions.append({"op": "rotate", "args": [y, x], "out": adj_x, "value": s})
        constructions.append({"op": "rotate", "args": [x, y], "out": adj_y, "value": -s})
        constraints.append({"type": "opposite_side", "args": [adj_y, z, x, y]})
        constraints.append({"type": "opposite_side", "args": [adj_x, z, x, y]})
        points += [adj_x, adj_y]
        segments += [[x, y], [y, adj_y], [adj_y, adj_x], [adj_x, x]]
    points = list(dict.fromkeys(points))

    # Все упомянутые точки должны принадлежать плану: чужая буква (M —
    # середина BG и т. п.) значит, что текст сложнее конфигурации.
    if not set(re.findall(r"[A-Z]", statement)) <= set(points):
        return None

    claims = _parse_claims(statement, set(points))
    if claims:
        # Ложное «докажите» не должно подменять условие частным положением:
        # проверяем утверждения на СВОБОДНОМ семействе (без них). Не держатся
        # — значит это не теорема данной конфигурации, отдаём задачу LLM.
        from .solver import solve as _solve
        base = FigurePlan.from_dict({
            "points": points, "constructions": constructions,
            "constraints": constraints,
            "draw": {"segments": segments},
            "target": {"kind": "none", "args": []}, "scale_free": True})
        sols = [s for s in _solve(base) if s.ok]
        if len(sols) < 2:
            return None
        import numpy as _np
        for kind, c in claims:
            a, b, d, e = c["args"]
            held = True
            for s in sols[:3]:
                P = {k: _np.asarray(v, dtype=float) for k, v in s.coords.items()}
                if kind == "dist_eq":
                    held = held and abs(_np.linalg.norm(P[b] - P[a])
                                        - _np.linalg.norm(P[e] - P[d])) < 1e-6
                else:
                    held = held and abs(float(_np.dot(P[b] - P[a], P[e] - P[d]))) < 1e-6
            if not held:
                return None
        for kind, c in claims:
            constraints.append(c)
            if kind == "dist_eq":
                a, b, d, e = c["args"]
                segments.append([a, b])
                segments.append([d, e])

    return FigurePlan.from_dict({
        "points": points,
        "constructions": constructions,
        "constraints": constraints,
        "draw": {"segments": segments},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": (
            "Квадраты на сторонах треугольника построены поворотами на 90° "
            "с внешней стороны (opposite_side фиксирует внешность)."),
    })


def _wrap_trisected(orig):
    """Расширение цепочки спец-планов: сначала прежняя цепь (Симсон и др.),
    затем — внешние квадраты на сторонах треугольника."""
    @functools.wraps(orig)
    def trisected_parallel_plan(text, with_aux):
        try:
            plan = orig(text, with_aux)
            if plan is not None:
                return plan
        except Exception:  # noqa: BLE001
            pass
        try:
            return external_squares_plan(text, with_aux)
        except Exception:  # noqa: BLE001
            return None
    trisected_parallel_plan._external_figures = True
    trisected_parallel_plan._original = orig
    return trisected_parallel_plan


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in external_figure_failures(text, coords)
                               if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._external_figures = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "46." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "46." in llm_module.SYS_FORMALIZE
        ok = ok and "EXTERNAL_FIGURE_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: спец-план + проверка внешности + правило 46 + суффикс."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.trisected_parallel_plan, "_external_figures", False):
            semantics_module.trisected_parallel_plan = _wrap_trisected(
                semantics_module.trisected_parallel_plan)
        if not getattr(semantics_module.semantic_failures, "_external_figures", False):
            semantics_module.semantic_failures = _wrap_semantic_failures(
                semantics_module.semantic_failures)
        ok = _install_llm_rules(llm_module)
        if pipeline_module is not None:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False
