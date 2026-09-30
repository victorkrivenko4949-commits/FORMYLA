"""Равные отрезки — равные цвета; черточки можно скрыть.

Цвета групп равенства зашиваются в сам SVG серверным рендером (классы
eqc-<count> + CSS-правила), поэтому равенство остаётся видимым даже когда
пользователь скрыл черточки переключателем на клиенте.
"""
import copy
import pathlib
import shutil
import subprocess

import pytest

from geoexact.core import llm
from geoexact.core.pipeline import generate
from geoexact.core.render import EQ_COLORS, render_svg
from geoexact.core.solver import solve
from geoexact.test_statement import triangle_plan


def style_block_of(svg):
    return svg.split("<style>", 1)[1].split("</style>", 1)[0]


def _solved(plan):
    return next(s for s in solve(plan, n_seeds=8) if s.ok)


def _render(equal_marks, segments=None):
    plan = triangle_plan()
    plan.draw.equal_marks = [dict(m) for m in equal_marks]
    if segments is not None:
        plan.draw.segments = [list(s) for s in segments]
    sol = _solved(plan)
    return render_svg(plan, sol)


def test_equal_segments_share_color():
    svg = _render([{"pts": ["B", "M"], "count": 1},
                   {"pts": ["M", "C"], "count": 1}],
                  segments=[["A", "B"], ["B", "M"], ["M", "C"], ["C", "A"]])
    assert svg.count('class="seg eqc-1"') == 2          # BM и MC одним цветом
    assert svg.count('class="tick eqc-1"') >= 2         # черточки того же цвета
    # правило обязано быть ВНУТРИ <style> (после </style> оно не применяется)
    style_block = svg.split("<style>", 1)[1].split("</style>", 1)[0]
    assert f".eqc-1 {{ stroke: {EQ_COLORS[0]}; }}" in style_block
    assert 'class="seg"' in svg                          # остальные — как были


def test_different_groups_get_different_colors():
    svg = _render([{"pts": ["A", "B"], "count": 1}, {"pts": ["A", "C"], "count": 1},
                   {"pts": ["B", "M"], "count": 2}, {"pts": ["M", "C"], "count": 2}],
                  segments=[["A", "B"], ["A", "C"], ["B", "M"], ["M", "C"], ["A", "M"]])
    assert svg.count('class="seg eqc-1"') == 2          # AB и AC
    assert svg.count('class="seg eqc-2"') == 2          # BM и MC
    assert (f".eqc-1 {{ stroke: {EQ_COLORS[0]}; }}" in style_block_of(svg)
            and f".eqc-2 {{ stroke: {EQ_COLORS[1]}; }}" in style_block_of(svg))
    assert EQ_COLORS[0] != EQ_COLORS[1]


def test_no_marks_no_colors():
    svg = _render([], segments=[["A", "B"], ["B", "C"], ["C", "A"]])
    assert "eqc-" not in svg


def test_pipeline_svg_carries_colors(monkeypatch):
    plan = triangle_plan()
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (copy.deepcopy(plan), []))
    r = generate("В треугольнике ABC проведена медиана AM.",
                 sess=object(), use_cache=False)
    assert r.ok
    # медиана достроена конвейером: половины BM и MC — одной группой цвета
    assert r.svg.count('class="seg eqc-1"') == 2
    assert 'class="tick eqc-1"' in r.svg


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_js_hides_ticks_but_keeps_them_in_svg():
    """Переключатель «черточки» прячет их CSS-правилом, не вырезая из файла."""
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('// Черточки равных отрезков');
const end = source.indexOf('function render()');
if (start < 0 || end < 0) throw new Error('withTicks not found');
const withTicks = new Function(source.slice(start, end) + ';return withTicks;')();
const svg = '<svg><style>.tick { stroke: #111; }</style>' +
  '<path class="tick" d="M 1 2 L 3 4"/></svg>';
const hidden = withTicks(svg, false);
if (!hidden.includes('.tick { display: none; }')) throw new Error('no hide rule');
if (!hidden.includes('<path class="tick"')) throw new Error('ticks must stay in DOM');
if (withTicks(svg, true) !== svg) throw new Error('shown svg must be unchanged');
if (withTicks('', false) !== '') throw new Error('empty svg must pass through');
const noStyle = '<svg><path class="tick"/></svg>';
if (withTicks(noStyle, false) !== noStyle) throw new Error('svg without style');
console.log('OK');
"""
    js = pathlib.Path(__file__).parent / "static" / "draw.js"
    out = subprocess.run(["node", "-e", script, str(js)],
                         text=True, capture_output=True, timeout=10)
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout
