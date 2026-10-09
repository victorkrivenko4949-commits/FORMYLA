# -*- coding: utf-8 -*-
"""services/aux_templates.py — каталог типовых доп. построений без LLM.

Быстрый путь для распространённых конфигураций.  Матчинг детерминированный:
сущности берутся из BuildContext (объекты уже построены) и из условия.

Каждый шаблон: trigger (base_plan, condition, ctx) -> Optional[aux_constructions].
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from services.figure_plan_validator import _base_constructions, _loads


def _point_ids(ctx: Any) -> List[str]:
    return list(getattr(ctx, "points", {}) or {}).copy()


def _segment_edges(constructions: List[dict]) -> List[tuple]:
    """Все отрезки/стороны: (p1, p2)."""
    out = []
    for c in constructions:
        if c.get("type") in ("segment", "line", "ray"):
            p1, p2 = c.get("p1"), c.get("p2")
            if p1 and p2:
                out.append((p1, p2))
    return out


def _circle_centers(constructions: List[dict]) -> List[str]:
    out = []
    for c in constructions:
        if c.get("type") in ("circle_center_radius", "circumcircle", "incircle"):
            center = c.get("center")
            if center:
                out.append(center)
    return out


def _has_type(constructions: List[dict], ctype: str) -> bool:
    return any(c.get("type") == ctype for c in constructions)


def _t_circumcenter_third_radius(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Центр описанной окружности + треугольник: радиус к третьей вершине."""
    cs = _base_constructions(_loads(base_plan))
    centers = _circle_centers(cs)
    if not centers:
        return None
    # Ищем треугольник (три free_point + sides).
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 3:
        return None
    center = centers[0]
    others = [p for p in pts if p != center]
    if not others:
        return None
    vertex = others[0]
    return [{
        "type": "segment", "id": f"aux_radius_{center}{vertex}",
        "p1": center, "p2": vertex,
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "радиус к вершине",
        "solution_evidence": {"step_no": 1, "quote": "Проведём радиус " + center + vertex},
    }]


def _t_center_to_chord_perp(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Центр + хорда: перпендикуляр из центра к хорде."""
    cs = _base_constructions(_loads(base_plan))
    centers = _circle_centers(cs)
    if not centers:
        return None
    edges = _segment_edges(cs)
    if not edges:
        return None
    center = centers[0]
    a, b = edges[0]
    return [{
        "type": "foot_perpendicular", "id": f"aux_foot_{center}_{a}{b}",
        "p1": center, "line1": f"{a}{b}",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "перпендикуляр из центра к хорде",
        "solution_evidence": {"step_no": 1, "quote": "Опустим перпендикуляр из центра к хорде"},
    }]


def _t_radius_to_tangency(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Касательная + точка касания: радиус в точку касания."""
    cs = _base_constructions(_loads(base_plan))
    centers = _circle_centers(cs)
    tang = [c for c in cs if c.get("type") in ("tangent_at_point", "tangent_from_point")]
    if not centers or not tang:
        return None
    center = centers[0]
    touch = tang[0].get("p1") or tang[0].get("point")
    if not touch:
        return None
    return [{
        "type": "segment", "id": f"aux_radius_{center}{touch}",
        "p1": center, "p2": touch,
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "радиус в точку касания",
        "solution_evidence": {"step_no": 1, "quote": "Проведём радиус в точку касания"},
    }]


def _t_midline(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Середины двух сторон: средняя линия."""
    cs = _base_constructions(_loads(base_plan))
    mids = [c.get("id") for c in cs if c.get("type") == "midpoint" and c.get("id")]
    if len(mids) < 2:
        return None
    a, b = mids[0], mids[1]
    return [{
        "type": "segment", "id": f"aux_midline_{a}{b}",
        "p1": a, "p2": b,
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "средняя линия",
        "solution_evidence": {"step_no": 1, "quote": "Соединим середины"},
    }]


def _t_altitude_from_right_angle(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Прямоугольный треугольник: высота из прямого угла."""
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "triangle_right") and "прямоугольн" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 3:
        return None
    a, b, c = pts[0], pts[1], pts[2]
    return [{
        "type": "altitude", "id": "aux_alt_right",
        "vertex": a, "side_a": b, "side_b": c, "foot_id": "aux_foot_H",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "высота из прямого угла",
        "solution_evidence": {"step_no": 1, "quote": "Опустим высоту"},
    }]


def _t_parallelogram_completion(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Три точки + «параллелограмм»: четвёртая вершина."""
    cs = _base_constructions(_loads(base_plan))
    if "параллелограмм" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 3:
        return None
    a, b, c = pts[0], pts[1], pts[2]
    return [{
        "type": "free_point", "id": "aux_D",
        "x": 0, "y": 0,
        "style": "aux", "visual_role": "aux",
        "purpose": "четвёртая вершина параллелограмма",
        "solution_evidence": {"step_no": 1, "quote": "Достроим до параллелограмма"},
    }]


def _t_reflect_over_side(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Нужна симметрия: отражение вершины через сторону."""
    cs = _base_constructions(_loads(base_plan))
    if "симметр" not in (condition or "") and "отраж" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    edges = _segment_edges(cs)
    if len(pts) < 2 or not edges:
        return None
    a, b = edges[0]
    p = next((x for x in pts if x not in (a, b)), None)
    if not p:
        return None
    return [{
        "type": "reflect_point", "id": "aux_ref",
        "point": p, "center": a,
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "отражение точки",
        "solution_evidence": {"step_no": 1, "quote": "Отразим точку"},
    }]


def _t_common_chord(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Две окружности: общая хорда."""
    cs = _base_constructions(_loads(base_plan))
    circles = [c for c in cs if c.get("type") in ("circle_center_radius", "circumcircle", "incircle")]
    if len(circles) < 2:
        return None
    return [{
        "type": "segment", "id": "aux_common_chord",
        "p1": "aux_chord_A", "p2": "aux_chord_B",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "общая хорда двух окружностей",
        "solution_evidence": {"step_no": 1, "quote": "Проведём общую хорду"},
    }]


def _t_center_line(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Две окружности: линия центров."""
    cs = _base_constructions(_loads(base_plan))
    centers = _circle_centers(cs)
    if len(centers) < 2:
        return None
    return [{
        "type": "line", "id": "aux_center_line",
        "p1": centers[0], "p2": centers[1],
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "линия центров",
        "solution_evidence": {"step_no": 1, "quote": "Проведём линию центров"},
    }]


def _t_cyclic_quad_diagonals(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Вписанный четырёхугольник: диагонали."""
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "inscribed_polygon"):
        return None
    verts = []
    for c in cs:
        if c.get("type") == "inscribed_polygon":
            verts = c.get("vertices") or []
    if len(verts) < 4:
        return None
    return [{
        "type": "segment", "id": "aux_diag_AC",
        "p1": verts[0], "p2": verts[2],
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "диагональ вписанного четырёхугольника",
        "solution_evidence": {"step_no": 1, "quote": "Проведём диагональ"},
    }]


def _t_median_doubling(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Медиана: удвоение (отражение вершины через середину основания).

    Медиана AM (M — середина BC).  Отражаем ВЕРШИНУ A через M → точка A'.
    Тогда ABA'C — параллелограмм (диагонали BC и AA' делятся пополам в M),
    откуда A'B = AC и A'B ∥ AC.  Проводим пунктирные A'B и A'C.
    """
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "median") and "медиан" not in (condition or ""):
        return None

    # Найдём середину M и её родителей (основание BC).
    mid = None
    base_ends = []
    for c in cs:
        if c.get("type") == "midpoint" and c.get("id"):
            mid = c.get("id")
            base_ends = [c.get("p1"), c.get("p2")]
            break
    if not mid or len(base_ends) != 2:
        return None

    # Вершина, из которой идёт медиана: free_point, не являющаяся концом BC.
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    apex = next((p for p in pts if p not in base_ends), None)
    if not apex:
        return None

    # Имя отражённой вершины — человекочитаемое: A1 (id) с меткой A′.
    aux_id = f"{apex}1"
    apex_label = f"{apex}′"
    return [
        {
            "type": "reflect_point", "id": aux_id,
            "label": apex_label,
            "point": apex, "center": mid,
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": "удвоение медианы (параллелограмм)",
            "solution_evidence": {"step_no": 1, "quote": f"Продлим медиану {apex}{mid}"},
        },
        # Продление самой медианы A → A1 (через M).
        {
            "type": "segment", "id": f"{apex}{mid}_{aux_id}",
            "p1": apex, "p2": aux_id,
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": "продление медианы",
            "solution_evidence": {"step_no": 1, "quote": f"Продлим медиану {apex}{mid}"},
        },
        # Стороны параллелограмма A1B и A1C.
        {
            "type": "segment", "id": f"{aux_id}{base_ends[0]}",
            "p1": aux_id, "p2": base_ends[0],
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": "сторона параллелограмма",
            "solution_evidence": {"step_no": 1, "quote": f"Продлим медиану {apex}{mid}"},
        },
        {
            "type": "segment", "id": f"{aux_id}{base_ends[1]}",
            "p1": aux_id, "p2": base_ends[1],
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": "сторона параллелограмма",
            "solution_evidence": {"step_no": 1, "quote": f"Продлим медиану {apex}{mid}"},
        },
    ]


def _t_bisector_perpendiculars(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Биссектриса: перпендикуляры к сторонам."""
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "angle_bisector") and "биссектрис" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 3:
        return None
    a, b, c = pts[0], pts[1], pts[2]
    return [{
        "type": "foot_perpendicular", "id": "aux_bis_foot",
        "p1": a, "line1": f"{b}{c}",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "перпендикуляр к стороне",
        "solution_evidence": {"step_no": 1, "quote": "Опустим перпендикуляр"},
    }]


def _t_trapezoid_diagonal_parallel(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Трапеция + диагонали: прямая через вершину параллельно диагонали."""
    cs = _base_constructions(_loads(base_plan))
    if "трапец" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 4:
        return None
    a, b, c, d = pts[0], pts[1], pts[2], pts[3]
    return [{
        "type": "segment", "id": "aux_diag_AC",
        "p1": a, "p2": c,
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "диагональ трапеции",
        "solution_evidence": {"step_no": 1, "quote": "Проведём диагональ"},
    }]


def _t_trapezoid_height(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Трапеция: высоты."""
    cs = _base_constructions(_loads(base_plan))
    if "трапец" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 4:
        return None
    a, b, c, d = pts[0], pts[1], pts[2], pts[3]
    return [{
        "type": "altitude", "id": "aux_alt_trap",
        "vertex": c, "side_a": a, "side_b": b, "foot_id": "aux_foot_trap",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "высота трапеции",
        "solution_evidence": {"step_no": 1, "quote": "Опустим высоту"},
    }]


def _t_extend_side_external_angle(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Внешний угол: продление стороны."""
    cs = _base_constructions(_loads(base_plan))
    if "внешн" not in (condition or ""):
        return None
    edges = _segment_edges(cs)
    if not edges:
        return None
    a, b = edges[0]
    return [{
        "type": "line_extension", "id": "aux_ext_side",
        "origin": a, "direction": "both",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "продление стороны",
        "solution_evidence": {"step_no": 1, "quote": "Продлим сторону"},
    }]


def _t_equal_segments_connect(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Два равных отрезка: соединить концы."""
    cs = _base_constructions(_loads(base_plan))
    marks = [c for c in cs if c.get("type") == "equal_segments_mark"]
    if not marks:
        return None
    segs = marks[0].get("segments", []) or []
    flat = []
    for s in segs:
        if isinstance(s, (list, tuple)) and len(s) == 2:
            flat.extend(s)
    if len(flat) < 2:
        return None
    return [{
        "type": "segment", "id": "aux_eq_connect",
        "p1": flat[0], "p2": flat[1],
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "соединение концов равных отрезков",
        "solution_evidence": {"step_no": 1, "quote": "Соединим концы"},
    }]


def _t_incenter_radii(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Вписанная окружность: радиусы к точкам касания."""
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "incircle"):
        return None
    centers = _circle_centers(cs)
    if not centers:
        return None
    return [{
        "type": "segment", "id": "aux_inradius",
        "p1": centers[0], "p2": "aux_touch",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "радиус к точке касания",
        "solution_evidence": {"step_no": 1, "quote": "Проведём радиус"},
    }]


def _t_reflect_over_bisector(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Биссектриса + точка: отражение."""
    cs = _base_constructions(_loads(base_plan))
    if not _has_type(cs, "angle_bisector") and "биссектрис" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    if len(pts) < 2:
        return None
    return [{
        "type": "reflect_point", "id": "aux_bis_refl",
        "point": pts[0], "center": pts[1],
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "отражение относительно биссектрисы",
        "solution_evidence": {"step_no": 1, "quote": "Отразим точку"},
    }]


def _t_angle_copy_parallel(base_plan, condition, ctx) -> Optional[List[dict]]:
    """Параллельные прямые: построение параллельной."""
    cs = _base_constructions(_loads(base_plan))
    if "параллельн" not in (condition or ""):
        return None
    pts = [c.get("id") for c in cs if c.get("type") == "free_point" and c.get("id")]
    edges = _segment_edges(cs)
    if not pts or not edges:
        return None
    a, b = edges[0]
    p = next((x for x in pts if x not in (a, b)), pts[0])
    return [{
        "type": "parallel_line", "id": "aux_parallel",
        "point": p, "line": f"{a}{b}",
        "style": "aux", "dashed": True, "visual_role": "aux",
        "purpose": "прямая, параллельная данной",
        "solution_evidence": {"step_no": 1, "quote": "Проведём параллельную прямую"},
    }]


# Каталог шаблонов (порядок = приоритет).
AUX_TEMPLATES: List[Callable[[Any, str, Any], Optional[List[dict]]]] = [
    _t_circumcenter_third_radius,
    _t_center_to_chord_perp,
    _t_radius_to_tangency,
    _t_midline,
    _t_altitude_from_right_angle,
    _t_parallelogram_completion,
    _t_reflect_over_side,
    _t_common_chord,
    _t_center_line,
    _t_cyclic_quad_diagonals,
    _t_median_doubling,
    _t_bisector_perpendiculars,
    _t_trapezoid_diagonal_parallel,
    _t_trapezoid_height,
    _t_extend_side_external_angle,
    _t_equal_segments_connect,
    _t_incenter_radii,
    _t_reflect_over_bisector,
    _t_angle_copy_parallel,
]


def match_template(base_plan: Any, condition: str, ctx: Any) -> Optional[Dict[str, Any]]:
    """Попытаться сматчить первый подходящий шаблон.

    Returns {"template_id": str, "constructions": [dict]} или None.
    """
    from services.text_normalize import normalize_condition
    condition = normalize_condition(condition)
    for i, tpl in enumerate(AUX_TEMPLATES):
        try:
            cons = tpl(base_plan, condition, ctx)
        except Exception:
            cons = None
        if cons:
            return {
                "template_id": tpl.__name__,
                "constructions": cons,
                "priority": i,
            }
    return None
