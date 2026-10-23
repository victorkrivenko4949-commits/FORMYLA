# -*- coding: utf-8 -*-
"""Режим доп. построения: результат построения строго отмечен.

Прод-дефект (задача «медианы 9 и 12, угол 150°», доп. построение «обозначить O
и провести CO»): точка пересечения медиан оставалась БЕЗ ИМЕНИ (рендер прячет
подпись по сырому hide_labels, а окружность финишер оставляет, потому что точка
используется построением), а результат построения — длины 6, 3, 4, 8, на которых
держится решение, — не отмечался вовсе. Теперь:

* точка, которой пользуется построение, обязана быть подписана (кроме центров
  вспомогательных окружностей и точек-свидетелей);
* числовые подписи результата (result_marks) проверяются движком по чертежу
  И по структурному основанию: отрезок нарисован построением или является
  куском разделённого им отрезка; случайное совпадение числа не принимается;
* классический случай — теорема о медианах (центроид делит медиану 2:1) —
  оформляется автоматически, даже если модель подписей не прислала;
* в виде с построением полная длина скрывается, если её куски отмечены
  («можно было отметить только 6 3 4 8»), в базовом виде полные длины остаются;
* подписи длин стоят сбоку от отрезков (штатное поведение рендера, зафиксировано
  проверкой прямоугольника подписи против отрезков)."""
import math

import pytest
import xml.etree.ElementTree as ET

from geoexact.core import auxplan
from geoexact.core.gates import rank_solutions
from geoexact.core.render import render_svg
from geoexact.core.solver import solve
from geoexact.test_angle_marks_layout import _medians_plan

NS = "http://www.w3.org/2000/svg"

AUX = {
    "idea": "Провести отрезок из C в точку пересечения медиан: три "
            "равновеликих треугольника, AO = 6, BO = 8.",
    "steps": [],
    "aux_segments": [["C", "G"]],
    "result_marks": [
        {"pts": ["A", "G"], "text": "6"},
        {"pts": ["G", "A_1"], "text": "3"},
        {"pts": ["B", "G"], "text": "8"},
        {"pts": ["G", "B_1"], "text": "4"},
    ],
}


def _solved():
    plan = _medians_plan()
    ranked = rank_solutions(plan, solve(plan, n_seeds=8), strict_readability=False)
    assert ranked
    return plan, ranked[0][0]


def _texts(svg):
    root = ET.fromstring(svg)
    out = []
    for el in root.iter("{" + NS + "}text"):
        content = (el.text or "") + "".join(t.text or "" for t in el)
        out.append(content.strip())
    return root, out


def test_aux_result_marks_verified_and_drawn():
    """6, 3, 4, 8 — проверенные подписи результата, слой aux, отрезок CM нарисован."""
    plan, sol = _solved()
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, AUX, why)
    assert applied is not None, why
    plan2 = applied[0]
    assert ["C", "G"] in [list(s) for s in plan2.draw.aux_segments]
    texts = {m["text"]: m for m in plan2.draw.length_marks if m.get("layer") == "aux"}
    assert set(texts) == {"6", "3", "4", "8"}, texts
    assert texts["6"]["pts"] == ["A", "G"]
    # повтор той же подписи в одном ответе не дублируется на чертеже
    dup = dict(AUX, result_marks=AUX["result_marks"] + [dict(AUX["result_marks"][0])])
    why_dup: list = []
    applied_dup = auxplan.apply_aux(_medians_plan(), sol.coords, dup, why_dup)
    assert applied_dup is not None, why_dup
    n6 = sum(1 for m in applied_dup[0].draw.length_marks
             if m.get("text") == "6" and m.get("layer") == "aux")
    assert n6 == 1


def test_aux_wrong_result_mark_dropped_with_reason():
    """Неверная длина не попадает на чертёж: отбрасывается с причиной, не молча.
    Классические куски медиан при этом выводятся теоремой (6/3/8/4) — плохая
    подпись не валит чертёж и не подменяет собой проверенный результат."""
    plan, sol = _solved()
    bad = dict(AUX, result_marks=[{"pts": ["A", "G"], "text": "5"}])
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, bad, why)
    assert applied is not None            # чертёж жив: плохая подпись не валит его
    texts = [m["text"] for m in applied[0].draw.length_marks if m.get("layer") == "aux"]
    assert "5" not in texts                # и на чертёж не попала
    assert any("не сходится" in w for w in why)
    assert "не сходится" in (applied[0].notes or "")


def test_aux_unfounded_result_mark_rejected():
    """Число, случайно совпавшее с чертежом на постороннем отрезке, — не результат.

    Сторона AB построением не тронута: точной по чертежу длины AB недостаточно,
    нужно доказуемое основание — теорема или данное."""
    plan, sol = _solved()
    import numpy as np
    ab = float(np.linalg.norm(sol.coords["A"] - sol.coords["B"]))
    unfounded = dict(AUX, result_marks=[{"pts": ["A", "B"], "text": f"{ab:.6g}"}])
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, unfounded, why)
    assert applied is not None, why
    marks = [m for m in applied[0].draw.length_marks
             if m.get("layer") == "aux" and m["pts"] == ["A", "B"]]
    assert not marks
    assert any("не доказана" in w or "без основания" in w for w in why)


def test_aux_drawn_segment_length_not_provable():
    """Отрезок нарисован построением, но его длина не определена условиями:
    совпавшее с одним решением число нельзя объявлять подтверждённым результатом."""
    plan, sol = _solved()
    import numpy as np
    cg = float(np.linalg.norm(sol.coords["C"] - sol.coords["G"]))
    guess = dict(AUX, result_marks=[{"pts": ["C", "G"], "text": f"{cg:.6g}"}])
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, guess, why)
    assert applied is not None, why
    marks = [m for m in applied[0].draw.length_marks
             if m.get("layer") == "aux" and m["pts"] == ["C", "G"]]
    assert not marks
    assert any("не доказана" in w for w in why)


def test_full_length_stays_when_pieces_have_hole():
    """Дыра в покрытии не прячет полную длину: куски накрывают только часть
    отрезка — полная длина остаётся в виде с построением (юнит-тест логики
    покрытия; через полный конвейер дыру не построить — теорема о медианах
    даёт все куски сразу)."""
    from geoexact.core import aux_view_marks
    coords = {"A": (0.0, 0.0), "B": (10.0, 0.0), "M": (3.0, 0.0), "N": (6.0, 0.0)}
    full = {"pts": ["A", "B"], "text": "10", "layer": "main"}
    # куски A-M и M-N накрывают [0, 0.6] — дыра (0.6, 1]
    partial = [{"pts": ["A", "M"], "text": "3", "layer": "aux"},
              {"pts": ["M", "N"], "text": "3", "layer": "aux"}]
    assert not aux_view_marks._covered_by_pieces(full, [full] + partial, coords)
    # символический кусок не считается покрытием
    sym = [{"pts": ["A", "B"], "text": "x", "layer": "aux"}]
    assert not aux_view_marks._covered_by_pieces(full, [full] + sym, coords)
    # полный кусок A-B числом — покрытие есть
    whole = [{"pts": ["A", "B"], "text": "10", "layer": "aux"}]
    assert aux_view_marks._covered_by_pieces(full, [full] + whole, coords)


def test_positional_show_aux_false():
    """Позиционный вызов render_svg(plan, sol, gate, False) не должен
    восприниматься как show_aux=True (иначе в базовом виде пропали бы все длины)."""
    plan, sol = _solved()
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, AUX, why)
    assert applied is not None, why
    svg = render_svg(applied[0], sol, None, False)
    _, texts = _texts(svg)
    assert any("9" in t and "=" in t for t in texts)          # AA_1 = 9 на месте
    assert not [t for t in texts if t in ("6", "3", "4", "8")]  # кусков нет


def test_disambiguate_tight_label_gets_segment_name():
    """Тесное место: числовая подпись результата, налегшая на линию отрезка,
    выносится прочь и получает однозначное имя «AG = 6» — единичный тест ветки."""
    from geoexact.core import aux_view_marks
    from geoexact.core import render as render_mod
    fs = render_mod.MARK_FS
    # синтетический SVG: точка-подпись «6» лежит прямо на отрезке AG
    ax, ay, gx, gy = 100.0, 100.0, 200.0, 100.0
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
           f'<line x1="{ax}" y1="{ay}" x2="{gx}" y2="{gy}" />'
           f'<circle data-point="A" cx="{ax}" cy="{ay}" r="3" />'
           f'<circle data-point="G" cx="{gx}" cy="{gy}" r="3" />'
           f'<text x="150" y="100" text-anchor="middle">6</text></svg>')
    marks = [{"pts": ["A", "G"], "text": "6", "layer": "aux"}]
    out = aux_view_marks._disambiguate(svg, render_mod, marks)
    root = ET.fromstring(out)
    texts = [((el.text or "") + "".join(t.text or "" for t in el)).strip()
             for el in root.iter("{" + NS + "}text")]
    assert "AG = 6" in texts                     # получила имя отрезка
    for el in root.iter("{" + NS + "}text"):
        content = ((el.text or "") + "".join(t.text or "" for t in el)).strip()
        if content == "AG = 6":
            x, y = float(el.get("x")), float(el.get("y"))
            assert abs(y - ay) > 8.0             # и вынесена прочь от линии


def test_no_result_marks_auto_derivation():
    """Модель не прислала подписи — классический случай оформляется сам:
    центроид делит медиану 2:1, из «AA_1 = 9» выводятся 6 и 3, из «BB_1 = 12» — 8 и 4."""
    plan, sol = _solved()
    data = {k: v for k, v in AUX.items() if k != "result_marks"}
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, data, why)
    assert applied is not None, why
    texts = {m["text"]: tuple(m["pts"]) for m in applied[0].draw.length_marks
             if m.get("layer") == "aux"}
    assert texts.get("6") == ("A", "G")
    assert texts.get("3") == ("G", "A_1")
    assert texts.get("8") == ("B", "G")
    assert texts.get("4") == ("G", "B_1")


def test_aux_referenced_point_gets_label():
    """«Обозначить точку» — точка построения не может остаться безымянной.

    Раньше: рендер прятал подпись по сырому hide_labels, а окружность финишер
    оставлял (точка используется построением) — на чертеже безымянная точка."""
    plan, sol = _solved()
    assert "G" in plan.draw.hide_labels  # исходно пересечение медиан спрятано
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, AUX, why)
    assert applied is not None, why
    plan2 = applied[0]
    assert "G" not in plan2.draw.hide_labels
    assert "обозначена построением" in (plan2.notes or "")
    svg = render_svg(plan2, sol, show_aux=True)
    root, texts = _texts(svg)
    assert "G" in texts                  # у точки появилось имя


def test_unreferenced_hidden_point_stays_hidden():
    """Построение, не пользующееся спрятанной точкой, её не раскрывает."""
    plan, sol = _solved()
    midline = {"idea": "средняя линия", "steps": [], "aux_segments": [["A_1", "B_1"]]}
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, midline, why)
    assert applied is not None, why
    assert "G" in applied[0].draw.hide_labels


def test_full_length_hidden_in_aux_view_kept_in_base():
    """«Только 6 3 4 8»: в виде с построением полные 9 и 12 скрыты кусками,
    в базовом виде — остаются, куски исчезают."""
    plan, sol = _solved()
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, AUX, why)
    assert applied is not None, why
    plan2 = applied[0]
    svg_aux = render_svg(plan2, sol, show_aux=True)
    _, texts_aux = _texts(svg_aux)
    for t in ("6", "3", "4", "8"):
        assert t in texts_aux
    assert not any("9" in t and "=" in t for t in texts_aux), texts_aux
    assert not any("12" in t and "=" in t for t in texts_aux), texts_aux
    svg_base = render_svg(plan2, sol, show_aux=False)
    _, texts_base = _texts(svg_base)
    assert any("9" in t and "=" in t for t in texts_base)     # AA_1 = 9 на месте
    assert any("12" in t and "=" in t for t in texts_base)
    assert not [t for t in texts_base if t in ("6", "3", "4", "8")]  # кусков нет


def test_aux_result_labels_render_beside_segments():
    """Подписи 6/3/4/8 есть на готовом чертеже и не пересекают отрезки:
    проверяем прямоугольник подписи (как рендер) против каждого отрезка —
    «пусть сбоку» — штатное поведение, фиксируем тестом."""
    plan, sol = _solved()
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, AUX, why)
    assert applied is not None, why
    svg = render_svg(applied[0], sol, show_aux=True)
    root, texts = _texts(svg)
    for t in ("6", "3", "4", "8"):
        assert t in texts, f"подпись результата {t} пропала"
    from geoexact.core import render as render_mod
    fs = render_mod.MARK_FS
    text_box = render_mod._text_box
    rect_seg_hit = render_mod._rect_seg_hit
    marks = {}
    for el in root.iter("{" + NS + "}text"):
        content = ((el.text or "") + "".join(t.text or "" for t in el)).strip()
        if content in ("6", "3", "4", "8"):
            marks[content] = (float(el.get("x")), float(el.get("y")))
    segs = [tuple(float(el.get(k)) for k in ("x1", "y1", "x2", "y2"))
            for el in root.iter("{" + NS + "}line")]
    assert marks and segs
    for t, (x, y) in marks.items():
        rect = text_box(t, (x, y - fs * 0.35), fs)
        for x1, y1, x2, y2 in segs:
            assert not rect_seg_hit(rect, (x1, y1), (x2, y2)), \
                f"подпись {t} пересекает линию отрезка"


def test_coincidental_two_to_one_not_derived():
    """Совпадение 2:1 на посторонних серединах — не теорема, куски не выводятся.

    M1 = midpoint(Y, Z) и M2 = midpoint(W, Z) с W ≠ X: пересечение [X, M1] и
    [Y, M2] делит [X, M1] ровно 2:1 по построению координат, но это не центроид
    треугольника (M2 — середина WZ, а не XZ). Слабая проверка (общая вершина +
    «медиана не к своей стороне») приняла бы это; строгая требует M2 = midpoint(X, Z).
    """
    import numpy as np
    from geoexact.core import auxplan as ap
    from geoexact.core.schema import FigurePlan

    plan = FigurePlan.from_dict({
        "points": ["X", "Y", "Z", "W", "M1", "M2", "G"],
        "constructions": [
            {"op": "free_point", "out": n} for n in ("X", "Y", "Z", "W")
        ] + [
            {"op": "midpoint", "out": "M1", "args": ["Y", "Z"]},
            {"op": "midpoint", "out": "M2", "args": ["W", "Z"]},
            {"op": "line_intersect", "out": "G", "args": ["X", "M1", "Y", "M2"]},
        ],
        "constraints": [{"type": "dist", "args": ["X", "M1"], "value": 3}],
        "draw": {"segments": [["X", "M1"], ["Y", "M2"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    known = {n: np.array(v, dtype=float) for n, v in {
        "X": (0.0, 0.0), "Y": (0.0, 6.0), "Z": (6.0, -6.0), "W": (2.0, -6.0),
        "M1": (3.0, 0.0), "M2": (4.0, -6.0), "G": (2.0, 0.0)}.items()}
    # численно 2:1 сходится (защита не на числах, а на структуре):
    assert abs(np.linalg.norm(known["X"] - known["G"]) - 2.0) < 1e-9
    assert abs(np.linalg.norm(known["G"] - known["M1"]) - 1.0) < 1e-9
    visible = {frozenset(("X", "M1")), frozenset(("Y", "M2"))}
    assert ap._median_piece_marks(plan, known, {"G"}, visible) == []


@pytest.mark.parametrize("swap_lines,flip1,flip2", [
    (s, f1, f2) for s in (False, True) for f1 in (False, True) for f2 in (False, True)])
def test_median_centroid_any_arg_order(swap_lines, flip1, flip2):
    """Порядок концов в line_intersect не должен влиять: формализатор может
    записать медиану и как (A, A_1), и как (A_1, A), прямые — в любом порядке.
    Все 8 эквивалентных записей дают одинаковые подписи 6/3/4/8."""
    import copy
    base = _medians_plan()
    c = next(x for x in base.constructions if x.op == "line_intersect")
    l1 = list(c.args[:2])
    l2 = list(c.args[2:])
    if flip1:
        l1.reverse()
    if flip2:
        l2.reverse()
    args = l2 + l1 if swap_lines else l1 + l2
    plan = copy.deepcopy(base)
    cc = next(x for x in plan.constructions if x.op == "line_intersect")
    cc.args = args
    ranked = rank_solutions(plan, solve(plan, n_seeds=8), strict_readability=False)
    assert ranked
    sol = ranked[0][0]
    data = {k: v for k, v in AUX.items() if k != "result_marks"}
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, data, why)
    assert applied is not None, why
    texts = {m["text"]: tuple(m["pts"]) for m in applied[0].draw.length_marks
             if m.get("layer") == "aux"}
    assert texts.get("6") == ("A", "G"), (swap_lines, flip1, flip2)
    assert texts.get("3") == ("G", "A_1")
    assert texts.get("8") == ("B", "G")
    assert texts.get("4") == ("G", "B_1")


def test_third_median_marks_centroid_via_result_marks():
    """Прод-сценарий (задача о медианах, живая генерация 23.10.2026): построение —
    третья медиана CC1, она НЕ ссылается на центроид явно. Модель прислала
    result_marks с перепутанными числами (6/8 при данных 12/9) — подписи верно
    отброшены, но построение обязано всё равно дать итог: автоподстановка выводит
    правильные 8/4/6/3, а точка G получает имя (не безымянная точка)."""
    import copy
    plan = _medians_plan()
    d = {"type": "dist", "args": ["A", "A_1"], "value": 12}
    plan.constraints[0] = type(plan.constraints[0])(**d)
    plan.constraints[1] = type(plan.constraints[1])(**{"type": "dist", "args": ["B", "B_1"], "value": 9})
    plan.draw.length_marks[0]["text"] = "AA_1 = 12"
    plan.draw.length_marks[1]["text"] = "BB_1 = 9"
    ranked = rank_solutions(plan, solve(plan, n_seeds=8), strict_readability=False)
    assert ranked
    sol = ranked[0][0]
    data = {
        "idea": "провести третью медиану CC1: три равновеликих треугольника",
        "steps": [{"op": "midpoint", "out": "C_1", "args": ["A", "B"]}],
        "aux_segments": [["C", "C_1"]],
        "result_marks": [
            {"pts": ["A", "G"], "text": "6"},   # модель перепутала медианы
            {"pts": ["B", "G"], "text": "8"},
        ],
    }
    why: list = []
    applied = auxplan.apply_aux(plan, sol.coords, data, why)
    assert applied is not None, why
    plan2 = applied[0]
    notes = plan2.notes or ""
    assert "отброшена" in notes                    # неверные 6/8 отвергнуты
    texts = {m["text"]: tuple(m["pts"]) for m in plan2.draw.length_marks
             if m.get("layer") == "aux"}
    assert texts.get("8") == ("A", "G")            # 2/3 от AA_1 = 12
    assert texts.get("4") == ("G", "A_1")
    assert texts.get("6") == ("B", "G")            # 2/3 от BB_1 = 9
    assert texts.get("3") == ("G", "B_1")
    assert "G" not in plan2.draw.hide_labels        # точка получила имя
    svg = render_svg(plan2, sol, show_aux=True)
    root, out_texts = _texts(svg)
    assert "G" in out_texts
