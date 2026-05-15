# -*- coding: utf-8 -*-
# End-to-end integration tests for services.drawing_service.
#
# We do NOT call OpenRouter here. Instead we monkeypatch `_call_llm`
# to return canned Python code blocks for each problem, then exercise
# the full pipeline: code-extract -> sandbox -> PNG -> cache.
#
# Five sample problems of growing complexity:
#   1. Triangle SAS (AB=5, AC=7, angle A = 60 deg)
#   2. Quadrilateral by diagonals (AC=8, BD=6, intersecting at O)
#   3. Circle with chord (radius R, chord AB, perpendicular OH)
#   4. Triangle inscribed in a circle (vertices on circumscribed circle)
#   5. Two externally tangent circles + common tangent line
#
# Each scenario asserts:
#   - DrawingResult.image_bytes starts with PNG magic
#   - len > 1KB
#   - cache_hit is False on first call, True on second call
#   - repair_iters == 0 (clean code)
#
# PNGs are written to tests/_artifacts/<name>.png for manual inspection.

import os
import shutil
import tempfile
import pytest


# ---------------------------------------------------------------- skip guard
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


# ---------------------------------------------------------------- fixtures
ART_DIR = os.path.join(os.path.dirname(__file__), "_artifacts")


@pytest.fixture(autouse=True)
def _ensure_artifacts_dir():
    os.makedirs(ART_DIR, exist_ok=True)
    yield


@pytest.fixture
def temp_root():
    # Isolated cache dir for each test.
    root = tempfile.mkdtemp(prefix="drw_test_")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _save_png(name: str, data: bytes):
    path = os.path.join(ART_DIR, name)
    with open(path, "wb") as f:
        f.write(data)


def _wrap(code_body: str) -> str:
    # Wrap a python snippet into a fenced LLM-style response.
    return "Here is the drawing:\n\n```python\n" + code_body + "\n```\n"


# ---------------------------------------------------------------- code samples
# Each sample mimics what Claude Sonnet would return: pure matplotlib + numpy,
# Agg backend, single plt.show() at the end (which sandbox intercepts).

TRIANGLE_SAS = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
ax.set_aspect('equal'); ax.axis('off')

A = np.array([0.0, 0.0])
B = np.array([5.0, 0.0])
angle = np.deg2rad(60.0)
C = np.array([7.0 * np.cos(angle), 7.0 * np.sin(angle)])

ax.plot([A[0], B[0], C[0], A[0]], [A[1], B[1], C[1], A[1]],
        color='black', linewidth=2.0)

for name, p, off in [('A', A, (-0.35, -0.35)),
                     ('B', B, (0.20, -0.35)),
                     ('C', C, (0.10, 0.20))]:
    ax.text(p[0] + off[0], p[1] + off[1], name,
            fontsize=20, fontweight='bold')

ax.set_xlim(-1, 8); ax.set_ylim(-1, 8)
plt.show()
"""

QUAD_BY_DIAGONALS = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
ax.set_aspect('equal'); ax.axis('off')

# Diagonals AC=8, BD=6 intersect at O.  Pick O at origin.
A = np.array([-4.0,  0.0])
C = np.array([ 4.0,  0.0])
B = np.array([ 0.0,  3.0])
D = np.array([ 0.0, -3.0])

ax.plot([A[0], B[0], C[0], D[0], A[0]],
        [A[1], B[1], C[1], D[1], A[1]],
        color='black', linewidth=2.0)
ax.plot([A[0], C[0]], [A[1], C[1]], color='gray', linewidth=1.2, linestyle='--')
ax.plot([B[0], D[0]], [B[1], D[1]], color='gray', linewidth=1.2, linestyle='--')

O = np.array([0.0, 0.0])
ax.plot(O[0], O[1], 'ko', markersize=5)

for name, p, off in [('A', A, (-0.45, -0.05)),
                     ('B', B, (-0.05,  0.30)),
                     ('C', C, ( 0.20, -0.05)),
                     ('D', D, (-0.05, -0.45)),
                     ('O', O, ( 0.18,  0.18))]:
    ax.text(p[0] + off[0], p[1] + off[1], name,
            fontsize=20, fontweight='bold')

ax.set_xlim(-5, 5); ax.set_ylim(-4, 4)
plt.show()
"""

CIRCLE_CHORD = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
ax.set_aspect('equal'); ax.axis('off')

R = 4.0
O = np.array([0.0, 0.0])
theta = np.linspace(0, 2 * np.pi, 360)
ax.plot(R * np.cos(theta), R * np.sin(theta),
        color='black', linewidth=2.0)
ax.plot(O[0], O[1], 'ko', markersize=4)

# Chord AB at height y = h.
h = 2.0
half = np.sqrt(R * R - h * h)
A = np.array([-half, h])
B = np.array([ half, h])
H = np.array([   0.0, h])

ax.plot([A[0], B[0]], [A[1], B[1]],
        color='black', linewidth=2.0)
ax.plot([O[0], H[0]], [O[1], H[1]],
        color='black', linewidth=1.5, linestyle='--')

# Small right-angle marker at H.
ax.plot([H[0] - 0.25, H[0] - 0.25, H[0]],
        [H[1] - 0.25, H[1],         H[1]],
        color='black', linewidth=1.2)

for name, p, off in [('O', O, (0.18, -0.30)),
                     ('A', A, (-0.45, 0.10)),
                     ('B', B, (0.20, 0.10)),
                     ('H', H, (0.15, 0.20))]:
    ax.text(p[0] + off[0], p[1] + off[1], name,
            fontsize=20, fontweight='bold')

ax.set_xlim(-5, 5); ax.set_ylim(-5, 5)
plt.show()
"""

INSCRIBED_TRIANGLE = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
ax.set_aspect('equal'); ax.axis('off')

R = 3.5
O = np.array([0.0, 0.0])
theta = np.linspace(0, 2 * np.pi, 360)
ax.plot(R * np.cos(theta), R * np.sin(theta),
        color='black', linewidth=2.0)

# Three vertices at chosen angles.
angs_deg = [90.0, 210.0, 330.0]
pts = []
for a in angs_deg:
    rad = np.deg2rad(a)
    pts.append(np.array([R * np.cos(rad), R * np.sin(rad)]))
A, B, C = pts

ax.plot([A[0], B[0], C[0], A[0]],
        [A[1], B[1], C[1], A[1]],
        color='black', linewidth=2.0)
ax.plot(O[0], O[1], 'ko', markersize=4)

for name, p in [('A', A), ('B', B), ('C', C), ('O', O)]:
    off = 0.35 * p / max(np.linalg.norm(p), 1e-9) if name != 'O' else np.array([0.20, 0.20])
    ax.text(p[0] + off[0], p[1] + off[1], name,
            fontsize=20, fontweight='bold')

ax.set_xlim(-5, 5); ax.set_ylim(-5, 5)
plt.show()
"""

TWO_TANGENT_CIRCLES = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
ax.set_aspect('equal'); ax.axis('off')

r1, r2 = 2.0, 1.2
O1 = np.array([0.0, 0.0])
O2 = np.array([r1 + r2, 0.0])

theta = np.linspace(0, 2 * np.pi, 360)
ax.plot(O1[0] + r1 * np.cos(theta), O1[1] + r1 * np.sin(theta),
        color='black', linewidth=2.0)
ax.plot(O2[0] + r2 * np.cos(theta), O2[1] + r2 * np.sin(theta),
        color='black', linewidth=2.0)

# Tangency point T on the line of centres.
T = O1 + r1 * (O2 - O1) / np.linalg.norm(O2 - O1)

# Common external tangent line through T (perpendicular to O1O2).
tangent_half_len = 3.0
P1 = T + np.array([0.0,  tangent_half_len])
P2 = T + np.array([0.0, -tangent_half_len])
ax.plot([P1[0], P2[0]], [P1[1], P2[1]],
        color='black', linewidth=1.5, linestyle='--')

# Line of centres.
ax.plot([O1[0], O2[0]], [O1[1], O2[1]],
        color='gray', linewidth=1.0, linestyle=':')

for name, p, off in [('O_1', O1, (-0.10, -0.45)),
                     ('O_2', O2, (-0.10, -0.45)),
                     ('T',   T,  ( 0.15,  0.25))]:
    ax.text(p[0] + off[0], p[1] + off[1], name,
            fontsize=18, fontweight='bold')

ax.set_xlim(-3, 6); ax.set_ylim(-3, 3.5)
plt.show()
"""


SAMPLES = [
    ("triangle_sas",
     "Постройте треугольник ABC, в котором AB=5, AC=7, угол A=60°.",
     TRIANGLE_SAS),
    ("quad_by_diagonals",
     "Постройте четырёхугольник ABCD, у которого диагонали AC=8 и BD=6 "
     "пересекаются в точке O и делятся пополам.",
     QUAD_BY_DIAGONALS),
    ("circle_with_chord",
     "Окружность с центром O радиуса R. Постройте хорду AB и опустите "
     "перпендикуляр OH на AB.",
     CIRCLE_CHORD),
    ("inscribed_triangle",
     "Постройте треугольник ABC, вписанный в окружность с центром O радиуса R.",
     INSCRIBED_TRIANGLE),
    ("two_tangent_circles",
     "Постройте две внешне касающиеся окружности с центрами O_1 и O_2 и общую "
     "касательную в точке касания T.",
     TWO_TANGENT_CIRCLES),
]


# ---------------------------------------------------------------- the test
@pytest.mark.parametrize("name,problem,code", SAMPLES,
                         ids=[s[0] for s in SAMPLES])
def test_drawing_pipeline_with_mocked_llm(monkeypatch, temp_root,
                                          name, problem, code):
    from services import drawing_service as ds

    calls = {"n": 0}

    def fake_call_llm(messages, model):
        calls["n"] += 1
        return {
            "content": _wrap(code),
            "cost_usd": 0.0,
            "model": model,
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
        }

    monkeypatch.setattr(ds, "_call_llm", fake_call_llm)

    # --- 1st call: should hit LLM mock, run sandbox, write cache.
    res1 = ds.generate_drawing(problem, app_root=temp_root, use_cache=True)
    assert isinstance(res1.image_bytes, (bytes, bytearray))
    assert res1.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(res1.image_bytes) > 1000
    assert res1.cache_hit is False
    assert res1.repair_iters == 0
    assert calls["n"] == 1

    # Save artifact for manual inspection.
    _save_png(name + ".png", bytes(res1.image_bytes))

    # --- 2nd call: cache must hit and skip LLM entirely.
    res2 = ds.generate_drawing(problem, app_root=temp_root, use_cache=True)
    assert res2.cache_hit is True
    assert res2.image_bytes == res1.image_bytes
    assert calls["n"] == 1, "LLM was called again on cache-hit path"


# ---------------------------------------------------------------- repair test
def test_drawing_pipeline_self_repair(monkeypatch, temp_root):
    # First LLM response: invalid (uses forbidden `os` module).
    # Second LLM response: valid TRIANGLE_SAS code.
    # The pipeline must retry once and succeed with repair_iters == 1.
    from services import drawing_service as ds

    sequence = [
        _wrap("import os\nos.listdir('.')\n"),
        _wrap(TRIANGLE_SAS),
    ]
    call_idx = {"i": 0}

    def fake_call_llm(messages, model):
        i = call_idx["i"]
        call_idx["i"] = i + 1
        return {
            "content": sequence[min(i, len(sequence) - 1)],
            "cost_usd": 0.0,
            "model": model,
        }

    monkeypatch.setattr(ds, "_call_llm", fake_call_llm)

    res = ds.generate_drawing(
        "Repair-test problem",
        app_root=temp_root,
        use_cache=False,
    )
    assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert res.repair_iters >= 1
    assert call_idx["i"] >= 2


def test_drawing_pipeline_gives_up_after_max_repairs(monkeypatch, temp_root):
    # All LLM responses are invalid -> pipeline must raise after MAX_REPAIR_ITERS.
    from services import drawing_service as ds
    from services.sandbox import SandboxError

    def fake_call_llm(messages, model):
        return {
            "content": _wrap("import socket\ns = socket.socket()\n"),
            "cost_usd": 0.0,
            "model": model,
        }

    monkeypatch.setattr(ds, "_call_llm", fake_call_llm)

    with pytest.raises(SandboxError):
        ds.generate_drawing(
            "Always-fails problem",
            app_root=temp_root,
            use_cache=False,
        )
