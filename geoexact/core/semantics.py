"""Guard model plans against a false 'verified' drawing for incenter/arc tasks.

The numeric gate can prove that a plan is self-consistent, but it cannot by
itself prove that the plan represents the user's text. The intentionally
narrow recognizer below covers the stated triangle configuration; unrelated
problems continue through the regular model pipeline.
"""
from __future__ import annotations

import re

import numpy as np

from .schema import FigurePlan, PlanError, validate_plan


def _claims_incenter_arc_bisector(text: str) -> bool:
    t = text.casefold()
    return (bool(re.search(r"\babc\b", t))
            and "вписанн" in t and "окружност" in t
            and "биссектрис" in t and "описанн" in t
            and bool(re.search(r"\bi\b", t)) and bool(re.search(r"\bw\b", t))
            and ("втор" in t or "повтор" in t))


def _claims_equal_distances(text: str) -> bool:
    compact = re.sub(r"[\s{}$\\()]+", "", text).upper()
    return "WB=WC=WI" in compact or "BW=CW=IW" in compact


_EXACT_THEOREM = (
    "Пусть I — центр вписанной окружности треугольника ABC. "
    "Биссектриса угла A второй раз пересекает описанную окружность "
    "треугольника в точке W. Докажите, что WB = WC = WI."
)

_EXCENTER_THEOREM = (
    "В треугольнике ABC (где AB AC) точка I — центр вписанной окружности, "
    "I_A — центр вневписанной окружности, касающейся стороны BC. "
    "Биссектриса угла A второй раз пересекает описанную окружность в точке W. "
    "Докажите, что W — середина отрезка II_A и WB = WC = WI = WI_A. "
    "Иными словами, точки B, C, I и I_A лежат на одной окружности с центром W."
)


def _canonical(text: str) -> str:
    # Vision OCR may wrap the same point names and equality in LaTeX.
    text = re.sub(r"\\(?:mathrm|text|operatorname)\s*\{([^{}]*)\}",
                  r"\1", text)
    text = re.sub(r"\\(?:neq|ne)\b|!=", "≠", text)
    return re.sub(r"[^\w=<>≠≤≥]+|_", "", text.casefold())


def theorem_plan(text: str, with_aux: bool) -> FigurePlan | None:
    """Only bypass the model for the two known theorems, not augmented tasks."""
    without_heading = re.sub(r"^\s*условие\s*[.:]\s*", "", text, flags=re.I)
    statement = _canonical(without_heading)
    with_excenter = statement == _canonical(_EXCENTER_THEOREM)
    if not with_excenter and statement != _canonical(_EXACT_THEOREM):
        return None
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "I", *(["I_A"] if with_excenter else []),
                   "O", "W"],
        "constructions": [
            *({"op": "free_point", "out": n} for n in "ABC"),
            {"op": "incenter", "out": "I", "args": ["A", "B", "C"]},
            *([{"op": "excenter", "out": "I_A",
                "args": ["A", "B", "C"], "value": 0}] if with_excenter else []),
            {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
            {"op": "bisector_circumcircle", "out": "W",
             "args": ["A", "B", "C"]},
        ],
        "constraints": [],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "W"],
                         ["W", "B"], ["W", "C"], ["W", "I"],
                         *([["W", "I_A"]] if with_excenter else [])],
            "circles": [["O", "A"], *([["W", "B"]] if with_excenter else [])],
            "aux_segments": [["B", "I"], ["C", "I"]] if with_aux else [],
            "aux_points": ["O"],
            "hide_labels": ["O"],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": ("Иллюстрация условия, середины и равных отрезков; рисунок "
                  if with_excenter else
                  "Иллюстрация условия и равных отрезков; рисунок ")
                 + "сам по себе не является доказательством.",
    })
    validate_plan(plan)
    return plan


def semantic_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    """Independently check the named incenter, circle and equality claims."""
    if not _claims_incenter_arc_bisector(text):
        return []
    if not all(name in coords for name in ("A", "B", "C", "I", "W")):
        return ["В плане отсутствуют A, B, C, I или W"]
    from .constructions import _circumcenter, _excenter, _incenter
    A, B, C, I, W = (np.asarray(coords[name], dtype=float)
                      for name in ("A", "B", "C", "I", "W"))
    try:
        O = _circumcenter(A, B, C)
        expected_I = _incenter(A, B, C)
    except PlanError as exc:
        return [str(exc)]
    scale = max(float(np.linalg.norm(B - A)),
                float(np.linalg.norm(C - A)), 1e-12)
    fails = []
    if float(np.linalg.norm(I - expected_I)) > 1e-5 * scale:
        fails.append("I не является центром вписанной окружности ABC")
    if abs(float(np.linalg.norm(W - O) - np.linalg.norm(A - O))) > 1e-5 * scale:
        fails.append("W не лежит на описанной окружности ABC")
    direction = I - A
    if (float(np.linalg.norm(W - A)) <= 1e-5 * scale
            or float(np.dot(W - A, direction)) <= 0
            or abs(float(np.linalg.det(np.array([W - A, direction]))))
               > 1e-5 * scale * scale):
        fails.append("W не является вторым пересечением биссектрисы A")
    if _claims_equal_distances(text):
        distances = [float(np.linalg.norm(W - coords[name]))
                     for name in ("B", "C", "I")]
        if max(distances) - min(distances) > 1e-4 * scale:
            fails.append("WB, WC и WI не равны на построенной фигуре")
    named_excenter = ("вневписанн" in text.casefold()
        and bool(re.search(r"(?<!\w)i\s*_\s*(?:\{\s*a\s*\}|a)(?!\w)|(?<!\w)iₐ(?!\w)",
                           text, re.I)))
    if named_excenter:
        if "I_A" not in coords:
            fails.append("в плане отсутствует вневписанный центр I_A")
        else:
            IA = np.asarray(coords["I_A"], dtype=float)
            if float(np.linalg.norm(IA - _excenter(A, B, C, value=0))) > 1e-5 * scale:
                fails.append("I_A не является вневписанным центром напротив A")
            if "середин" in text.casefold() and (
                float(np.linalg.norm(W - (I + IA) / 2)) > 1e-5 * scale
            ):
                fails.append("W не является серединой II_A")
            if "WI_A" in re.sub(r"[\s{}$\\()]+", "", text).upper():
                distances = [float(np.linalg.norm(W - coords[name]))
                             for name in ("B", "C", "I", "I_A")]
                if max(distances) - min(distances) > 1e-4 * scale:
                    fails.append("WB, WC, WI и WI_A не равны на фигуре")
    # An illustrative scale is harmless; three invented side lengths are not.
    # Limit this check to this named configuration so other, possibly numeric
    # problems keep their existing behaviour.
    explicit_lengths = re.search(
        r"\b(?:AB|BC|CA|AC|BA|CB)\s*=\s*\d", text, re.I,
    )
    if not explicit_lengths and (
        sum(c.type == "dist" for c in plan.constraints) > 1
        or plan.draw.length_marks
    ):
        fails.append("план придумал числовые длины, которых нет в условии")
    return fails
