"""Guard model plans against a false 'verified' drawing for incenter/arc tasks.

The numeric gate can prove that a plan is self-consistent, but it cannot by
itself prove that the plan represents the user's text. The intentionally
narrow recognizer below covers the stated triangle configuration; unrelated
problems continue through the regular model pipeline.
"""
from __future__ import annotations

import math
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

_PARALLELOGRAM_PROOF = (
    "В равнобедренном треугольнике ABC (AB = BC) проведена биссектриса CD. "
    "На основании AC отмечена точка F так, что BD = CF. "
    "Точка E выбрана так, что четырёхугольник CDEF — параллелограмм. "
    "Докажите, что BE = BF."
)

_TRISECTOR_PREFIX = (
    "На стороне BC треугольника ABC отмечены точки M и N так, что BM = MN = NC. "
    "Прямая, параллельная AN и проходящая через точку M, пересекает продолжение "
    "стороны AC за точку A в такой точке D, что AB = CD. Найдите AB, "
)


def _math_text(text: str) -> str:
    """Small OCR/LaTeX equivalences, without guessing a missing operator."""
    text = re.sub(r"\\(?:operatorname|mathrm)\s*\{\s*(cos|sin|tan|cot)\s*\}",
                  r"\1", text, flags=re.I)
    text = re.sub(r"\\frac\s*\{\s*(\d+)\s*\}\s*\{\s*(\d+)\s*\}",
                  r"\1/\2", text)
    return (text.replace(r"\angle", "∠").replace(r"\cos", "cos")
            .replace(r"\(", "").replace(r"\)", "").replace("$", "")
            .replace("−", "-"))


def _cos_double_claims(text: str) -> list[tuple[str, float]]:
    from .gates import numeric_mark_value
    text = _math_text(text)
    pattern = (r"\bcos\s*\(\s*2\s*∠\s*([A-Z]{3})\s*\)\s*=\s*"
               r"([-+]?\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?)")
    result = []
    for match in re.finditer(pattern, text, re.I):
        value = numeric_mark_value(match[2])
        if value is not None:
            result.append((match[1].upper(), value))
    return result


def preflight_condition_error(text: str) -> str | None:
    """Reject a bare negative angle, rather than asking the model to invent cos."""
    normalized = _math_text(text)
    pattern = (r"\(\s*2\s*∠\s*([A-Z]{3})\s*\)\s*=\s*"
               r"(-\s*\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?)")
    for match in re.finditer(pattern, normalized, re.I):
        if re.search(r"(?:cos|sin|tan|tg|ctg|кос|син)\s*$",
                     normalized[max(0, match.start() - 12):match.start()], re.I):
            continue
        return (f"В распознанном условии 2∠{match[1].upper()} равно "
                f"{match[2].replace(' ', '')}, что невозможно для угла. "
                "Проверьте фото: возможно, перед скобкой пропущено cos.")
    for angle, value in _cos_double_claims(text):
        if not -1 <= value <= 1:
            return f"cos(2∠{angle})={value:g} вне допустимого диапазона [-1,1]."
    return None


def trisected_parallel_plan(text: str, with_aux: bool) -> FigurePlan | None:
    """Exact affine construction for a recognized trisector/parallel family."""
    statement = re.sub(r"^\s*условие\s*[.:]\s*", "", _math_text(text), flags=re.I)
    head = re.search(r"\bесли\b", statement, re.I)
    if head is None or _canonical(statement[:head.start()]) != _canonical(_TRISECTOR_PREFIX):
        return None
    tail = statement[head.start():]
    match = re.fullmatch(
        r"если\s+BC\s*=\s*(\d+(?:[.,]\d+)?)\s*,\s*"
        r"cos\s*\(\s*2\s*∠\s*CAN\s*\)\s*=\s*"
        r"([-+]?\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?)\s*\.?\s*",
        tail, re.I)
    if not match:
        return None
    from .gates import numeric_mark_value
    length = numeric_mark_value(match[1])
    cosine = numeric_mark_value(match[2])
    if length is None or length <= 0 or cosine is None or not -1 <= cosine <= 1:
        return None
    plan = FigurePlan.from_dict({
        "points": ["B", "C", "A", "M", "N", "D"],
        "constructions": [
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "free_point", "out": "A"},
            {"op": "divide_segment", "out": "M", "args": ["B", "C"], "value": 1 / 3},
            {"op": "divide_segment", "out": "N", "args": ["B", "C"], "value": 2 / 3},
            # The parallels intersect CD at its midpoint A: D=2A-C.
            {"op": "reflect_point", "out": "D", "args": ["C", "A"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["B", "C"], "value": length},
            {"type": "dist_eq", "args": ["A", "B", "C", "D"]},
            {"type": "cos_double_angle", "args": ["C", "A", "N"], "value": cosine},
            {"type": "parallel", "args": ["M", "D", "A", "N"]},
            {"type": "on_segment", "args": ["A", "C", "D"]},
        ],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["A", "C"], ["A", "N"],
                         ["M", "D"], ["A", "D"], ["C", "D"]],
            "aux_segments": [["A", "M"]] if with_aux else [],
            "equal_marks": [{"pts": [p, q], "count": 1}
                            for p, q in (("B", "M"), ("M", "N"), ("N", "C"))]
                           + [{"pts": [p, q], "count": 2}
                              for p, q in (("A", "B"), ("C", "D"))],
            "length_marks": [{"pts": ["B", "C"], "text": f"{length:g}"}],
        },
        "target": {"kind": "dist", "args": ["A", "B"]},
        "notes": ("M и N делят BC на три равные части; из MD ∥ AN следует, "
                  "что A — середина CD. Значение AB измерено на одном "
                  "проверенном чертеже, а не объявлено доказанным ответом."),
    })
    validate_plan(plan)
    return plan


def _canonical(text: str) -> str:
    # Vision OCR may wrap the same point names and equality in LaTeX.
    text = re.sub(r"\\(?:mathrm|text|operatorname)\s*\{([^{}]*)\}",
                  r"\1", text)
    text = re.sub(r"\\(?:neq|ne)\b|!=", "≠", text)
    return re.sub(r"[^\w=<>≠≤≥]+|_", "", text.casefold())


def proof_parallelogram_plan(text: str, with_aux: bool) -> FigurePlan | None:
    """An exact, non-LLM construction for the stated theorem, not its variants.

    The arbitrary altitude and AC=1 fix an illustrative shape and scale;
    neither appears as an asserted measurement on the drawing.
    """
    statement = re.sub(r"^\s*условие\s*[.:]\s*", "", text, flags=re.I)
    if _canonical(statement) != _canonical(_PARALLELOGRAM_PROOF):
        return None
    plan = FigurePlan.from_dict({
        "points": ["A", "C", "M", "B", "D", "R", "F", "E"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "C"},
            {"op": "midpoint", "out": "M", "args": ["A", "C"]},
            {"op": "perp_point", "out": "B",
             "args": ["M", "A", "C"], "value": 0.65},
            {"op": "bisector_point", "out": "D", "args": ["C", "A", "B"]},
            # |CR|=|BD|. The first intersection on the oriented line AC
            # is F=C-|BD|*unit(AC), rather than the exterior root.
            {"op": "translate", "out": "R", "args": ["C", "B", "D"]},
            {"op": "line_circle", "out": "F",
             "args": ["A", "C", "C", "R"], "value": 0},
            # CDEF is a parallelogram in cyclic order: E=D+(F-C).
            {"op": "translate", "out": "E", "args": ["D", "C", "F"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "C"], "value": 1},
        ],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"],
                         ["C", "D"], ["D", "E"], ["E", "F"], ["F", "C"],
                         ["B", "E"], ["B", "F"]],
            "aux_segments": [["B", "M"], ["D", "F"]] if with_aux else [],
            "aux_points": ["M"],
            "hide_labels": ["M", "R"],
            "equal_marks": [
                {"pts": ["A", "B"], "count": 1},
                {"pts": ["B", "C"], "count": 1},
                {"pts": ["B", "D"], "count": 2},
                {"pts": ["C", "F"], "count": 2},
            ],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": ("Иллюстрация доказательства; AC=1 задаёт только масштаб, "
                  "высота выбрана для невырожденного примера. "
                  "Равенство BE=BF проверено на чертеже, "
                  "но рисунок сам по себе не является доказательством."),
    })
    validate_plan(plan)
    return plan


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


def proof_equality(text: str) -> tuple[str, str] | None:
    """A plain named-segment equality requested as a proof, not a target kind."""
    match = re.search(
        r"\bдокажите\s*,?\s*что\b[^.!?]{0,140}?"
        r"(?<![A-Z_])([A-Z]{2})\s*=\s*([A-Z]{2})(?![A-Z_])",
        text, re.I,
    )
    return (match[1].upper(), match[2].upper()) if match else None


_OPERATOR_BEFORE = re.compile(r"[:/·*×+\-^∙]\s*$")
_OPERATOR_AFTER = re.compile(r"^(?:\s*[:/·*×+\-^∙]|[A-Za-zА-Яа-я(√])")


def _plain_relation(text: str, start: int, end: int) -> bool:
    """True for a bare 'XY = value' claim, not a term of a ratio/expression.

    'BD : DC = 1 : 2' must not be read as DC = 1, and
    'BD : DC = AE : EC' must not be read as DC = AE.
    """
    return not (_OPERATOR_BEFORE.search(text[max(0, start - 6):start])
                or _OPERATOR_AFTER.match(text[end:end + 3]))


def _statement_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    """Check explicitly named 2D relationships independent of the LLM plan.

    Unlike constraints, these are parsed from the user's wording, so a model
    cannot quietly replace a point on a side by an intersection at its end or
    omit a stated equality and still return a verified drawing.
    """
    P = {name: np.asarray(value, dtype=float) for name, value in coords.items()}
    if not P:
        return []
    fails: list[str] = []

    for match in re.finditer(
        r"(?<![A-Z_])(?=([A-Z]{2})\s*=\s*([A-Z]{2})(?![A-Z_]))",
        text, re.I,
    ):
        left, right = match[1].upper(), match[2].upper()
        end = match.start() + len(re.match(r"[A-Z]{2}\s*=\s*[A-Z]{2}",
                                           text[match.start():], re.I)[0])
        if not _plain_relation(text, match.start(), end):
            continue
        names = set(left + right)
        if not names <= P.keys():
            fails.append(f"отсутствуют точки равенства {left}={right}")
        else:
            lengths = [float(np.linalg.norm(P[s[0]] - P[s[1]]))
                       for s in (left, right)]
            if abs(lengths[0] - lengths[1]) > 1e-4 * max(*lengths, 1e-9):
                fails.append(f"заданное равенство {left}={right} не выполняется")

    from .gates import numeric_mark_value, _angle_deg
    for match in re.finditer(
        r"(?<![A-Z_])([A-Z]{2})\s*=\s*(\d+(?:[.,]\d+)?)\b", text, re.I,
    ):
        name, expected = match[1].upper(), numeric_mark_value(match[2])
        if expected is None or not _plain_relation(text, match.start(), match.end()):
            continue
        if not set(name) <= P.keys():
            fails.append(f"отсутствуют точки заданной длины {name}")
        elif abs(float(np.linalg.norm(P[name[0]] - P[name[1]]))
                 - expected) > 1e-4 * max(abs(expected), 1e-9):
            fails.append(f"заданная длина {name}={expected:g} не выполняется")

    for angle, expected in _cos_double_claims(text):
        if not set(angle) <= P.keys():
            fails.append(f"отсутствуют точки угла {angle}")
            continue
        theta = _angle_deg(P[angle[0]], P[angle[1]], P[angle[2]])
        if not math.isfinite(theta) or abs(
            math.cos(2 * math.radians(theta)) - expected
        ) > 1e-4:
            fails.append(f"cos(2∠{angle}) не совпадает с условием")

    # A common affine construction: ordered trisectors on BC, MD parallel
    # AN and D on the continuation of CA beyond A. Verify the wording even
    # when a model omitted the equivalent constraints from its own plan.
    t = _math_text(text)
    if (re.search(r"на\s+сторон\w*\s+BC\b[^.!?]{0,90}\bточк\w*\s+M\s+и\s+N\b", t, re.I)
            and re.search(r"BM\s*=\s*MN\s*=\s*NC\b", t, re.I)):
        if not set("BCMN") <= P.keys():
            fails.append("отсутствуют M и N на стороне BC")
        else:
            v = P["C"] - P["B"]
            den = float(v @ v)
            if den < 1e-18:
                fails.append("сторона BC вырождена")
            else:
                fs = [float(np.dot(P[k] - P["B"], v) / den) for k in "MN"]
                errs = [abs(float(np.linalg.det(np.array([v, P[k] - P["B"]]))))
                        for k in "MN"]
                if not 1e-5 < fs[0] < fs[1] < 1 - 1e-5 or max(errs) > 1e-5 * den:
                    fails.append("M и N не лежат по порядку внутри BC")

    if (re.search(r"параллельн\w*\s+AN\b[^.!?]{0,65}через\s+точк\w*\s+M\b", t, re.I)
            and re.search(r"продолжени\w*\s+сторон\w*\s+AC\s+за\s+точк\w*\s+A", t, re.I)
            and re.search(r"\bточк\w*\s+D\b", t, re.I)):
        if not set("ACDMN") <= P.keys():
            fails.append("отсутствуют точки параллели MD и продолжения AC")
        else:
            u, v = P["D"] - P["M"], P["N"] - P["A"]
            length = float(np.linalg.norm(u) * np.linalg.norm(v))
            cross = abs(float(np.linalg.det(np.array([u, v]))))
            ca = P["A"] - P["C"]
            den = float(ca @ ca)
            position = float(np.dot(P["D"] - P["C"], ca) / den) if den > 1e-18 else -1
            off = abs(float(np.linalg.det(np.array([ca, P["D"] - P["C"]]))))
            if length < 1e-12 or cross > 1e-5 * length:
                fails.append("MD не параллельна AN")
            if den < 1e-18 or position <= 1 + 1e-5 or off > 1e-5 * den:
                fails.append("D не лежит на продолжении AC за A")

    sides = []
    for match in re.finditer(
        r"\bточк\w*\s+([A-Z])\s+(?:лежит|находится)\b"
        r"[^.!?]{0,35}?\bна\s+(?:сторон\w*|основани\w*)\s+([A-Z]{2})\b",
        text, re.I,
    ):
        sides.append((match[1].upper(), match[2].upper()))
    for match in re.finditer(
        r"\bна\s+(?:сторон\w*|основани\w*)\s+([A-Z]{2})\b"
        r"[^.!?]{0,45}?\bточк\w*\s+([A-Z])\b",
        text, re.I,
    ):
        sides.append((match[2].upper(), match[1].upper()))
    for point, side in dict.fromkeys(sides):
        if not set(point + side) <= P.keys():
            fails.append(f"отсутствует точка {point} на стороне {side}")
            continue
        a, b, x = P[side[0]], P[side[1]], P[point]
        v = b - a
        den = float(v @ v)
        if den <= 1e-18:
            fails.append(f"сторона {side} вырождена")
            continue
        t = float(np.dot(x - a, v) / den)
        cross = abs(float(np.linalg.det(np.array([v, x - a]))))
        if cross > 1e-5 * den or not 1e-5 < t < 1 - 1e-5:
            fails.append(f"точка {point} не лежит внутри стороны {side}")

    triangle = re.search(r"\bтреугольник\w*\s+([A-Z]{3})\b", text, re.I)
    triangle_names = triangle[1].upper() if triangle else ""
    bisector = re.search(r"\bбиссектрис\w*\s+([A-Z])([A-Z])\b", text, re.I)
    if bisector and triangle_names:
        vertex, foot = bisector[1].upper(), bisector[2].upper()
        if vertex in triangle_names:
            others = [n for n in triangle_names if n != vertex]
            if len(others) == 2:
                refs = {vertex, foot, *others}
                if not refs <= P.keys():
                    fails.append(f"для биссектрисы {vertex}{foot} отсутствуют точки")
                else:
                    from .gates import _angle_deg
                    a, b, f, v = P[others[0]], P[others[1]], P[foot], P[vertex]
                    direction = b - a
                    den = float(direction @ direction)
                    tri_scale = max(float(np.linalg.norm(direction)),
                                    float(np.linalg.norm(v - a)),
                                    float(np.linalg.norm(v - b)), 1e-9)
                    t = float(np.dot(f - a, direction) / den) if den > 1e-15 else -1
                    left = _angle_deg(a, v, f)
                    right = _angle_deg(f, v, b)
                    if (not 1e-5 < t < 1 - 1e-5
                            or abs(float(np.linalg.det(np.array([direction, f - a]))))
                               > 1e-5 * tri_scale * tri_scale
                            or not np.isfinite([left, right]).all()
                            or abs(left - right) > 0.01):
                        fails.append(f"{vertex}{foot} не является биссектрисой треугольника {triangle_names}")
                    if frozenset((vertex, foot)) not in {
                            frozenset(s) for s in plan.draw.segments}:
                        fails.append(f"биссектриса {vertex}{foot} не показана на основном чертеже")

    figure = re.search(
        r"\b(?:четырёхугольник|четырехугольник)\s+([A-Z]{4})\s*"
        r"(?:[-—–:]\s*)?параллелограмм\b"
        r"|\bпараллелограмм\s+([A-Z]{4})\b", text, re.I,
    )
    if figure:
        names = (figure[1] or figure[2]).upper()
        if len(set(names)) != 4 or not set(names) <= P.keys():
            fails.append(f"отсутствуют вершины параллелограмма {names}")
        else:
            V = [P[n] for n in names]
            edges = [V[(i + 1) % 4] - V[i] for i in range(4)]
            figure_scale = max(*(float(np.linalg.norm(e)) for e in edges), 1e-9)
            turns = [float(np.linalg.det(np.array([edges[i], edges[(i + 1) % 4]])))
                     for i in range(4)]
            cross = lambda u, v: abs(float(np.linalg.det(np.array([u, v]))))
            if (min(float(np.linalg.norm(e)) for e in edges) < 1e-5 * figure_scale
                    or not (all(t > 1e-5 * figure_scale ** 2 for t in turns)
                            or all(t < -1e-5 * figure_scale ** 2 for t in turns))
                    or cross(edges[0], edges[2]) > 1e-5 * figure_scale ** 2
                    or cross(edges[1], edges[3]) > 1e-5 * figure_scale ** 2
                    or np.linalg.norm(edges[0] + edges[2]) > 1e-4 * figure_scale):
                fails.append(f"{names} не является невырожденным параллелограммом")
            sides = {frozenset((names[i], names[(i + 1) % 4])) for i in range(4)}
            if not sides <= {frozenset(s) for s in plan.draw.segments}:
                fails.append(f"не все стороны параллелограмма {names} показаны")
    fails += _ratio_and_point_failures(_math_text(text), P)
    return fails


_NAME = r"[A-Z](?:_?\d{1,2})?"
_HYPOTHETICAL = re.compile(r"может\s+ли|верно\s+ли|возможно\s+ли|если\s+бы|предполож|неверно",
                           re.I)


def _point_key(name: str, P: dict) -> str | None:
    for candidate in (name, name.replace("_", ""), re.sub(r"(\d)", r"_\1", name, count=1)):
        if candidate in P:
            return candidate
    return None


def _ratio_and_point_failures(text: str, P: dict) -> list[str]:
    """Stated segment ratios and explicitly named points must be on the figure.

    'BD : DC = 1 : 2', 'AE/EC = 1/3', 'AB : BC : CA = 3 : 4 : 5' are checked
    as proportions (never as lengths); 'пересекаются в точке O' requires O.
    """
    fails: list[str] = []
    seg = rf"({_NAME})({_NAME})(?![A-Za-z0-9_])"
    for sentence in re.split(r"(?<=[.;!?])\s+", text):
        if _HYPOTHETICAL.search(sentence):
            continue
        chains = re.finditer(
            rf"(?<![A-Za-z0-9_])((?:{_NAME}){{2}}(?:\s*[:/]\s*(?:{_NAME}){{2}})+)(?![A-Za-z0-9_])"
            r"\s*=\s*(\d+(?:[.,]\d+)?(?:\s*[:/]\s*\d+(?:[.,]\d+)?)+)(?![\d.,]*\s*[A-Za-z(√])",
            sentence)
        for m in chains:
            segs = [re.match(seg, part.strip()) for part in re.split(r"[:/]", m[1])]
            nums = [float(x.replace(",", ".")) for x in re.split(r"\s*[:/]\s*", m[2])]
            if len(segs) != len(nums) or not all(segs) or min(nums) <= 0:
                continue
            keys = [(_point_key(g[1], P), _point_key(g[2], P)) for g in segs]
            label = m[0].strip()
            if not all(a and b for a, b in keys):
                fails.append(f"отсутствуют точки отношения {label}")
                continue
            lengths = [float(np.linalg.norm(P[a] - P[b])) for a, b in keys]
            if min(lengths) <= 1e-9:
                fails.append(f"вырожденный отрезок в отношении {label}")
                continue
            for length, num in zip(lengths[1:], nums[1:]):
                want = num / nums[0]
                got = length / lengths[0]
                if abs(got - want) > 1e-4 * max(want, 1e-9):
                    fails.append(f"заданное отношение {label} не выполняется")
                    break
        for m in re.finditer(rf"точк[а-яё]*\s+((?:{_NAME})(?![A-Za-z0-9_])"
                             rf"(?:\s*(?:,|и)\s*(?:{_NAME})(?![A-Za-z0-9_]))*)", sentence):
            for name in re.findall(_NAME, m[1]):
                if _point_key(name, P) is None:
                    fails.append(f"на чертеже нет точки {name}, названной в условии")
    return list(dict.fromkeys(fails))


def semantic_failures(text: str, plan: FigurePlan, coords: dict) -> list[str]:
    """Independently check the named incenter, circle and equality claims."""
    fails = (_incircle_failures(text, plan, coords)
             + _circumcircle_failures(text, plan, coords)
             + _rhombus_failures(text, plan, coords)
             + _statement_failures(text, plan, coords))
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
