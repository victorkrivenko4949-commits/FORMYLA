# -*- coding: utf-8 -*-
"""
Smoke tests for static/js/board/pen_stroke.js.

Two layers:

1. Static text checks (always run, no JS engine needed) that guard the
   public surface of the module and its integration into whiteboard.js +
   templates/whiteboard.html.

2. Dynamic Node.js exercises (skipped if `node` is not on PATH) that
   actually call the JS functions and verify mathematical invariants.
"""

import os
import shutil
import subprocess
import textwrap

import pytest


PEN_JS = os.path.join("static", "js", "board", "pen_stroke.js")
WB_JS = os.path.join("static", "js", "whiteboard.js")
WB_HTML = os.path.join("templates", "whiteboard.html")


# ───────────────────────── Static text checks ──────────────────────────


def test_pen_js_file_exists_and_exports_public_api():
    assert os.path.exists(PEN_JS), f"missing {PEN_JS}"
    txt = open(PEN_JS, encoding="utf-8").read()
    # IIFE pattern + window install
    assert "FormylaPen" in txt
    # Public API surface
    for fn in [
        "drawSmoothStroke",
        "smoothPath",
        "thicknessProfile",
        "pointSpeeds",
        "normalize01",
    ]:
        assert fn in txt, f"pen_stroke.js missing {fn}"
    # Sanity: ribbon polygon + cubic Bézier ingredients present.
    assert "bezierCurveTo" in txt or "cubic" in txt.lower() or "p0.x" in txt


def test_template_includes_pen_stroke_before_whiteboard_js():
    txt = open(WB_HTML, encoding="utf-8").read()
    assert "pen_stroke.js" in txt, "templates/whiteboard.html must load pen_stroke.js"
    # It MUST load before whiteboard.js so the global is ready.
    pen_idx = txt.index("pen_stroke.js")
    wb_idx = txt.index("whiteboard.js")
    assert pen_idx < wb_idx, "pen_stroke.js must be loaded before whiteboard.js"


def test_whiteboard_js_delegates_pen_rendering_to_FormylaPen():
    txt = open(WB_JS, encoding="utf-8").read()
    assert "FormylaPen" in txt, "whiteboard.js must reference window.FormylaPen"
    assert "drawSmoothStroke" in txt, "whiteboard.js must call drawSmoothStroke"


def test_whiteboard_js_captures_timestamp_on_pen_points():
    txt = open(WB_JS, encoding="utf-8").read()
    # The new push must carry t (timestamp) and p (pressure) fields.
    assert "drag.preview.points.push({ x: w.x, y: w.y, t:" in txt, (
        "onMove pen branch must push points with timestamp `t`"
    )


# ─────────────────── Dynamic checks (need node.js) ─────────────────────


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str) -> str:
    """Execute a snippet of JS that has access to the loaded module."""
    full = textwrap.dedent(f"""
        const fs = require('fs');
        const code = fs.readFileSync({PEN_JS!r}, 'utf8');
        const sandbox = {{}};
        global.window = sandbox;
        eval(code);
        const FP = sandbox.FormylaPen;
        if (!FP) {{ console.error('FormylaPen missing'); process.exit(2); }}
        {script}
    """)
    proc = subprocess.run(
        ["node", "-e", full],
        capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


_node_skip = pytest.mark.skipif(not _node_available(), reason="node.js not on PATH")


@_node_skip
def test_smoothPath_two_points_returns_one_segment():
    out = _run_node("""
        const pts = [{x:0,y:0},{x:10,y:0}];
        const segs = FP.smoothPath(pts);
        if (segs.length !== 1) { console.error('len', segs.length); process.exit(3); }
        const s = segs[0];
        if (s.p0.x !== 0 || s.p1.x !== 10) { console.error('endpoints'); process.exit(4); }
        console.log('ok');
    """)
    assert "ok" in out


@_node_skip
def test_smoothPath_many_points_produces_n_minus_1_segments():
    out = _run_node("""
        const pts = [{x:0,y:0},{x:10,y:5},{x:20,y:0},{x:30,y:-5},{x:40,y:0}];
        const segs = FP.smoothPath(pts);
        if (segs.length !== 4) process.exit(3);
        if (segs[0].p0.x !== 0 || segs[0].p0.y !== 0) process.exit(4);
        const last = segs[segs.length-1];
        if (last.p1.x !== 40 || last.p1.y !== 0) process.exit(5);
        console.log('ok');
    """)
    assert "ok" in out


@_node_skip
def test_thicknessProfile_is_clamped_and_tapers_at_edges():
    out = _run_node("""
        const pts = [];
        for (let i=0;i<60;i++) pts.push({x: i*3, y: Math.sin(i/4)*10, t: i*16});
        const prof = FP.thicknessProfile(pts, {});
        if (prof.length !== pts.length) process.exit(3);
        for (const v of prof) {
            if (!Number.isFinite(v)) process.exit(4);
            if (v < 0.04 || v > FP.MAX_THICKNESS_MULT + 0.001) process.exit(5);
        }
        const mid = prof[Math.floor(prof.length/2)];
        if (!(prof[0] < mid && prof[prof.length-1] < mid)) process.exit(6);
        console.log('ok');
    """)
    assert "ok" in out


@_node_skip
def test_normalize01_handles_constant_input():
    out = _run_node("""
        const r = FP.normalize01([5,5,5,5]);
        if (r.some(v => !Number.isFinite(v))) process.exit(3);
        if (r.some(v => v < 0 || v > 1)) process.exit(4);
        console.log('ok');
    """)
    assert "ok" in out


@_node_skip
def test_drawSmoothStroke_runs_without_throwing_on_mock_ctx():
    out = _run_node("""
        const calls = [];
        const ctx = new Proxy({}, {
            get(_, k) {
                const noops = ['save','restore','beginPath','moveTo','lineTo',
                               'arc','fill','stroke','closePath','bezierCurveTo'];
                if (noops.indexOf(k) >= 0) return function () { calls.push(k); };
                return undefined;
            },
            set() { return true; },
        });
        const pts = [];
        for (let i=0;i<30;i++) pts.push({x:i*4, y: Math.cos(i/3)*8, t:i*16});
        FP.drawSmoothStroke(ctx, pts, { color:'#fff', thickness:3 });
        if (calls.indexOf('fill') < 0) process.exit(3);
        console.log('ok ' + calls.length);
    """)
    assert "ok" in out
