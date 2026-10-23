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
    "parallel_through": ("parallel_line", False),
    "perpendicular_through": ("perpendicular_bisector", False),
    "line_extension": ("line_extension", True),
    "circle_center_radius": ("circle_center_radius", False),
    "tangent_at_point": ("tangent_at_point", False),
    "line_intersection": ("intersect_lines", True),
    "reflect_point": ("reflect_point", True),
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
