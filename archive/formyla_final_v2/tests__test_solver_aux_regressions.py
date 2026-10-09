# -*- coding: utf-8 -*-
"""Регрессионные тесты фиксов E8/E9/E10 конвейера ФОРМУЛА.

Запуск:
  cd <проект>
  python -m pytest tests/test_solver_aux_regressions.py -v
  # или без pytest:
  python tests/test_solver_aux_regressions.py
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from services.aux_compiler import compile_solver_aux
from services.base_normalizer import normalize_base_plan

FX = os.path.join(HERE, "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


# --- E10: base-стиль нормализован (всё данное = solid) ---

def test_e10_base_style_normalized():
    """normalize_base_plan делает все base-объекты solid (style=base, dashed=False)."""
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    bad = [c for c in base["constructions"] if c.get("style") == "aux" or c.get("dashed")]
    bm = next((c for c in base["constructions"] if c.get("id") == "BM"), None)
    assert len(bad) == 0, f"base-объекты не должны быть style=aux/dashed: {bad}"
    assert bm is not None and bm.get("style") == "base" and not bm.get("dashed"), \
        f"медиана BM должна быть solid, получено: {bm}"


# --- E8: solver пере-диктует данное → пропускается, без краша ---

def test_e8_duplicate_median_skipped():
    """solver продиктовал медиану BM как aux; foot_id M уже в base —
    компилятор пропускает её (FULFILLED_BY_BASE), не падая."""
    solver = _load("solver_parallelogram.json")
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    aux, issues = compile_solver_aux(solver, base)
    assert any("FULFILLED_BY_BASE" in str(i) and "median:M" in str(i) for i in issues), \
        f"должно быть FULFILLED_BY_BASE:median:M, issues={issues}"
    assert aux.get("has_aux") is True, "aux не пустой (есть point K)"
    assert all("уже существует" not in str(i) for i in issues), \
        f"не должно быть 'уже существует': {issues}"


# --- E9: line_extension эмитит видимый отрезок продления ---

def test_e9_line_extension_emits_segment():
    """line_extension → reflect_point эмитит видимый отрезок продления
    (center→id), иначе точка K повисает без линии."""
    solver = _load("solver_parallelogram.json")
    base = normalize_base_plan(_load("base_plan_parallelogram.json"))
    aux, _ = compile_solver_aux(solver, base)
    ext = [c for c in aux.get("constructions", []) if c.get("id", "").startswith("aux_ext_")]
    assert len(ext) >= 1, f"должен эмитить >=1 отрезок продления, constructions={aux.get('constructions')}"
    assert any(c.get("p1") == "M" and c.get("p2") == "K" for c in ext), \
        f"отрезок продления должен быть M-K: {ext}"
    assert all(c.get("style") == "aux" and c.get("dashed") for c in ext), \
        f"отрезок продления должен быть aux/dashed: {ext}"


# --- Регресс: ложное утверждение → нет aux ---

def test_false_statement_no_aux():
    """Ложное утверждение (CH=AM ⇒ A=2B): solver solvable=false,
    aux пустой, base нормализован (стиль solid)."""
    solver = _load("solver_cham_false.json")
    base_raw = {"constructions": [
        {"type": "free_point", "id": "A", "x": 150, "y": 100, "label": "A"},
        {"type": "free_point", "id": "B", "x": 430, "y": 110, "label": "B"},
        {"type": "free_point", "id": "C", "x": 300, "y": 420, "label": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B", "style": "aux", "dashed": True},
        {"type": "altitude", "id": "alt_CH", "vertex": "C", "side_a": "A", "side_b": "B", "foot_id": "H"},
        {"type": "segment", "id": "CH", "p1": "C", "p2": "H", "style": "aux", "dashed": True},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M", "style": "aux", "dashed": True},
    ]}
    base = normalize_base_plan(base_raw)
    aux, issues = compile_solver_aux(solver, base)
    bad = [c for c in base["constructions"] if c.get("style") == "aux" or c.get("dashed")]
    assert solver.get("solvable") is False, "утверждение должно быть solvable=false"
    assert aux.get("has_aux") is False, "для ложного утверждения aux должен быть пустым"
    assert len(bad) == 0, f"base должен быть нормализован (0 aux-styled): {bad}"


def test_e11_segment_duplicate_skipped():
    """solver пере-диктовал данное (медиану AM) как segment aux —
    компилятор пропускает его (FULFILLED_BY_BASE:segment:AM),
    не кладя пунктирную aux-копию поверх сплошного данного."""
    base_raw = {"constructions": [
        {"type": "free_point", "id": "A", "x": 150, "y": 150, "label": "A"},
        {"type": "free_point", "id": "B", "x": 150, "y": 400, "label": "B"},
        {"type": "free_point", "id": "C", "x": 400, "y": 150, "label": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C", "label": "M"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},  # данное
    ]}
    base = normalize_base_plan(base_raw)
    solver = {
        "solvable": True, "aux_needed": True, "confidence": 0.9,
        "aux_constructions": [
            {"op": "segment", "points": ["A", "M"], "step_no": 1,
             "purpose": "провести медиану", "quote": "Проведём медиану AM."},
        ],
    }
    aux, issues = compile_solver_aux(solver, base)
    assert any("FULFILLED_BY_BASE:segment:AM" in str(i) for i in issues), \
        f"должно быть FULFILLED_BY_BASE:segment:AM, issues={issues}"
    assert not any(c.get("type") == "segment" and c.get("id", "").startswith("aux_")
                  and {c.get("p1"), c.get("p2")} == {"A", "M"}
                  for c in aux.get("constructions", [])), \
        f"aux-сегмент AM не должен дублироваться: {aux.get('constructions')}"


if __name__ == "__main__":
    tests = [
        ("E10 base_style_normalized", test_e10_base_style_normalized),
        ("E8 duplicate_median_skipped", test_e8_duplicate_median_skipped),
        ("E9 line_extension_emits_segment", test_e9_line_extension_emits_segment),
        ("E11 segment_duplicate_skipped", test_e11_segment_duplicate_skipped),
        ("false_statement_no_aux", test_false_statement_no_aux),
    ]
    npass = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            npass += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
    print(f"\n{npass}/{len(tests)} passed")
    sys.exit(0 if npass == len(tests) else 1)
