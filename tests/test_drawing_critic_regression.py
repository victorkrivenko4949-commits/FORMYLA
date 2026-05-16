# -*- coding: utf-8 -*-
# Regression tests for the two production bugs found on 2026-05-15
# (see docs/CRITIC_AB_TEST_REPORT.md).
#
#   Bug #1: MODEL_CRITIC pointed to a model ID that does NOT exist in
#           OpenRouter ("google/gemini-3.1-pro").  Anything not in the
#           OpenRouter catalog returns HTTP 400, the pipeline silently
#           degrades, and the critic loop never produces a finding.
#           These tests pin the model ID to the *-preview SKU that
#           actually exists, and require pricing/RPM entries so we can
#           spot the next time someone bumps MODEL_CRITIC without also
#           updating the catalog.
#
#   Bug #2: _critique_with_gemini called the LLM with max_tokens=1500.
#           Gemini 3.x is a thinking model: it spends ~1500-2000 tokens
#           on hidden reasoning_tokens (billed but NOT returned in
#           `content`).  With max_tokens=1500, the JSON answer truncates
#           mid-string, _parse_critique_response catches the resulting
#           JSONDecodeError, and silently returns [].  The critic
#           appeared to work but never produced findings.

import json
import os

import pytest


# ============================================================== Bug #1
# Model ID hygiene -- catch the next "I renamed it but forgot pricing"
# regression as soon as it lands, not when CRITIC_ENABLED flips on prod.

def test_model_critic_id_is_preview_alias():
    # The bare "google/gemini-3.1-pro" alias does NOT exist on OpenRouter
    # as of 2026-05-15.  If you bump this, replace the *-preview SKU with
    # whatever stable name OpenRouter exposes -- and update RPM/PRICING
    # in services/openrouter_client.py at the same time.
    from services.drawing_service import MODEL_CRITIC
    assert MODEL_CRITIC, "MODEL_CRITIC must be set"
    assert "preview" in MODEL_CRITIC or MODEL_CRITIC.endswith("-stable"), (
        "MODEL_CRITIC should point at a real OpenRouter SKU; "
        "current value " + repr(MODEL_CRITIC) + " looks like a bare alias"
    )


def test_model_critic_has_pricing_and_rpm():
    # If MODEL_CRITIC isn't in MODEL_PRICING, cost_usd silently logs as
    # $0.0000 in drawing_generations.cost_usd (we already lost a few
    # dollars worth of opus-4.7 calls that way -- see openrouter_client
    # v2.5 hotfix).  Same logic for DEFAULT_RPM: missing entry means the
    # rate limiter falls back to 30 RPM which may not match reality.
    from services.drawing_service import MODEL_CRITIC
    from services.openrouter_client import DEFAULT_RPM, MODEL_PRICING
    assert MODEL_CRITIC in MODEL_PRICING, (
        "Add a MODEL_PRICING entry for " + MODEL_CRITIC
    )
    assert MODEL_CRITIC in DEFAULT_RPM, (
        "Add a DEFAULT_RPM entry for " + MODEL_CRITIC
    )
    in_per_m, out_per_m = MODEL_PRICING[MODEL_CRITIC]
    assert in_per_m > 0 and out_per_m > 0, (
        "MODEL_PRICING for " + MODEL_CRITIC + " must be non-zero"
    )


# ============================================================== Bug #2
# Token-budget hygiene -- a 1500-token call to a Gemini-3.x style
# thinking model is guaranteed to truncate mid-answer.

def test_critique_max_tokens_is_thinking_model_safe():
    # Read the actual constant by parsing the source -- we don't want to
    # call the real API in unit tests, but we DO want the test to fail
    # if someone reverts the value back to 1500.  We must skip occurrences
    # inside comments (the bug-postmortem text quotes "max_tokens=1500")
    # and only look at the live keyword argument to openrouter.chat().
    import ast
    import inspect
    from services import drawing_service as ds

    src = inspect.getsource(ds._critique_with_gemini)
    tree = ast.parse(src)

    found_values = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords or []:
            if kw.arg == "max_tokens" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, int):
                    found_values.append(kw.value.value)

    assert found_values, (
        "could not find a max_tokens=<int> keyword argument in any call "
        "inside _critique_with_gemini"
    )
    # If there are several, take the minimum -- ANY value <3000 is unsafe.
    smallest = min(found_values)
    assert smallest >= 3000, (
        "max_tokens=" + str(smallest) + " is unsafe for a thinking model "
        "(Gemini 3.x spends 1500-2000 tokens on hidden reasoning before "
        "emitting a single content token). Use >= 3000 (we ship 6000)."
    )


def test_parse_critique_response_truncated_yields_empty():
    # Exactly the kind of payload we saw with max_tokens=1500: the JSON
    # got cut in the middle of a string value.  Parser must NOT raise --
    # it should degrade to [] so the pipeline can fall through to the
    # current PNG.
    from services.drawing_service import _parse_critique_response
    truncated = (
        '\n  "findings": [\n    '
        '\n      "id": "f1",\n'
        '      "severity": "blocker",\n'
        '      "title": "Missing circumscribed circle",\n'
        '      "detail": "Statement explicitly asks for an inscribed circle aroun'
    )
    # prepend "{" via concatenation so the source itself stays simple
    truncated = "{" + truncated
    out = _parse_critique_response(truncated)
    assert out == [], "truncated JSON must degrade to [] without raising"


def test_parse_critique_response_full_payload_yields_all_findings():
    # Build a realistic 3-finding payload via json.dumps() to avoid having
    # to type curly braces inline (some editors mangle them).
    from services.drawing_service import _parse_critique_response
    payload = dict(findings=[
        dict(id="f1", severity="blocker", title="no circle",
             detail="circumscribed circle is missing",
             fix_hint="add plt.Circle((cx,cy), R)"),
        dict(id="f2", severity="major", title="H off-axis",
             detail="for an isoceles triangle H must lie on the symmetry axis",
             fix_hint="recompute H via A+B+C-2O"),
        dict(id="f3", severity="minor", title="label collision",
             detail="M and H1 labels overlap",
             fix_hint="offset M label upward"),
    ])
    raw = "Some preamble text...\n" + json.dumps(payload) + "\ntrailing junk"
    out = _parse_critique_response(raw)
    assert len(out) == 3
    ids = [f.id for f in out]
    assert ids == ["f1", "f2", "f3"]
    assert out[0].severity == "blocker"
    assert out[1].severity == "major"
    assert out[2].severity == "minor"


# ============================================================== Integration
# Optional online check that talks to the real OpenRouter.  Skipped in CI
# unless OPENROUTER_API_KEY is set.  Run locally with:
#   pytest tests/test_drawing_critic_regression.py -v -m integration

needs_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="needs OPENROUTER_API_KEY in env",
)


@pytest.mark.integration
@needs_key
def test_critic_actually_finds_things_on_broken_drawing():
    # Sanity: with both fixes applied, the live critic must return >= 1
    # finding for a chart that is missing 3 required objects.  If this
    # ever starts returning [], either the system prompt got softened
    # too much or max_tokens regressed again.
    import pathlib
    from services.drawing_service import _critique_with_gemini

    root = pathlib.Path(__file__).resolve().parents[1]
    problem = (root / "scripts" / "_critic_ab_problem.txt").read_text(
        encoding="utf-8").strip()
    code = (root / "scripts" / "_critic_ab_out" /
            "broken.code.py").read_text(encoding="utf-8")
    png = (root / "scripts" / "_critic_ab_out" / "broken.png").read_bytes()

    findings, cost = _critique_with_gemini(problem, code, png)
    assert len(findings) >= 1, (
        "live critic returned no findings on a deliberately broken drawing "
        "-- regression of bug #2 (max_tokens) or bug #1 (model id), or "
        "the system prompt has been softened. Investigate."
    )
    # All five categories the critic is supposed to detect should be at
    # least covered by SOMETHING in the findings list (we don't pin
    # exact wording -- model output drifts).
    assert cost > 0, "cost should be > 0 if the API call really happened"


# ============================================================== Bug #3
# Token-budget hygiene for the MAIN code-generation call.
#
# 2026-05-16 incident ("nine-point Euler circle"): _call_llm shipped
# with max_tokens=2048.  Once we added the QW-1 plan-and-asserts prompt
# AND the architect spec as system context, Claude's reply is routinely
# 120-180 lines of Python -- which overflows 2048 tokens.  Anthropic
# silently truncates mid-line, the AST pre-check fails on every repair
# iteration with the SAME syntax error, MAX_REPAIR_ITERS exhausts, and
# the user sees "SandboxRejected".  Raising to 8000 fixed it (verified
# locally: 4 -> 0 repair iters, $2.02 -> $0.96 on the same task).
# Anything below 4000 is unsafe with the current prompts.

def test_call_llm_max_tokens_is_long_program_safe():
    import ast
    import inspect
    from services import drawing_service as ds

    src = inspect.getsource(ds._call_llm)
    tree = ast.parse(src)

    found_values = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords or []:
            if kw.arg == "max_tokens" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, int):
                    found_values.append(kw.value.value)

    assert found_values, (
        "could not find a max_tokens=<int> keyword argument in any call "
        "inside _call_llm"
    )
    smallest = min(found_values)
    assert smallest >= 4000, (
        "max_tokens=" + str(smallest) + " is unsafe for _call_llm.  With "
        "the QW-1 plan+asserts prompt plus the architect spec, Claude's "
        "drawing programmes routinely exceed 2048 tokens and get "
        "truncated mid-line, causing infinite repair loops on hard "
        "tasks (see 2026-05-16 nine-point-circle incident).  Use >= 4000 "
        "(we ship 8000)."
    )
