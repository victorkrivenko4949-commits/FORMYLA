# -*- coding: utf-8 -*-
"""Tests for text_normalize + integration with parsers (REC-2/REC-3)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.text_normalize import normalize_condition, normalized_or_original


# ──────────────────────────────────────────────────────────────────────────
# Unit tests
# ──────────────────────────────────────────────────────────────────────────

def test_angle_latex():
    assert normalize_condition(r"угол \(A\) равен \(45^\circ\)") == "угол A равен 45°"


def test_dollar_angle():
    assert normalize_condition(r"$\angle BAC = 45^\circ$") == "∠BAC = 45°"


def test_triangle():
    assert normalize_condition(r"\(\triangle ABC\)") == "треугольник ABC"


def test_bd_ce():
    assert normalize_condition(r"\(BD = CE\)") == "BD = CE"


def test_idempotent():
    samples = [
        r"угол \(A\) равен \(45^\circ\)",
        r"$\angle BAC = 45^\circ$",
        r"\(\triangle ABC\)",
        r"\(BD = CE\)",
        r"45^\circ°",
    ]
    for s in samples:
        once = normalize_condition(s)
        twice = normalize_condition(once)
        assert twice == once, (s, once, twice)


def test_latin_stuck_to_cyrillic():
    assert normalize_condition(r"угол\(A\)") == "угол A"


def test_plain_unchanged():
    assert normalize_condition("Треугольник ABC, угол A равен 45 градусов") == \
        "Треугольник ABC, угол A равен 45 градусов"


def test_degree_collapse():
    assert normalize_condition(r"45^\circ°") == "45°"


# ──────────────────────────────────────────────────────────────────────────
# Integration: REC-2/REC-3 on job-152 condition
# ──────────────────────────────────────────────────────────────────────────

JOB152_CONDITION = (
    "В остроугольном треугольнике \\(ABC\\) угол \\(A\\) равен \\(45^\\circ\\). "
    "Точка \\(O\\) — центр описанной окружности. Прямая \\(BO\\) пересекает "
    "сторону \\(AC\\) в точке \\(D\\), а прямая \\(CO\\) пересекает сторону "
    "\\(AB\\) в точке \\(E\\). Оказалось, что \\(BD = CE\\). Найдите угол \\(B\\)."
)

JOB152_PLAN = {
    "version": 2,
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "circumcircle", "id": "omega", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "circumcenter", "id": "O", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "line", "id": "BO", "p1": "B", "p2": "O"},
        {"type": "line", "id": "CO", "p1": "C", "p2": "O"},
        {"type": "intersect_lines", "id": "D", "line1": "BO", "line2": "AC"},
        {"type": "intersect_lines", "id": "E", "line1": "CO", "line2": "AB"},
        {"type": "segment", "id": "BD", "p1": "B", "p2": "D"},
        {"type": "segment", "id": "CE", "p1": "C", "p2": "E"},
        {"type": "angle_label", "id": "ang_A", "vertex": "A", "ray1": "B",
         "ray2": "C", "text": "45°"},
        {"type": "angle_label", "id": "ang_B", "vertex": "B", "ray1": "A",
         "ray2": "C", "visual_role": "key_point"},
    ],
}


def test_extract_condition_points():
    from services.figure_plan_validator import extract_condition_points
    norm = normalize_condition(JOB152_CONDITION)
    pts = extract_condition_points(norm)
    assert pts == {"A", "B", "C", "D", "E", "O"}, pts


def test_num_angle_re_finds_A_45():
    from services.condition_coverage import _NUM_ANGLE_RE
    norm = normalize_condition(JOB152_CONDITION)
    m = _NUM_ANGLE_RE.search(norm)
    assert m is not None
    assert m.group(1) == "A" and float(m.group(2)) == 45.0


def test_resolve_angle_triple_A():
    from services.visual_audit import resolve_angle_triple
    norm = normalize_condition(JOB152_CONDITION)
    triple = resolve_angle_triple("A", JOB152_PLAN, norm)
    assert triple == ("B", "A", "C") or triple == ("C", "A", "B"), triple


def test_check_condition_coverage_returns_not_realized():
    from services.condition_coverage import check_condition_coverage
    from geometric_engine.engine import GeometricEngine
    norm = normalize_condition(JOB152_CONDITION)
    engine = GeometricEngine()
    _, ctx = engine.build(JOB152_PLAN)
    cov = check_condition_coverage(norm, JOB152_PLAN, build_context=ctx,
                                   settings=engine.settings)
    assert any(e.startswith("CONDITION_NOT_REALIZED") for e in cov.get("errors", [])), cov


def test_verify_answer_mismatch():
    from services.answer_verifier import verify_answer
    from geometric_engine.engine import GeometricEngine
    norm = normalize_condition(JOB152_CONDITION)
    engine = GeometricEngine()
    _, ctx = engine.build(JOB152_PLAN)
    solver = {
        "target": {"kind": "angle", "object": "B"},
        "answer": {"value": 67.5, "is_numeric": True},
    }
    r = verify_answer(solver, ctx, JOB152_PLAN, condition_text=norm,
                      settings=engine.settings)
    assert r["verdict"] == "mismatch", r
