# -*- coding: utf-8 -*-
"""services/aux_ops.py — закрытый словарь операций доп. построений.

Единый источник истины для промпта solver'а и компилятора.
op → (движковый тип geometric_engine, создаёт ли точку).

Подмножество geometric_engine/CONSTRUCTIONS.md.  Неизвестная op отклоняется
компилятором с кодом UNKNOWN_AUX_OP.
"""

from __future__ import annotations

from typing import Dict, Tuple

# op solver-контракта -> (тип движка, создаёт ли новую точку)
AUX_ALLOWED_OPS: Dict[str, Tuple[str, bool]] = {
    "segment": ("segment", False),
    "line": ("line", False),
    "ray": ("ray", False),
    "altitude": ("altitude", True),
    "median": ("median", True),
    "angle_bisector": ("angle_bisector", True),
    "perpendicular_bisector": ("perpendicular_bisector", False),
    "midpoint": ("midpoint", True),
    # «точка на прямой/луче» — point_on_segment (частный случай: на отрезке).
    "point_on_line": ("point_on_segment", True),
    "parallel_through": ("parallel_line", False),
    # «перпендикуляр из точки P на прямую [A,B]» — это ВЫСОТА (создаёт foot),
    # а не серединный перпендикуляр отрезка.  Раньше маппилось на
    # perpendicular_bisector, из-за чего чертёж выходил неверным.
    "perpendicular_through": ("altitude", True),
    # «продлим отрезок P1P2 за P2 до точки NEW» = центральная симметрия
    # P1 относительно P2 (NEW = 2*P2 − P1).  Движковый тип reflect_point.
    "line_extension": ("reflect_point", True),
    "circle_center_radius": ("circle_center_radius", False),
    "tangent_at_point": ("tangent_at_point", False),
    "line_intersection": ("intersect_lines", True),
    # «отразить точку P относительно прямой [A,B]» — это ОСЕВАЯ симметрия,
    # а не центральная.  Движковый тип reflect_point_over_line.
    "reflect_point": ("reflect_point_over_line", True),
    # «отметим равные отрезки P1P2, P3P4, ...» — насечки равенства, не создают точек.
    "mark_equal_segments": ("equal_segments_mark", False),
}


def engine_op_for(solver_op: str) -> str:
    """Тип движка для solver-op (или '' если неизвестна)."""
    return AUX_ALLOWED_OPS.get(solver_op, ("", False))[0]


def creates_point(solver_op: str) -> bool:
    """True, если операция создаёт новую точку."""
    return AUX_ALLOWED_OPS.get(solver_op, ("", False))[1]


def allowed_ops_text() -> str:
    """Человекочитаемый список операций (для промпта)."""
    return "\n".join(f"  {op}" for op in AUX_ALLOWED_OPS)
