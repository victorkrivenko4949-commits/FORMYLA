"""GeoExact: контракт плана чертежа. ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ ДЛЯ ВСЕХ МОДУЛЕЙ.

LLM возвращает FigurePlan (JSON). Движок его исполняет. Модель НЕ считает координаты.

Поток: llm -> FigurePlan -> validate_plan -> constructions+solver -> Solution -> gates -> render
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------- конструкции
# Детерминированные построения: точка вычисляется из уже известных.
# out = имя новой точки, args = имена существующих точек/объектов, value = число
CONSTRUCTIONS: dict[str, dict[str, Any]] = {
    # --- базис ---
    "free_point":      {"args": 0, "doc": "свободная точка (координаты ищет решатель)"},
    # --- деление отрезков ---
    "midpoint":        {"args": 2, "doc": "середина AB"},
    "divide_segment":  {"args": 2, "value": True, "doc": "точка на AB с AP:PB = value:(1-value)"},
    "reflect_point":   {"args": 2, "doc": "отражение A относительно B (центральная симметрия)"},
    # --- перпендикуляры ---
    "foot":            {"args": 3, "doc": "основание перпендикуляра из A на BC"},
    "perp_point":      {"args": 3, "value": True, "doc": "точка на перпендикуляре к BC в A на расстоянии value"},
    # --- замечательные точки ---
    "circumcenter":    {"args": 3, "doc": "центр описанной окружности ABC"},
    "incenter":        {"args": 3, "doc": "центр вписанной окружности ABC"},
    "centroid":        {"args": 3, "doc": "центроид ABC"},
    "orthocenter":     {"args": 3, "doc": "ортоцентр ABC"},
    # --- пересечения ---
    "line_intersect":  {"args": 4, "doc": "пересечение прямых AB и CD"},
    "line_circle":     {"args": 4, "value": True, "doc": "пересечение AB с окружностью (центр C, радиус |CD|); value=0/1 выбор корня"},
    "circle_circle":   {"args": 4, "value": True, "doc": "пересечение окружностей (C1=A,r=|AB|),(C2=C,r=|CD|); value=0/1"},
    # --- биссектрисы и параллели ---
    "bisector_point":  {"args": 3, "doc": "пересечение бисс. угла A треугольника ABC со стороной BC; НЕ с описанной окружностью"},
    "bisector_circumcircle": {"args": 3, "doc": "второе после A пересечение биссектрисы угла A треугольника ABC с описанной окружностью"},
    "parallel_point":  {"args": 3, "value": True, "doc": "точка через A параллельно BC на расстоянии value*|BC|"},
    "translate":       {"args": 3, "doc": "A + (C - B)"},
    "rotate":          {"args": 2, "value": True, "doc": "поворот A вокруг B на value градусов"},
    "tangent_point":   {"args": 3, "value": True, "doc": "точка касания из A к окружности (центр B, радиус |BC|); value=0/1"},
    # --- преобразования и дополнительные замечательные точки ---
    "reflect_line":    {"args": 3, "doc": "отражение A относительно прямой BC"},
    "homothety":       {"args": 2, "value": True, "doc": "гомотетия A с центром B и коэффициентом value"},
    "excenter":        {"args": 3, "value": True, "doc": "вневписанный центр ABC; value=0/1/2 напротив A/B/C"},
    "external_bisector_point": {"args": 3, "doc": "пересечение внешней биссектрисы угла A с прямой BC"},
    "invert_point":    {"args": 3, "doc": "инверсия A относительно окружности с центром B и радиусом |BC|"},
    "angle_ray":       {"args": 2, "value": True, "doc": "точка на луче из A: вектор AB повёрнут на value градусов"},
    "regular_polygon_vertex": {"args": 2, "value": True, "doc": "следующая вершина правильного n-угольника слева от AB; value=n>=3"},
    "ninepoint_center": {"args": 3, "doc": "центр окружности девяти точек треугольника ABC"},
    "radical_axis_point": {"args": 4, "doc": "точка радикальной оси окружностей (A,|AB|) и (C,|CD|) на линии центров"},
}

# ---------------------------------------------------------------- ограничения
# Численные условия. Решатель минимизирует их невязку по свободным точкам.
CONSTRAINTS: dict[str, dict[str, Any]] = {
    "dist":          {"pts": 2, "value": True,  "doc": "|AB| = value"},
    "dist_eq":       {"pts": 4, "value": False, "doc": "|AB| = |CD|"},
    "dist_ratio":    {"pts": 4, "value": True,  "doc": "|AB| = value * |CD|"},
    "angle":         {"pts": 3, "value": True,  "doc": "угол ABC (вершина B) = value градусов"},
    "angle_eq":      {"pts": 6, "value": False, "doc": "угол ABC = угол DEF"},
    "collinear":     {"pts": 3, "value": False, "doc": "A, B, C на одной прямой"},
    "perpendicular": {"pts": 4, "value": False, "doc": "AB ⟂ CD"},
    "parallel":      {"pts": 4, "value": False, "doc": "AB ∥ CD"},
    "concyclic":     {"pts": 4, "value": False, "doc": "A, B, C, D на одной окружности"},
    "on_circle":     {"pts": 4, "value": False, "doc": "A на окружности (центр B, радиус |CD|)"},
    "area":          {"pts": 3, "value": True,  "doc": "площадь ABC = value"},
    "on_segment":    {"pts": 3, "value": False, "doc": "A лежит на замкнутом отрезке BC"},
    "same_side":     {"pts": 4, "value": False, "doc": "A и B по одну сторону от прямой CD"},
    "opposite_side": {"pts": 4, "value": False, "doc": "A и B по разные стороны от прямой CD"},
}

# ---------------------------------------------------------------- цель (что измеряем)
TARGETS = {
    "dist":  2,   # длина AB
    "angle": 3,   # угол ABC
    "area":  3,   # площадь ABC
    "ratio": 4,   # |AB|/|CD|
    "none":  0,   # измерение не требуется (только чертёж)
}


@dataclass
class Construction:
    op: str
    out: str | None = None
    args: list[str] = field(default_factory=list)
    value: float | None = None


@dataclass
class Constraint:
    type: str
    args: list[str] = field(default_factory=list)
    value: float | None = None


@dataclass
class Draw:
    """Что рисовать. aux_* = вспомогательные построения (отдельный слой)."""
    segments: list[list[str]] = field(default_factory=list)
    aux_segments: list[list[str]] = field(default_factory=list)
    # бесконечные прямые/лучи задаются парой точек; clipping выполняет renderer
    lines: list[list[str]] = field(default_factory=list)
    rays: list[list[str]] = field(default_factory=list)
    aux_lines: list[list[str]] = field(default_factory=list)
    aux_rays: list[list[str]] = field(default_factory=list)
    aux_points: list[str] = field(default_factory=list)
    # окружность: [центр, точка_на_окружности]
    circles: list[list[str]] = field(default_factory=list)
    aux_circles: list[list[str]] = field(default_factory=list)
    # прямой угол: [A, B, C] — метка при вершине B
    right_angles: list[list[str]] = field(default_factory=list)
    # Угловая метка: {"pts": [A,B,C], "text": "60°", "reflex": False}.
    # Явно заданный count=1..3 также заявляет равенство углов с тем же count.
    # Без count дуга — только аннотация, не утверждение равенства.
    angle_marks: list[dict] = field(default_factory=list)
    # метка длины: {"pts": [A,B], "text": "6"}
    length_marks: list[dict] = field(default_factory=list)
    # {pts:[A,B], count:1..3, layer:"main"|"aux"}
    equal_marks: list[dict] = field(default_factory=list)
    # {center:O,start:A,end:B,reflex:bool,layer:"main"|"aux"}
    arcs: list[dict] = field(default_factory=list)
    # точки, которые НЕ подписывать (напр. служебные)
    hide_labels: list[str] = field(default_factory=list)


@dataclass
class Target:
    kind: str = "none"
    args: list[str] = field(default_factory=list)


@dataclass
class FigurePlan:
    space: str = "plane"                       # plane | space(не поддерживается)
    points: list[str] = field(default_factory=list)
    constructions: list[Construction] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    draw: Draw = field(default_factory=Draw)
    target: Target = field(default_factory=Target)
    # свободный масштаб: если True, размеры произвольны (подобие) -> нормируем
    scale_free: bool = False
    notes: str = ""

    # ---- сериализация
    @staticmethod
    def from_dict(d: dict) -> "FigurePlan":
        if not isinstance(d, dict):
            raise PlanError("BAD_TYPE", f"plan: ожидался объект, получено {type(d).__name__}")
        _check_finite_tree(d)
        dr = d.get("draw", {})
        tg = d.get("target", {})
        if not isinstance(dr, dict) or not isinstance(tg, dict):
            raise PlanError("BAD_TYPE", "draw и target должны быть объектами")
        for key in ("points", "constructions", "constraints"):
            if key in d and not isinstance(d[key], list):
                raise PlanError("BAD_TYPE", f"{key} должен быть списком")

        def _pick(c, cl, kind):
            """Модель иногда добавляет лишние ключи (например points вместо args).
            Такое должно давать читаемый отказ и ретрай, а не падение процесса."""
            if not isinstance(c, dict):
                raise PlanError("BAD_ITEM", f"{kind}: ожидался объект, получено {type(c).__name__}")
            allowed = set(cl.__dataclass_fields__)
            extra = set(c) - allowed
            # частая подмена имени: points -> args
            c = dict(c)
            if "args" not in c and "points" in c:
                c["args"] = c.pop("points"); extra.discard("points")
            if extra:
                raise PlanError("UNKNOWN_FIELD", f"{kind}: недопустимые поля {sorted(extra)}")
            try:
                return cl(**{k: v for k, v in c.items() if k in allowed})
            except TypeError as e:
                raise PlanError("BAD_ITEM", f"{kind}: отсутствует обязательное поле") from e

        unknown = set(d) - set(FigurePlan.__dataclass_fields__)
        if unknown:
            raise PlanError("UNKNOWN_FIELD", f"plan: недопустимые поля {sorted(unknown)}")
        draw_unknown = set(dr) - set(Draw.__dataclass_fields__)
        if draw_unknown:
            raise PlanError("UNKNOWN_FIELD", f"draw: недопустимые поля {sorted(draw_unknown)}")
        if set(tg) - set(Target.__dataclass_fields__):
            raise PlanError("UNKNOWN_FIELD", "target: недопустимые поля")
        return FigurePlan(
            space=d.get("space", "plane"),
            points=d.get("points", []),
            constructions=[_pick(c, Construction, "construction")
                           for c in (d.get("constructions") or [])],
            constraints=[_pick(c, Constraint, "constraint")
                         for c in (d.get("constraints") or [])],
            draw=Draw(**{k: v for k, v in dr.items() if k in Draw.__dataclass_fields__}),
            target=Target(kind=tg.get("kind", "none"), args=tg.get("args", [])),
            scale_free=d.get("scale_free", False),
            notes=d.get("notes", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class PlanError(Exception):
    """Нарушение контракта плана. code -> причина отказа в логах."""

    def __init__(self, code: str, msg: str):
        self.code = code
        super().__init__(f"{code}: {msg}")


def _check_finite_tree(value: Any, path: str = "plan") -> None:
    """Reject non-JSON values and NaN/Infinity even inside optional metadata."""
    if isinstance(value, float) and not math.isfinite(value):
        raise PlanError("NON_FINITE_VALUE", f"{path}: число должно быть конечным")
    if isinstance(value, str) and any(
        (ord(c) < 32 and c not in "\t\n\r") or 0xD800 <= ord(c) <= 0xDFFF
        or ord(c) in (0xFFFE, 0xFFFF) for c in value
    ):
        raise PlanError("INVALID_TEXT", f"{path}: недопустимые для XML символы")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise PlanError("BAD_TYPE", f"{path}: ключ должен быть строкой")
            _check_finite_tree(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _check_finite_tree(v, f"{path}[{i}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise PlanError("BAD_TYPE", f"{path}: недопустимый тип {type(value).__name__}")


def validate_construction_value(op: str, value: Any) -> None:
    """Shared by schema validation and direct analytic execution."""
    spec = CONSTRUCTIONS[op]
    if value is None:
        if spec.get("value"):
            raise PlanError("NO_VALUE", f"{op} требует value")
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanError("BAD_TYPE", f"{op}.value должно быть числом")
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        finite = False
    if not finite:
        raise PlanError("NON_FINITE_VALUE", f"{op}.value должно быть конечным")
    if op in ("line_circle", "circle_circle", "tangent_point") and value not in (0, 1):
        raise PlanError("BAD_VALUE", f"{op}: value должно быть точно 0 или 1")
    if op == "excenter" and value not in (0, 1, 2):
        raise PlanError("BAD_VALUE", "excenter: value=0/1/2 выбирает вершину A/B/C")
    if op == "regular_polygon_vertex" and (value < 3 or value != int(value)):
        raise PlanError("BAD_VALUE", "regular_polygon_vertex: value — целое число сторон n>=3")


def validate_plan(plan: FigurePlan) -> list[str]:
    """Этап 5 конвейера. Бросает PlanError при фатальном; возвращает список мягких замечаний."""
    warn: list[str] = []
    if not isinstance(plan, FigurePlan):
        raise PlanError("BAD_TYPE", "ожидался FigurePlan")
    _check_finite_tree(asdict(plan))
    if not isinstance(plan.scale_free, bool) or not isinstance(plan.notes, str):
        raise PlanError("BAD_TYPE", "scale_free должен быть bool, notes — строкой")
    for name in ("points", "constructions", "constraints"):
        if not isinstance(getattr(plan, name), list):
            raise PlanError("BAD_TYPE", f"{name} должен быть списком")
    if not isinstance(plan.draw, Draw) or not isinstance(plan.target, Target):
        raise PlanError("BAD_TYPE", "draw/target должны быть Draw/Target")
    if not isinstance(plan.target.kind, str) or not isinstance(plan.target.args, list):
        raise PlanError("BAD_TYPE", "target.kind должен быть строкой, target.args — списком")
    if not all(isinstance(a, str) for a in plan.target.args):
        raise PlanError("BAD_TYPE", "target.args должен содержать строки")
    for name in Draw.__dataclass_fields__:
        if not isinstance(getattr(plan.draw, name), list):
            raise PlanError("BAD_TYPE", f"draw.{name} должен быть списком")
    if plan.space != "plane":
        raise PlanError("UNSUPPORTED_SPACE", "движок работает только с планиметрией")
    if not plan.points:
        raise PlanError("NO_POINTS", "план не содержит точек")
    if not all(isinstance(p, str) and p for p in plan.points):
        raise PlanError("BAD_TYPE", "points должен быть списком непустых строк")
    if len(set(plan.points)) != len(plan.points):
        raise PlanError("DUPLICATE_POINTS", "имена точек повторяются")

    def finite_value(value: Any, where: str) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PlanError("BAD_TYPE", f"{where}: value должно быть числом")
        try:
            finite = math.isfinite(float(value))
        except OverflowError:
            finite = False
        if not finite:
            raise PlanError("NON_FINITE_VALUE", f"{where}: value должно быть конечным")

    known: set[str] = set()
    for i, c in enumerate(plan.constructions):
        if not isinstance(c, Construction):
            raise PlanError("BAD_TYPE", f"construction[{i}] должен быть объектом Construction")
        if not isinstance(c.op, str) or (c.out is not None and not isinstance(c.out, str)):
            raise PlanError("BAD_TYPE", f"construction[{i}].op/out должны быть строками")
        if not isinstance(c.args, list) or not all(isinstance(a, str) for a in c.args):
            raise PlanError("BAD_TYPE", f"construction[{i}].args должен быть списком строк")
        finite_value(c.value, f"construction[{i}]")
        spec = CONSTRUCTIONS.get(c.op)
        if spec is None:
            raise PlanError("UNKNOWN_CONSTRUCTION", f"[{i}] неизвестная конструкция {c.op!r}")
        if not c.out:
            raise PlanError("NO_OUT", f"[{i}] {c.op} без out")
        if c.out not in plan.points:
            raise PlanError("UNDECLARED_POINT", f"[{i}] точка {c.out!r} не объявлена в points")
        if c.out in known:
            raise PlanError("REDEFINED_POINT", f"[{i}] точка {c.out!r} определена дважды")
        if len(c.args) != spec["args"]:
            raise PlanError("ARITY", f"[{i}] {c.op} ждёт {spec['args']} аргументов, получено {len(c.args)}")
        if c.op == "circle_circle" and c.args[0] == c.args[2]:
            raise PlanError("SAME_CIRCLE_CENTERS",
                "circle_circle требует ДВА разных центра: args=[O,R1,P,R2], "
                "радиусы |OR1| и |PR2|. Создай отдельные точки R1,R2 для радиусов; "
                "args=[O,P,O,P] пересекает окружность саму с собой.")
        for a in c.args:
            if a not in known:
                raise PlanError("FORWARD_REF", f"[{i}] {c.op} ссылается на неопределённую точку {a!r}")
        if spec.get("value") and c.value is None:
            raise PlanError("NO_VALUE", f"[{i}] {c.op} требует value")
        validate_construction_value(c.op, c.value)
        known.add(c.out)

    missing = set(plan.points) - known
    if missing:
        raise PlanError("UNBUILT_POINTS", f"точки не построены: {sorted(missing)}")

    for i, c in enumerate(plan.constraints):
        if not isinstance(c, Constraint):
            raise PlanError("BAD_TYPE", f"constraint[{i}] должен быть объектом Constraint")
        if not isinstance(c.type, str):
            raise PlanError("BAD_TYPE", f"constraint[{i}].type должен быть строкой")
        if not isinstance(c.args, list) or not all(isinstance(a, str) for a in c.args):
            raise PlanError("BAD_TYPE", f"constraint[{i}].args должен быть списком строк")
        finite_value(c.value, f"constraint[{i}]")
        spec = CONSTRAINTS.get(c.type)
        if spec is None:
            raise PlanError("UNKNOWN_CONSTRAINT", f"[{i}] неизвестное ограничение {c.type!r}")
        if len(c.args) != spec["pts"]:
            raise PlanError("ARITY", f"[{i}] {c.type} ждёт {spec['pts']} точек, получено {len(c.args)}")
        for a in c.args:
            if a not in known:
                raise PlanError("UNKNOWN_REF", f"[{i}] {c.type}: точка {a!r} не существует")
        if spec["value"] and c.value is None:
            raise PlanError("NO_VALUE", f"[{i}] {c.type} требует value")
        if c.value is not None:
            if c.type in ("dist", "area", "dist_ratio") and c.value <= 0:
                raise PlanError("BAD_VALUE", f"{c.type}.value должно быть положительным")
            if c.type == "angle" and not 0 < c.value < 180:
                raise PlanError("BAD_VALUE", "angle.value должно быть между 0 и 180 градусами")

    fixed_distances = {frozenset(c.args): c.value for c in plan.constraints if c.type == "dist"}
    for c in plan.constructions:
        if c.op != "circle_circle":
            continue
        for center, radius_point in (c.args[:2], c.args[2:]):
            ref = fixed_distances.get(frozenset((center, radius_point)))
            desired = fixed_distances.get(frozenset((center, c.out)))
            if ref is not None and desired is not None and not math.isclose(ref, desired, rel_tol=1e-8):
                raise PlanError("CONTRADICTORY_RADIUS",
                    f"circle_circle({c.out}): ты задал радиус |{center}{radius_point}|={ref}, "
                    f"но условие требует |{center}{c.out}|={desired}. "
                    f"Создай НОВУЮ служебную точку R с |{center}R|={desired} через perp_point, "
                    "затем используй её как точку радиуса; не используй второй центр как радиус.")

    # степени свободы: 2 на свободную точку, минус 3 на сдвиг+поворот
    n_free = sum(1 for c in plan.constructions if c.op == "free_point")
    dof = max(0, 2 * n_free - 3)
    n_eq = len(plan.constraints)
    if n_free and n_eq < dof:
        warn.append(f"UNDERDETERMINED: уравнений {n_eq} < степеней свободы {dof}")
    if n_eq > dof + 2:
        warn.append(f"OVERDETERMINED: уравнений {n_eq} при {dof} степенях свободы")

    # ссылочная целостность отрисовки
    draw_pairs = ("segments", "aux_segments", "lines", "rays", "aux_lines", "aux_rays",
                  "circles", "aux_circles")
    for name, items in ((n, getattr(plan.draw, n)) for n in draw_pairs):
        if not isinstance(items, list):
            raise PlanError("BAD_TYPE", f"draw.{name} должен быть списком")
        for it in items:
            if not isinstance(it, list) or len(it) != 2:
                raise PlanError("DRAW_ARITY", f"{name}: каждый элемент должен содержать 2 точки")
            for a in it:
                if not isinstance(a, str) or a not in known:
                    raise PlanError("DRAW_REF", f"{name}: неизвестная точка {a!r}")
    for name, items in (("right_angles", plan.draw.right_angles),):
        for it in items:
            if not isinstance(it, list) or len(it) != 3:
                raise PlanError("DRAW_ARITY", f"{name}: каждый элемент должен содержать 3 точки")
            for a in it:
                if not isinstance(a, str) or a not in known:
                    raise PlanError("DRAW_REF", f"{name}: неизвестная точка {a!r}")
    for p in plan.draw.aux_points + plan.draw.hide_labels:
        if not isinstance(p, str) or p not in known:
            raise PlanError("DRAW_REF", f"неизвестная точка {p!r}")
    for name, marks, arity in (("angle_marks", plan.draw.angle_marks, 3),
                               ("length_marks", plan.draw.length_marks, 2),
                               ("equal_marks", plan.draw.equal_marks, 2)):
        for m in marks:
            if not isinstance(m, dict) or not isinstance(m.get("pts"), list) or len(m["pts"]) != arity:
                raise PlanError("DRAW_ARITY", f"{name}: pts должен содержать {arity} точки")
            if any(not isinstance(p, str) or p not in known for p in m["pts"]):
                raise PlanError("DRAW_REF", f"{name}: ссылка на неизвестную точку")
            if "text" in m and not isinstance(m["text"], str):
                raise PlanError("BAD_MARK", f"{name}.text должен быть строкой")
            if name in ("angle_marks", "equal_marks"):
                count = m.get("count", 1)
                if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 3:
                    raise PlanError("BAD_MARK", f"{name}: count должен быть 1..3")
            if "layer" in m and m["layer"] not in ("main", "aux"):
                raise PlanError("BAD_MARK", f"{name}: layer должен быть main или aux")
            if name == "angle_marks" and "reflex" in m and not isinstance(m["reflex"], bool):
                raise PlanError("BAD_MARK", "angle_marks.reflex должен быть bool")
    for arc in plan.draw.arcs:
        if not isinstance(arc, dict) or not all(isinstance(arc.get(k), str) for k in ("center", "start", "end")):
            raise PlanError("BAD_MARK", "arcs требует center/start/end")
        if any(arc[k] not in known for k in ("center", "start", "end")):
            raise PlanError("DRAW_REF", "arcs: ссылка на неизвестную точку")
        if "reflex" in arc and not isinstance(arc["reflex"], bool):
            raise PlanError("BAD_MARK", "arcs.reflex должен быть bool")
        if "layer" in arc and arc["layer"] not in ("main", "aux"):
            raise PlanError("BAD_MARK", "arcs.layer должен быть main или aux")
    if not (plan.draw.segments or plan.draw.circles or plan.draw.lines or plan.draw.rays
            or any(a.get("layer", "main") == "main" for a in plan.draw.arcs)):
        warn.append("EMPTY_DRAW: нечего рисовать в основном слое")

    if plan.target.kind not in TARGETS:
        raise PlanError("UNKNOWN_TARGET", f"цель {plan.target.kind!r} не поддерживается")
    if len(plan.target.args) != TARGETS[plan.target.kind]:
        raise PlanError("ARITY", f"цель {plan.target.kind} ждёт {TARGETS[plan.target.kind]} точек")
    for a in plan.target.args:
        if a not in known:
            raise PlanError("TARGET_REF", f"цель ссылается на неизвестную точку {a!r}")

    return warn


def plan_json_schema() -> str:
    """Компактное описание схемы для промпта LLM (кэшируемая статика)."""
    cons = "\n".join(
        f"  {op}(out, {spec['args']} точк{'и' if spec['args'] != 1 else 'а'}"
        + (", value" if spec.get("value") else "") + ") — " + spec["doc"]
        for op, spec in CONSTRUCTIONS.items())
    cstr = "\n".join(
        f"  {t}({spec['pts']} точек" + (", value" if spec["value"] else "") + ") — " + spec["doc"]
        for t, spec in CONSTRAINTS.items())
    draw = (
        "DRAW: segments,lines,rays,aux_segments,aux_lines,aux_rays,circles,aux_circles"
        " — списки пар точек; aux_points/hide_labels — списки имён; "
        "right_angles — тройки [A,B,C] с вершиной B; "
        "angle_marks=[{pts:[A,B,C],text:'60°',reflex:false,count:1,layer:'main'}]; "
        "length_marks=[{pts:[A,B],text:'6',layer:'main'}]; "
        "equal_marks=[{pts:[A,B],count:1,layer:'main'}]; "
        "arcs=[{center:O,start:A,end:B,reflex:false,layer:'main'}]. "
        "count=1..3; layer='main'|'aux'. reflex выбирает большой угол/большую дугу. "
        "Одинаковый count в equal_marks означает равные длины; явно указанный count "
        "в angle_marks означает равные углы. Для обычной угловой подписи count опускай. "
        "Вспомогательный слой может быть пуст, если дополнительные построения не нужны."
    )
    return f"КОНСТРУКЦИИ:\n{cons}\n\nОГРАНИЧЕНИЯ:\n{cstr}\n\nЦЕЛИ: {', '.join(TARGETS)}\n\n{draw}"


if __name__ == "__main__":
    print(plan_json_schema())
    print(f"\nвсего: {len(CONSTRUCTIONS)} конструкций, {len(CONSTRAINTS)} ограничений")
