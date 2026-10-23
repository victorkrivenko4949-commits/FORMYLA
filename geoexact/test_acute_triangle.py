# -*- coding: utf-8 -*-
"""Качественные условия чертежа: острота, антипод, принадлежность отрезку.

Прод-сценарий (задача 2, живая генерация 23.10.2026): «Дан острый
треугольник ABC. На его описанной окружности точка D диаметрально
противоположна A. Точки X и Y на стороне BC таковы, что BX = XD и
CY = YD (X лежит на отрезке BY)». Формализатор потерял остроту — солвер
выдал прямоугольный треугольник (угол B = 90°), антипод A совпал с C,
и чертёж выродился. Здесь: верная конфигурация проходит все проверки,
вырожденная — бракуется с указанием конкретной нарушенной фразы.
"""
from unittest.mock import patch

from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.acute_triangle import (
    acute_failures, antipode_failures, between_failures, order_failures)
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.gates import rank_solutions

PROBLEM = ("Задача 2. Дан остроугольный треугольник \\(ABC\\). На его описанной окружности "
           "отмечена точка \\(D\\), диаметрально противоположная вершине \\(A\\). "
           "Точки \\(X\\) и \\(Y\\) на стороне \\(BC\\) таковы, что \\(BX = XD\\) и "
           "\\(CY = YD\\) (точка \\(X\\) лежит на отрезке \\(BY\\)). Докажите, что "
           "\\(DA\\) — биссектриса угла \\(XDY\\).")

# Контрфигурация советника: B=(0,0), C=(6,0), A=(2,4), O=(3,1), D=(4,-2),
# X=(5/2,0), Y=(4,0): треугольник острый, D — антипод A, BX=XD=5/2,
# CY=YD=2, порядок B-X-Y-C.
GOOD = {"A": (2, 4), "B": (0, 0), "C": (6, 0), "O": (3, 1),
        "D": (4, -2), "X": (2.5, 0), "Y": (4, 0)}

# Вырожденная конфигурация из прода: угол B = 90°, антипод A совпал с C,
# X и Y слиплись с C.
BAD = {"A": (0, 4), "B": (0, 0), "C": (4, 0), "O": (2, 2),
       "D": (4, 0), "X": (4, 0), "Y": (4, 0)}


def test_acute_good_config_passes():
    assert acute_failures(PROBLEM, GOOD) == []


def test_acute_bad_config_names_the_right_angle():
    fails = acute_failures(PROBLEM, BAD)
    assert any("не остроугольный" in f and "угол B = 90" in f for f in fails), fails


def test_antipode_good_config_passes():
    assert antipode_failures(PROBLEM, GOOD) == []


def test_antipode_bad_config_fails():
    # антипод нарушен: D не на окружности напротив A (в вырожденном случае
    # прод-чертежа D=C совпадала с антиподом — там вырождение ловят острота
    # и равенства; здесь проверяем саму проверку антипода)
    coords = dict(BAD, D=(4, -1))
    fails = antipode_failures(PROBLEM, coords)
    assert any("D не диаметрально противоположна" in f for f in fails), fails


def test_between_good_config_passes():
    assert between_failures(PROBLEM, GOOD) == []


def test_between_bad_config_fails():
    fails = order_failures(PROBLEM, BAD)
    # X=Y=C: слипание с концом названо явно, порядок B-X-Y-C нарушен
    assert any("X совпала с концом отрезка BY" in f for f in fails), fails
    assert any("нарушен порядок точек на стороне BC" in f for f in fails), fails


def test_semantic_wrapper_installed():
    assert getattr(semantics.semantic_failures, "_acute_triangle", False)


def _plan():
    """Верный план: антипод и равноудалённые точки — конструкции, острота —
    иллюстративные углы (правило 37), как должен оформить формализатор."""
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "O", "D", "M", "N", "P", "Q", "X", "Y"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
            {"op": "reflect_point", "out": "D", "args": ["A", "O"]},
            {"op": "midpoint", "out": "M", "args": ["B", "D"]},
            {"op": "perp_point", "out": "N", "args": ["M", "B", "D"], "value": 1},
            {"op": "line_intersect", "out": "X", "args": ["B", "C", "M", "N"]},
            {"op": "midpoint", "out": "P", "args": ["C", "D"]},
            {"op": "perp_point", "out": "Q", "args": ["P", "C", "D"], "value": 1},
            {"op": "line_intersect", "out": "Y", "args": ["B", "C", "P", "Q"]},
        ],
        "constraints": [],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["X", "D"], ["Y", "D"], ["D", "A"]],
            "circles": [["O", "A"]],
            "equal_marks": [
                {"pts": ["B", "X"], "count": 1}, {"pts": ["X", "D"], "count": 1},
                {"pts": ["C", "Y"], "count": 2}, {"pts": ["Y", "D"], "count": 2},
            ],
            "aux_lines": [["M", "N"], ["P", "Q"]],
            "hide_labels": ["O", "M", "N", "P", "Q"],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def test_full_pipeline_verified_drawing():
    """Конвейер с верным планом: чертёж верифицирован, равенства выполняются,
    вырожденных предупреждений нет, все точки на месте."""
    with patch.object(L, "formalize", lambda *a, **k: (_plan(), [])), \
         patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}):
        result = pipeline.generate(PROBLEM, use_cache=False)
    assert result.ok, (result.stage, result.detail)
    assert result.verification == "constraints_only", result.warnings
    joined = " | ".join(result.warnings)
    assert "BX=XD" not in joined and "CY=YD" not in joined, result.warnings
    assert "не остроугольный" not in joined
    # все точки фигуры различны и присутствуют на чертеже
    import re as _re
    labels = {m.group(1) for m in _re.finditer(r'<text[^>]*data-point="([A-Z](?:_\w)*)"', result.svg)}
    assert {"A", "B", "C", "D", "X", "Y"} <= labels
    # порядок B-X-Y-C на решённой фигуре (по координатам точек в SVG)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(result.svg)
    NS = "{http://www.w3.org/2000/svg}"
    pts = {}
    for c in root.iter(NS + "circle"):
        name = c.get("data-point")
        if name:
            pts[name] = (float(c.get("cx")), float(c.get("cy")))
    assert {"A", "B", "C", "D", "X", "Y"} <= set(pts), sorted(pts)
    # X и Y лежат на прямой BC, порядок B-X-Y-C
    (bx, by), (cx, cy) = pts["B"], pts["C"]
    along = {}
    for n in ("B", "X", "Y", "C"):
        px, py = pts[n]
        along[n] = ((px - bx) * (cx - bx) + (py - by) * (cy - by)) / (
            (cx - bx) ** 2 + (cy - by) ** 2)
    assert -1e-6 <= along["X"] <= 1 + 1e-6 and -1e-6 <= along["Y"] <= 1 + 1e-6, along
    assert along["B"] < along["X"] < along["Y"] < along["C"], along
    # D не слиплась ни с одной вершиной
    for n in ("A", "B", "C", "X", "Y"):
        assert abs(pts["D"][0] - pts[n][0]) + abs(pts["D"][1] - pts[n][1]) > 1, (n, pts["D"])


def test_degenerate_solution_excluded_by_checks():
    """Вырожденное решение бракуется проверками — и не может быть показано
    как верифицированный чертёж."""
    fails = semantics.semantic_failures(PROBLEM, _plan(), BAD)
    assert any("не остроугольный" in f for f in fails), fails
    assert any("совпала с концом отрезка BY" in f for f in fails), fails
    assert any("BX=XD не выполняется" in f or "равенство BX=XD" in f for f in fails), fails


def test_point_off_line_rejected():
    """Точка вне прямой: B=(0,0), Y=(4,0), X=(2,100) — проекция внутри, но
    отклонение огромное. Принадлежность обязана проверять расстояние до
    прямой, а не только параметр проекции."""
    coords = dict(GOOD, X=(2, 100))
    fails = between_failures(PROBLEM, coords)
    assert any("X не лежит на отрезке BY" in f for f in fails), fails


def test_capital_sentence_start_side_check():
    """«Точки X и Y на стороне BC» — с заглавной буквы (начало предложения):
    проверка стороны обязана находить фразу и отклонять Y за концом C."""
    coords = dict(GOOD, Y=(7, 0))          # Y за пределами BC (C=(6,0))
    fails = between_failures(PROBLEM, coords)
    assert any("Y не лежит на стороне BC" in f for f in fails), fails


def test_endpoint_allowed_by_membership_but_rejected_by_order():
    """Принадлежность замкнутому отрезку принимает конец; порядок ЭТОЙ
    конфигурации (строго B-X-Y-C, без слипания) — отвергает."""
    ENDPT = dict(GOOD, X=GOOD["Y"])          # X совпала с Y
    assert between_failures(PROBLEM, ENDPT) == []      # конец допустим
    fails = order_failures(PROBLEM, ENDPT)
    assert any("X совпала с концом отрезка BY" in f for f in fails), fails
    assert any("нарушен порядок" in f for f in fails), fails


def _honest_coords(a, b, c):
    """Координаты, честно вычисленные конструкциями плана (та же цепочка,
    что и солвер): O, D, X, Y из A, B, C."""
    import numpy as np
    from geoexact.core.constructions import (
        _circumcenter, _midpoint, _perp_point, _line_intersect)
    A, B, C = (np.asarray(v, float) for v in (a, b, c))
    O = _circumcenter(A, B, C)
    D = 2.0 * O - A
    M = _midpoint(B, D)
    N = _perp_point(M, B, D, 1)
    X = _line_intersect(B, C, M, N)
    P = _midpoint(C, D)
    Q = _perp_point(P, C, D, 1)
    Y = _line_intersect(B, C, P, Q)
    return {"A": A, "B": B, "C": C, "O": O, "D": D, "M": M, "N": N,
            "P": P, "Q": Q, "X": X, "Y": Y}


def test_controlled_candidates_selection(monkeypatch):
    """Управляемая регрессия выбора: солвер подменён списком из двух честных
    кандидатов — тупоугольного и острого. Оба доходят до семантической
    фильтрации, первый отвергнут («не остроугольный»), второй принят, и
    итоговый SVG соответствует второму (без выдуманных углов)."""
    import numpy as np
    from geoexact.core import solver as solver_module, semantics
    from geoexact.core.solver import Solution

    obtuse = _honest_coords((7, 5), (0, 0), (6, 0))    # угол C > 90°
    acute = _honest_coords((2, 4), (0, 0), (6, 0))     # контрфигурация советника
    # проверяем сам факт: первый кандидат действительно тупоугольный
    assert any("не остроугольный" in f for f in acute_failures(PROBLEM, obtuse))
    assert acute_failures(PROBLEM, acute) == []

    seen: list[tuple[dict, list]] = []
    real_semantic = semantics.semantic_failures

    def spy(text, plan, coords, *a, **k):
        fails = real_semantic(text, plan, coords, *a, **k)
        seen.append(({n: tuple(v) for n, v in coords.items()}, list(fails)))
        return fails
    monkeypatch.setattr(semantics, "semantic_failures", spy)

    def fake_solve(plan, *a, **k):
        return [Solution(coords=obtuse, residual=0.0, ok=True),
                Solution(coords=acute, residual=0.0, ok=True)]
    monkeypatch.setattr(solver_module, "solve", fake_solve)

    with patch.object(L, "formalize", lambda *a, **k: (_plan(), [])), \
         patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}):
        result = pipeline.generate(PROBLEM, use_cache=False)

    # оба кандидата дошли до семантической фильтрации
    def _key(d):
        return {n: tuple(round(float(x), 6) for x in v) for n, v in d.items()}
    okey, akey = _key(obtuse), _key(acute)
    seen_keys = [(_key(c), f) for c, f in seen]
    assert any(k == okey for k, _ in seen_keys), "тупоугольный кандидат не дошёл до фильтра"
    assert any(k == akey for k, _ in seen_keys), "острый кандидат не дошёл до фильтра"
    # первый кандидат отвергнут проверкой остроты, второй — чист
    assert any("не остроугольный" in f for k, fs in seen_keys if k == okey for f in fs), \
        "тупоугольный кандидат не отвергнут"
    assert all(not fs for k, fs in seen_keys if k == akey), \
        [fs for k, fs in seen_keys if k == akey]
    # итог: верифицированный чертёж (острый кандидат принят)
    assert result.ok, (result.stage, result.detail)
    assert result.verification == "constraints_only", result.warnings
    # SVG соответствует острому кандидату: все точки различны, треугольник острый
    import xml.etree.ElementTree as ET
    import math as _math
    root = ET.fromstring(result.svg)
    NS = "{http://www.w3.org/2000/svg}"
    pts = {}
    for c in root.iter(NS + "circle"):
        name = c.get("data-point")
        if name:
            pts[name] = (float(c.get("cx")), float(c.get("cy")))
    assert {"A", "B", "C", "D", "X", "Y"} <= set(pts)
    uniq = {tuple(round(x, 3) for x in pts[n]) for n in ("A", "B", "C", "D", "X", "Y")}
    assert len(uniq) == 6, "слипшиеся точки на итоговом чертеже"

    def angle(v, p, q):
        V = pts[v]
        u = np.array(pts[p]) - np.array(V)
        w = np.array(pts[q]) - np.array(V)
        cosv = float(np.clip(u @ w / (np.linalg.norm(u) * np.linalg.norm(w)), -1, 1))
        return _math.degrees(_math.acos(cosv))

    for v, o1, o2 in (("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")):
        assert angle(v, o1, o2) < 89.0, f"на итоговом чертеже треугольник не острый ({v})"


def test_lone_phrases_impose_no_order():
    """По отдельности фразы порядка не задают (полный semantic_failures):
    «точка P лежит на отрезке AB» с P=A — конец допустим; «точки X и Y на
    стороне BC» с порядком B-Y-X-C — перечисление не задаёт порядок.
    Порядок проверяется только для СВЯЗАННОЙ пары фраз этой задачи."""
    from geoexact.core.schema import FigurePlan
    plan = FigurePlan.from_dict({"points": [], "constructions": [],
                                 "constraints": [], "draw": {},
                                 "target": {"kind": "none", "args": []}})
    T1 = "Точка P лежит на отрезке AB"
    c1 = {"A": (0, 0), "B": (4, 0), "P": (0, 0)}
    assert semantics.semantic_failures(T1, plan, c1) == []
    T2 = "Точки X и Y на стороне BC"
    c2 = {"B": (0, 0), "C": (6, 0), "X": (4, 0), "Y": (2, 0)}
    assert semantics.semantic_failures(T2, plan, c2) == []


def test_order_direction_from_linked_phrase():
    """Направление порядка — из связанной фразы, не из перечисления и не из
    записи стороны: «Y лежит на отрезке BX» задаёт B-Y-X-C — и он допустим;
    GOOD при записи стороны CB вместо BC — тоже без нарушений (полный
    semantic_failures)."""
    from geoexact.core.schema import FigurePlan
    plan = FigurePlan.from_dict({"points": [], "constructions": [],
                                 "constraints": [], "draw": {},
                                 "target": {"kind": "none", "args": []}})
    T = "Точки X и Y на стороне BC. Точка Y лежит на отрезке BX"
    c = {"B": (0, 0), "C": (6, 0), "Y": (2, 0), "X": (4, 0)}   # B-Y-X-C
    assert semantics.semantic_failures(T, plan, c) == []
    T2 = "Точки X и Y на стороне CB. Точка X лежит на отрезке BY"
    assert semantics.semantic_failures(T2, plan, GOOD) == []
