# -*- coding: utf-8 -*-
"""scripts/ch19_lib.py — общие детерминированные хелперы для CH19.

Без внешних зависимостей.  Не трогает конвейер/движок/промпты.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.solution_style import classify_solution_style  # noqa: E402
from services.solution_style import expected_has_aux  # noqa: E402

# Типы, создающие новую точку-результат (id конструкции — имя точки).
POINT_CREATING_TYPES = {
    "free_point", "midpoint", "point_on_segment", "foot_perpendicular",
    "intersect_lines", "intersect_line_circle", "intersect_circles",
    "reflect_point_over_point", "reflect_point_over_line",
    "circumcenter", "incenter", "centroid", "orthocenter", "incircle_touch",
}

# Разрешённая палитра dark_geometry: цвета семантической темы + legacy-цвета
# движка (это единая тёмная тема, просто часть объектов детерминированно
# использует mark_color/label_color и т.п.).
_ALLOWED_COLORS = {
    # semantic_theme.DARK_GEOMETRY
    "#D9E5F5", "#EAF1FA", "#73B6E6", "#9BCDF0", "#B7A2E8", "#55D6BE",
    "#F6B44C", "#FFD28A", "#FFD166", "#A6B7CC",
    # EngineSettings (legacy dark palette)
    "#c8d6e5", "#e8f0fb", "#d0ddf0", "#a0b8d8", "#7a8fa8", "#ffd700",
    "#3a5070", "#0f172a", "#070C18",
    # допустимые не-hex значения
    "none", "transparent",
}
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def loads(data: Any) -> Any:
    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    if not isinstance(data, str) or not data.strip():
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def constructions_of(plan: Any, key: str = "constructions") -> List[dict]:
    p = loads(plan)
    if not isinstance(p, dict):
        return []
    cs = p.get(key)
    if isinstance(cs, list):
        return [c for c in cs if isinstance(c, dict)]
    return []


def base_constructions(plan: Any) -> List[dict]:
    p = loads(plan)
    if not isinstance(p, dict):
        return []
    if "base" in p and isinstance(p["base"], dict):
        return constructions_of(p["base"])
    return constructions_of(p)


def aux_constructions(plan: Any) -> List[dict]:
    p = loads(plan)
    if not isinstance(p, dict):
        return []
    aux = p.get("aux", p) if isinstance(p.get("aux"), dict) else p
    return constructions_of(aux)


def has_aux_flag(aux_plan: Any) -> bool:
    p = loads(aux_plan)
    if not isinstance(p, dict):
        return False
    aux = p.get("aux", p) if isinstance(p.get("aux"), dict) else p
    return bool(aux.get("has_aux", False))


def merge_base_aux_plan(base_plan: Any, aux_plan: Any) -> Dict[str, Any]:
    from services.figure_plan_validator import merge_base_aux
    return merge_base_aux(base_plan, aux_plan)


def build_ctx(plan: Any):
    """Детерминированно построить контекст движка (без LLM)."""
    from geometric_engine.engine import GeometricEngine
    p = loads(plan)
    if not isinstance(p, dict):
        return None
    eng = GeometricEngine()
    try:
        _svg, ctx = eng.build(p)
        return ctx
    except Exception:
        return None


def visible_points(plan: Any) -> Set[str]:
    """Имена видимых точек, которые движок отрисует как кружки."""
    ctx = build_ctx(plan)
    if ctx is None:
        return set()
    out = set()
    for name, meta in ctx.meta.items():
        if name not in ctx.points:
            continue
        if meta.get("hidden") or meta.get("type") == "polygon_vertex":
            continue
        out.add(name)
    return out


def count_visible_points(plan: Any) -> int:
    return len(visible_points(plan))


def plan_point_labels(plan: Any) -> Dict[str, str]:
    """Имя точки -> display label (что будет нарисовано в SVG)."""
    ctx = build_ctx(plan)
    if ctx is None:
        return {}
    out = {}
    for name in visible_points(plan):
        meta = ctx.meta.get(name, {})
        label = meta.get("label", name)
        if label is None:
            label = ""
        out[name] = str(label)
    return out


def error_code_from(job_error: Optional[str]) -> str:
    if not job_error:
        return ""
    err = str(job_error).strip()
    if ":" in err:
        head = err.split(":", 1)[0].strip()
        if re.match(r"^(LLM_|MISSING_|INVALID_|BASE_|AUX_|FOOT_|STYLE$|"
                    r"GIVEN_|UNNECESSARY_|INCONSISTENT_|DIRECT_COLOR_)", head):
            return head
        return "OTHER"
    return "OTHER"


def allowed_colors() -> Set[str]:
    # Нормализуем к верхнему регистру — SVG рендер использует как lower, так
    # и upper-case hex; сравнение должно быть регистронезависимым.
    return {c.upper() for c in _ALLOWED_COLORS}


def extract_hex_colors(svg_text: Optional[str]) -> Set[str]:
    if not svg_text:
        return set()
    return {m.group(0).upper() for m in _COLOR_RE.finditer(svg_text)}
