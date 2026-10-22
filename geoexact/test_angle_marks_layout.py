# -*- coding: utf-8 -*-
"""Широкий угол (150° между медианами): дуга компактнее, подпись — у дуги.

Воспроизведение прод-дефекта: у угла 150° с вершиной в точке пересечения
медиан подпись «150°» уезжала за верхнюю сторону AB — стартовый отступ
кандидатов (outer + halfdiag + 5) выводил её прямоугольник за сторону,
дальние шаги получали штраф за пересечение отрезка, и emit_text выбирал
позицию НАД стороной. Дуга радиуса 30px к тому же съедала треть высоты
до стороны. Обёртка angle_marks_layout сжимает дугу широкого угла и
возвращает подпись в первое свободное окно у дуги."""
import math
import xml.etree.ElementTree as ET

from geoexact.core.angle_marks_layout import screen_coords
from geoexact.core.gates import rank_solutions
from geoexact.core.render import render_svg
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve

NS = "http://www.w3.org/2000/svg"


def _medians_plan(angle=150):
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "A_1", "B_1", "G"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "midpoint", "out": "A_1", "args": ["B", "C"]},
            {"op": "midpoint", "out": "B_1", "args": ["A", "C"]},
            {"op": "line_intersect", "out": "G", "args": ["A", "A_1", "B", "B_1"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "A_1"], "value": 9},
            {"type": "dist", "args": ["B", "B_1"], "value": 12},
            {"type": "angle", "args": ["A", "G", "B"], "value": angle},
        ],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "A_1"], ["B", "B_1"]],
            "angle_marks": [{"pts": ["A", "G", "B"], "text": f"{angle}°"}],
            "length_marks": [{"pts": ["A", "A_1"], "text": "AA_1 = 9"},
                            {"pts": ["B", "B_1"], "text": "BB_1 = 12"}],
            "hide_labels": ["G"],
        },
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def _render(plan):
    ranked = rank_solutions(plan, solve(plan, n_seeds=8), strict_readability=False)
    assert ranked
    sol = ranked[0][0]
    return render_svg(plan, sol), sol


def _parts(svg, text):
    root = ET.fromstring(svg)
    arcs = []
    for el in root.iter("{" + NS + "}path"):
        if "arc" not in (el.get("class") or "").split():
            continue
        t = (el.get("d") or "").split()
        if len(t) == 11 and t[0] == "M" and t[3] == "A":
            arcs.append(((float(t[1]), float(t[2])), (float(t[9]), float(t[10])),
                         float(t[4])))
    label = None
    for el in root.iter("{" + NS + "}text"):
        if (el.text or "").strip() == text:
            label = (float(el.get("x")), float(el.get("y")) - 12.5 * 0.35)
    dots = {e.get("data-point"): (float(e.get("cx")), float(e.get("cy")))
            for e in root.iter("{" + NS + "}circle") if e.get("data-point")}
    return root, arcs, label, dots


def test_wide_angle_arc_is_compact():
    svg, _ = _render(_medians_plan())
    _, arcs, _, _ = _parts(svg, "150°")
    assert arcs, "дуга угла не нарисована"
    _, _, r = arcs[0]
    assert r <= 20.0, f"дуга широкого угла должна быть компактной, радиус {r}"


def test_wide_angle_label_stays_near_arc_and_below_side():
    svg, sol = _render(_medians_plan())
    root, arcs, label, dots = _parts(svg, "150°")
    assert label, "подпись 150° пропала"
    assert arcs and all(n in dots for n in ("A", "B"))
    # вершина угла — экранные координаты точки G из решения (не эвристика)
    q = screen_coords(root, {n: tuple(sol.coords[n][:2]) for n in sol.coords})
    vertex = q["G"]
    # подпись не дальше 60px от вершины угла (раньше уезжала на ~75px за сторону)
    assert math.dist(label, vertex) < 60.0, f"подпись улетела: {label} от {vertex}"
    # и подпись ниже верхней стороны AB (внутри треугольника)
    ab_y = min(dots["A"][1], dots["B"][1])
    assert label[1] > ab_y, f"подпись выше стороны AB: {label} против y={ab_y}"


def test_narrow_angle_is_untouched():
    # контроль: узкий угол при вершине треугольника — дугу не сжимаем,
    # обёртка не меняет прежнее поведение (сжатие только для >= 110°)
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [{"type": "angle", "args": ["B", "A", "C"], "value": 50}],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"]],
            "angle_marks": [{"pts": ["B", "A", "C"], "text": "50°"}],
        },
        "target": {"kind": "none", "args": []}, "scale_free": True,
    })
    svg, _ = _render(plan)
    _, arcs, label, _ = _parts(svg, "50°")
    assert label, "подпись угла пропала"
    assert arcs and arcs[0][2] > 20.0, "узкий угол не сжимаем"


def test_ambiguous_arc_group_is_untouched():
    """Две отметки углов с общей вершиной — группа неоднозначна, обёртка
    обязана пропустить обе дуги (не сжать «первую попавшуюся»)."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABCD"],
        "constraints": [
            {"type": "angle", "args": ["B", "A", "C"], "value": 130},
            {"type": "angle", "args": ["B", "A", "D"], "value": 100},
        ],
        "draw": {
            "segments": [["A", "B"], ["A", "C"], ["A", "D"]],
            "angle_marks": [{"pts": ["B", "A", "C"], "text": "130°"},
                           {"pts": ["B", "A", "D"], "text": "100°"}],
        },
        "target": {"kind": "none", "args": []}, "scale_free": True,
    })
    svg, _ = _render(plan)
    _, arcs, _, _ = _parts(svg, "130°")
    assert len(arcs) >= 2, "обе дуги должны быть нарисованы"
    for _, _, r in arcs:
        assert r > 20.0, "неоднозначная группа не сжимается"
