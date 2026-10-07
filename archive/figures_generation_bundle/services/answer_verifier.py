# -*- coding: utf-8 -*-
"""services/answer_verifier.py — сверка ответа solver'а с фактическим чертежом.

ЯДРО solver-driven aux.  Модель вернула answer.value; движок построил чертёж
по условию.  Измеряем искомую величину на BuildContext и сравниваем.

Совпало → решение почти наверняка верное, построениям можно доверять.
Не совпало → решение ошибочно, построения использовать нельзя.

Без LLM, без символьных вычислений.
"""

from __future__ import annotations

import math
import statistics
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from geometric_engine import geom as _geom
except Exception:  # pragma: no cover
    _geom = None

from services.visual_audit import resolve_angle_triple

DEFAULT_ANGLE_TOL_DEG = 0.5
DEFAULT_LENGTH_REL_TOL = 0.01


def _angle_abc_deg(pts: Dict[str, Any], a: str, b: str, c: str) -> Optional[float]:
    if _geom is None:
        return None
    pa, pb, pc = pts.get(a), pts.get(b), pts.get(c)
    if not pa or not pb or not pc:
        return None
    try:
        return math.degrees(_geom.angle_between_three(pa, pb, pc))
    except Exception:
        return None


def _resolve_target(kind: str, obj: str, pts: Dict[str, Any],
                    base_plan: dict, condition: str) -> Optional[Any]:
    """Резолвить объект цели в геометрические примитивы.

    angle "ADC" -> ("A","D","C"); angle "B" -> resolve_angle_triple;
    length "CH" -> ("C","H"); area "ABC" -> ["A","B","C"].
    """
    obj = (obj or "").replace("∠", "").strip()
    if kind == "angle":
        letters = re.findall(r"[A-Z]", obj)
        if len(letters) == 3:
            return ("angle", letters[0], letters[1], letters[2])
        if len(letters) == 1:
            triple = resolve_angle_triple(letters[0], base_plan, condition)
            if triple:
                return ("angle", triple[0], triple[1], triple[2])
        return None
    if kind == "length":
        letters = re.findall(r"[A-Z]", obj)
        if len(letters) == 2:
            return ("length", letters[0], letters[1])
        return None
    if kind == "area":
        letters = re.findall(r"[A-Z]", obj)
        if len(letters) >= 3:
            return ("area", letters)
        return None
    return None


def _measure(resolved: Any, pts: Dict[str, Any]) -> Optional[float]:
    """Вычислить фактическое значение величины."""
    if resolved is None:
        return None
    kind = resolved[0]
    if kind == "angle":
        return _angle_abc_deg(pts, resolved[1], resolved[2], resolved[3])
    if kind == "length":
        a, b = resolved[1], resolved[2]
        if a in pts and b in pts and _geom is not None:
            return _geom.dist(pts[a], pts[b])
        return None
    if kind == "area":
        verts = resolved[1]
        coords = [pts.get(v) for v in verts if v in pts]
        if len(coords) >= 3 and _geom is not None:
            return _geom.triangle_area(coords[0], coords[1], coords[2])
        return None
    return None


def verify_answer(
    solver_result: dict,
    build_context: Any,
    base_plan: dict,
    condition_text: str = "",
    settings: Optional[Any] = None,
) -> Dict[str, Any]:
    """Сверить ответ solver'а с измерением на фактическом чертеже.

    Returns:
      {
        "verdict": "verified" | "mismatch" | "unverifiable",
        "declared": float|None,
        "measured": float|None,
        "delta": float|None,
        "tolerance": float,
        "target_resolved": ...,
        "reason": str,
      }
    """
    angle_tol = DEFAULT_ANGLE_TOL_DEG
    if settings is not None:
        angle_tol = float(getattr(settings, "angle_tol", None) or angle_tol)

    target = (solver_result or {}).get("target") or {}
    answer = (solver_result or {}).get("answer") or {}
    kind = target.get("kind", "")
    obj = target.get("object", "")

    if not answer.get("is_numeric", True) or answer.get("value") is None:
        return {
            "verdict": "unverifiable",
            "declared": None, "measured": None, "delta": None,
            "tolerance": angle_tol,
            "target_resolved": None,
            "reason": "ответ не численный (доказательство)",
        }

    from services.text_normalize import normalize_condition
    condition_text = normalize_condition(condition_text)

    pts = getattr(build_context, "points", {}) if build_context else {}
    resolved = _resolve_target(kind, obj, pts, base_plan, condition_text)
    if resolved is None:
        return {
            "verdict": "unverifiable",
            "declared": answer.get("value"), "measured": None, "delta": None,
            "tolerance": angle_tol,
            "target_resolved": None,
            "reason": f"не удалось резолвить цель '{kind}:{obj}'",
        }

    declared = float(answer["value"])
    measured = _measure(resolved, pts)
    if measured is None:
        return {
            "verdict": "unverifiable",
            "declared": declared, "measured": None, "delta": None,
            "tolerance": angle_tol,
            "target_resolved": resolved,
            "reason": "не удалось измерить цель на чертеже",
        }

    if kind == "angle":
        delta = abs(measured - declared)
        tol = angle_tol
        ok = delta <= tol
    else:
        # Длины/площади: без масштаба сравнивать нельзя — unverifiable,
        # если нет второго опорного значения в условии.
        return {
            "verdict": "unverifiable",
            "declared": declared, "measured": measured,
            "delta": abs(measured - declared),
            "tolerance": DEFAULT_LENGTH_REL_TOL,
            "target_resolved": resolved,
            "reason": f"величина '{kind}' не проверяема без масштаба условия",
        }

    verdict = "verified" if ok else "mismatch"
    reason = "совпало" if ok else f"расхождение {delta:.2f} > допуска {tol}"
    return {
        "verdict": verdict,
        "declared": declared,
        "measured": round(measured, 4),
        "delta": round(delta, 4),
        "tolerance": tol,
        "target_resolved": resolved,
        "reason": reason,
    }
