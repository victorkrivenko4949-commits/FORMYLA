# -*- coding: utf-8 -*-
# Tests for the FIX-1 / FIX-2 reliability hardening and the ARCH-1..4
# Gemini-architect pre-stage.
#
#   FIX-1: MAX_REPAIR_ITERS bumped 2 -> 4
#   FIX-2: _ast_check() pre-flight; SyntaxErrors are reported with the
#          offending line number/context BEFORE the sandbox is spawned.
#   ARCH:  architect stage runs before Claude when DRAWING_ARCHITECT=1
#          (or when DRAWING_CRITIC_ENABLED is on and DRAWING_ARCHITECT
#          is not explicitly set).  Spec is injected as a second system
#          message ahead of the user problem.

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
    root = tempfile.mkdtemp(prefix="drw_fix_")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


VALID_CODE = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "fig, ax = plt.subplots(figsize=(6, 6), dpi=110)\n"
    "ax.set_aspect('equal'); ax.axis('off')\n"
    "ax.plot([0, 5], [0, 0], 'k-', lw=2)\n"
    "ax.set_xlim(-1, 6); ax.set_ylim(-1, 1)\n"
)
BROKEN_CODE_MISSING_PAREN = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "fig, ax = plt.subplots(figsize=(6, 6, dpi=110)\n"  # missing ')'
    "ax.set_aspect('equal'); ax.axis('off')\n"
)


def _wrap(code: str) -> str:
    return "```python\n" + code + "\n```"


# ============================================================ FIX-1 budget

def test_max_repair_iters_is_at_least_3():
    # Bumping it down to 2 would re-introduce the prod failure mode
    # where a long new prompt makes Claude fumble three times in a row.
    from services.drawing_service import MAX_REPAIR_ITERS
    assert MAX_REPAIR_ITERS >= 3, (
        "MAX_REPAIR_ITERS=" + str(MAX_REPAIR_ITERS) + " is too tight; "
        "see the 2026-05-15 prod incident where a nine-point-circle "
        "task burned all 2 iters on the same syntax bug."
    )


# ============================================================ FIX-2 ast

def test_ast_check_passes_on_valid_code():
    from services.drawing_service import _ast_check
    assert _ast_check(VALID_CODE) is None


def test_ast_check_reports_line_number_for_missing_paren():
    from services.drawing_service import _ast_check
    err = _ast_check(BROKEN_CODE_MISSING_PAREN)
    assert err is not None
    # Must include the line number so Claude can find the bug.
    assert "line 5" in err, "ast error must point at the broken line"
    # Must include a contextual snippet with a `>>>` marker.
    assert ">>>" in err
    # Must NOT raise.


def test_ast_check_handles_empty_code():
    from services.drawing_service import _ast_check
    assert _ast_check("") is None  # empty parses fine


def test_ast_check_short_circuits_sandbox(monkeypatch, temp_root):
    # When Claude returns syntactically broken code, the sandbox must
    # NOT be invoked -- the repair message is built from _ast_check
    # instead.  We detect this by counting sandbox calls.
    from services import drawing_service as ds

    monkeypatch.setattr(ds, "CRITIC_ENABLED", False)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", False)
    monkeypatch.setattr(ds, "ARCHITECT_ENABLED", False)

    sandbox_calls = {"n": 0}

    def fake_run(code, timeout):
        sandbox_calls["n"] += 1
        # Return a minimal valid PNG; this path is only reachable after
        # a valid syntax check.
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
        return buf.getvalue()

    # Claude returns broken code first, then valid.
    responses = [
        _wrap(BROKEN_CODE_MISSING_PAREN),
        _wrap(VALID_CODE),
    ]

    def fake_llm(messages, model):
        return {"content": responses.pop(0), "cost_usd": 0.0, "model": model}

    monkeypatch.setattr(ds, "_call_llm", fake_llm)
    monkeypatch.setattr(ds, "run_drawing_code", fake_run)

    res = ds.generate_drawing("ast test", app_root=temp_root, use_cache=False)
    # Sandbox must have been called EXACTLY once (only on the valid
    # second attempt) -- the broken first attempt was caught by ast.
    assert sandbox_calls["n"] == 1
    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# =========================================================== ARCH stage

def test_architect_toggle_default_follows_critic():
    # If the user explicitly sets DRAWING_CRITIC_ENABLED=1 but does NOT
    # set DRAWING_ARCHITECT, the architect should turn ON too -- that's
    # the "max quality" mode we wired up.  The module captures envs at
    # import time, so we test the actual logic by re-importing with
    # patched os.environ via importlib.reload.
    import importlib
    import os
    saved = {
        "DRAWING_CRITIC_ENABLED": os.environ.get("DRAWING_CRITIC_ENABLED"),
        "DRAWING_ARCHITECT": os.environ.get("DRAWING_ARCHITECT"),
    }
    try:
        os.environ["DRAWING_CRITIC_ENABLED"] = "1"
        os.environ.pop("DRAWING_ARCHITECT", None)
        from services import drawing_service
        importlib.reload(drawing_service)
        assert drawing_service.ARCHITECT_ENABLED is True
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from services import drawing_service
        importlib.reload(drawing_service)


def test_architect_can_be_disabled_explicitly():
    import importlib
    import os
    saved = {
        "DRAWING_CRITIC_ENABLED": os.environ.get("DRAWING_CRITIC_ENABLED"),
        "DRAWING_ARCHITECT": os.environ.get("DRAWING_ARCHITECT"),
    }
    try:
        os.environ["DRAWING_CRITIC_ENABLED"] = "1"
        os.environ["DRAWING_ARCHITECT"] = "0"
        from services import drawing_service
        importlib.reload(drawing_service)
        assert drawing_service.ARCHITECT_ENABLED is False
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from services import drawing_service
        importlib.reload(drawing_service)


def test_build_initial_messages_injects_spec():
    from services.drawing_service import _build_initial_messages
    spec = "## 1. КЛАССИФИКАЦИЯ\nТреугольник.\n## 2. ПЕРЕЧЕНЬ\n- A, B, C\n"
    msgs = _build_initial_messages("задача про треугольник", architect_spec=spec)
    # 2 system + 1 user
    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert "ПЛАН ПОСТРОЕНИЯ" in msgs[0]["content"]
    assert msgs[1]["role"] == "system"
    assert "АРХИТЕКТОРА" in msgs[1]["content"]
    assert "## 1. КЛАССИФИКАЦИЯ" in msgs[1]["content"]
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == "задача про треугольник"


def test_build_initial_messages_no_spec_legacy_shape():
    # When no spec is given, the message list must be identical to the
    # pre-architect shape (1 system + 1 user) so existing behaviour and
    # unit tests don't shift.
    from services.drawing_service import _build_initial_messages
    msgs = _build_initial_messages("задача")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_architect_failure_is_swallowed(monkeypatch, temp_root):
    # If the architect API call raises, generate_drawing must still
    # succeed -- the architect is strictly an enhancement.
    from services import drawing_service as ds
    from services.openrouter_client import OpenRouterError

    monkeypatch.setattr(ds, "ARCHITECT_ENABLED", True)
    monkeypatch.setattr(ds, "CRITIC_ENABLED", False)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", False)

    def boom(problem):
        raise OpenRouterError("architect-down simulation")

    # _get_architect_spec swallows OpenRouterError internally, so we
    # monkeypatch _get_architect_spec to simulate the swallowed result.
    monkeypatch.setattr(ds, "_get_architect_spec",
                        lambda p: (None, 0.0))

    def fake_llm(messages, model):
        return {
            "content": _wrap(VALID_CODE),
            "cost_usd": 0.0,
            "model": model,
        }

    monkeypatch.setattr(ds, "_call_llm", fake_llm)

    res = ds.generate_drawing("architect down", app_root=temp_root,
                               use_cache=False)
    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_architect_spec_is_added_to_messages(monkeypatch, temp_root):
    # When the architect returns a spec, the FIRST call to _call_llm
    # must receive 3 messages (sys + sys-arch + user).
    from services import drawing_service as ds

    monkeypatch.setattr(ds, "ARCHITECT_ENABLED", True)
    monkeypatch.setattr(ds, "CRITIC_ENABLED", False)
    monkeypatch.setattr(ds, "COSMETIC_CRITIC_ENABLED", False)

    fake_spec = (
        "## 1. КЛАССИФИКАЦИЯ\nПростой треугольник.\n"
        "## 2. ПЕРЕЧЕНЬ ВСЕХ ИМЕНОВАННЫХ ТОЧЕК\n- A, B, C\n"
        "## 3. ПОСЛЕДОВАТЕЛЬНОСТЬ ПОСТРОЕНИЯ\n1. ...\n"
    )

    monkeypatch.setattr(ds, "_get_architect_spec",
                        lambda p: (fake_spec, 0.05))

    seen = {"first_messages": None}

    def fake_llm(messages, model):
        if seen["first_messages"] is None:
            seen["first_messages"] = list(messages)
        return {
            "content": _wrap(VALID_CODE),
            "cost_usd": 0.0,
            "model": model,
        }

    monkeypatch.setattr(ds, "_call_llm", fake_llm)

    ds.generate_drawing("arch test", app_root=temp_root, use_cache=False)
    msgs = seen["first_messages"]
    assert msgs is not None
    # Two system messages then the user problem.
    sys_roles = [m for m in msgs if m["role"] == "system"]
    assert len(sys_roles) == 2
    assert "ПЛАН ПОСТРОЕНИЯ" in sys_roles[0]["content"]
    assert "АРХИТЕКТОРА" in sys_roles[1]["content"]
    assert "Простой треугольник" in sys_roles[1]["content"]
