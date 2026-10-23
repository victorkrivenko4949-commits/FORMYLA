# -*- coding: utf-8 -*-
"""Tests for CH15: condition → solution two-layer figure pipeline.

Covers the deterministic layer (no LLM/network):

  - base/aux invariant validation (services.figure_plan_validator)
  - prompt loading (routes.figures_generator)
  - solution step numbering
  - base+aux merge for the engine
  - pydantic schemas parse/fallback

Tests do NOT call DeepSeek/Novita — they exercise only the deterministic
parts of the new pipeline.
"""

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────

def _base_plan():
    """Base-план: треугольник ABC + медиана AM (всё из условия)."""
    return {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 400},
            {"type": "free_point", "id": "B", "x": 500, "y": 400},
            {"type": "free_point", "id": "C", "x": 300, "y": 80},
            {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
            {"type": "midpoint", "id": "M", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},
        ],
    }


def _aux_plan():
    """Aux-план: высота BH (пунктир, style=aux, с evidence)."""
    return {
        "has_aux": True,
        "reason": "Опустим высоту BH на сторону AC.",
        "constructions": [
            {
                "type": "altitude",
                "id": "aux_altitude_BH",
                "vertex": "B",
                "side_a": "A",
                "side_b": "C",
                "dashed": True,
                "style": "aux",
                "purpose": "Создать прямоугольные треугольники ABH и CBH",
                "solution_evidence": {
                    "step_no": 2,
                    "quote": "Опустим высоту BH на сторону AC",
                },
            }
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
# 1. Deterministic invariant validation
# ──────────────────────────────────────────────────────────────────────────

class TestInvariantValidation:

    def test_valid_base_and_aux(self):
        from services.figure_plan_validator import validate_condition_solution
        r = validate_condition_solution(_base_plan(), _aux_plan())
        assert r["valid"] is True, r.get("errors")

    def test_base_leak_dashed_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        base = _base_plan()
        base["constructions"].append(
            {"type": "segment", "id": "leak", "p1": "A", "p2": "C", "dashed": True}
        )
        r = validate_condition_solution(base, _aux_plan())
        assert r["valid"] is False
        assert any("BASE_LEAK" in e for e in r["errors"])

    def test_base_leak_style_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        base = _base_plan()
        base["constructions"].append(
            {"type": "segment", "id": "leak", "p1": "A", "p2": "C", "style": "aux"}
        )
        r = validate_condition_solution(base, _aux_plan())
        assert r["valid"] is False
        assert any("BASE_LEAK" in e for e in r["errors"])

    def test_aux_missing_dashed_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        aux["constructions"][0]["dashed"] = False
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("dashed=true" in e for e in r["errors"])

    def test_aux_missing_style_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        del aux["constructions"][0]["style"]
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("STYLE" in e for e in r["errors"])

    def test_aux_missing_purpose_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        del aux["constructions"][0]["purpose"]
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("purpose" in e for e in r["errors"])

    def test_aux_missing_evidence_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        del aux["constructions"][0]["solution_evidence"]
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("solution_evidence" in e for e in r["errors"])

    def test_aux_missing_quote_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        aux["constructions"][0]["solution_evidence"]["quote"] = ""
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("quote" in e for e in r["errors"])

    def test_aux_redefines_base_id_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        aux["constructions"][0]["id"] = "A"  # конфликт с base
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("BASE_OVERRIDE" in e for e in r["errors"])

    def test_aux_unknown_reference_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        aux["constructions"][0]["side_a"] = "ZZZ"  # не существует
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("INVALID_REFERENCE" in e for e in r["errors"])

    def test_has_aux_false_with_constructions_rejected(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _aux_plan()
        aux["has_aux"] = False
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is False
        assert any("INCONSISTENT_AUX" in e for e in r["errors"])

    def test_no_aux_valid(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {"has_aux": False, "reason": "Не требуется", "constructions": []}
        r = validate_condition_solution(_base_plan(), aux)
        assert r["valid"] is True


# ──────────────────────────────────────────────────────────────────────────
# 2. Base + aux merge for the engine
# ──────────────────────────────────────────────────────────────────────────

class TestMerge:

    def test_merge_preserves_base_order(self):
        from services.figure_plan_validator import merge_base_aux
        base = _base_plan()
        aux = _aux_plan()
        merged = merge_base_aux(base, aux)
        base_ids = [c["id"] for c in base["constructions"]]
        merged_ids = [c["id"] for c in merged["constructions"]]
        # base идёт первым, aux в конце
        assert merged_ids[:len(base_ids)] == base_ids
        assert "aux_altitude_BH" in merged_ids
        assert merged_ids.index("aux_altitude_BH") > merged_ids.index("AM")


# ──────────────────────────────────────────────────────────────────────────
# 3. Solution step numbering
# ──────────────────────────────────────────────────────────────────────────

class TestNumbering:

    def test_numbers_paragraphs(self):
        from routes.figures_generator import _number_solution_steps
        out = _number_solution_steps("Опустим высоту BH.\nРассмотрим треугольник.")
        assert out.startswith("S1. ")
        assert "S2. " in out

    def test_keeps_existing_numbering(self):
        from routes.figures_generator import _number_solution_steps
        text = "1. Опустим высоту.\n2. Рассмотрим."
        assert _number_solution_steps(text) == text

    def test_empty_solution(self):
        from routes.figures_generator import _number_solution_steps
        assert _number_solution_steps("") == ""
        assert _number_solution_steps("   ") == ""


# ──────────────────────────────────────────────────────────────────────────
# 4. Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────

class TestSchemas:

    def test_parse_base_plan(self):
        from services.figure_plan_schemas import parse_base_plan
        p = parse_base_plan(json.dumps(_base_plan()))
        assert p is not None
        assert p["version"] == 2
        assert isinstance(p["constructions"], list)

    def test_parse_aux_plan(self):
        from services.figure_plan_schemas import parse_aux_plan
        p = parse_aux_plan(json.dumps(_aux_plan()))
        assert p is not None
        assert p["has_aux"] is True

    def test_parse_audit_result(self):
        from services.figure_plan_schemas import parse_audit_result
        p = parse_audit_result(json.dumps({"approved": True, "issues": []}))
        assert p is not None
        assert p["approved"] is True

    def test_parse_invalid_json_returns_none(self):
        from services.figure_plan_schemas import parse_base_plan
        assert parse_base_plan("not json") is None
        assert parse_base_plan("") is None


# ──────────────────────────────────────────────────────────────────────────
# 5. Model fields exist (no migration needed at import time)
# ──────────────────────────────────────────────────────────────────────────

class TestModelFields:

    def test_figure_build_job_has_new_columns(self):
        from models import FigureBuildJob
        cols = [c.name for c in FigureBuildJob.__table__.columns]
        for expected in [
            'solution_text', 'generation_mode', 'current_stage',
            'base_model', 'aux_model', 'audit_model',
            'base_plan_json', 'aux_plan_json', 'audit_json',
        ]:
            assert expected in cols, f"missing column {expected}"
