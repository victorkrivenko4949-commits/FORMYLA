"""Validated, deterministic solid geometry; independent of the 2-D solver.

Only :func:`scene_schema_prompt` and :func:`build_scene` are public. Coordinates
are ordinary JSON-compatible lists, not projected coordinates. No dependencies
other than the standard library and the shared ``schema.PlanError``.
"""
from __future__ import annotations

import math
import re
from html import escape
from typing import Any

from .schema import PlanError

__all__ = ["scene_schema_prompt", "build_scene"]

Vec = tuple[float, float, float]
_EPS = 1e-12
# A fixed non-symmetric orthographic view avoids collapsing a cube's opposite
# vertices, which exact isometry necessarily does for a body diagonal.
_AZIMUTH, _ELEVATION = math.radians(33), math.radians(22)
_VIEW: Vec = (math.cos(_ELEVATION) * math.cos(_AZIMUTH),
              -math.cos(_ELEVATION) * math.sin(_AZIMUTH), math.sin(_ELEVATION))
_RIGHT: Vec = (math.sin(_AZIMUTH), math.cos(_AZIMUTH), 0.0)
_DOWN: Vec = (math.sin(_ELEVATION) * math.cos(_AZIMUTH),
              -math.sin(_ELEVATION) * math.sin(_AZIMUTH), -math.cos(_ELEVATION))
_PROJECTION_NOTE = (
    "Ортографическая аксонометрическая проекция: длины и углы на экране "
    "не равны пространственным; измерения вычислены по координатам 3D."
)
_DIMENSIONS = {
    "cube": ("side",),
    "cuboid": ("a", "b", "c"),
    "regular_prism": ("n", "side", "height"),
    "regular_pyramid": ("n", "side", "height"),
    "tetrahedron": ("side",),
    "cylinder": ("radius", "height"),
    "cone": ("radius", "height"),
    "sphere": ("radius",),
}
_OPS = {"midpoint": 2, "divide_segment": 2, "foot": 3,
        "translate": 3, "line_plane_intersection": 5}
_TARGETS = {"none": 0, "dist": 2, "angle": 3, "line_angle": 4,
            "line_plane_angle": 5}


def scene_schema_prompt() -> str:
    """The complete model-facing JSON contract (no invented coordinates)."""
    return r"""СТЕРЕОМЕТРИЯ: верни только JSON, не задавай координаты.
{
  "space":"space",
  "solid":{"kind":"cube","side":1},
  "constructions":[],
  "draw":{"segments":[],"aux_segments":[],"aux_points":[],"right_angles":[],
          "length_marks":[],"hide_labels":[]},
  "target":{"kind":"none","args":[]},
  "notes":""
}
Обязательны space и solid.kind и ВСЕ размеры выбранного тела. Размеры не
подставляются по умолчанию: если условие не определяет тело, откажись, не
подменяй его кубом. Числа конечные JSON numbers (не bool и не строки).
Каждый размер в [1e-9,1e9], отношение наибольшего к наименьшему <=1e9.
Единицы всех длин одинаковы; углы результата в градусах.
Неизвестные поля/тела/операции запрещены. Никаких points, coords, constraints,
произвольных многогранников, косых призм, усечений или сечений.

ТЕЛА (размеры обязательны, вершины вычисляет движок):
cube: side; cuboid: a,b,c.
  ABCD — нижняя грань: A=(0,0,0), B=(a,0,0), C=(a,b,0), D=(0,b,0).
  A1,B1,C1,D1 — соответствующие верхние вершины на высоте c.
  Для куба a=b=c=side. O — центр нижней грани, O1 — верхней.
regular_prism: n,side,height. Прямая призма с правильным n-угольником.
regular_pyramid: n,side,height. Вершина S над центром правильного основания.
  n — целое от 3 до 12, side — СТОРОНА основания (не радиус).
  Основание в z=0, центр O=(0,0,0); вершины A,B,C,... (первые n букв
  ABCDEFGHIJKL) против часовой стрелки при взгляде с +z.
  A=(R,0,0), R=side/(2*sin(pi/n)).
  Призма: A1,B1,... над A,B,... на высоте height, O1=(0,0,height).
  Пирамида: S=(0,0,height).
tetrahedron: side. Только ПРАВИЛЬНЫЙ тетраэдр.
  ABC — правильный треугольник как выше (n=3), O — его центр;
  D=(0,0,side*sqrt(2/3)) — вершина; все шесть рёбер равны side.
cylinder: radius,height. O=(0,0,0), O1=(0,0,height).
  A=(radius,0,0), B=(0,radius,0), C=(-radius,0,0), D=(0,-radius,0);
  A1,B1,C1,D1 — над ними на верхнем круге.
cone: radius,height. O=(0,0,0), S=(0,0,height);
  A,B,C,D — те же четыре точки нижнего круга.
sphere: radius. O=(0,0,0); X=(radius,0,0), Y=(0,radius,0),
  Z=(0,0,radius), Xn=(-radius,0,0), Yn=(0,-radius,0), Zn=(0,0,-radius).
solid.names (необязательный объект): переименование СТАНДАРТНЫХ имён,
  например {"A":"P","A1":"P1"}; остальные остаются прежними.
  Итоговые имена уникальны; ссылки используют уже переименованные имена.
  Имя: 1–24 символа, первый — буква Unicode, далее буквы/цифры,
  "_" или штрихи ' ′ ″. Никаких XML/HTML. Тексты меток экранируются.

ПОСТРОЕНИЯ выполняются по порядку: {"op":...,"out":"M","args":[...]}.
out — новое уникальное имя; args — только уже известные точки.
midpoint [A,B]: (A+B)/2.
divide_segment [A,B], value: t, 0<=t<=1: A+t*(B-A), AP:PB=t:(1-t).
foot [A,B,C]: основание из A на БЕСКОНЕЧНУЮ прямую BC в пространстве.
translate [A,B,C]: A+(C-B).
line_plane_intersection [A,B,C,D,E]: пересечение бесконечной прямой AB
  и плоскости CDE; параллельность, прямая в плоскости, коллинеарные CDE
  и нулевые направляющие — ошибка, не произвольная точка.
value допустимо только у divide_segment. Вырожденные направления запрещены.

РИСОВАНИЕ: рёбра/очертания тела рисуются автоматически; скрытые рёбра
выпуклых многогранников определяются видимостью граней и идут пунктиром.
draw.segments: [[A,B],...] — дополнительные чёрные отрезки.
draw.aux_segments: [[A,M],...] — синие пунктирные вспомогательные отрезки.
draw.aux_points: ["H",...] — ЯВНО объявленные дополнительные вспомогательные
  точки. Все построенные точки по умолчанию ОСНОВНЫЕ: данная в условии
  середина M/N не исчезает при show_aux=False.
  aux_points могут быть построенными точками или центрами, но не вершинами
  исходного тела; точка не может одновременно быть в aux_points и segments.
draw.right_angles: [[A,B,C],...] — угол ABC ОБЯЗАН быть прямым в 3D;
  знак строится в плоскости пространственных лучей и затем проецируется,
  поэтому на экране не обязательно выглядит квадратом.
draw.length_marks: [{"pts":[A,B],"text":"a"}] — подписи длин.
  Числовые литералы, дроби p/q и корни sqrt(3), √3, 2√3 проверяются
  по ИСТИННОЙ длине в 3D (относительный допуск 1e-6), иначе ошибка.
  Символические подписи вроде a или x допустимы без проверки их значения.
draw.hide_labels: ["O",...] — скрыть подписи, но не геометрию.
Служебные центры O/O1 по умолчанию вспомогательные.
  ЯВНОЕ использование центра в draw.segments переводит его в основной слой:
  запрошенная ось/высота/отрезок не исчезает при show_aux=False.
  show_aux=False убирает остальные вспомогательные точки/подписи,
  aux_segments и метки, ссылающиеся на скрытые вспомогательные точки,
  но НЕ убирает точки из coords и измерений.
show_aux=True рисует вспомогательные точки и подписи синим.
Отрезки draw.segments — пользовательские линии, без автоматической
проверки их перекрытия телом; для вспомогательных используй aux_segments.
Кривые тел вращения аппроксимируются полилиниями, не гранями многогранника.
Проекция ортографическая аксонометрическая (фиксированный несимметричный
ракурс, азимут -33°, высота 22°); экранные длины и углы НЕ пространственные.

ЦЕЛЬ {"kind":...,"args":[...]}:
none [] -> null;
dist [A,B] -> расстояние AB в 3D;
angle [A,B,C] -> угол ABC при B, 0..180 градусов;
line_angle [A,B,C,D] -> меньший угол бесконечных прямых AB и CD,
  0..90 градусов, в том числе скрещивающихся;
line_plane_angle [A,B,C,D,E] -> угол прямой AB с плоскостью CDE,
  0..90 градусов. Коллинеарные точки плоскости запрещены.

Необязательные конструкции и все списки draw по умолчанию пусты,
target по умолчанию {"kind":"none","args":[]}, notes по умолчанию "".
notes — строка до 4000 символов, не HTML. Не более 256 построений
и 512 элементов в каждом списке рисования.
build_scene(data,show_aux=True,width=700): width — целое 240..2400.
Результат: {"svg":строка,"coords":{имя:[x,y,z]},"measured":число|null,
  "warnings":[строки],"notes":строка с исходным notes и пояснением проекции}.
"""


def _fail(code: str, message: str) -> None:
    raise PlanError(code, message)


def _object(value: Any, allowed: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        _fail("BAD_ITEM", f"{where}: ожидался объект")
    if any(not isinstance(k, str) for k in value):
        _fail("BAD_FIELD", f"{where}: ключи должны быть строками")
    extra = set(value) - allowed
    if extra:
        _fail("UNKNOWN_FIELD", f"{where}: неизвестные поля {sorted(extra)}")
    return value


def _list(value: Any, where: str, limit: int = 512) -> list:
    if not isinstance(value, list) or len(value) > limit:
        _fail("BAD_LIST", f"{where}: требуется список длиной не более {limit}")
    return value


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("BAD_NUMBER", f"{where}: требуется конечное число")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        _fail("BAD_NUMBER", f"{where}: число вне допустимого диапазона")
    if not math.isfinite(number):
        _fail("BAD_NUMBER", f"{where}: требуется конечное число")
    return number


def _name(value: Any) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 24
            or not value[0].isalpha()
            or any(not (c.isalnum() or c in "_'′″") for c in value)):
        _fail("BAD_NAME", "имя точки: буква, затем буквы/цифры/_/штрихи, до 24 символов")
    return value


def _text(value: Any, where: str, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit:
        _fail("BAD_TEXT", f"{where}: требуется строка до {limit} символов")
    # XML 1.0 characters, including exclusion of surrogate code points.
    if any(not (c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF
                or 0xE000 <= ord(c) <= 0xFFFD
                or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        _fail("BAD_TEXT", f"{where}: недопустимый символ XML")
    return value


def _length_value(text: str) -> float | None:
    """Parse small numeric labels safely; symbolic text has no numeric claim."""
    text = text.strip().replace("−", "-").replace(",", ".")
    atom = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    try:
        value = float(text)
    except ValueError:
        fraction = re.fullmatch(rf"({atom})\s*/\s*({atom})", text)
        root = re.fullmatch(rf"({atom})?\s*(?:√\s*({atom})|sqrt\(\s*({atom})\s*\))", text)
        if fraction:
            denominator = float(fraction[2])
            if denominator == 0:
                _fail("BAD_MARK", "нулевой знаменатель числовой подписи")
            value = float(fraction[1]) / denominator
        elif root:
            radicand = float(root[2] if root[2] is not None else root[3])
            if radicand < 0:
                _fail("BAD_MARK", "отрицательное подкоренное выражение подписи")
            value = float(root[1] or 1) * math.sqrt(radicand)
        else:
            return None
    if not math.isfinite(value):
        _fail("BAD_MARK", "числовая подпись должна быть конечной")
    return value


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec, t: float) -> Vec:
    return (a[0] * t, a[1] * t, a[2] * t)


def _dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec, tolerance: float = 0.0) -> Vec:
    length = math.hypot(*a)
    if not math.isfinite(length) or length <= tolerance:
        _fail("DEGENERATE", "нулевое или численно вырожденное направление")
    return _mul(a, 1 / length)


def _normal(a: Vec, b: Vec, c: Vec, tolerance: float) -> Vec:
    return _unit(_cross(_unit(_sub(b, a), tolerance),
                        _unit(_sub(c, a), tolerance)), _EPS)


def _finite_point(point: Vec) -> Vec:
    if any(not math.isfinite(x) or abs(x) > 1e100 for x in point):
        _fail("BAD_COORDINATE", "построение вышло за численный диапазон координат")
    return point


def _refs(value: Any, count: int, points: dict[str, Vec], where: str) -> list[str]:
    refs = _list(value, where)
    if len(refs) != count:
        _fail("ARITY", f"{where}: требуется {count} точек")
    for name in refs:
        _name(name)
        if name not in points:
            _fail("UNKNOWN_REF", f"{where}: неизвестная точка {name!r}")
    return refs


def _solid(spec: Any) -> tuple[dict[str, Vec], list[list[str]],
                               list[tuple[list[Vec], bool]], set[str], float, str]:
    """Return analytic points, faces, curves, auxiliary names, scale, kind."""
    if not isinstance(spec, dict):
        _fail("BAD_ITEM", "solid: ожидался объект")
    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in _DIMENSIONS:
        _fail("UNSUPPORTED_SOLID", f"неподдерживаемое тело {kind!r}")
    _object(spec, {"kind", "names", *_DIMENSIONS[kind]}, "solid")
    dims: dict[str, float] = {}
    n = 0
    for key in _DIMENSIONS[kind]:
        if key not in spec:
            _fail("MISSING_DIMENSION", f"{kind}: требуется {key}")
        if key == "n":
            if isinstance(spec[key], bool) or not isinstance(spec[key], int) or not 3 <= spec[key] <= 12:
                _fail("BAD_DIMENSION", "n: требуется целое от 3 до 12")
            n = spec[key]
        else:
            dims[key] = _number(spec[key], f"solid.{key}")
            if not 1e-9 <= dims[key] <= 1e9:
                _fail("BAD_DIMENSION", f"{key}: размер должен быть в [1e-9,1e9]")
    if max(dims.values()) / min(dims.values()) > 1e9:
        _fail("DEGENERATE", "отношение размеров превышает 1e9")
    points: dict[str, Vec] = {}
    faces: list[list[str]] = []
    curves: list[tuple[list[Vec], bool]] = []
    aux: set[str] = set()
    scale = max(dims.values())

    if kind in ("cube", "cuboid"):
        a, b, c = ((dims["side"],) * 3 if kind == "cube"
                   else (dims["a"], dims["b"], dims["c"]))
        base = ["A", "B", "C", "D"]
        points.update(zip(base, [(0., 0., 0.), (a, 0., 0.), (a, b, 0.), (0., b, 0.)]))
        points.update({p + "1": _add(points[p], (0., 0., c)) for p in base})
        points.update(O=(a / 2, b / 2, 0.), O1=(a / 2, b / 2, c))
        aux.update(("O", "O1"))
        faces = [base, [p + "1" for p in base]]
        faces += [[base[i], base[(i + 1) % 4], base[(i + 1) % 4] + "1", base[i] + "1"]
                  for i in range(4)]
    elif kind in ("regular_prism", "regular_pyramid", "tetrahedron"):
        if kind == "tetrahedron":
            n = 3
        radius = dims["side"] / (2 * math.sin(math.pi / n))
        height = (dims["side"] * math.sqrt(2 / 3) if kind == "tetrahedron"
                  else dims["height"])
        base = list("ABCDEFGHIJKL"[:n])
        points.update({p: (radius * math.cos(2 * math.pi * i / n),
                            radius * math.sin(2 * math.pi * i / n), 0.)
                       for i, p in enumerate(base)})
        points["O"] = (0., 0., 0.)
        aux.add("O")
        faces = [base]
        scale = max(radius, height, scale)
        if kind == "regular_prism":
            points.update({p + "1": _add(points[p], (0., 0., height)) for p in base})
            points["O1"] = (0., 0., height)
            aux.add("O1")
            faces.append([p + "1" for p in base])
            faces += [[base[i], base[(i + 1) % n], base[(i + 1) % n] + "1", base[i] + "1"]
                      for i in range(n)]
        else:
            apex = "D" if kind == "tetrahedron" else "S"
            points[apex] = (0., 0., height)
            faces += [[base[i], base[(i + 1) % n], apex] for i in range(n)]
    else:
        radius = dims["radius"]
        points["O"] = (0., 0., 0.)
        aux.add("O")
        steps = 144

        def circle(z: float) -> list[Vec]:
            return [(radius * math.cos(2 * math.pi * i / steps),
                     radius * math.sin(2 * math.pi * i / steps), z)
                    for i in range(steps + 1)]

        def split_ring(ring: list[Vec], hidden) -> None:
            # Classify short arc intervals, then join equal visibility runs.
            for a, b in zip(ring, ring[1:]):
                hidden_arc = bool(hidden(_mul(_add(a, b), .5)))
                if curves and curves[-1][1] == hidden_arc and curves[-1][0][-1] == a:
                    curves[-1][0].append(b)
                else:
                    curves.append(([a, b], hidden_arc))

        if kind == "sphere":
            points.update(X=(radius, 0., 0.), Y=(0., radius, 0.), Z=(0., 0., radius),
                          Xn=(-radius, 0., 0.), Yn=(0., -radius, 0.), Zn=(0., 0., -radius))
            curves.append(([_add(_mul(_RIGHT, radius * math.cos(2 * math.pi * i / steps)),
                                  _mul(_DOWN, radius * math.sin(2 * math.pi * i / steps)))
                            for i in range(steps + 1)], False))
            split_ring(circle(0.), lambda p: _dot(p, _VIEW) < 0)
        else:
            height = dims["height"]
            points.update(A=(radius, 0., 0.), B=(0., radius, 0.),
                          C=(-radius, 0., 0.), D=(0., -radius, 0.))
            if kind == "cylinder":
                points["O1"] = (0., 0., height)
                aux.add("O1")
                points.update({p + "1": _add(points[p], (0., 0., height)) for p in "ABCD"})
                split_ring(circle(0.), lambda p: p[0] * _VIEW[0] + p[1] * _VIEW[1] < 0)
                curves.append((circle(height), False))
                azimuth = math.atan2(_VIEW[1], _VIEW[0])
                for theta in (azimuth - math.pi / 2, azimuth + math.pi / 2):
                    p = (radius * math.cos(theta), radius * math.sin(theta), 0.)
                    curves.append(([p, _add(p, (0., 0., height))], False))
            else:
                points["S"] = (0., 0., height)
                split_ring(circle(0.), lambda p: height * (
                    p[0] * _VIEW[0] + p[1] * _VIEW[1]) + radius * radius * _VIEW[2] < 0)
                ratio = -radius * _VIEW[2] / (height * math.hypot(*_VIEW[:2]))
                if ratio > -1:
                    theta = math.acos(ratio)
                    azimuth = math.atan2(_VIEW[1], _VIEW[0])
                    for t in (azimuth - theta, azimuth + theta):
                        curves.append(([(radius * math.cos(t), radius * math.sin(t), 0.),
                                        points["S"]], False))
    names = spec.get("names", {})
    _object(names, set(points), "solid.names")
    renamed = {p: _name(names.get(p, p)) for p in points}
    if len(set(renamed.values())) != len(points):
        _fail("DUPLICATE_POINTS", "solid.names: итоговые имена повторяются")
    points = {renamed[p]: _finite_point(v) for p, v in points.items()}
    return points, [[renamed[p] for p in face] for face in faces], curves, {
        renamed[p] for p in aux}, scale, kind


def _construct(items: Any, points: dict[str, Vec], tol: float) -> None:
    for i, raw in enumerate(_list(items, "constructions", 256)):
        item = _object(raw, {"op", "out", "args", "value"}, f"constructions[{i}]")
        op = item.get("op")
        if not isinstance(op, str) or op not in _OPS:
            _fail("UNKNOWN_CONSTRUCTION", f"неизвестная конструкция {op!r}")
        name = _name(item.get("out"))
        if name in points:
            _fail("REDEFINED_POINT", f"точка {name!r} уже определена")
        refs = _refs(item.get("args", []), _OPS[op], points, op)
        p = [points[r] for r in refs]
        if op != "divide_segment" and "value" in item:
            _fail("UNKNOWN_FIELD", f"{op}: value не используется")
        if op in ("midpoint", "divide_segment"):
            delta = _sub(p[1], p[0])
            _unit(delta, tol)
            t = .5 if op == "midpoint" else _number(item.get("value"), "value")
            if not 0 <= t <= 1:
                _fail("BAD_VALUE", "divide_segment: value должен быть в [0,1]")
            result = _add(_mul(p[0], 1 - t), _mul(p[1], t))
        elif op == "translate":
            delta = _sub(p[2], p[1])
            _unit(delta, tol)
            result = _add(p[0], delta)
        elif op == "foot":
            u = _unit(_sub(p[2], p[1]), tol)
            result = _add(p[1], _mul(u, _dot(_sub(p[0], p[1]), u)))
        else:
            u = _unit(_sub(p[1], p[0]), tol)
            normal = _normal(p[2], p[3], p[4], tol)
            denominator = _dot(u, normal)
            if abs(denominator) <= _EPS:
                _fail("DEGENERATE", "прямая параллельна плоскости или лежит в ней")
            result = _add(p[0], _mul(u, _dot(_sub(p[2], p[0]), normal) / denominator))
        points[name] = _finite_point(result)


def _measure(target: Any, points: dict[str, Vec], tol: float) -> float | None:
    target = _object(target, {"kind", "args"}, "target")
    kind = target.get("kind", "none")
    if not isinstance(kind, str) or kind not in _TARGETS:
        _fail("UNKNOWN_TARGET", f"неизвестная цель {kind!r}")
    refs = _refs(target.get("args", []), _TARGETS[kind], points, "target")
    p = [points[r] for r in refs]
    if kind == "none":
        return None
    if kind == "dist":
        return math.dist(p[0], p[1])
    if kind == "angle":
        u, v = _unit(_sub(p[0], p[1]), tol), _unit(_sub(p[2], p[1]), tol)
        return math.degrees(math.atan2(math.hypot(*_cross(u, v)), _dot(u, v)))
    u = _unit(_sub(p[1], p[0]), tol)
    if kind == "line_angle":
        v = _unit(_sub(p[3], p[2]), tol)
        return math.degrees(math.atan2(math.hypot(*_cross(u, v)), abs(_dot(u, v))))
    normal = _normal(p[2], p[3], p[4], tol)
    return math.degrees(math.atan2(abs(_dot(u, normal)), math.hypot(*_cross(u, normal))))


def _draw_spec(raw: Any, points: dict[str, Vec], tol: float) -> dict:
    raw = _object(raw, {"segments", "aux_segments", "aux_points", "right_angles",
                        "length_marks", "hide_labels"}, "draw")
    result: dict[str, list] = {}
    for key, arity in (("segments", 2), ("aux_segments", 2), ("right_angles", 3)):
        result[key] = [_refs(item, arity, points, f"draw.{key}")
                       for item in _list(raw.get(key, []), f"draw.{key}")]
        for refs in result[key]:
            p = [points[r] for r in refs]
            if arity == 2:
                _unit(_sub(p[1], p[0]), tol)
            else:
                u, v = _unit(_sub(p[0], p[1]), tol), _unit(_sub(p[2], p[1]), tol)
                if abs(_dot(u, v)) > 1e-9:
                    _fail("NOT_RIGHT_ANGLE", f"угол {refs} не прямой в 3D")
    for key in ("hide_labels", "aux_points"):
        result[key] = []
        for name in _list(raw.get(key, []), f"draw.{key}"):
            result[key].extend(_refs([name], 1, points, f"draw.{key}"))
    result["length_marks"] = []
    for item in _list(raw.get("length_marks", []), "draw.length_marks"):
        item = _object(item, {"pts", "text"}, "length_mark")
        refs = _refs(item.get("pts", []), 2, points, "length_mark")
        _unit(_sub(points[refs[1]], points[refs[0]]), tol)
        text = _text(item.get("text"), "length_mark.text", 120)
        value = _length_value(text)
        actual = math.dist(points[refs[0]], points[refs[1]])
        if value is not None and not math.isclose(value, actual, rel_tol=1e-6, abs_tol=tol * 10):
            _fail("FALSE_LENGTH_MARK", f"подпись {text!r} не равна длине {refs} в 3D: {actual:g}")
        result["length_marks"].append({"pts": refs, "text": text})
    return result


def _edges(points: dict[str, Vec], faces: list[list[str]]) -> list[tuple[str, str, bool]]:
    """An edge is hidden iff all its incident outward faces face away."""
    if not faces:
        return []
    vertices = sorted({p for face in faces for p in face})
    center = tuple(sum(points[p][i] / len(vertices) for p in vertices) for i in range(3))
    visible_by_edge: dict[tuple[str, str], bool] = {}
    for face in faces:
        a, b, c = (points[p] for p in face[:3])
        normal = _normal(a, b, c, 0.)
        face_center = tuple(sum(points[p][i] / len(face) for p in face) for i in range(3))
        if _dot(normal, _sub(face_center, center)) < 0:
            normal = _mul(normal, -1)
        visible = _dot(normal, _VIEW) >= -_EPS
        for a_name, b_name in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((a_name, b_name)))
            visible_by_edge[key] = visible_by_edge.get(key, False) or visible
    return [(a, b, not visible) for (a, b), visible in visible_by_edge.items()]


def _project(p: Vec) -> tuple[float, float]:
    return _dot(p, _RIGHT), _dot(p, _DOWN)


def _render(points: dict[str, Vec], faces: list[list[str]],
            curves: list[tuple[list[Vec], bool]], aux: set[str], draw: dict,
            show_aux: bool, width: int, scale: float, notes: str,
            warnings: list[str]) -> str:
    displayed = {p: v for p, v in points.items() if show_aux or p not in aux}
    samples = list(displayed.values()) + [p for curve, _ in curves for p in curve]
    projection = [_project(p) for p in samples]
    xmin, xmax = min(p[0] for p in projection), max(p[0] for p in projection)
    ymin, ymax = min(p[1] for p in projection), max(p[1] for p in projection)
    span = max(xmax - xmin, ymax - ymin)
    if not math.isfinite(span) or span <= 0:
        _fail("DEGENERATE", "вырожденная проекция")
    height = width
    margin = max(40., width * .10)
    factor = (width - 2 * margin) / span
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    def screen(point: Vec) -> tuple[float, float]:
        x, y = _project(point)
        return width / 2 + (x - cx) * factor, height / 2 + (y - cy) * factor

    def xy(point: Vec) -> str:
        x, y = screen(point)
        return f"{x:.3f},{y:.3f}"

    def line(a: str, b: str, cls: str, hidden: bool = False) -> str:
        p, q = screen(points[a]), screen(points[b])
        return (f'<line class="{cls}" data-a="{escape(a, quote=True)}" '
                f'data-b="{escape(b, quote=True)}" data-hidden="{str(hidden).lower()}" '
                f'x1="{p[0]:.3f}" y1="{p[1]:.3f}" x2="{q[0]:.3f}" y2="{q[1]:.3f}"/>')

    edges = _edges(points, faces)
    main = [line(a, b, "edge hidden" if hidden else "edge", hidden)
            for a, b, hidden in sorted(edges, key=lambda e: not e[2])]
    main.extend(f'<polyline class="outline{" hidden" if hidden else ""}" '
                f'data-hidden="{str(hidden).lower()}" points="{" ".join(xy(p) for p in curve)}"/>'
                for curve, hidden in sorted(curves, key=lambda e: not e[1]))
    main.extend(line(a, b, "segment") for a, b in draw["segments"]
                if a in displayed and b in displayed)
    aux_lines = ([line(a, b, "aux-segment") for a, b in draw["aux_segments"]]
                 if show_aux else [])
    marks: list[str] = []
    for a, b, c in draw["right_angles"]:
        if any(p not in displayed for p in (a, b, c)):
            continue
        u, v = _sub(points[a], points[b]), _sub(points[c], points[b])
        step = min(scale * .09, math.hypot(*u) * .2, math.hypot(*v) * .2)
        u, v = _mul(_unit(u), step), _mul(_unit(v), step)
        corners = [_add(points[b], u), _add(_add(points[b], u), v), _add(points[b], v)]
        cls = "right-angle aux-mark" if any(p in aux for p in (a, b, c)) else "right-angle"
        marks.append(f'<polyline class="{cls}" data-angle-deg="90" '
                     f'points="{" ".join(xy(p) for p in corners)}"/>')
    for item in draw["length_marks"]:
        a, b = item["pts"]
        if a not in displayed or b not in displayed:
            continue
        x, y = screen(_mul(_add(points[a], points[b]), .5))
        cls = "length-mark aux-label" if a in aux or b in aux else "length-mark"
        marks.append(f'<text class="{cls}" x="{x:.3f}" y="{y - 8:.3f}">'
                     f'{escape(item["text"])}</text>')

    dots: list[str] = []
    labels: list[str] = []
    occupied: list[tuple[float, float, float, float]] = []
    previous: list[tuple[str, float, float]] = []
    hidden_labels = set(draw["hide_labels"])
    # Main labels get priority; a projected overlap never alters 3-D geometry.
    for name in sorted(displayed, key=lambda p: (p in aux, p)):
        x, y = screen(points[name])
        escaped = escape(name, quote=True)
        cls = "point aux-point" if name in aux else "point"
        dots.append(f'<circle class="{cls}" data-point="{escaped}" '
                    f'cx="{x:.3f}" cy="{y:.3f}" r="2.8"/>')
        if name in hidden_labels:
            continue
        for other, ox, oy in previous:
            if math.hypot(x - ox, y - oy) < 1:
                warnings.append(f"PROJECTED_OVERLAP: {other} и {name} совпадают на проекции, не обязательно в 3D.")
                break
        previous.append((name, x, y))
        w = max(12., len(name) * 8.)
        choices = [(10., -10.), (-w - 10., -10.), (10., 22.), (-w - 10., 22.),
                   (-w / 2, -22.), (-w / 2, 34.), (20., 7.), (-w - 20., 7.)]
        best = None
        for dx, dy in choices:
            tx = min(max(6., x + dx), width - w - 6.)
            ty = min(max(20., y + dy), height - 8.)
            rect = (tx, ty - 16., tx + w, ty + 3.)
            collisions = sum(not (rect[2] < r[0] or r[2] < rect[0]
                                  or rect[3] < r[1] or r[3] < rect[1]) for r in occupied)
            candidate = (collisions, tx, ty, rect)
            if best is None or collisions < best[0]:
                best = candidate
            if collisions == 0:
                break
        _, tx, ty, rect = best
        occupied.append(rect)
        cls = "point-label aux-label" if name in aux else "point-label"
        labels.append(f'<text class="{cls}" data-label="{escaped}" '
                      f'x="{tx:.3f}" y="{ty:.3f}">{escape(name)}</text>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="space3d-title space3d-desc">'
        '<title id="space3d-title">Стереометрия — ортографическая проекция</title>'
        f'<desc id="space3d-desc">{escape(notes)}</desc>'
        '<style>'
        '.edge,.outline,.segment,.right-angle{fill:none;stroke:#111111;stroke-width:1.8;'
        'stroke-linejoin:round;stroke-linecap:round}'
        '.hidden{stroke-dasharray:6 5;stroke-width:1.3;stroke:#667085}'
        '.aux-segment{fill:none;stroke:#1f6feb;stroke-width:1.6;stroke-dasharray:7 5}'
        '.point{fill:#111111}.aux-point{fill:#1f6feb}'
        '.point-label,.length-mark{font-family:Georgia,serif;font-style:italic;'
        'font-size:16px;fill:#111111}'
        '.length-mark{font-size:14px;text-anchor:middle}'
        '.aux-label{fill:#1f6feb}.aux-mark{stroke:#1f6feb}'
        '</style><rect width="100%" height="100%" fill="white"/>'
        f'<g id="main">{"".join(main)}</g><g id="aux">{"".join(aux_lines)}</g>'
        f'<g id="marks">{"".join(marks)}</g><g id="points">{"".join(dots)}</g>'
        f'<g id="labels">{"".join(labels)}</g></svg>'
    )


def build_scene(data: dict, show_aux: bool = True, width: int = 700) -> dict:
    """Validate, analytically build, measure in 3-D, then project to SVG.

    Invalid or unsupported input raises the shared :class:`schema.PlanError`.
    The input is never mutated; hiding auxiliary geometry changes only the SVG.
    """
    data = _object(data, {"space", "solid", "constructions", "draw", "target", "notes"}, "plan")
    if data.get("space") != "space":
        _fail("UNSUPPORTED_SPACE", '3D-план требует space="space"')
    if not isinstance(show_aux, bool):
        _fail("BAD_OPTION", "show_aux должен быть bool")
    if isinstance(width, bool) or not isinstance(width, int) or not 240 <= width <= 2400:
        _fail("BAD_OPTION", "width должен быть целым от 240 до 2400")
    notes = _text(data.get("notes", ""), "notes", 4000)
    points, faces, curves, aux, scale, kind = _solid(data.get("solid"))
    vertices = set(points) - aux
    _construct(data.get("constructions", []), points, scale * _EPS)
    draw = _draw_spec(data.get("draw", {}), points, scale * _EPS)
    declared_aux = set(draw["aux_points"])
    main_refs = {p for segment in draw["segments"] for p in segment}
    if declared_aux & vertices:
        _fail("BAD_AUX_POINT", "вершина исходного тела не может быть вспомогательной")
    if declared_aux & main_refs:
        _fail("AMBIGUOUS_LAYER", "точка одновременно в draw.aux_points и draw.segments")
    # Explicit main geometry must not silently disappear with the auxiliary
    # toggle (e.g. SO of a pyramid, or the axis OO1 of a cylinder).
    aux = (aux - main_refs) | declared_aux
    measured = _measure(data.get("target", {}), points, scale * _EPS)
    warnings: list[str] = []
    notes = (notes + "\n" if notes else "") + _PROJECTION_NOTE
    if kind in ("cylinder", "cone", "sphere"):
        note = "Круговые очертания аппроксимированы полилиниями; экранные эллипсы не задают пространственные углы."
        notes += "\n" + note
        warnings.append("CURVE_APPROXIMATION: " + note)
    svg = _render(points, faces, curves, aux, draw, show_aux, width, scale, notes, warnings)
    return {"svg": svg, "coords": {p: list(v) for p, v in points.items()},
            "measured": measured, "warnings": warnings, "notes": notes}
