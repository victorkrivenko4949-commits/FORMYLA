# -*- coding: utf-8 -*-
# Tests for services.sandbox: AST whitelist validation + end-to-end PNG generation.
#
# Strategy:
#   - validate_drawing_code: covers the static-analysis layer (no subprocess).
#   - run_drawing_code: spawns python child via subprocess on a known-good snippet.
#     This requires matplotlib/numpy in the parent venv; the test is skipped if not.

import sys
import pytest

from services.sandbox import (
    validate_drawing_code,
    run_drawing_code,
    SandboxRejected,
    SandboxError,
)


# ---------------------------------------------------------------------------
# Static AST validation
# ---------------------------------------------------------------------------

ALLOWED_SAMPLES = [
    # bare minimum
    "import matplotlib\nimport matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n",
    # numpy + math allowed
    "import numpy as np\nimport math\nx = np.linspace(0, 1, 10)\ny = math.sin(0.5)\n",
    # function definitions, control flow allowed
    (
        "import matplotlib.pyplot as plt\n"
        "def draw():\n"
        "    fig, ax = plt.subplots()\n"
        "    for i in range(3):\n"
        "        ax.plot([0, i], [0, 1])\n"
        "    return fig\n"
        "draw()\n"
    ),
]


@pytest.mark.parametrize("code", ALLOWED_SAMPLES)
def test_validate_allows_safe_code(code):
    # Should not raise.
    validate_drawing_code(code)


REJECTED_SAMPLES = [
    # forbidden modules
    "import os\n",
    "import sys\n",
    "import subprocess\n",
    "import socket\n",
    "import urllib.request\n",
    "from os import path\n",
    "from subprocess import run\n",
    # dynamic import / eval / exec / compile
    "x = __import__('os')\n",
    "eval('1+1')\n",
    "exec('print(1)')\n",
    "compile('x=1', '<s>', 'exec')\n",
    # filesystem / network builtins
    "open('/etc/passwd').read()\n",
    # third-party not in whitelist
    "import requests\n",
    "import flask\n",
    # dunder access
    "().__class__.__bases__\n",
    # globals leak
    "globals()['os'] = 1\n",
]


@pytest.mark.parametrize("code", REJECTED_SAMPLES)
def test_validate_rejects_dangerous_code(code):
    with pytest.raises(SandboxRejected):
        validate_drawing_code(code)


def test_validate_rejects_syntax_error():
    with pytest.raises(SandboxRejected):
        validate_drawing_code("def broken(:\n")


def test_validate_rejects_empty():
    with pytest.raises(SandboxRejected):
        validate_drawing_code("")
    with pytest.raises(SandboxRejected):
        validate_drawing_code("   \n\n  ")


# ---------------------------------------------------------------------------
# Subprocess execution (live)
# ---------------------------------------------------------------------------

def _matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


SIMPLE_TRIANGLE = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "fig, ax = plt.subplots(figsize=(6, 6), dpi=110)\n"
    "ax.set_aspect('equal'); ax.axis('off')\n"
    "A = np.array([0.0, 0.0])\n"
    "B = np.array([5.0, 0.0])\n"
    "C = np.array([2.5, 4.33])\n"
    "ax.plot([A[0], B[0], C[0], A[0]], [A[1], B[1], C[1], A[1]], 'k-', lw=2)\n"
    "for name, p in [('A', A), ('B', B), ('C', C)]:\n"
    "    ax.text(p[0], p[1], name, fontsize=18)\n"
)


@pytest.mark.skipif(not _matplotlib_available(),
                    reason="matplotlib/numpy not installed in test env")
def test_run_drawing_code_produces_png():
    png = run_drawing_code(SIMPLE_TRIANGLE, timeout=20.0)
    assert isinstance(png, (bytes, bytearray))
    assert len(png) > 1000
    # PNG magic header
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.skipif(not _matplotlib_available(),
                    reason="matplotlib/numpy not installed in test env")
def test_run_drawing_code_rejects_before_spawn():
    # validate_drawing_code is called inside run_drawing_code,
    # so dangerous code must fail before any subprocess is spawned.
    with pytest.raises(SandboxRejected):
        run_drawing_code("import os\nos.system('echo hi')\n", timeout=5.0)
