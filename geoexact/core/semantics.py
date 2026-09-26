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
            "angle_marks": [
                {"pts": ["B", "A", "W"], "count": 1},
                {"pts": ["W", "A", "C"], "count": 1},
            ],
            "equal_marks": [
                {"pts": ["W", name], "count": 1}
                for name in ("B", "C", "I", *(["I_A"] if with_excenter else []))
            ],
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


_SIMPLE_INCIRCLE_TEXTS = (
    "В треугольнике ABC точка I — центр вписанной окружности. "
    "Постройте вписанную окружность.",
    "Постройте вписанную окружность треугольника ABC.",
    "В треугольнике ABC проведите окружность с центром I, "
    "касающуюся всех трёх сторон, где I — инцентр.",
)
_SIMPLE_CIRCUMCIRCLE_TEXT = "Постройте описанную окружность треугольника ABC."


def requests_incircle(text: str) -> bool:
    """A request to draw the ABC incircle, not merely mention its center."""
    t = text.casefold()
    if not re.search(r"\babc\b", t):
        return False
    action = r"(?:постройте|проведите|изобразите|начертите|нарисуйте)"
    direct = re.search(
        rf"\b{action}\b[^.!?]{{0,180}}\bвписанн\w*\s+окружност\w*", t
    )
    tangency = re.search(
        rf"\b{action}\b[^.!?]{{0,180}}\bокружност\w*"
        r"[^.!?]{0,130}\bкасающ\w*[^.!?]{0,65}\bсторон", t
    )
    return bool(direct or tangency)


def requests_circumcircle(text: str) -> bool:
    t = text.casefold()
    return bool(re.search(r"\babc\b", t) and re.search(
        r"\b(?:постройте|проведите|изобразите|начертите|нарисуйте)\b"
        r"[^.!?]{0,180}\bописанн\w*\s+окружност\w*", t))


def requests_rhombus(text: str) -> bool:
    return bool(re.search(r"\bромб\s+abcd\b", text, re.I))


def common_plan(text: str, with_aux: bool) -> FigurePlan | None:
    """Small, fully specified drawing requests; do not swallow added facts."""
    statement = re.sub(r"^\s*условие\s*[.:]\s*", "", text, flags=re.I)
    if _canonical(statement) in {_canonical(t) for t in _SIMPLE_INCIRCLE_TEXTS}:
        plan = FigurePlan.from_dict({
            "points": ["A", "B", "C", "I", "T"],
            "constructions": [
                *({"op": "free_point", "out": p} for p in "ABC"),
                {"op": "incenter", "out": "I", "args": ["A", "B", "C"]},
                {"op": "foot", "out": "T", "args": ["I", "B", "C"]},
            ],
            "constraints": [],
            "draw": {
                "segments": [["A", "B"], ["B", "C"], ["C", "A"]],
                "circles": [["I", "T"]],
                "aux_segments": [["I", "T"], ["B", "I"], ["C", "I"]]
                                if with_aux else [],
                "hide_labels": ["T"],
            },
            "target": {"kind": "none", "args": []},
            "scale_free": True,
            "notes": "Иллюстрация вписанной окружности; радиус IT перпендикулярен BC.",
        })
        validate_plan(plan)
        return plan

    if _canonical(statement) == _canonical(_SIMPLE_CIRCUMCIRCLE_TEXT):
        plan = FigurePlan.from_dict({
            "points": ["A", "B", "C", "O"],
            "constructions": [
                *({"op": "free_point", "out": p} for p in "ABC"),
                {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
            ],
            "constraints": [],
            "draw": {
                "segments": [["A", "B"], ["B", "C"], ["C", "A"]],
                "circles": [["O", "A"]],
                "aux_segments": [["O", "A"], ["O", "B"], ["O", "C"]]
                                if with_aux else [],
                "hide_labels": ["O"],
            },
            "target": {"kind": "none", "args": []},
            "scale_free": True,
            "notes": "Иллюстрация описанной окружности; радиус равен OA=OB=OC.",
        })
        validate_plan(plan)
        return plan

    match = re.fullmatch(
        r"\s*постройте\s+ромб\s+ABCD"
        r"(?:\s*,\s*в\s+котором\s+угол\s+A\s+равен\s+"
        r"(\d+(?:[.,]\d+)?)\s*(?:°|градус(?:ов|а)?)?)?"
        r"\s*\.?\s*", statement, re.I,
    )
    if match is None:
        return None
    angle = float(match[1].replace(",", ".")) if match[1] else 65.0
    if not 0 < angle < 180:
        return None
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "angle_ray", "out": "D",
             "args": ["A", "B"], "value": angle},
            {"op": "translate", "out": "C",
             "args": ["B", "A", "D"]},
        ],
        "constraints": [],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]],
            "aux_segments": [["A", "C"], ["B", "D"]] if with_aux else [],
            "angle_marks": ([{"pts": ["B", "A", "D"],
                              "text": f"{angle:g}°"}] if match[1] else []),
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": "Иллюстрация ромба с равными сторонами; масштаб произвольный.",
    })
    validate_plan(plan)
    return plan


def _incircle_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    if not requests_incircle(text):
        return []
    if not all(p in coords for p in "ABC"):
        return ["нет вершин A, B, C для вписанной окружности"]
    from .constructions import _incenter
    A, B, C = (np.asarray(coords[p], dtype=float) for p in "ABC")
    try:
        expected = _incenter(A, B, C)
    except PlanError as exc:
        return [str(exc)]
    scale = max(float(np.linalg.norm(B - A)),
                float(np.linalg.norm(C - A)), 1e-12)
    failures = []
    if re.search(r"(?<!\w)I(?!\w)", text, re.I):
        if "I" not in coords or np.linalg.norm(coords["I"] - expected) > 1e-5 * scale:
            failures.append("I не является инцентром ABC")
    radius = abs(float(np.linalg.det(np.array([C - B, expected - B])))) / float(np.linalg.norm(C - B))
    if not plan.draw.circles:
        failures.append("на основном чертеже отсутствует запрошенная вписанная окружность")
    elif not any(
        center in coords and point in coords
        and np.linalg.norm(coords[center] - expected) <= 1e-5 * scale
        and abs(float(np.linalg.norm(coords[point] - coords[center])) - radius)
            <= 1e-5 * scale
        for center, point in plan.draw.circles
    ):
        failures.append("вписанная окружность нарисована с неверным центром или радиусом")
    return failures


def _circumcircle_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    if not requests_circumcircle(text):
        return []
    if not all(p in coords for p in "ABC"):
        return ["нет вершин A, B, C для описанной окружности"]
    from .constructions import _circumcenter
    A, B, C = (np.asarray(coords[p], dtype=float) for p in "ABC")
    try:
        expected = _circumcenter(A, B, C)
    except PlanError as exc:
        return [str(exc)]
    scale = max(float(np.linalg.norm(B - A)),
                float(np.linalg.norm(C - A)), 1e-12)
    radius = float(np.linalg.norm(A - expected))
    if not plan.draw.circles:
        return ["на основном чертеже отсутствует запрошенная описанная окружность"]
    if not any(
        center in coords and point in coords
        and np.linalg.norm(coords[center] - expected) <= 1e-5 * scale
        and abs(float(np.linalg.norm(coords[point] - coords[center])) - radius)
            <= 1e-5 * scale
        for center, point in plan.draw.circles
    ):
        return ["описанная окружность нарисована с неверным центром или радиусом"]
    return []


def _rhombus_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    if not requests_rhombus(text):
        return []
    names = "ABCD"
    if not all(p in coords for p in names):
        return ["в плане отсутствуют вершины ромба A, B, C или D"]
    vertices = [np.asarray(coords[p], dtype=float) for p in names]
    scale = max(float(np.linalg.norm(vertices[1] - vertices[0])), 1e-12)
    lengths = [float(np.linalg.norm(vertices[(i + 1) % 4] - vertices[i]))
               for i in range(4)]
    failures = []
    if min(lengths) <= 1e-8 * scale or max(lengths) - min(lengths) > 1e-4 * scale:
        failures.append("стороны ABCD не равны: построена не ромбическая фигура")
    turns = [float(np.linalg.det(np.array([
        vertices[(i + 1) % 4] - vertices[i],
        vertices[(i + 2) % 4] - vertices[(i + 1) % 4],
    ]))) for i in range(4)]
    if not (all(v > 1e-6 * scale * scale for v in turns)
            or all(v < -1e-6 * scale * scale for v in turns)):
        failures.append("контур ABCD не является невырожденным выпуклым ромбом")
    sides = {frozenset((names[i], names[(i + 1) % 4])) for i in range(4)}
    drawn = {frozenset(pair) for pair in plan.draw.segments}
    if not sides <= drawn:
        failures.append("не все четыре стороны ромба показаны на основном чертеже")
    angle = re.search(r"\bугол\s+A\s+равен\s+(\d+(?:[.,]\d+)?)\s*"
                      r"(?:°|градус(?:ов|а)?)?", text, re.I)
    if angle and min(lengths) > 1e-8 * scale:
        wanted = float(angle[1].replace(",", "."))
        u, v = vertices[1] - vertices[0], vertices[3] - vertices[0]
        actual = float(np.degrees(np.arccos(np.clip(
            np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))
        if abs(actual - wanted) > 0.01:
            failures.append("угол A ромба не совпадает с условием")
    return failures


def semantic_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    """Independently check the named incenter, circle and equality claims."""
    fails = (_incircle_failures(text, plan, coords)
             + _circumcircle_failures(text, plan, coords)
             + _rhombus_failures(text, plan, coords))
    if not _claims_incenter_arc_bisector(text):
        return fails
    if not all(name in coords for name in ("A", "B", "C", "I", "W")):
        return fails + ["В плане отсутствуют A, B, C, I или W"]
    from .constructions import _circumcenter, _excenter, _incenter
    A, B, C, I, W = (np.asarray(coords[name], dtype=float)
                      for name in ("A", "B", "C", "I", "W"))
    try:
        O = _circumcenter(A, B, C)
        expected_I = _incenter(A, B, C)
    except PlanError as exc:
        return fails + [str(exc)]
    scale = max(float(np.linalg.norm(B - A)),
                float(np.linalg.norm(C - A)), 1e-12)
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
