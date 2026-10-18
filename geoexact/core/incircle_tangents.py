"""Касательные из точек прямой AC к вписанной окружности: правила и точный план.

Повод (региональный этап ВсОШ 2014/15, 9 класс, задача 4): «В неравнобедренном
треугольнике ABC биссектрисы угла ABC и смежного с ним угла пересекают прямую AC
в точках B_1 и B_2. Из B_1 и B_2 проведены касательные к вписанной окружности,
отличные от AC, касающиеся её в K_1 и K_2. Докажите, что B, K_1, K_2 лежат на
одной прямой». Конвейер не смог построить план ни с одной попытки и отдал
эскиз по ключевым словам (9-render-sketch): равносторонний треугольник с
окружностью без B_1, B_2, K_1, K_2.

Что делает модуль (обёртки, как general_position / formalize_rules / convexity):
  1) EXTRA_RULES для формализатора: точка касания второй касательной из точки P
     на прямой AC — ОТРАЖЕНИЕ точки касания K относительно PI (reflect_line), а
     не tangent_point с перебором корней (один корень всегда совпадает с K);
     внешняя биссектриса — external_bisector_point; «неравнобедренный» — без
     dist_eq/angle_eq.
  2) Точный план без модели для этой семьи условий (обёртка
     semantics.theorem_plan): I=incenter, K=foot(I,A,C), B1=bisector_point,
     B2=external_bisector_point, K1=reflect_line(K,B,I), K2=reflect_line(K,B2,I).
     Касательные из B1 симметричны относительно B1I=BI, из B2 — относительно
     B2I, поэтому K1 и K2 — точные точки касания; проверено численно
     (|IK1|=|IK2|=r, B1K1 ⟂ IK1, B2K2 ⟂ IK2).
  3) Диагностика эскиза: _sketch_result дописывает FALLBACK_FROM с этапом и
     кодом исходного отказа — раньше эскиз терял причину (stage пустой).

GEOEXACT_INCIRCLE_TANGENTS=0 выключает всё.
"""
from __future__ import annotations

import os
import re

ENABLED = (os.environ.get("GEOEXACT_INCIRCLE_TANGENTS") or "1").strip().lower() not in ("0", "no", "off")
MARK = "reflect_line(K,P,I)"

EXTRA_RULES = """
30. Касательная из точки P, лежащей на прямой стороны AC, к ВПИСАННОЙ окружности
    (центр I), отличная от AC. Пусть K=foot(I,A,C) — точка касания с AC. Тогда точка
    касания второй касательной: T=reflect_line(K,P,I) (обе касательные из P
    симметричны относительно прямой PI). НЕ используй tangent_point с перебором
    value: один из корней совпадает с K, и чертёж будет отвергнут. Касательную рисуй
    отрезком [P,T]; если P вне отрезка AC, прямую AC рисуй как lines [[A,C]].
31. Пересечение биссектрисы угла B треугольника ABC с прямой AC —
    bisector_point(B,A,C); биссектрисы СМЕЖНОГО (внешнего) угла —
    external_bisector_point(B,A,C). Внешняя точка лежит на продолжении AC.
32. «Неравнобедренный», «разносторонний» треугольник: вершины — три free_point,
    никаких dist_eq/angle_eq между сторонами или углами, форму не фиксируй.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
_FAMILY = re.compile(
    rf"биссектрис\w*\s+угла\s+([A-Z])([A-Z])([A-Z])\s+и\s+смежн\w*\s+с\s+ним\s+угла\s+"
    rf"пересека\w*\s+прям\w*\s+([A-Z])([A-Z])\s+в\s+точках\s+({_NAME})\s+и\s+({_NAME})", re.I)
_TANGENTS = re.compile(r"касательн\w*\s+к\s+вписанн\w*\s+окружност\w*", re.I)
_TOUCH = re.compile(rf"каса\w*\s+(?:её|ее)?\s*в\s+точках\s+({_NAME})\s+и\s+({_NAME})", re.I)
_SCALENE = re.compile(r"неравнобедренн|разносторонн", re.I)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def recognize(text: str) -> dict | None:
    """Имена точек семьи «биссектрисы угла B и смежного → B1,B2 на AC; касательные → K1,K2»."""
    t = _plain(text)
    m = _FAMILY.search(t)
    if not m or not _TANGENTS.search(t):
        return None
    x, b, z, p, q = (m[i].upper() for i in range(1, 6))
    if b in (x, z) or {x, z} != {p, q}:
        return None
    touch = _TOUCH.search(t)
    if not touch:
        return None
    b1, b2 = m[6].upper(), m[7].upper()
    k1, k2 = touch[1].upper(), touch[2].upper()
    names = [p, q, b, b1, b2, k1, k2]
    if len(set(names)) != len(names) or "I" in names or "K" in names:
        return None
    return {"A": p, "C": q, "B": b, "B1": b1, "B2": b2, "K1": k1, "K2": k2}


def incircle_tangents_plan(text: str, with_aux: bool):
    """FigurePlan для распознанной семьи условий или None."""
    n = recognize(text)
    if n is None:
        return None
    from .schema import FigurePlan, validate_plan
    A, B, C, B1, B2, K1, K2 = n["A"], n["B"], n["C"], n["B1"], n["B2"], n["K1"], n["K2"]
    plan = FigurePlan.from_dict({
        "points": [A, B, C, "I", "K", B1, B2, K1, K2],
        "constructions": [
            {"op": "free_point", "out": A},
            {"op": "free_point", "out": B},
            {"op": "free_point", "out": C},
            {"op": "incenter", "out": "I", "args": [A, B, C]},
            {"op": "foot", "out": "K", "args": ["I", A, C]},
            {"op": "bisector_point", "out": B1, "args": [B, A, C]},
            {"op": "external_bisector_point", "out": B2, "args": [B, A, C]},
            # касательные из B1 симметричны относительно B1I = BI, из B2 — относительно B2I
            {"op": "reflect_line", "out": K1, "args": ["K", B, "I"]},
            {"op": "reflect_line", "out": K2, "args": ["K", B2, "I"]},
        ],
        "constraints": [],
        "draw": {
            "segments": [[A, B], [B, C], [A, C], [B, B1], [B, B2], [B1, K1], [B2, K2]],
            "lines": [[A, C]],
            "circles": [["I", "K"]],
            "aux_segments": [[B, K1], [K1, K2]] if with_aux else [],
            "hide_labels": ["K"],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": ("Иллюстрация условия: B1 и B2 — точки внутренней и внешней биссектрис угла B "
                  "на прямой AC; K1 и K2 — точки касания вторых касательных из них к вписанной "
                  "окружности. Коллинеарность B, K1, K2 — утверждение задачи, рисунок её не доказывает."),
    })
    validate_plan(plan)
    return plan


def _wrap_theorem_plan(orig):
    def theorem_plan(text, with_aux, *args, **kwargs):
        res = orig(text, with_aux, *args, **kwargs)
        if res is not None:
            return res
        try:
            return incircle_tangents_plan(text, with_aux)
        except Exception:  # noqa: BLE001 — точный план вспомогательный
            return None
    theorem_plan._incircle_tangents = True
    theorem_plan._original = orig
    theorem_plan.__doc__ = getattr(orig, "__doc__", None)
    theorem_plan.__name__ = "theorem_plan"
    return theorem_plan


def _wrap_sketch(orig):
    def _sketch_result(text, with_aux, base, aux=None):
        res = orig(text, with_aux, base, aux)
        try:
            stage = getattr(base, "stage", "") or ""
            reason = getattr(base, "reason", "") or ""
            if res is not None and (stage or reason):
                detail = (getattr(base, "detail", "") or "")[:200]
                res.warnings.append(f"FALLBACK_FROM: {stage} {reason} {detail}".rstrip())
        except Exception:  # noqa: BLE001
            pass
        return res
    _sketch_result._incircle_tangents = True
    _sketch_result._original = orig
    _sketch_result.__doc__ = getattr(orig, "__doc__", None)
    _sketch_result.__name__ = "_sketch_result"
    return _sketch_result


def _append_rules(llm_module) -> bool:
    base = getattr(llm_module, "SYS_FORMALIZE", None)
    aux = getattr(llm_module, "SYS_AUX", None)
    if not isinstance(base, str) or MARK in base:
        return False
    new_base = base.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    llm_module.SYS_FORMALIZE = new_base
    if isinstance(aux, str):
        if aux.startswith(base):
            llm_module.SYS_AUX = new_base + aux[len(base):]
        elif MARK not in aux:
            llm_module.SYS_AUX = aux.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    return True


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Правила формализатора, точный план семьи и диагностика эскиза. Повторно — no-op."""
    if not ENABLED:
        return False
    done = _append_rules(llm_module)
    orig_tp = getattr(semantics_module, "theorem_plan", None)
    if orig_tp is not None and not getattr(orig_tp, "_incircle_tangents", False):
        semantics_module.theorem_plan = _wrap_theorem_plan(orig_tp)
        done = True
    if pipeline_module is None:
        try:
            from . import pipeline as pipeline_module  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            pipeline_module = None
    orig_sk = getattr(pipeline_module, "_sketch_result", None) if pipeline_module else None
    if orig_sk is not None and not getattr(orig_sk, "_incircle_tangents", False):
        pipeline_module._sketch_result = _wrap_sketch(orig_sk)
        done = True
    return done
