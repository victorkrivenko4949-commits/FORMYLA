"""Auxiliary constructions on top of an already verified figure.

The main figure is built and checked first. The auxiliary layer is a small,
separate step, so a weak model answer can no longer leave the "with auxiliary
constructions" mode empty:

1. a deterministic rule for the classical trapezoid-diagonals construction;
2. otherwise the model is asked only for the auxiliary steps, in a tiny
   whitelisted language (new points from exact operations on existing ones);
3. every step is executed by the engine, checked (finite, not degenerate,
   near the figure) and only then drawn. Equal-length ticks are added only
   for equalities that follow from the operation itself and hold numerically.

Nothing here changes the main figure or any verified point.
"""
from __future__ import annotations

import copy
import math
import re

import numpy as np

from .constructions import OPS
from .schema import Construction

# op -> (number of point arguments, needs numeric value)
ALLOWED = {
    "midpoint": (2, False), "divide_segment": (2, True), "reflect_point": (2, False),
    "translate": (3, False), "parallel_point": (3, True), "line_intersect": (4, False),
    "foot": (3, False), "homothety": (2, True), "rotate": (2, True),
    "circumcenter": (3, False), "incenter": (3, False), "centroid": (3, False),
    "orthocenter": (3, False),
    # построения, которые эксперт часто предлагает вторым вариантом
    "bisector_point": (3, False), "bisector_circumcircle": (3, False),
    "external_bisector_point": (3, False), "line_circle_other": (4, False),
    "line_circle": (4, True), "circle_circle": (4, True),
    "tangent_point": (3, True), "excenter": (3, True),
}
_ROOT_OPS = {"line_circle": (0, 1), "circle_circle": (0, 1), "tangent_point": (0, 1), "excenter": (0, 1, 2)}
MAX_NEW_POINTS = 6
_NAME = re.compile(r"^[A-Z](?:_?\d{1,2})?$")

OP_DOC = """Разрешённые операции (out — НОВОЕ имя точки, args — уже существующие точки; число k/t/градусы
пишется ОТДЕЛЬНЫМ полем "value", а не в args):
midpoint(A,B) — середина AB;
divide_segment(A,B,value=t) — точка A+t·(B−A) (t>1 даёт продолжение за B);
reflect_point(A,O) — точка, симметричная A относительно точки O;
translate(A,B,C) — A+(C−B), то есть A, сдвинутая на вектор BC;
parallel_point(A,B,C,value=k) — A+k·(C−B);
line_intersect(A,B,C,D) — пересечение прямых AB и CD;
parallel_intersect(P,A,B,C,D) — точка пересечения прямой, проведённой через P параллельно AB, с прямой CD
  («через P провести прямую, параллельную AB, до пересечения с CD»);
foot(P,A,B) — основание перпендикуляра из P на прямую AB;
homothety(A,O,value=k) — O+k·(A−O);
rotate(A,O,value=градусы) — поворот A вокруг O против часовой стрелки;
circumcenter(A,B,C), incenter(A,B,C), centroid(A,B,C), orthocenter(A,B,C);
bisector_point(A,B,C) — пересечение биссектрисы угла A со стороной BC;
bisector_circumcircle(A,B,C) — второе пересечение биссектрисы угла A с описанной окружностью ABC;
external_bisector_point(A,B,C) — пересечение внешней биссектрисы угла A с прямой BC;
line_circle_other(A,B,C,D) — второе пересечение прямой AB с окружностью (центр C, радиус CD), A на окружности;
line_circle(A,B,C,D,value=0|1), circle_circle(A,B,C,D,value=0|1) — пересечения с окружностями;
tangent_point(A,B,C,value=0|1) — точка касания из A к окружности (центр B, радиус BC);
excenter(A,B,C,value=0|1|2) — центр вневписанной окружности напротив A/B/C."""

SYS_AUXPLAN = """Ты помогаешь оформить чертёж школьной или олимпиадной геометрической задачи.
Основной чертёж по условию УЖЕ построен и проверен. Если в описании чертежа приведено
построение, которое модель уже описала словами, нарисуй именно его. Сначала реши задачу про себя лучшим
способом и выбери построение, которое реально используется в этом решении. Твоя задача — ТОЛЬКО
указать дополнительное построение, которое сделал бы хороший учитель при решении: то, что
сводит задачу к известной конфигурации (параллельный перенос диагонали или стороны,
удвоение медианы, параллельная прямая через точку, продолжение стороны, симметрия,
высота, средняя линия, описанная окружность и т. п.).

""" + OP_DOC + """

Верни ТОЛЬКО JSON:
{"idea": "одна строка по-русски: зачем это построение",
 "steps": [{"op": "translate", "out": "E", "args": ["D","B","C"]}],
 "aux_segments": [["C","E"]],
 "aux_extensions": [["A","D"]],
 "aux_lines": [],
 "aux_circles": [["O","A"]]}

Правила:
1. Не больше 6 новых точек; имена — заглавные латинские буквы, которых ещё нет на чертеже.
2. Используй только точки, которые есть в описании чертежа, и точки, созданные выше.
3. aux_segments — ВСЕ отрезки нового построения, в том числе продолжения сторон и
   медиан: продолжение AM за M до новой точки D задаётся отрезком [M,D]. aux_extensions
   не используй. aux_circles [центр, точка на окружности].
4. Не дублируй уже нарисованное (в том числе то, что перечислено как уже нарисованное
   доп. построение): добавляй только недостающее. Пустой ответ {"idea": "", "steps": []} допустим только
   для совсем элементарной задачи, где хороший учитель не рисует ничего сверх условия.
   Если решение можно упростить или прояснить построением, предложи его.
5. Не пиши решение и ответ, не выдумывай данных, только построение."""


_CUE = re.compile(r"провед|продол|достро|параллел|перенес|сдвин|симметр|удво|отложим|отметим|"
                  r"опустим|высот[уа]|пересеч|описан|вписан|соедин|построим", re.I)


def mentions_construction(notes) -> bool:
    """Does the model's own text describe an auxiliary construction?"""
    return isinstance(notes, str) and bool(_CUE.search(notes))


STATEMENT_ONLY = ("(чертёж по условию строится автоматически параллельно; используй имена точек "
                  "из условия, новые точки называй буквами, которых в условии нет)")


def describe_figure(plan, coords) -> str:
    lines = ["Точки чертежа (имя: способ построения):"]
    by_out = {c.out: c for c in plan.constructions if c.out}
    for name in plan.points:
        if name in plan.draw.hide_labels or name not in coords:
            continue
        c = by_out.get(name)
        how = "свободная" if c is None or c.op == "free_point" else f"{c.op}({', '.join(c.args)})"
        lines.append(f"{name}: {how}")
    if plan.draw.segments:
        lines.append("Нарисованы отрезки: " + ", ".join("".join(s) for s in plan.draw.segments))
    if plan.draw.circles:
        lines.append("Окружности [центр, точка]: " + ", ".join("".join(c) for c in plan.draw.circles))
    d = plan.draw
    drawn = [("отрезки", d.aux_segments), ("прямые", d.aux_lines), ("лучи", d.aux_rays),
             ("окружности [центр, точка]", d.aux_circles)]
    for label, items in drawn:
        if items:
            lines.append(f"Уже нарисовано как доп. построение, {label}: "
                         + ", ".join("".join(x) for x in items))
    if plan.notes and mentions_construction(plan.notes):
        lines.append("Как модель уже описала построение (нарисуй именно его, если оно осмысленно): "
                     + plan.notes[:600])
    return "\n".join(lines)


def has_aux(plan) -> bool:
    d = plan.draw
    return bool(d.aux_segments or d.aux_lines or d.aux_rays or d.aux_extensions or d.aux_circles)


# ---------------------------------------------------------------- deterministic

def trapezoid_diagonals(plan, coords, text: str) -> dict | None:
    """Classical step: translate a diagonal by a base, giving a triangle with
    sides = both diagonals and the sum of the bases (also the midline*2)."""
    t = text.lower()
    if "трапец" not in t or "диагонал" not in t:
        return None
    m = re.search(r"трапеци\w*\s+([A-Z])([A-Z])([A-Z])([A-Z])(?![A-Za-z])", text, re.I)
    if not m:
        return None
    a, b, c, d = (g.upper() for g in m.groups())
    if not all(n in coords for n in (a, b, c, d)) or len({a, b, c, d}) != 4:
        return None
    bases = re.search(r"основани\w*\s+([A-Z])([A-Z])\s+и\s+([A-Z])([A-Z])", text, re.I)
    order = None
    if bases:
        s1, s2 = frozenset(x.upper() for x in bases.group(1, 2)), frozenset(x.upper() for x in bases.group(3, 4))
        if {s1, s2} == {frozenset((a, d)), frozenset((b, c))}:
            order = (a, b, c, d)
        elif {s1, s2} == {frozenset((a, b)), frozenset((c, d))}:
            order = (b, c, d, a)
    if order is None:
        # bases from the geometry: a pair of opposite sides that is parallel
        P = {n: np.asarray(coords[n], float) for n in (a, b, c, d)}
        cross = lambda u, v: abs(u[0] * v[1] - u[1] * v[0])
        scale = max(np.linalg.norm(P[x] - P[y]) for x in P for y in P) ** 2
        if cross(P[d] - P[a], P[c] - P[b]) < 1e-7 * scale:
            order = (a, b, c, d)
        elif cross(P[b] - P[a], P[d] - P[c]) < 1e-7 * scale:
            order = (b, c, d, a)
    if order is None:
        return None
    v0, v1, v2, v3 = order
    e = next((n for n in "EFGHKLMNPQ" if n not in coords and n not in plan.points), None)
    if e is None:
        return None
    return {"idea": f"Сдвиг диагонали {v1}{v3} на {v1}{v2}: треугольник {v0}{v2}{e} со сторонами, "
                    f"равными диагоналям и сумме оснований.",
            "steps": [{"op": "translate", "out": e, "args": [v3, v1, v2]}],
            "aux_segments": [[v2, e], [v3, e]], "aux_extensions": [], "aux_lines": [],
            "aux_circles": [], "_expect_collinear": [v0, v3, e]}


# ---------------------------------------------------------------- validation / apply

def _pair_list(value, known, limit=8):
    out = []
    for item in value if isinstance(value, list) else []:
        if (isinstance(item, list) and len(item) == 2 and all(isinstance(n, str) for n in item)
                and all(n in known for n in item) and item[0] != item[1]):
            out.append(list(item))
    return out[:limit]


_SEG = r"([A-Z][A-Z0-9_']?)\s*([A-Z][A-Z0-9_']?)"


def claims_hold(idea: str, coords: dict, why: list | None = None, involve: set | None = None) -> bool:
    """Numerically check equalities and parallelism the model states in words.

    Only explicit claims about named points are checked («DG = BD», «EF ∥ CD»); a
    claim that mentions an unknown point is ignored. False means the drawing
    contradicts the model's own description, so it must not be shown.
    """
    if not isinstance(idea, str) or not idea:
        return True
    pt = {k: np.asarray(v, float) for k, v in coords.items()}
    span = max((float(np.linalg.norm(a - b)) for a in pt.values() for b in pt.values()),
               default=0.0)
    if span <= 1e-9:
        return True

    def seg(a, b):
        return (pt[a], pt[b]) if a in pt and b in pt else None

    for m in re.finditer(rf"(?<![A-Za-z]){_SEG}\s*=\s*{_SEG}(?!\s*[=+\-*/\d])", idea):
        s1, s2 = seg(m[1], m[2]), seg(m[3], m[4])
        if s1 is None or s2 is None:
            continue
        if involve is not None and not ({m[1], m[2], m[3], m[4]} & involve):
            continue                # a claim about the original figure only: not ours to veto
        l1, l2 = float(np.linalg.norm(s1[0] - s1[1])), float(np.linalg.norm(s2[0] - s2[1]))
        if abs(l1 - l2) > 1e-3 * span:
            if why is not None:
                why.append(f"равенство {m[1]}{m[2]} = {m[3]}{m[4]} в тексте не выполняется на чертеже")
            return False
    for m in re.finditer(rf"(?<![A-Za-z]){_SEG}\s*(?:∥|\|\||параллельн\w*)\s*{_SEG}", idea):
        s1, s2 = seg(m[1], m[2]), seg(m[3], m[4])
        if s1 is None or s2 is None:
            continue
        if involve is not None and not ({m[1], m[2], m[3], m[4]} & involve):
            continue                # a claim about the original figure only: not ours to veto
        d1, d2 = s1[1] - s1[0], s2[1] - s2[0]
        n1, n2 = float(np.linalg.norm(d1)), float(np.linalg.norm(d2))
        if n1 > 1e-9 and n2 > 1e-9 and abs(d1[0] * d2[1] - d1[1] * d2[0]) > 1e-3 * n1 * n2:
            if why is not None:
                why.append(f"параллельность {m[1]}{m[2]} и {m[3]}{m[4]} в тексте не выполняется на чертеже")
            return False
    return True


_POINT_TOKEN = re.compile(r"[A-Z](?:_?\d{1,2})?")
_STEP_TEXT = re.compile(r"^\s*(?:([A-Z](?:_?\d{1,2})?)\s*=\s*)?([a-z_]+)\s*\((.*)\)\s*$")


def _flatten_points(args, need):
    """["D","AC","BC"] -> ["D","A","C","B","C"] when the model glued point names together."""
    out = []
    for a in args:
        if not isinstance(a, str):
            return None
        toks = _POINT_TOKEN.findall(a) if _POINT_TOKEN.sub("", a) == "" else None
        if not toks:
            return None
        out += toks
    return out if len(out) == need else None


def _step_from_text(text):
    """«K = translate(D, B, C)» written as a string instead of an object."""
    m = _STEP_TEXT.match(text)
    if not m:
        return None
    out, op, raw = m.groups()
    args, value = [], None
    for part in (x.strip() for x in raw.split(",") if x.strip()):
        try:
            value = float(part)
        except ValueError:
            args.append(part.strip("\"' "))
    return {"op": op, "out": out, "args": args, **({"value": value} if value is not None else {})}


def _expand_steps(steps, taken: set, why: list | None = None):
    """Normalise model steps: a stray numeric last argument becomes `value`, glued point
    names are split, a step written as text is parsed, and the compound
    «parallel_intersect(P,A,B,C,D)» becomes two ordinary steps. On failure returns None and
    says which step was unusable (a silent None left nobody knowing the real format)."""
    def bad(reason, step):
        if why is not None:
            raw = str(step)
            why.append(f"{reason}: {raw[:110]}")
        return None
    out = []
    for step in steps:
        if isinstance(step, str):
            parsed = _step_from_text(step)
            if parsed is None:
                return bad("шаг записан не как объект", step)
            step = parsed
        if not isinstance(step, dict):
            return bad("шаг не объект", step)
        step = dict(step)
        op, args = step.get("op"), step.get("args")
        if op == "parallel_intersect" and isinstance(args, list) and len(args) != 5:
            flat = _flatten_points(args, 5)
            if flat:
                args = step["args"] = flat
        elif op in ALLOWED and isinstance(args, list) and len(args) != ALLOWED[op][0] \
                and not (ALLOWED[op][1] and len(args) == ALLOWED[op][0] + 1 and isinstance(args[-1], (int, float))):
            flat = _flatten_points(args, ALLOWED[op][0])
            if flat:
                args = step["args"] = flat
        if op in ALLOWED and isinstance(args, list) and ALLOWED[op][1] and step.get("value") is None \
                and len(args) == ALLOWED[op][0] + 1 and isinstance(args[-1], (int, float)) \
                and not isinstance(args[-1], bool):
            step["value"], step["args"] = args[-1], args[:-1]
        if op == "parallel_intersect":
            if not (isinstance(args, list) and len(args) == 5 and all(isinstance(a, str) for a in args)):
                return bad("parallel_intersect: нужно ровно 5 точек P,A,B,C,D", step)
            p, a, b, c, d = args
            helper = next((f"Z_{i}" for i in range(1, 100) if f"Z_{i}" not in taken), None)
            if helper is None:
                return bad("нет свободного имени для вспомогательной точки", step)
            taken.add(helper)
            out.append({"op": "translate", "out": helper, "args": [p, a, b]})
            out.append({"op": "line_intersect", "out": step.get("out"), "args": [p, helper, c, d]})
            continue
        out.append(step)
    return out


def apply_aux(plan, coords: dict, data, why: list | None = None) -> tuple | None:
    """Validate and execute an auxiliary plan. Returns (plan, coords) or None.

    Every refusal appends a short human-readable reason to `why` (if given): a silent
    refusal used to leave the drawing without construction and nobody knew why."""
    def no(reason):
        if why is not None:
            why.append(reason)
        return None

    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return no("ответ не в формате шагов")
    if len(data["steps"]) > MAX_NEW_POINTS:
        return no(f"больше {MAX_NEW_POINTS} новых точек")
    known = {k: np.asarray(v, float) for k, v in coords.items()}
    pts = np.array(list(known.values()))
    span = float(np.max(np.ptp(pts, axis=0))) if len(pts) else 0.0
    if span <= 1e-9:
        return no("чертёж вырожден")
    centre = pts.mean(axis=0)
    new: list[Construction] = []
    bad_steps: list = []
    steps = _expand_steps(data["steps"], set(known) | set(plan.points), bad_steps)
    if steps is None:
        return no("шаги не разобраны — " + (bad_steps[0] if bad_steps else "неизвестная форма"))
    for step in steps:
        if not isinstance(step, dict):
            return no("шаг не объект")
        op, out, args = step.get("op"), step.get("out"), step.get("args")
        value = step.get("value")
        if op not in ALLOWED:
            return no(f"операция «{op}» не поддерживается")
        if not isinstance(out, str) or not _NAME.match(out) or out in known or out in plan.points \
                or not isinstance(args, list):
            return no(f"имя новой точки «{out}» занято или недопустимо")
        need, needs_value = ALLOWED[op]
        if len(args) != need:
            return no(f"{op}: нужно {need} точек, дано {len(args)}")
        missing = [a for a in args if not (isinstance(a, str) and a in known)]
        if missing:
            return no(f"{op}: на чертеже нет точек {', '.join(map(str, missing))}")
        if needs_value:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return no(f"{op}: нужно число value")
            if op == "divide_segment" and not -3 <= value <= 4:
                return no("divide_segment: value вне [-3, 4]")
            if op in ("parallel_point", "homothety") and not -4 <= value <= 4:
                return no(f"{op}: value вне [-4, 4]")
            if op in _ROOT_OPS and value not in _ROOT_OPS[op]:
                return no(f"{op}: value должно быть одним из {_ROOT_OPS[op]}")
        else:
            value = None
        try:
            p = np.asarray(OPS[op](*[known[a] for a in args], value=value), dtype=float).reshape(2)
        except Exception:  # noqa: BLE001 - degenerate step
            return no(f"{op}({', '.join(args)}): построение невозможно на этом чертеже")
        if not np.all(np.isfinite(p)) or float(np.linalg.norm(p - centre)) > 3.0 * span:
            return no(f"точка {out} далеко за пределами чертежа")
        if any(float(np.linalg.norm(p - q)) < 1e-6 * span for q in known.values()):
            return no(f"точка {out} совпадает с уже существующей")
        known[out] = p
        new.append(Construction(op=op, out=out, args=list(args),
                                value=float(value) if value is not None else None))

    names = set(known)
    segments = _pair_list(data.get("aux_segments"), names)
    extensions = _pair_list(data.get("aux_extensions"), names)
    # A continuation "PQ beyond Q up to a new point R" is just the segment QR.
    for p, q in extensions:
        for c in new:
            r = known[c.out]
            d = known[q] - known[p]
            v = r - known[q]
            if float(d @ v) > 0 and abs(d[0] * v[1] - d[1] * v[0]) <= 1e-7 * float(d @ d) ** 0.5 * span:
                segments.append([q, c.out])
    extensions = []
    # The continuation created by a reflection or an extension must be visible.
    for c in new:
        if c.op == "reflect_point":
            segments.append([c.args[1], c.out])
        elif c.op == "divide_segment" and (c.value or 0) > 1:
            segments.append([c.args[1], c.out])
    lines = _pair_list(data.get("aux_lines"), names, 4)
    circles = _pair_list(data.get("aux_circles"), names, 2)
    if not (segments or extensions or lines or circles):
        return no("нет ни одного отрезка, прямой или окружности для рисования")
    expect = data.get("_expect_collinear")
    if expect:
        a, b, c = (known[n] for n in expect)
        d = b - a
        if abs(d[0] * (c - a)[1] - d[1] * (c - a)[0]) > 2e-2 * float(d @ d) ** 0.5 * span:
            return no("ожидаемая коллинеарность не выполняется")

    plan = copy.deepcopy(plan)
    draw = plan.draw
    for c in new:
        plan.points.append(c.out)
        plan.constructions.append(c)
    used = {n for grp in (segments, extensions, lines, circles) for pr in grp for n in pr}
    for c in new:
        if c.out in used:
            draw.aux_points.append(c.out)
        else:
            draw.hide_labels.append(c.out)
    have = {frozenset(s) for s in draw.segments + draw.aux_segments}
    for s in segments:
        if frozenset(s) not in have:
            draw.aux_segments.append(s)
            have.add(frozenset(s))
    draw.aux_extensions += [e for e in extensions if e not in draw.aux_extensions]
    draw.aux_lines += lines
    draw.aux_circles += circles
    if data.get("idea") and isinstance(data["idea"], str):
        plan.notes = data["idea"][:300]     # the text always matches what is drawn
    _verified_ticks(plan, known, new)
    return plan, known


def _verified_ticks(plan, coords, new) -> None:
    """Equal-length ticks for equalities implied by the operation, if they hold."""
    d = plan.draw
    used = {m.get("count", 1) for m in d.equal_marks}
    pairs: list[list[tuple[str, str]]] = []
    for c in new:
        a = c.args
        if c.op in ("translate", "parallel_point") and (c.op == "translate" or c.value == 1.0):
            pairs.append([(a[0], a[1]), (c.out, a[2])])      # the translated segment first
            pairs.append([(a[1], a[2]), (a[0], c.out)])
        elif c.op == "midpoint":
            pairs.append([(a[0], c.out), (c.out, a[1])])
        elif c.op == "reflect_point":
            pairs.append([(a[1], a[0]), (a[1], c.out)])
    length = lambda p: float(np.linalg.norm(coords[p[0]] - coords[p[1]]))
    for group in pairs:
        if any(p[0] not in coords or p[1] not in coords for p in group):
            continue
        if max(length(p) for p in group) - min(length(p) for p in group) > 1e-6 * max(length(p) for p in group):
            continue
        # both segments must be visible to carry a mark
        visible = {frozenset(s) for f in ("segments", "aux_segments") for s in getattr(d, f)}
        if not all(frozenset(p) in visible for p in group):
            continue
        labelled = [m for m in d.length_marks if m.get("text")
                    and any(frozenset(m["pts"]) == frozenset(p) for p in group)]
        if labelled:
            # a segment already carries its length: its copy gets the same label
            text = labelled[0]["text"]
            for p in group:
                if not any(frozenset(m["pts"]) == frozenset(p) for m in d.length_marks + d.equal_marks):
                    d.length_marks.append({"pts": list(p), "text": text, "layer": "aux"})
            continue
        if any(frozenset(m["pts"]) == frozenset(p) for m in d.equal_marks + d.length_marks
               for p in group):
            continue
        count = next((n for n in (1, 2, 3) if n not in used), None)
        if count is None:
            return
        used.add(count)
        for p in group:
            d.equal_marks.append({"pts": list(p), "count": count, "layer": "aux"})


# ---------------------------------------------------------------- circles named in the text
_CIRCLE = re.compile(r"окружност\w*\s*\(?\s*([A-Z])\s*([A-Z])\s*([A-Z])\s*\)?(?![A-Za-z0-9_])")


def add_named_circles(plan, coords: dict, text: str):
    """The circle the statement names by three points, e.g. "окружности (PXQ)",
    belongs to the main drawing: build its centre exactly and draw it."""
    from .constructions import _circumcenter
    done = plan
    coords = dict(coords)
    for m in _CIRCLE.finditer(text):
        a, b, c = m.groups()
        if len({a, b, c}) != 3 or not all(n in coords for n in (a, b, c)):
            continue
        P = [np.asarray(coords[n], float) for n in (a, b, c)]
        try:
            centre = _circumcenter(*P)
        except Exception:  # noqa: BLE001 - collinear points
            continue
        r = float(np.linalg.norm(centre - P[0]))
        if not np.all(np.isfinite(centre)) or r <= 1e-9:
            continue
        drawn = False
        for k, ref in list(done.draw.circles) + list(done.draw.aux_circles):
            if k in coords and abs(np.linalg.norm(np.asarray(coords[k]) - centre)) < 1e-6 * r \
                    and abs(np.linalg.norm(np.asarray(coords[k]) - np.asarray(coords[ref])) - r) < 1e-6 * r:
                drawn = True
        if drawn:
            continue
        name = next((n for n in ("Z", "Y", "W", "V", "U", "T", "S", "R") if n not in coords
                     and n not in done.points), None)
        if name is None:
            return done, coords
        done = copy.deepcopy(done)
        done.points.append(name)
        done.constructions.append(Construction(op="circumcenter", out=name, args=[a, b, c]))
        done.draw.circles.append([name, a])
        done.draw.hide_labels.append(name)
        coords[name] = centre
    return done, coords
