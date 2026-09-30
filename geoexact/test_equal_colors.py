"""Равные отрезки — равные цвета; черточки можно скрыть.

Цвета групп равенства зашиваются в сам SVG серверным рендером (классы
eqc-<count> + CSS-правила), поэтому равенство остаётся видимым даже когда
пользователь скрыл черточки переключателем на клиенте.
"""
import copy
import re
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


# ---------------------------------------------- цвета в обоих режимах

from geoexact.core.schema import FigurePlan  # noqa: E402


def _generate(monkeypatch, text, aux, plan):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (copy.deepcopy(plan), []))
    return generate(text, aux, sess=object(), use_cache=False)


@pytest.mark.parametrize("aux", [False, True])
@pytest.mark.parametrize("text", [
    "В треугольнике ABC углы B=60°, C=50°, M — середина стороны BC. Найдите угол A.",
    "В треугольнике ABC углы B=60°, C=50°, проведена медиана AM.",
])
def test_halves_are_colored_in_both_modes(monkeypatch, text, aux):
    """Половины стороны, проведённой целиком, красятся и получают засечки."""
    r = _generate(monkeypatch, text, aux, triangle_plan())
    assert r.ok
    assert r.svg.count('class="tick eqc-1') == 2
    colored = re.findall(r'<line class="[^"]*eqc-1[^"]*"', r.svg)
    assert len(colored) == 2, r.svg


@pytest.mark.parametrize("aux", [False, True])
def test_isosceles_sides_are_colored_in_both_modes(monkeypatch, aux):
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [{"type": "dist_eq", "args": ["A", "B", "A", "C"]},
                        {"type": "angle", "args": ["B", "A", "C"], "value": 40}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "scale_free": True})
    r = _generate(monkeypatch, "В треугольнике ABC AB = AC, угол A равен 40°.", aux, plan)
    assert r.ok
    assert len(re.findall(r'<line class="[^"]*eqc-1[^"]*"', r.svg)) == 2
    assert r.svg.count('class="tick eqc-1') == 2


def test_aux_part_of_line_is_colored_only_with_aux_layer(monkeypatch):
    """Слой доп. построений скрыт — его цветной слой тоже не рисуется."""
    plan = triangle_plan()
    plan.draw.equal_marks = [{"pts": ["B", "M"], "count": 1, "layer": "aux"},
                             {"pts": ["M", "C"], "count": 1, "layer": "aux"}]
    sol = _solved(plan)
    shown = render_svg(plan, sol, show_aux=True)
    hidden = render_svg(plan, sol, show_aux=False)
    assert len(re.findall(r'<line class="[^"]*eqc-1[^"]*"', shown)) == 2
    assert 'data-kind="eq-part"' not in hidden
    assert 'class="tick' not in hidden


def test_midpoint_phrases_are_recognized():
    from geoexact.core.statement import _MIDPOINT, _MIDPOINTS2
    assert _MIDPOINT.search("M — середина стороны BC.")[1] == "M"
    assert _MIDPOINT.search("точка K является серединой отрезка AB")[2] == "AB"
    assert _MIDPOINTS2.search("M и N — середины сторон AB и AC")[4] == "AC"


def test_colored_lines_are_drawn_on_top_of_black_duplicates():
    plan = triangle_plan()
    plan.draw.segments = [["A", "B"], ["B", "M"], ["M", "C"], ["C", "A"], ["B", "C"]]
    plan.draw.equal_marks = [{"pts": ["B", "M"], "count": 1}, {"pts": ["M", "C"], "count": 1}]
    svg = render_svg(plan, _solved(plan))
    lines = re.findall(r'<line class="([^"]*)"', svg)
    last_plain = max(i for i, c in enumerate(lines) if "eqc-" not in c)
    first_colored = min(i for i, c in enumerate(lines) if "eqc-" in c)
    assert first_colored > last_plain
