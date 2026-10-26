# -*- coding: utf-8 -*-
"""«Точка с отношением на медиане + параллельная прямая»: спец-план без LLM.

Прод-кейс (баг-хант 26.10.2026, задача пользователя, owner=5): «В треугольнике
ABC на медиане BM отмечена точка K так, что BK:KM = 3:1. Через точку K
проведена прямая, параллельная AC, пересекающая стороны AB и BC в точках P
и Q соответственно. Найдите отношение площади четырёхугольника APQC к
площади треугольника ABC.» — формализатор строил P по прямой [K, Q] до
построения Q (FORWARD_REF), три повтора не справились, конвейер ушёл в
схематичный эскиз (на чертеже только четырёхугольник APQC без треугольника).

Конфигурация — точная аффинная: медиана из вершины V к середине M
противоположной стороны SZ, точка K на VM с данным отношением, прямая
через K параллельно SZ пересекает стороны VS и VZ. Канонический план
строит её без ограничений-циклов: X = параллельный перенос SZ в K, затем
два line_intersect.

Спец-план берёт только разобранное семейство (любые имена точек, любое
отношение m:n, медиана из любой вершины); любые данные, которых план не
умеет учитывать (длины, углы, вторая точка на другой медиане и т. п.),
отдают задачу формализатору.

GEOEXACT_MEDIAN_PARALLEL=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

ENABLED = (os.environ.get("GEOEXACT_MEDIAN_PARALLEL") or "1").strip().lower() not in ("0", "no", "off")

CACHE_SUFFIX = "+medPar1"

_L = r"[A-Z](?:_?\d{1,2})?"

# «В треугольнике ABC ... на медиане BM отмечена точка K так, что BK:KM = 3:1»
_TRI = re.compile(rf"треугольник\w*\s+({_L})({_L})({_L})(?![A-Za-z0-9_])", re.I)
_MEDIAN = re.compile(rf"на\s+медиан\w*\s+({_L})({_L})(?![A-Za-z0-9_])", re.I)
_RATIO = re.compile(rf"({_L})({_L})\s*:\s*({_L})({_L})\s*=\s*(\d+)\s*:\s*(\d+)")
# «прям[ая|ую], параллельн[ая|ую] AC» / «параллельно AC»
_PARALLEL = re.compile(
    rf"параллельн\w+\s+({_L})({_L})(?![A-Za-z0-9_])|параллельно\s+({_L})({_L})(?![A-Za-z0-9_])")
# «пересека[ющая/ет] стороны AB и BC в точках P и Q»
_MEETS = re.compile(
    rf"пересека\w*\s+стороны\w*\s+({_L})({_L})\s+и\s+({_L})({_L})\s+"
    rf"в\s+точках?\s+({_L})\s+и\s+({_L})(?![A-Za-z0-9_])")

# Данные, которые спец-план не умеет учитывать.
_EXTRA_DATA = re.compile(
    r"\b(?:BC|CA|AB|AC|BD)\s*=\s*\d|равнобедренн|равносторонн|прямоугольн|высот|"
    r"биссектрис|угол\s+[A-Z]\s*=|площадь\s+\w+\s*=", re.I)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text or "")
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def median_parallel_plan(text: str, with_aux: bool) -> "FigurePlan | None":  # noqa: F821
    """Канонический план: K на медиане с отношением m:n, PQ ∥ стороне."""
    statement = _plain(text or "")
    if _EXTRA_DATA.search(statement):
        return None
    m_tri = _TRI.search(statement)
    if m_tri is None:
        return None
    tri = [m_tri[i].upper() for i in range(1, 4)]
    if len(set(tri)) != 3:
        return None

    m_med = _MEDIAN.search(statement)
    if m_med is None:
        return None
    v_v, m_v = m_med[1].upper(), m_med[2].upper()
    if v_v not in tri or m_v in tri:
        return None                       # медиана не из вершины — LLM

    m_r = _RATIO.search(statement)
    if m_r is None:
        return None
    # «BK:KM = 3:1»: B=V, K в обоих отрезках, M — конец медианы
    a1, k1, k2, a2 = (m_r[i].upper() for i in range(1, 5))
    if a1 != v_v or a2 != m_v or k1 != k2 or k1 in tri or k1 == m_v:
        return None                       # отношение не про точку на медиане
    k_v = k1
    m_num, n_num = int(m_r[5]), int(m_r[6])
    if m_num <= 0 or n_num <= 0 or m_num + n_num > 10_000:
        return None

    m_par = _PARALLEL.search(statement)
    if m_par is None:
        return None
    if m_par[1]:
        s_v, z_v = m_par[1].upper(), m_par[2].upper()
    else:
        s_v, z_v = m_par[3].upper(), m_par[4].upper()
    if {s_v, z_v} != set(tri) - {v_v}:
        return None                       # параллель не противоположной стороне

    m_meet = _MEETS.search(statement)
    if m_meet is None:
        return None
    l1, l2, r1s, r2s, p_v, q_v = (m_meet[i].upper() for i in range(1, 7))
    sides = {frozenset((l1, l2)), frozenset((r1s, r2s))}
    if sides != {frozenset((v_v, s_v)), frozenset((v_v, z_v))}:
        return None                       # прямая пересекает не стороны при V
    if p_v == q_v or {p_v, q_v} & set(tri) or p_v == m_v or q_v == m_v:
        return None

    # порядок P/Q по сторонам: P на стороне с s_v, Q — с z_v
    p_side = frozenset((l1, l2))
    if p_side == frozenset((v_v, s_v)):
        p_on_s, q_on_z = p_v, q_v
    else:
        p_on_s, q_on_z = q_v, p_v

    from .schema import FigurePlan
    points = list(tri) + [m_v, k_v, p_on_s, q_on_z]
    if not set(re.findall(r"[A-Z]", statement)) <= set(points):
        return None                       # чужие буквы — текст сложнее семейства

    frac = m_num / (m_num + n_num)
    constructions = [
        {"op": "free_point", "out": t} for t in tri]
    constructions += [
        {"op": "midpoint", "args": [s_v, z_v], "out": m_v},
        # K на VM: VK:KM = m:n → K = homothety(M, V, m/(m+n))
        {"op": "homothety", "args": [m_v, v_v], "out": k_v, "value": frac},
        # X: KX ∥ SZ, |KX| = |SZ| (параллельный перенос стороны в K)
        {"op": "parallel_point", "args": [k_v, s_v, z_v], "out": "X_", "value": 1.0},
        {"op": "line_intersect", "args": [k_v, "X_", v_v, z_v], "out": q_on_z},
        {"op": "line_intersect", "args": [k_v, q_on_z, v_v, s_v], "out": p_on_s},
    ]
    constraints = [
        {"type": "on_segment", "args": [k_v, v_v, m_v]},
        {"type": "on_segment", "args": [p_on_s, v_v, s_v]},
        {"type": "on_segment", "args": [q_on_z, v_v, z_v]},
    ]
    segments = [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]],
                [v_v, m_v], [p_on_s, q_on_z], [v_v, k_v]]

    plan = FigurePlan.from_dict({
        "points": points + ["X_"],
        "constructions": constructions,
        "constraints": constraints,
        "draw": {"segments": segments},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": (f"K делит медиану {v_v}{m_v} в отношении {m_num}:{n_num}; "
                  f"прямая через K параллельна {s_v}{z_v} — точное "
                  f"аффинное построение (перенос стороны в K и два "
                  f"пересечения со сторонами)."),
    })
    try:
        from .schema import validate_plan
        validate_plan(plan)
    except Exception:  # noqa: BLE001
        return None
    return plan


def _wrap_trisected(orig):
    @functools.wraps(orig)
    def trisected_parallel_plan(text, with_aux):
        try:
            plan = orig(text, with_aux)
            if plan is not None:
                return plan
        except Exception:  # noqa: BLE001
            pass
        try:
            return median_parallel_plan(text, with_aux)
        except Exception:  # noqa: BLE001
            return None
    trisected_parallel_plan._median_parallel = True
    trisected_parallel_plan._original = orig
    return trisected_parallel_plan


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: спец-план в цепочку + суффикс версии движка."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.trisected_parallel_plan, "_median_parallel", False):
            semantics_module.trisected_parallel_plan = _wrap_trisected(
                semantics_module.trisected_parallel_plan)
        if pipeline_module is not None:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return True
    except Exception:  # noqa: BLE001
        return False
