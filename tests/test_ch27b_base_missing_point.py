# -*- coding: utf-8 -*-
"""CH27b: BLOCKING-проверка точек условия на base-стадии."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.figure_plan_validator import (  # noqa: E402
    extract_condition_points,
    check_condition_points,
)


def test_extract_vertex_and_polygon():
    pts = extract_condition_points(
        "Повернём плоскость вокруг вершины B на 60° так, "
        "чтобы точка A перешла в точку C"
    )
    assert pts == {"A", "B", "C"}


def test_extract_polygon_name_letters():
    pts = extract_condition_points(
        "Точка P лежит внутри равностороннего треугольника ABC, PB = 4."
    )
    # P из «Точка P», A/B/C из «треугольника ABC».  PB=4 не добавляет нового.
    assert pts == {"P", "A", "B", "C"}


def test_check_missing_point_base():
    statement = "Повернём плоскость вокруг вершины B на 60°."
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 0, "y": 0},
            {"type": "free_point", "id": "C", "x": 10, "y": 0},
        ],
    }
    warnings = check_condition_points(statement, base)
    assert any("MISSING_CONDITION_POINT" in w and "'B'" in w for w in warnings)


def test_check_no_missing_point():
    statement = "Повернём плоскость вокруг вершины B на 60°."
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 0, "y": 0},
            {"type": "free_point", "id": "B", "x": 5, "y": 5},
            {"type": "free_point", "id": "C", "x": 10, "y": 0},
        ],
    }
    warnings = check_condition_points(statement, base)
    assert warnings == []


def test_pb_formula_no_false_positive():
    # «PB = 4» не должен порождать требование точки P, если P уже из
    # «Точка P» или из имени фигуры.  Здесь P объявлен явно.
    statement = "В треугольнике ABC точка P такова, что PB = 4."
    pts = extract_condition_points(statement)
    assert pts == {"A", "B", "C", "P"}
