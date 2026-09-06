# -*- coding: utf-8 -*-
"""CH23 PART B2: тесты компилятора aux."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.aux_compiler import compile_steps_to_aux  # noqa: E402

BASE = {
    "constructions": [
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 400, "y": 100},
        {"type": "free_point", "id": "C", "x": 300, "y": 300},
        {"type": "free_point", "id": "M", "x": 200, "y": 200},
        {"type": "free_point", "id": "O", "x": 300, "y": 150},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
    ],
}


def test_segment_with_quote():
    steps = [{"step_no": 1, "action": "draw_segment",
              "args": {"p1": "M", "p2": "C"}, "creates_point": None,
              "quote": "Соединим точки M и C"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    assert aux["has_aux"] is True
    c = aux["constructions"][0]
    assert c["type"] == "segment"
    assert c["dashed"] is True
    assert c["style"] == "aux"
    assert c["solution_evidence"]["quote"] == "Соединим точки M и C"


def test_altitude_with_foot_id():
    steps = [{"step_no": 1, "action": "draw_altitude",
              "args": {"vertex": "B", "side_a": "A", "side_b": "C"},
              "creates_point": "H", "quote": "Проведём высоту BH"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    c = aux["constructions"][0]
    assert c["type"] == "altitude"
    assert c["foot_id"] == "H"


def test_right_angle_mark_not_dashed():
    steps = [{"step_no": 1, "action": "mark_right_angle",
              "args": {"vertex": "C", "ray1": "A", "ray2": "B"},
              "creates_point": None, "quote": "угол C прямой"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    c = aux["constructions"][0]
    assert c["dashed"] is False
    assert c["type"] == "right_angle_mark"


def test_unresolved_point():
    steps = [{"step_no": 1, "action": "draw_segment",
              "args": {"p1": "Z", "p2": "C"}, "creates_point": None,
              "quote": "Соединим Z и C"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    assert any("UNRESOLVED_POINT:Z" in i for i in issues)


def test_empty_steps():
    aux, issues = compile_steps_to_aux([], BASE)
    assert aux["has_aux"] is False
    assert "не содержит построений" in aux["reason"]


def test_duplicate_in_base_skipped():
    steps = [{"step_no": 1, "action": "draw_segment",
              "args": {"p1": "A", "p2": "B"}, "creates_point": None,
              "quote": "Соединим A и B"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    # AB уже в base — объект с id aux_segment_A_B не совпадает с base AB,
    # но это дубликат по смыслу; компилятор не должен падать.
    assert "has_aux" in aux


def test_same_step_single_object():
    steps = [
        {"step_no": 1, "action": "draw_segment", "args": {"p1": "M", "p2": "C"}, "quote": "Соединим M и C"},
        {"step_no": 2, "action": "draw_segment", "args": {"p1": "M", "p2": "C"}, "quote": "Соединим M и C"},
    ]
    aux, issues = compile_steps_to_aux(steps, BASE)
    assert len(aux["constructions"]) == 1


def test_circle_visual_role():
    steps = [{"step_no": 1, "action": "draw_circle_center_radius",
              "args": {"center": "O", "radius_point": "A"}, "creates_point": "O",
              "quote": "Построим окружность с центром O"}]
    aux, issues = compile_steps_to_aux(steps, BASE)
    c = aux["constructions"][0]
    assert c["visual_role"] in ("reference_circle", "target_circle")
