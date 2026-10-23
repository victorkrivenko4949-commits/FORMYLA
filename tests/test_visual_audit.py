# -*- coding: utf-8 -*-
"""Tests for CH22/visual_check: services/visual_audit.py.

Регресс на найденные дефекты D1–D6, резолвер вершины угла и позитивные кейсы.
Без LLM и без БД.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.visual_audit import (
    audit_rendered_figure,
    resolve_angle_triple,
)
from geometric_engine.engine import GeometricEngine


def _plan(constructions, **extra):
    plan = {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
        "given_marks": [],
        "assumptions": [],
        "aux": {"has_aux": False, "reason": "", "constructions": []},
    }
    plan.update(extra)
    return plan


def _build(plan):
    engine = GeometricEngine()
    svg, ctx = engine.build(plan)
    return svg, ctx, engine


# ──────────────────────────────────────────────────────────────────────────
# Резолвер вершины угла
# ──────────────────────────────────────────────────────────────────────────

def test_resolve_angle_triple_by_polygon():
    triple = resolve_angle_triple("A", {}, "В треугольнике ABC угол A равен 45°.")
    assert triple == ("C", "A", "B"), triple


def test_resolve_angle_triple_by_two_segments():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "B", "x": 100, "y": 0},
        {"type": "free_point", "id": "C", "x": 0, "y": 100},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
    ])
    triple = resolve_angle_triple("A", plan)
    assert triple in (("B", "A", "C"), ("C", "A", "B")), triple


def test_resolve_angle_triple_ambiguous():
    # Вершина с 3+ лучами и без фигуры → None.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "B", "x": 100, "y": 0},
        {"type": "free_point", "id": "C", "x": 0, "y": 100},
        {"type": "free_point", "id": "D", "x": -50, "y": -50},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
    ])
    assert resolve_angle_triple("A", plan) is None


# ──────────────────────────────────────────────────────────────────────────
# V1 · LABEL_CONTRADICTS_GEOMETRY (D1)
# ──────────────────────────────────────────────────────────────────────────

def test_label_contradicts_geometry():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "angle_label", "id": "ang_A", "vertex": "A", "ray1": "B",
         "ray2": "C", "text": "45°"},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "В треугольнике ABC угол A равен 45°.",
                              settings=engine.settings)
    assert any("LABEL_CONTRADICTS_GEOMETRY" in e for e in r["errors"]), r


def test_label_matches_geometry_no_error():
    # Угол 50°, подписан 50° → ошибок нет.
    # Используем символьную метку (не сравнивается численно) — проще.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "B", "x": 100, "y": 0},
        {"type": "angle_label", "id": "ang_x", "vertex": "A", "ray1": "B",
         "ray2": "C", "text": "x"},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "", settings=engine.settings)
    assert not any("LABEL_CONTRADICTS_GEOMETRY" in e for e in r["errors"])


# ──────────────────────────────────────────────────────────────────────────
# V2 · MARK_CONTRADICTS_GEOMETRY (D4)
# ──────────────────────────────────────────────────────────────────────────

def test_mark_contradicts_geometry():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 200, "y": 100},
        {"type": "free_point", "id": "C", "x": 100, "y": 300},
        {"type": "equal_segments_mark", "id": "eq", "segments": [["A", "B"], ["A", "C"]]},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "", settings=engine.settings)
    assert any("MARK_CONTRADICTS_GEOMETRY" in e for e in r["errors"]), r


# ──────────────────────────────────────────────────────────────────────────
# V3 · MISSING_GIVEN_EQUALITY_MARK_STRICT (D5)
# ──────────────────────────────────────────────────────────────────────────

def test_missing_given_equality_mark_strict():
    plan = _plan([
        {"type": "free_point", "id": "B", "x": 0, "y": 0},
        {"type": "free_point", "id": "D", "x": 100, "y": 0},
        {"type": "free_point", "id": "C", "x": 0, "y": 100},
        {"type": "free_point", "id": "E", "x": 100, "y": 100},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "Оказалось, что BD = CE.",
                              settings=engine.settings)
    assert any("MISSING_GIVEN_EQUALITY_MARK_STRICT" in e for e in r["errors"]), r


def test_three_equal_segments_all_must_be_marked():
    # D4/D5: условие «AK = KL = LC» (3 равных отрезка), но отмечены только
    # AK и KL → дефект: третий отрезок LC без метки.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "K", "x": 100, "y": 0},
        {"type": "free_point", "id": "L", "x": 200, "y": 0},
        {"type": "free_point", "id": "C", "x": 300, "y": 0},
        {"type": "equal_segments_mark", "id": "eq_AK_KL",
         "segments": [["A", "K"], ["K", "L"]]},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "AK = KL = LC.",
                              settings=engine.settings)
    assert any("MISSING_GIVEN_EQUALITY_MARK_STRICT" in e for e in r["errors"]), r
    # В тексте ошибки должен упоминаться недостающий отрезок LC.
    assert any("LC" in e for e in r["errors"]), r


def test_three_equal_segments_fully_marked_no_error():
    # Все 3 отрезка отмечены → ошибки нет.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "K", "x": 100, "y": 0},
        {"type": "free_point", "id": "L", "x": 200, "y": 0},
        {"type": "free_point", "id": "C", "x": 300, "y": 0},
        {"type": "equal_segments_mark", "id": "eq_all",
         "segments": [["A", "K"], ["K", "L"], ["L", "C"]]},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "AK = KL = LC.",
                              settings=engine.settings)
    assert not any("MISSING_GIVEN_EQUALITY_MARK_STRICT" in e for e in r["errors"]), r


# ──────────────────────────────────────────────────────────────────────────
# V4 · LABEL_COLLISION (D2)
# ──────────────────────────────────────────────────────────────────────────

def test_label_collision_detected():
    # Два <text> наложены друг на друга.  Коллизия — warning (presentation),
    # не блокирующая ошибка.
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="500">'
        '<text x="100" y="100" font-size="14">140°</text>'
        '<text x="101" y="101" font-size="14">40°</text>'
        '</svg>'
    )
    plan = _plan([])
    r = audit_rendered_figure(svg, None, plan, "", settings=None)
    assert any("LABEL_COLLISION" in w for w in r["warnings"]), r
    assert not any("LABEL_COLLISION" in e for e in r["errors"]), r


def test_no_collision_when_separated():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="500">'
        '<text x="100" y="100" font-size="14">140°</text>'
        '<text x="300" y="300" font-size="14">40°</text>'
        '</svg>'
    )
    plan = _plan([])
    r = audit_rendered_figure(svg, None, plan, "", settings=None)
    assert not any("LABEL_COLLISION" in e for e in r["warnings"]), r


# ──────────────────────────────────────────────────────────────────────────
# V5 · ANSWER_SPOILER (D3)
# ──────────────────────────────────────────────────────────────────────────

def test_answer_spoiler():
    plan = _plan([
        {"type": "angle_label", "id": "ang1", "vertex": "A", "ray1": "B",
         "ray2": "C", "text": "40°"},
        {"type": "angle_label", "id": "ang2", "vertex": "B", "ray1": "A",
         "ray2": "C", "text": "140°"},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(
        svg, ctx, plan, "Две прямые, угол равен 40°. Найдите ∠ABC.",
        settings=engine.settings,
    )
    assert any("ANSWER_SPOILER" in w for w in r["warnings"]), r


# ──────────────────────────────────────────────────────────────────────────
# V6 · TARGET_NOT_ANNOTATED (D6)
# ──────────────────────────────────────────────────────────────────────────

def test_target_not_annotated():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "D", "x": 200, "y": 100},
        {"type": "free_point", "id": "C", "x": 150, "y": 200},
        {"type": "angle_label", "id": "ang_ADC", "vertex": "D", "ray1": "A",
         "ray2": "C", "text": ""},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "Найдите ∠ADC.", settings=engine.settings)
    assert any("TARGET_NOT_ANNOTATED" in w for w in r["warnings"]), r


def test_clean_figure_positive():
    # Символьные метки, без противоречий → clean=True.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
        {"type": "free_point", "id": "C", "x": 200, "y": 300},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "angle_label", "id": "ang_B", "vertex": "B", "ray1": "A",
         "ray2": "C", "text": "x"},
    ])
    svg, ctx, engine = _build(plan)
    r = audit_rendered_figure(svg, ctx, plan, "", settings=engine.settings)
    assert r["clean"] is True, r
    assert r["visual_score"] >= 0.9, r
