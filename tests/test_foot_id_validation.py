# -*- coding: utf-8 -*-
"""Регрессия: altitude/median/angle_bisector с foot_id объявляют точку.

Дефект: validate_figure_json считал ссылку на foot_id (например 'H' из altitude)
dangling reference, хотя движок создаёт эту точку в ctx.points.  Из-за этого
валидный план Gemini/Claude с высотой отклонялся «Модель не смогла создать
корректный base-план».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.figure_validator import validate_figure_json


def _plan(constructions):
    return {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
    }


def test_altitude_foot_id_is_declared():
    """Прямоугольный треугольник с высотой CH: ссылка на H валидна."""
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 160, "y": 140},
        {"type": "free_point", "id": "B", "x": 480, "y": 380},
        {"type": "free_point", "id": "C", "x": 160, "y": 380},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "altitude", "id": "alt_CH", "vertex": "C",
         "side_a": "A", "side_b": "B", "foot_id": "H"},
        {"type": "segment", "id": "CH", "p1": "C", "p2": "H"},
        {"type": "right_angle_mark", "id": "ra_H", "vertex": "H",
         "ray1": "C", "ray2": "B"},
    ])
    r = validate_figure_json(plan)
    assert r.get("valid"), r.get("errors")


def test_median_foot_id_is_declared():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 400, "y": 100},
        {"type": "free_point", "id": "C", "x": 250, "y": 300},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "median", "id": "med", "vertex": "C",
         "side_a": "A", "side_b": "B", "foot_id": "M"},
        {"type": "segment", "id": "CM", "p1": "C", "p2": "M"},
    ])
    r = validate_figure_json(plan)
    assert r.get("valid"), r.get("errors")


def test_foot_id_collision_is_rejected():
    """foot_id не должен совпадать с уже объявленным id другой точки."""
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 400, "y": 100},
        {"type": "free_point", "id": "C", "x": 250, "y": 300},
        {"type": "free_point", "id": "H", "x": 250, "y": 150},
        {"type": "altitude", "id": "alt_CH", "vertex": "C",
         "side_a": "A", "side_b": "B", "foot_id": "H"},
    ])
    r = validate_figure_json(plan)
    assert not r.get("valid")
    assert any("collides" in e for e in r.get("errors", []))
