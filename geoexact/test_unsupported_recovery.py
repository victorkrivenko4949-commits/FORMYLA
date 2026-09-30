"""Do not claim a verified diagram when OCR drops an angle function."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.constructions import execute
from geoexact.core.gates import constraint_residual
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan, PlanError, validate_plan
from geoexact.core.semantics import (
    _TRISECTOR_PREFIX, preflight_condition_error, semantic_failures,
    trisected_parallel_plan,
)
from geoexact.core.solver import residuals

VALID = _TRISECTOR_PREFIX + "если BC = 12, cos(2∠CAN) = -1/4."
OCR = _TRISECTOR_PREFIX + "если BC = 12, (2∠CAN) = -1/4."


def test_bare_negative_angle_is_diagnosed_before_model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("invalid OCR must not call an LLM"))
    result = generate(OCR, sess=object(), use_cache=False)
    # The figure is still drawn as a sketch; the impossible value is reported
    # and never used as a constraint.
    assert result.ok and result.verification == "sketch"
    assert result.measured is None
    assert result.warnings[0].startswith("INVALID_CONDITION:")
    assert "возможно, перед скобкой пропущено cos" in result.warnings[0]
    assert {"M", "N"} <= set(result.plan["points"])
    assert preflight_condition_error(VALID) is None
    assert preflight_condition_error(
        _TRISECTOR_PREFIX + "если BC = 12, sin(2∠CAN) = -1/4."
    ) is None
    assert preflight_condition_error(
        _TRISECTOR_PREFIX + "если BC = 12, cos(2∠CAN) = -5/4."
    )


def test_worker_reports_actionable_ocr_error():
    env = dict(os.environ, DEEPSEEK_API_KEY="offline-placeholder")
    p = subprocess.run(
        [sys.executable, "-m", "geoexact.worker"],
        input=json.dumps({"problem": OCR, "with_aux": False}),
        text=True, capture_output=True, env=env, timeout=15,
    )
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["ok"] and data["verification"] == "sketch"
    assert "пропущено cos" in data["warnings"][0]
    assert "plan" not in data


@pytest.mark.parametrize("aux", [False, True])
def test_trisector_cosine_builds_verified_geometry_without_model(aux, monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("recognized figure must not call an LLM"))
    result = generate(VALID, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.warnings == []
    assert result.usage == []
    assert result.measured == pytest.approx(4 * math.sqrt(6), rel=1e-6)
    assert result.measurement_range[1] - result.measurement_range[0] < 1e-5
    # CD contains A: a group with a split member is not drawn, and there is no bracket
    assert result.svg.count('class="tick') == 3
    assert 'data-kind="span"' not in result.svg
    assert result.plan["target"] == {"kind": "dist", "args": ["A", "B"]}
    assert len(result.plan["draw"]["aux_segments"]) == int(aux)


def test_cos_double_angle_constraint_is_checked_independently():
    plan = trisected_parallel_plan(VALID, False)
    assert plan is not None
    validate_plan(plan)
    coords = execute(plan, free_values=np.array([0., 0., 12., 0., 14., 4.]))
    value = next(c.value for c in plan.constraints if c.type == "cos_double_angle")
    assert constraint_residual("cos_double_angle",
                               [coords[n] for n in ("C", "A", "N")],
                               value, 12) > 0.01
    assert max(abs(x) for x in residuals(plan, coords)) > 0.01
    broken = plan.to_dict()
    next(c for c in broken["constraints"] if c["type"] == "cos_double_angle"
         )["value"] = 1.1
    with pytest.raises(PlanError, match="BAD_VALUE"):
        validate_plan(FigurePlan.from_dict(broken))


def test_semantics_catch_omitted_model_constraints_and_wrong_extension():
    plan = trisected_parallel_plan(VALID, False)
    coords = execute(plan, free_values=np.array([0., 0., 12., 0., 14., 4.]))
    assert any("cos(2∠CAN)" in s for s in semantic_failures(VALID, plan, coords))
    coords["M"] = coords["M"] + np.array([0., 0.5])
    coords["D"] = coords["A"] - (coords["A"] - coords["C"]) / 2
    failures = semantic_failures(VALID, plan, coords)
    assert any("M и N" in s for s in failures)
    assert any("MD не параллельна AN" in s for s in failures)
    assert any("D не лежит на продолжении" in s for s in failures)


def test_augmented_text_cannot_silently_use_special_plan():
    assert trisected_parallel_plan(VALID + " Также дан угол B=60°.", False) is None
    latex = VALID.replace("cos(2∠CAN)", r"\cos(2\angle CAN)").replace("-1/4", r"-\frac{1}{4}")
    assert trisected_parallel_plan(latex, False) is not None
    wrapped = VALID.replace("cos(2∠CAN)", r"\operatorname{cos}(2\angle CAN)")
    assert trisected_parallel_plan(r"\(" + wrapped + r"\)", False) is not None


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_photo_display_does_not_erase_math_operators():
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function latexToPlain(src)');
const end = source.indexOf('  // Сжатие/конвертация фото', start);
if (start < 0 || end < 0) throw new Error('OCR formatter not found');
const format = new Function(source.slice(start, end) + ';return latexToPlain;')();
const examples = [
  String.raw`\cos(2\angle CAN)=-\frac{1}{4}`,
  String.raw`\operatorname{cos}(2\angle CAN)=-\frac{1}{4}`,
  String.raw`\sin(\angle ABC)=1/2`,
  String.raw`\foo(2\angle CAN)=1/2`
].map(format);
console.log(JSON.stringify(examples));
"""
    js = Path(__file__).parent / "static" / "draw.js"
    p = subprocess.run(["node", "-e", script, str(js)],
                       text=True, capture_output=True, timeout=10)
    assert p.returncode == 0, p.stderr
    plain = json.loads(p.stdout)
    assert plain[0] == "cos(2∠ CAN)=-1/4"
    assert plain[1] == plain[0]
    assert plain[2].startswith("sin(")
    assert plain[3].startswith(r"\foo(")


def test_model_refusal_gets_a_recovery_attempt(monkeypatch):
    text = VALID + " Постройте ту же фигуру."
    assert trisected_parallel_plan(text, False) is None
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    seen = []

    def fake_formalize(sess, problem, cls, aux, budget, feedback="", prev_code=""):
        seen.append((feedback, prev_code))
        if len(seen) == 1:
            raise PlanError("UNSUPPORTED_CONSTRUCTION", "параллель и удвоенный угол")
        return trisected_parallel_plan(VALID, False), []

    monkeypatch.setattr(llm, "formalize", fake_formalize)
    result = generate(text, sess=object(), use_cache=False, max_retries=1)
    assert result.ok, (result.reason, result.detail)
    assert len(seen) == 2 and seen[1][1] == "UNSUPPORTED_CONSTRUCTION"
