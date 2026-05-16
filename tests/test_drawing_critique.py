# -*- coding: utf-8 -*-
# Tests for the Gemini-critique stage of services.drawing_service.
#
# We monkeypatch:
#   - drawing_service._call_llm        : the Claude-side LLM call
#   - drawing_service._critique_with_gemini : the vision critic
#
# Scenarios covered:
#   1. clean_first_try   : critic returns [] -> no revision, rounds == 0
#   2. one_accepted      : critic returns 1 finding -> Claude accepts and fixes
#   3. one_rejected      : critic returns 1 finding -> Claude rejects, keeps code
#   4. give_up           : critic keeps finding bugs every round -> rounds maxed
#   5. critic_transport_error : critic raises OpenRouterError -> degrade gracefully

import os
import shutil
import tempfile
import pytest

from services.drawing_service import (
    CritiqueFinding,
    MAX_CRITIQUE_ROUNDS,
)


# ----------------------------------------------------------------- guards
def _matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _matplotlib_available(),
    reason="matplotlib/numpy not installed in test env",
)


# ----------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _enable_critic(monkeypatch):
    from services import drawing_service as ds
    monkeypatch.setattr(ds, "CRITIC_ENABLED", True)
    # Architect and cosmetic critic default to the same value as the
    # main critic at import time.  Since CRITIC_ENABLED is now True by
    # default, both of these stages may try to hit the real OpenRouter
    # API during tests.  Disable them explicitly here and stub the
    # architect call to keep these unit tests hermetic.
    monkeypatch.setattr(ds, "ARCHITECT_ENABLED", False)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", False)
    monkeypatch.setattr(
        ds, "_get_architect_spec", lambda problem: (None, 0.0)
    )


@pytest.fixture
def temp_root():
    root = tempfile.mkdtemp(prefix="drw_crit_")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


# A minimal valid matplotlib snippet — always renders to a small PNG.
VALID_CODE_V1 = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "fig, ax = plt.subplots(figsize=(6, 6), dpi=110)\n"
    "ax.set_aspect('equal'); ax.axis('off')\n"
    "ax.plot([0, 5], [0, 0], 'k-', lw=2)\n"
    "ax.text(2.5, 0.2, 'V1', fontsize=18)\n"
    "ax.set_xlim(-1, 6); ax.set_ylim(-1, 1)\n"
)
VALID_CODE_V2 = VALID_CODE_V1.replace("'V1'", "'V2'")
VALID_CODE_V3 = VALID_CODE_V1.replace("'V1'", "'V3'")


def _wrap(code: str, decisions_json: str = "") -> str:
    body = ""
    if decisions_json:
        body = decisions_json + "\n\n"
    return body + "```python\n" + code + "\n```"


# ----------------------------------------------------------------- 1. clean
def test_clean_first_try(monkeypatch, temp_root):
    from services import drawing_service as ds

    claude_calls = {"n": 0}
    critic_calls = {"n": 0}

    def fake_llm(messages, model):
        claude_calls["n"] += 1
        return {"content": _wrap(VALID_CODE_V1), "cost_usd": 0.0, "model": model}

    def fake_critic(problem, code, png):
        critic_calls["n"] += 1
        return [], 0.0

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_critic)

    res = ds.generate_drawing("clean test", app_root=temp_root, use_cache=False)

    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert res.critique_rounds == 0
    assert res.critique_findings == []
    assert res.critique_accepted == 0
    assert res.critique_rejected == 0
    assert claude_calls["n"] == 1, "Claude called more than once"
    assert critic_calls["n"] == 1, "Critic should run exactly once on clean PNG"


# ----------------------------------------------------------------- 2. accepted
def test_one_finding_accepted(monkeypatch, temp_root):
    from services import drawing_service as ds

    # First Claude call returns V1, second returns V2 (post-fix).
    claude_responses = [
        _wrap(VALID_CODE_V1),
        _wrap(
            VALID_CODE_V2,
            decisions_json='{"decisions": [{"id": "f1",'
                           ' "decision": "accepted",'
                           ' "reason": "ок, поправил подпись"}]}',
        ),
    ]
    claude_idx = {"i": 0}

    def fake_llm(messages, model):
        i = claude_idx["i"]
        claude_idx["i"] = i + 1
        return {"content": claude_responses[min(i, len(claude_responses) - 1)],
                "cost_usd": 0.0, "model": model}

    critic_responses = [
        [CritiqueFinding(id="f1", severity="major",
                         title="неверная подпись",
                         detail="V1 должно быть V2", fix_hint="замени V1 -> V2")],
        [],  # after Claude's fix
    ]
    critic_idx = {"i": 0}

    def fake_critic(problem, code, png):
        i = critic_idx["i"]
        critic_idx["i"] = i + 1
        return critic_responses[min(i, len(critic_responses) - 1)], 0.0

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_critic)

    res = ds.generate_drawing("accepted test", app_root=temp_root, use_cache=False)

    assert res.critique_rounds == 1
    assert len(res.critique_findings) == 1
    assert res.critique_findings[0].claude_decision == "accepted"
    assert res.critique_accepted == 1
    assert res.critique_rejected == 0
    assert "V2" in res.code  # Claude actually applied the fix
    assert claude_idx["i"] == 2
    assert critic_idx["i"] == 2


# ----------------------------------------------------------------- 3. rejected
def test_one_finding_rejected(monkeypatch, temp_root):
    from services import drawing_service as ds

    # Claude returns the SAME code both times and rejects the finding.
    claude_responses = [
        _wrap(VALID_CODE_V1),
        _wrap(
            VALID_CODE_V1,  # unchanged
            decisions_json='{"decisions": [{"id": "f1",'
                           ' "decision": "rejected",'
                           ' "reason": "условие задачи допускает V1"}]}',
        ),
    ]
    claude_idx = {"i": 0}

    def fake_llm(messages, model):
        i = claude_idx["i"]
        claude_idx["i"] = i + 1
        return {"content": claude_responses[min(i, len(claude_responses) - 1)],
                "cost_usd": 0.0, "model": model}

    # Critic keeps complaining about the same issue — but pipeline must stop
    # after MAX_CRITIQUE_ROUNDS regardless, even if Claude rejects.
    critic_calls = {"n": 0}

    def fake_critic(problem, code, png):
        critic_calls["n"] += 1
        return [CritiqueFinding(id="f1", severity="minor",
                                title="подпись не такая",
                                detail="ожидалось V2",
                                fix_hint="замени V1 -> V2")], 0.0

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_critic)

    res = ds.generate_drawing("rejected test", app_root=temp_root, use_cache=False)

    # After MAX_CRITIQUE_ROUNDS = 2 we definitely stop.
    assert res.critique_rounds == MAX_CRITIQUE_ROUNDS
    # The code never changed — V1 stayed.
    assert "V1" in res.code
    assert "V2" not in res.code
    # All findings recorded; the last applied decision is "rejected".
    assert any(f.claude_decision == "rejected" for f in res.critique_findings)
    assert res.critique_rejected >= 1


# ----------------------------------------------------------------- 4. give_up
def test_give_up_after_max_rounds(monkeypatch, temp_root):
    # Critic always finds a different issue.  After MAX_CRITIQUE_ROUNDS the
    # pipeline must return the latest PNG (no exception).
    from services import drawing_service as ds

    versions = [VALID_CODE_V1, VALID_CODE_V2, VALID_CODE_V3]
    claude_idx = {"i": 0}

    def fake_llm(messages, model):
        i = min(claude_idx["i"], len(versions) - 1)
        claude_idx["i"] += 1
        return {"content": _wrap(versions[i]), "cost_usd": 0.0, "model": model}

    def fake_critic(problem, code, png):
        # Always one fresh major finding.
        return [CritiqueFinding(id="f" + str(claude_idx["i"]),
                                severity="major",
                                title="ещё ошибка",
                                detail="всё ещё неидеально",
                                fix_hint="попробуй иначе")], 0.0

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_critic)

    res = ds.generate_drawing("give-up test", app_root=temp_root, use_cache=False)

    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert res.critique_rounds == MAX_CRITIQUE_ROUNDS
    assert len(res.critique_findings) == MAX_CRITIQUE_ROUNDS


# ----------------------------------------------------------------- 5. degrade
def test_critic_transport_error_is_swallowed(monkeypatch, temp_root):
    from services import drawing_service as ds
    from services.openrouter_client import OpenRouterError

    def fake_llm(messages, model):
        return {"content": _wrap(VALID_CODE_V1), "cost_usd": 0.0, "model": model}

    def fake_critic(problem, code, png):
        raise OpenRouterError("simulated 502 from openrouter")

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_critic)

    # Must NOT raise — degrade gracefully and return the rendered PNG.
    res = ds.generate_drawing("critic-down test", app_root=temp_root, use_cache=False)

    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert res.critique_rounds == 0
    # The failing critic call is recorded in attempts:
    assert any(a.get("stage") == "critic" and a.get("ok") is False
               for a in res.attempts)


# ----------------------------------------------------------------- 6. parsers
def test_parse_critique_response_extracts_findings():
    from services.drawing_service import _parse_critique_response
    raw = ('Some text before...\n'
           '{"findings": [{"id":"f1","severity":"major","title":"t",'
           '"detail":"d","fix_hint":"h"}]} trailing junk')
    out = _parse_critique_response(raw)
    assert len(out) == 1
    assert out[0].id == "f1"
    assert out[0].severity == "major"


def test_parse_critique_response_empty():
    from services.drawing_service import _parse_critique_response
    assert _parse_critique_response("") == []
    assert _parse_critique_response("not json at all") == []
    assert _parse_critique_response('{"findings": []}') == []


def test_parse_decisions_mutates_findings():
    from services.drawing_service import _parse_decisions, CritiqueFinding
    findings = [
        CritiqueFinding(id="f1", severity="major", title="t1",
                        detail="d1", fix_hint="h1"),
        CritiqueFinding(id="f2", severity="minor", title="t2",
                        detail="d2", fix_hint="h2"),
    ]
    text = ('{"decisions": [{"id":"f1","decision":"accepted","reason":"ok"},'
            '{"id":"f2","decision":"rejected","reason":"no"}]}'
            '\n```python\nprint(1)\n```')
    _parse_decisions(text, findings)
    assert findings[0].claude_decision == "accepted"
    assert findings[0].claude_reasoning == "ok"
    assert findings[1].claude_decision == "rejected"
    assert findings[1].claude_reasoning == "no"
