# -*- coding: utf-8 -*-
# Tests for the QW-1 / QW-2 quality improvements landed in this PR.
#
#   QW-1: SYSTEM_PROMPT now demands an explicit "plan + asserts" block,
#         so generated code starts with a # === ПЛАН ПОСТРОЕНИЯ === comment.
#   QW-2: A separate COSMETIC critic stage runs AFTER the geometric
#         critic converges; it has its own env toggle and its own
#         system prompt that ignores math and looks only at readability.
#
# These tests are unit-level: they monkeypatch both critics and the
# Claude call, so no real network traffic happens.

import shutil
import tempfile

import pytest


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


@pytest.fixture
def temp_root():
    root = tempfile.mkdtemp(prefix="drw_qw_")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


def _wrap(code: str, decisions_json: str = "") -> str:
    body = ""
    if decisions_json:
        body = decisions_json + "\n\n"
    return body + "```python\n" + code + "\n```"


# ----------------------------------------------------------- QW-1 prompt

def test_system_prompt_requires_plan_and_asserts():
    from services.drawing_service import SYSTEM_PROMPT
    # The new prompt explicitly demands a plan block and asserts.
    assert "ПЛАН ПОСТРОЕНИЯ" in SYSTEM_PROMPT
    assert "assert" in SYSTEM_PROMPT.lower()


def test_system_prompt_keeps_format_strict():
    # We must NOT have softened the "single ```python``` block, no prose
    # before/after" rule -- otherwise repair_iters explode.
    from services.drawing_service import SYSTEM_PROMPT
    assert "```python" in SYSTEM_PROMPT
    # the prompt mentions that an answer without the fence is a critical
    # error -- this is what makes Claude reliably emit the block.
    assert "критическая" in SYSTEM_PROMPT.lower()


# --------------------------------------------------- QW-1 extract robustness

def test_extract_code_handles_missing_fence_with_imports():
    # Sometimes Claude forgets the fence after a long system update.  The
    # extractor must still recover the snippet if it can find a
    # matplotlib/numpy/math import anywhere in the answer.
    from services.drawing_service import _extract_code
    raw = (
        "Хорошо, вот код для построения чертежа:\n\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([0, 1], [0, 1])\n"
    )
    out = _extract_code(raw)
    assert out is not None
    assert out.startswith("import matplotlib.pyplot")
    assert "plt.subplots" in out


def test_extract_code_prefers_fenced_block_over_loose_imports():
    # If both a fenced block and a loose import exist, fence wins.
    from services.drawing_service import _extract_code
    raw = (
        "Заметка: ниже идёт код.\n"
        "import matplotlib  # this is NOT what we want\n"
        "\n"
        "```python\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "```\n"
    )
    out = _extract_code(raw)
    assert out is not None
    assert out.startswith("import numpy")
    assert "this is NOT what we want" not in out


def test_extract_code_returns_none_on_prose_only():
    from services.drawing_service import _extract_code
    assert _extract_code("Извини, я не понял условие.") is None
    assert _extract_code("") is None


# ----------------------------------------------------------- QW-2 cosmetic

def test_cosmetic_critic_has_separate_toggle():
    # The whole point of having a SECOND env var is so unit tests that
    # only stub _critique_with_gemini don't accidentally hit the real
    # OpenRouter API for the cosmetic call.  Verify the constant exists
    # and is a bool.
    from services import drawing_service as ds
    assert hasattr(ds, "COSMETIC_CRITIC_ENABLED")
    assert isinstance(ds.COSMETIC_CRITIC_ENABLED, bool)


def test_cosmetic_critic_runs_when_geometric_clean(monkeypatch, temp_root):
    # Geometric critic returns []; cosmetic critic returns 1 finding;
    # Claude replies with revised code; final PNG must be the revised one.
    from services import drawing_service as ds

    monkeypatch.setattr(ds, "CRITIC_ENABLED", True)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", True)

    claude_responses = [
        _wrap(VALID_CODE_V1),
        _wrap(
            VALID_CODE_V2,
            decisions_json='{"decisions": [{"id": "c1",'
                           ' "decision": "accepted",'
                           ' "reason": "moved label"}]}',
        ),
    ]
    call_log = {"claude": 0, "geo": 0, "cos": 0}

    def fake_llm(messages, model):
        idx = call_log["claude"]
        call_log["claude"] += 1
        return {
            "content": claude_responses[idx],
            "cost_usd": 0.001,
            "model": model,
        }

    def fake_geo_critic(problem, code, png):
        call_log["geo"] += 1
        return [], 0.001

    cos_finding = ds.CritiqueFinding(
        id="c1", severity="minor",
        title="label overlaps line",
        detail="V1 label overlaps the segment",
        fix_hint="move label down by 0.3",
    )

    def fake_cos_critic(problem, code, png):
        call_log["cos"] += 1
        return [cos_finding], 0.002

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_geo_critic)
    monkeypatch.setattr(ds, "_cosmetic_critique_with_gemini", fake_cos_critic)

    res = ds.generate_drawing("qw test", app_root=temp_root, use_cache=False)

    # Geo critic ran once (returned []); cosmetic ran once.
    assert call_log["geo"] == 1
    assert call_log["cos"] == 1
    # Claude was called twice: once for initial, once for cosmetic revise.
    assert call_log["claude"] == 2
    # Final code is V2 (post-revision).
    assert "'V2'" in res.code
    # And the cosmetic finding is recorded.
    assert any(f.id == "c1" for f in res.critique_findings)


def test_cosmetic_skipped_when_disabled(monkeypatch, temp_root):
    # If COSMETIC_CRITIC_ENABLED is False, we must NEVER call the
    # cosmetic critic, even with the geometric critic on.
    from services import drawing_service as ds

    monkeypatch.setattr(ds, "CRITIC_ENABLED", True)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", False)

    log = {"cos": 0}

    def fake_llm(messages, model):
        return {
            "content": _wrap(VALID_CODE_V1),
            "cost_usd": 0.0,
            "model": model,
        }

    def fake_geo(p, c, png):
        return [], 0.0

    def fake_cos(p, c, png):
        log["cos"] += 1
        return [], 0.0

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "_critique_with_gemini", fake_geo)
    monkeypatch.setattr(ds, "_cosmetic_critique_with_gemini", fake_cos)

    ds.generate_drawing("disabled cos", app_root=temp_root, use_cache=False)
    assert log["cos"] == 0
