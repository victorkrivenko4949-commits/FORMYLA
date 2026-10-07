# -*- coding: utf-8 -*-
"""semantic_theme.py — CH16: ограниченная семантическая система цветов.

Никаких произвольных hex в LLM JSON.  Роли визуализации задаются строкой
`visual_role` из фиксированного enum; renderer детерминированно выбирает цвет
из фиксированной тёмной темы `dark_geometry`.

Только stdlib.  Не используется numpy/matplotlib/внешние зависимости.
"""

from __future__ import annotations

from typing import Optional

# ──────────────────────────────────────────────────────────────────────────
# Тема dark_geometry (фиксированные цвета)
# ──────────────────────────────────────────────────────────────────────────

BASE_STROKE = "#D9E5F5"
BASE_TEXT = "#EAF1FA"

AUX_STROKE = "#73B6E6"
AUX_TEXT = "#9BCDF0"

REFERENCE_CIRCLE = "#B7A2E8"
TARGET_CIRCLE = "#55D6BE"

KEY_POINT = "#F6B44C"
KEY_TEXT = "#FFD28A"

RIGHT_ANGLE = "#FFD166"
GIVEN_MARK = "#D9E5F5"
SECONDARY = "#A6B7CC"

# Разрешённый enum ролей.
VALID_VISUAL_ROLES = frozenset({
    "base",
    "aux",
    "reference_circle",
    "target_circle",
    "key_point",
    "right_angle_mark",
    "given_mark",
    "secondary",
})

# Роль -> {stroke, text, fill}.  Один источник истины, чтобы не размазывать
# hex-литералы по render_svg.
DARK_GEOMETRY = {
    "base": {"stroke": BASE_STROKE, "text": BASE_TEXT, "fill": BASE_STROKE},
    "aux": {"stroke": AUX_STROKE, "text": AUX_TEXT, "fill": AUX_STROKE},
    "reference_circle": {"stroke": REFERENCE_CIRCLE, "text": REFERENCE_CIRCLE,
                         "fill": REFERENCE_CIRCLE},
    "target_circle": {"stroke": TARGET_CIRCLE, "text": TARGET_CIRCLE,
                      "fill": TARGET_CIRCLE},
    "key_point": {"stroke": KEY_POINT, "text": KEY_TEXT, "fill": KEY_POINT},
    "right_angle_mark": {"stroke": RIGHT_ANGLE, "text": RIGHT_ANGLE,
                         "fill": RIGHT_ANGLE},
    "given_mark": {"stroke": GIVEN_MARK, "text": GIVEN_MARK, "fill": GIVEN_MARK},
    "secondary": {"stroke": SECONDARY, "text": SECONDARY, "fill": SECONDARY},
}

# Категории конструкций для детерминированных defaults.
_SEGMENT_LIKE = frozenset({
    "segment", "ray", "line", "line_extension", "altitude", "median",
    "angle_bisector", "perpendicular_bisector", "tangent_from_point",
    "tangent_at_point",
})
_CIRCLE_TYPES = frozenset({
    "circle_center_radius", "circumcircle", "incircle", "circle_three_points",
})
_GIVEN_MARK_TYPES = frozenset({
    "equal_segments_mark", "equal_angles_mark", "angle_label", "midpoint_mark",
    "parallel_mark", "length_label",
})
_RIGHT_ANGLE_TYPES = frozenset({"right_angle_mark", "perpendicular_mark"})


def resolve_visual_role(obj: dict, meta: Optional[dict] = None) -> str:
    """Детерминированно определить visual_role конструкции.

    Приоритет:
      1. Явное поле `visual_role` (если валидно).
      2. Default по style/origin/op.

    Не окрашивает базовые стороны в aux-color: base-конструкция без style="aux"
    всегда получает "base".
    """
    ctype = obj.get("type") or ""

    vr = obj.get("visual_role")
    if vr in VALID_VISUAL_ROLES:
        return vr

    style = obj.get("style") or ((meta or {}).get("style"))

    if style == "aux":
        if ctype in _SEGMENT_LIKE:
            return "aux"
        if ctype in _CIRCLE_TYPES:
            return "reference_circle"
        if ctype in _RIGHT_ANGLE_TYPES:
            return "right_angle_mark"
        if ctype in _GIVEN_MARK_TYPES:
            return "given_mark"
        return "aux"

    # Base (без style="aux") или mark.
    if ctype in _RIGHT_ANGLE_TYPES:
        return "right_angle_mark"
    if ctype in _GIVEN_MARK_TYPES:
        return "given_mark"
    return "base"


def resolve_point_role(meta: Optional[dict]) -> str:
    """Определить visual_role точки по её метаданным.

    Вспомогательная точка (style="aux" — foot/midpoint/intersection и т.п.)
    получает "secondary", если planner явно не задал key_point/secondary/... .
    """
    meta = meta or {}
    vr = meta.get("visual_role")
    if vr in VALID_VISUAL_ROLES:
        return vr
    if meta.get("style") == "aux":
        return "secondary"
    return "base"


def semantic_color(role: str, kind: str, fallback: str) -> str:
    """Цвет для роли и вида элемента (stroke/text/fill), либо fallback."""
    if role not in VALID_VISUAL_ROLES:
        return fallback
    return DARK_GEOMETRY[role].get(kind, fallback)
