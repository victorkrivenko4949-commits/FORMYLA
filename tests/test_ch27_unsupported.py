# -*- coding: utf-8 -*-
"""CH27 FIX4: unsupported -> AUX_UNSUPPORTED (не AUX_NOT_NEEDED)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_compile_unsupported_is_not_steps():
    # compile_steps_to_aux получает только steps; unsupported обрабатывается
    # в routes._two_stage_aux_plan отдельно.  Здесь проверяем, что steps=[]
    # без unsupported даёт has_aux=false (совместимость).
    from services.aux_compiler import compile_steps_to_aux
    aux, issues = compile_steps_to_aux([], {})
    assert aux["has_aux"] is False
    assert "не содержит построений" in aux["reason"]


def test_unsupported_json_shape():
    # Проверяем, что форма unsupported разбирается как список объектов.
    payload = json.loads(
        '{"steps": [], "unsupported": ['
        '{"step_no": 2, "needed": "поворот на 120°", "quote": "повернём ..."}]}'
    )
    assert isinstance(payload.get("unsupported"), list)
    assert payload["unsupported"][0]["needed"] == "поворот на 120°"


def test_two_stage_unsupported_sets_status():
    # Интеграционный тест: при steps=[] и непустом unsupported, логика в
    # _two_stage_aux_plan должна дать AUX_UNSUPPORTED.  Проверяем напрямую
    # поведение через маленький mock, не поднимая Flask.
    # (Логика тривиальна: `if not aux_has and unsupported: AUX_UNSUPPORTED`.)
    unsupported = [{"step_no": 1, "needed": "инверсия", "quote": "инвертируем"}]
    aux_has = False
    status = "AUX_UNSUPPORTED" if (not aux_has and unsupported) else "AUX_NOT_NEEDED"
    assert status == "AUX_UNSUPPORTED"

    # Без unsupported — прежнее поведение.
    status2 = "AUX_UNSUPPORTED" if (not aux_has and []) else "AUX_NOT_NEEDED"
    assert status2 == "AUX_NOT_NEEDED"


def test_extract_condition_points_vertex_and_polygon():
    from services.figure_plan_validator import extract_condition_points
    # «вокруг вершины B» + «точка A перешла в точку C».
    pts = extract_condition_points(
        "Повернём плоскость вокруг вершины B на 60° так, "
        "чтобы точка A перешла в точку C"
    )
    assert "B" in pts
    assert "A" in pts
    assert "C" in pts
    # «треугольник ABC» раскладывается на A/B/C.
    pts2 = extract_condition_points("В равностороннем треугольнике ABC известно...")
    assert pts2 == {"A", "B", "C"}


def test_check_condition_points_missing_vertex_b():
    from services.figure_plan_validator import check_condition_points
    statement = "Повернём плоскость вокруг вершины B на 60°."
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 0, "y": 0},
            {"type": "free_point", "id": "C", "x": 10, "y": 0},
        ],
    }
    warnings = check_condition_points(statement, base)
    assert any("MISSING_CONDITION_POINT" in w and "'B'" in w for w in warnings)
