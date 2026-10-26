# -*- coding: utf-8 -*-
"""«D диаметрально противоположна A, BX=XD, CY=YD»: канонический план без LLM.

Прод-кластер (баг-хант 23–26.10.2026, 6 неудачных отправок пользователя):
«Дан остроугольный треугольник ABC. На его описанной окружности отмечена
точка D, диаметрально противоположная вершине A. Точки X и Y на стороне BC
таковы, что BX = XD и CY = YD (точка X лежит на отрезке BY). Докажите,
что DA — биссектриса угла XDY.»

Починка equidistant_repair ловила две известные кодировки LLM (line_circle,
пересечение с прямой DA), но формализатор находил новые: 26.10.2026 план
прошёл валидацию, а солвер выдал DEGENERATE_FIGURE (треугольник ACD
схлопнулся) — задача снова упала в схему. Условие распознаётся ЦЕЛИКОМ
шаблоном equidistant_repair (_recognize): строим канонический план сами,
без формализатора — как median_parallel для медианы.

Построение точное: D = гомотетия A с центром O=центр описанной окружности
(коэффициент 2); X и Y — пересечения стороны BC с серединными
перпендикулярами к BD и CD (равенства BX=XD и CY=YD выполняются по
построению). Утверждение-«докажите» проверено численно на свободном
семействе (биссектриса — теорема конфигурации).

GEOEXACT_DIAMETRAL_PLAN=0 выключает.
"""
from __future__ import annotations

import functools
import os

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_DIAMETRAL_PLAN") or "1").strip().lower() not in ("0", "no", "off")

CACHE_SUFFIX = "+diaPlan1"


def diametral_plan(text: str, with_aux: bool) -> "FigurePlan | None":  # noqa: F821
    """Канонический план «диаметральная D + равноудалённые X и Y на BC».

    Распознавание — закрытый полный шаблон equidistant_repair: любое
    неизвестное дополнение к условию — отказ (задача уходит формализатору).
    """
    try:
        from .equidistant_repair import _recognize
        cfg = _recognize(text or "")
    except Exception:  # noqa: BLE001
        return None
    if not cfg:
        return None
    try:
        a_v, b_v, c_v = cfg["a"], cfg["b"], cfg["c"]
        d_v, x_v, y_v = cfg["d"], cfg["x"], cfg["y"]
    except Exception:  # noqa: BLE001
        return None
    if not all(isinstance(v, str) and v for v in
               (a_v, b_v, c_v, d_v, x_v, y_v)):
        return None
    if len({a_v, b_v, c_v, d_v, x_v, y_v}) != 6:
        return None

    from .schema import FigurePlan, validate_plan
    points = [a_v, b_v, c_v, d_v, x_v, y_v]
    # Остроугольность и порядок B-X-Y-C — ПО ПОСТРОЕНИЮ, без ограничений:
    # A = M0 + 0.3·(C−B) + 0.9·R90(C−B). |0.3| < 1/2 — углы B и C острые;
    # 0.3² + 0.9² > 1/4 — угол A острый; численно: X ≈ 0.18·BC, Y ≈ 0.58·BC
    # (порядок B-X-Y-C), стороны не равны. Форма фиксирована — канонический
    # чертёж теоремы (прецедент: proof_parallelogram_plan).
    constructions = [
        {"op": "free_point", "out": b_v},
        {"op": "free_point", "out": c_v},
        {"op": "midpoint", "args": [b_v, c_v], "out": "M0_"},
        # U = M0 + 0.3·(C−B)
        {"op": "parallel_point", "args": ["M0_", b_v, c_v], "out": "U_", "value": 0.3},
        # W = M0 + R90(C−B)/2  (поворот B вокруг M0 на −90°)
        {"op": "rotate", "args": [b_v, "M0_"], "out": "W_", "value": -90.0},
        # A = U + 1.8·(W−M0) = M0 + 0.3·(C−B) + 0.9·R90(C−B)
        {"op": "parallel_point", "args": ["U_", "M0_", "W_"], "out": a_v, "value": 1.8},
        # O — центр описанной окружности; D — антипод A: D = 2O − A
        {"op": "circumcenter", "args": [a_v, b_v, c_v], "out": "O_"},
        {"op": "homothety", "args": [a_v, "O_"], "out": d_v, "value": -1.0},
        # X: |BX| = |XD| ⟺ серединный перпендикуляр к BD
        {"op": "midpoint", "args": [b_v, d_v], "out": "M1_"},
        {"op": "perp_point", "args": ["M1_", b_v, d_v], "out": "T1_", "value": 1.0},
        {"op": "line_intersect", "args": [b_v, c_v, "M1_", "T1_"], "out": x_v},
        # Y: |CY| = |YD| ⟺ серединный перпендикуляр к CD
        {"op": "midpoint", "args": [c_v, d_v], "out": "M2_"},
        {"op": "perp_point", "args": ["M2_", c_v, d_v], "out": "T2_", "value": 1.0},
        {"op": "line_intersect", "args": [b_v, c_v, "M2_", "T2_"], "out": y_v},
    ]
    constraints: list[dict] = []
    segments = [
        [a_v, b_v], [b_v, c_v], [c_v, a_v],
        [d_v, a_v], [d_v, x_v], [d_v, y_v],
    ]
    plan = FigurePlan.from_dict({
        "points": points + ["O_", "M0_", "U_", "W_", "M1_", "T1_", "M2_", "T2_"],
        "constructions": constructions,
        "constraints": constraints,
        "draw": {"segments": segments,
                 "hide_labels": ["O_", "M0_", "U_", "W_", "M1_", "T1_", "M2_", "T2_"]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": (f"D — точка, диаметрально противоположная {a_v} "
                  f"(D = 2O − {a_v}); X и Y — пересечения стороны {b_v}{c_v} "
                  f"с серединными перпендикулярами к {b_v}{d_v} и "
                  f"{c_v}{d_v}: равенства {b_v}{x_v}={x_v}{d_v} и "
                  f"{c_v}{y_v}={y_v}{d_v} выполнены точно по построению."),
    })
    try:
        validate_plan(plan)
    except Exception:  # noqa: BLE001
        return None

    # «Докажите, что DA — биссектриса угла XDY» обязано быть теоремой
    # конфигурации: проверяем численно на свободном семействе. Луч DA может
    # делить и внешний угол — принимаем оба (равенство синусов).
    try:
        from .solver import solve as _solve
        sols = [s for s in _solve(plan) if s.ok]
        if len(sols) < 2:
            return None
        for s in sols[:3]:
            P = {k: np.asarray(v, dtype=float) for k, v in s.coords.items()}
            if not {a_v, d_v, x_v, y_v} <= set(P):
                return None
            u1, u2 = P[x_v] - P[d_v], P[a_v] - P[d_v]
            v1, v2 = P[y_v] - P[d_v], P[a_v] - P[d_v]
            def _sin(u, v):
                nu, nv = np.linalg.norm(u), np.linalg.norm(v)
                cr = float(abs(u[0] * v[1] - u[1] * v[0]))
                return cr / (nu * nv)
            if abs(_sin(u1, u2) - _sin(v1, v2)) > 1e-6:
                return None                      # не теорема — отдаём LLM
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
            return diametral_plan(text, with_aux)
        except Exception:  # noqa: BLE001
            return None
    trisected_parallel_plan._diametral_plan = True
    trisected_parallel_plan._original = orig
    return trisected_parallel_plan


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.trisected_parallel_plan, "_diametral_plan", False):
            semantics_module.trisected_parallel_plan = _wrap_trisected(
                semantics_module.trisected_parallel_plan)
        if pipeline_module is not None:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return True
    except Exception:  # noqa: BLE001
        return False
