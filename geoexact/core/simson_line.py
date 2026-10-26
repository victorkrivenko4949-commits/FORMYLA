# -*- coding: utf-8 -*-
"""Прямая Симсона: «основания перпендикуляров из P на ПРЯМЫЕ» + «P на
описанной окружности» — канонический план + защита от вырожденной хорды.

Прод-ошибка (баг-хант 26.10.2026): «Точка P лежит на описанной окружности
треугольника ABC. X, Y и Z — основания перпендикуляров, опущенных из точки P
на прямые AB, BC и CA соответственно. Докажите, что точки X, Y и Z лежат на
одной прямой.» Все три плана формализатора строили P как
line_circle(A, B, O, A) — пересечение прямой AB (хорды!) с описанной
окружностью, то есть P совпадал с вершиной A или B. Вырожденная система
ушла в схематичный фолбэк (FALLBACK_FROM: 6-solve DEGENERATE) — честно, но
точный чертёж конфигурация допускает: свободная точка + on_circle даёт
16 решений, все корректны.

Здесь три исправления одного корня:
  1) simson_plan — распознавание фразы и канонический план без LLM
     (в цепочке спец-планов, обёртка trisected_parallel_plan);
  2) правило 45 формализатора: «точка P лежит на окружности» — free_point +
     on_circle, НИКОГДА line_circle по выдуманной хорде;
  3) семантическая проверка: построенная через line_circle точка совпала с
     концом хорды — чертёж вырожден, это отказ, а не предупреждение.

GEOEXACT_SIMSON=0 выключает.
"""
from __future__ import annotations

import functools
import math
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_SIMSON") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новый спец-план и проверка меняют приёмку чертежей.
CACHE_SUFFIX = "+simson1"

EXTRA_RULES = """
45. POINT_ON_CIRCLE_RULE («точка P лежит на описанной окружности треугольника
    ABC» / «точка P лежит на окружности ω»): НЕ задавай P через line_circle —
    пересечение ПРОИЗВОЛЬНОЙ хорды (например прямой AB) с окружностью даёт
    ВЕРШИНУ треугольника, и чертёж вырождается. Точка на окружности без
    явной прямой в условии кодируется free_point + ограничение
    on_circle([P, O, O, A]) (O — центр окружности, A — точка на ней).
    line_circle/line_circle_other допустимы ТОЛЬКО если в тексте названа
    прямая/отрезок, на котором лежит точка («прямая l пересекает окружность
    в точке P»). Основания перпендикуляров на прямую AB — конструкция
    foot([P, A, B]); на «сторону/отрезок AB» — тоже foot, но добавь
    on_segment([X, A, B]) только если основание обязано лежать на отрезке.
"""

_N = r"[A-Z](?:_?\d{1,2})?"

# «Точка P лежит на описанной окружности треугольника ABC»
_P_ON_CIRC = re.compile(
    rf"точк\w*\s+({_N})\s+(?:лежит|находится|расположена)\s+на\s+описанн\w*\s+"
    rf"окружност\w+\s+треугольник\w*\s+({_N})({_N})({_N})", re.I)

# «X, Y и Z — основания перпендикуляров, опущенных из точки P на прямые
#  AB, BC и CA»
_FEET = re.compile(
    rf"({_N})\s*,\s*({_N})\s+и\s+({_N})\s+[—–-]+\s+основани\w*\s+"
    rf"перпендикуляр\w*,?\s+опущенн\w*\s+из\s+точки\s+({_N})\s+на\s+прям\w*\s+"
    rf"({_N})({_N})\s*,\s*({_N})({_N})\s+и\s+({_N})({_N})", re.I)

# «точки X, Y и Z лежат на одной прямой» (заключение теоремы)
_COLLINEAR = re.compile(
    rf"(?:точки\s+)?({_N})\s*,\s*({_N})\s+и\s+({_N})\s+"
    rf"(?:лежат|находятся|принадлежат)\s+на\s+одной\s+прямой|"
    rf"точки\s+({_N})\s*,\s*({_N})\s+и\s+({_N})\s+коллинеарн\w*", re.I)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def simson_plan(text: str, with_aux: bool) -> "FigurePlan | None":  # noqa: F821
    """Канонический план прямой Симсона по распознанной фразе, иначе None.

    Требования к фразе (все обязательны, чтобы не зацепить чужие задачи):
      • «точка P лежит на описанной окружности треугольника ABC»;
      • «X, Y и Z — основания перпендикуляров, опущенных из точки P
        на прямые AB, BC и CA» (именно ПРЯМЫЕ, не стороны);
      • заключение «X, Y и Z лежат на одной прямой»;
      • три прямые — ровно стороны треугольника ABC.
    """
    statement = _plain(text or "")
    m_circ = _P_ON_CIRC.search(statement)
    if m_circ is None:
        return None
    p_label = m_circ[1].upper()
    tri = [m_circ[i].upper() for i in range(2, 5)]
    m_feet = _FEET.search(statement)
    if m_feet is None:
        return None
    feet = [m_feet[i].upper() for i in range(1, 4)]
    src = m_feet[4].upper()
    lines = [(m_feet[5].upper(), m_feet[6].upper()),
             (m_feet[7].upper(), m_feet[8].upper()),
             (m_feet[9].upper(), m_feet[10].upper())]
    if src != p_label or len(set(feet)) != 3 or p_label in tri or p_label in feet:
        return None
    if any(f in tri for f in feet):
        return None
    sides = {frozenset(s) for s in (tri[0] + tri[1], tri[1] + tri[2], tri[2] + tri[0])}
    # Каждая прямая — сторона треугольника, каждая сторона названа.
    line_sets = [frozenset(l) for l in lines]
    if sorted(map(sorted, line_sets)) != sorted(map(sorted, sides)):
        return None
    m_col = _COLLINEAR.search(statement)
    if m_col is None:
        return None
    claim = {m_col[i].upper() for i in range(1, 4) if m_col[i]}
    if claim != set(feet):
        return None
    foot_by_line = dict(zip(map(frozenset, lines), feet))
    a, b, c = tri
    from .schema import FigurePlan
    constructions = [
        {"op": "free_point", "out": a}, {"op": "free_point", "out": b},
        {"op": "free_point", "out": c},
        {"op": "circumcenter", "args": [a, b, c], "out": "O"},
        {"op": "free_point", "out": p_label},
    ]
    for u, v in ((a, b), (b, c), (c, a)):
        constructions.append(
            {"op": "foot", "args": [p_label, u, v], "out": foot_by_line[frozenset((u, v))]})
    x, y, z = (foot_by_line[frozenset(s)] for s in ((a, b), (b, c), (c, a)))
    return FigurePlan.from_dict({
        "points": [a, b, c, "O", p_label, x, y, z],
        "constructions": constructions,
        "constraints": [
            {"type": "on_circle", "args": [p_label, "O", "O", a]},
            {"type": "collinear", "args": [x, y, z]},
        ],
        "draw": {
            "segments": [[a, b], [b, c], [c, a],
                         [p_label, x], [p_label, y], [p_label, z]],
            "lines": [[x, y]],
            "circles": [["O", a]],
            "right_angles": [[p_label, x, a], [p_label, y, b], [p_label, z, c]],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": (
            f"Точка {p_label} на описанной окружности треугольника {a}{b}{c}; "
            f"{x}, {y}, {z} — основания перпендикуляров из {p_label} на прямые "
            f"{a}{b}, {b}{c}, {c}{a}. Прямая {x}{y} — прямая Симсона."),
    })


def chord_coincidence_failures(plan, coords) -> list[str]:
    """line_circle по хорде окружности, чей выход совпал с концом хорды.

    Формализатор, не зная правила 45, строит «точку на окружности» как
    пересечение хорды с окружностью — выход либо вершина (вырождение),
    либо неверная ветвь. Это отказ: чертёж с совпавшими заявленными
    точками не может показываться как точный.
    """
    fails: list[str] = []
    if plan is None or not coords:
        return fails
    pts = coords
    span = max(
        (math.hypot(float(p[0] - q[0]), float(p[1] - q[1]))
         for p, q in _pairs(pts.values())), default=1.0) or 1.0
    for con in getattr(plan, "constructions", None) or []:
        op = getattr(con, "op", None)
        args = list(getattr(con, "args", None) or [])
        out = getattr(con, "out", None)
        if op != "line_circle" or len(args) != 4 or not out or out not in pts:
            continue
        u, v, cen, ref = args
        if not all(k in pts for k in (u, v, cen, ref)):
            continue
        r = _dist(pts[cen], pts[ref])
        if r <= 1e-12:
            continue
        # обе точки прямой лежат на окружности (центр cen, радиус r)
        if abs(_dist(pts[cen], pts[u]) - r) > 1e-6 * span:
            continue
        if abs(_dist(pts[cen], pts[v]) - r) > 1e-6 * span:
            continue
        if (_dist(pts[out], pts[u]) <= 1e-6 * span
                or _dist(pts[out], pts[v]) <= 1e-6 * span):
            fails.append(
                f"POINT_ON_CIRCLE: точка {out} совпала с концом хорды {u}{v} — "
                f"точка на окружности кодируется free_point + on_circle, "
                f"а не line_circle по хорде (правило 45)")
    return fails


def _dist(p, q) -> float:
    p, q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)
    return float(np.hypot(*(p - q)))


def _pairs(seq):
    seq = list(seq)
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            yield seq[i], seq[j]


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in chord_coincidence_failures(plan, coords)
                               if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._simson = True
    semantic_failures._original = orig
    return semantic_failures


def _wrap_trisected(orig):
    """Расширение цепочки спец-планов: сначала Симсон, потом оригинал."""
    @functools.wraps(orig)
    def trisected_parallel_plan(text, with_aux):
        try:
            plan = simson_plan(text, with_aux)
            if plan is not None:
                return plan
        except Exception:  # noqa: BLE001
            pass
        return orig(text, with_aux)
    trisected_parallel_plan._simson = True
    trisected_parallel_plan._original = orig
    return trisected_parallel_plan


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "45." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "45." in llm_module.SYS_FORMALIZE
        ok = ok and "POINT_ON_CIRCLE_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: спец-план + проверка хорды + правило 45 + суффикс кэша."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.trisected_parallel_plan, "_simson", False):
            semantics_module.trisected_parallel_plan = _wrap_trisected(
                semantics_module.trisected_parallel_plan)
        if not getattr(semantics_module.semantic_failures, "_simson", False):
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
