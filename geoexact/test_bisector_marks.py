"""Regression tests for deterministic external-bisector decoration."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from geoexact.core.bisector_marks import decorate, install


def fixture(degrees):
    theta = math.radians(degrees)
    a, b = np.array([0., 0.]), np.array([23., 0.])
    c = 8 * np.array([math.cos(theta), math.sin(theta)])
    d = a + .5 * (a-b)
    l = (np.linalg.norm(a-c)*d + np.linalg.norm(a-d)*c) / (np.linalg.norm(a-c)+np.linalg.norm(a-d))
    cons = [NS(out='D', op='divide_segment', args=['B','A'], value=1.5),
            NS(out='L', op='bisector_point', args=['A','D','C'], value=None)]
    draw = NS(segments=[['A','B'],['B','C'],['C','A']], lines=[['A','L']],
              rays=[], angle_marks=[], extensions=[])
    return NS(constructions=cons, draw=draw), NS(coords=dict(A=a,B=b,C=c,D=d,L=l))


@pytest.mark.parametrize('degrees', [28,53,74,90,112,147])
def test_equal_marks_are_added_without_mutating_input(degrees):
    plan, sol = fixture(degrees)
    result = decorate(plan, sol)
    marks = result.draw.angle_marks
    assert len(marks) == 2
    assert marks[0]['count'] == marks[1]['count']
    assert marks[0]['reverse_first'] is True
    assert result.draw.extensions == [['B','A']]
    assert plan.draw.angle_marks == []
    assert decorate(result, sol).draw.angle_marks == marks


def test_wrong_bisector_is_not_marked():
    plan, sol = fixture(74)
    sol.coords['L'] = sol.coords['C'].copy()
    assert decorate(plan, sol).draw.angle_marks == []


def test_undrawn_bisector_is_not_marked():
    plan, sol = fixture(74)
    plan.draw.lines = []
    assert decorate(plan, sol).draw.angle_marks == []


def test_other_angle_group_is_not_reused():
    plan, sol = fixture(74)
    plan.draw.angle_marks = [{'pts':['A','B','C'], 'count':1}]
    marks = decorate(plan, sol).draw.angle_marks
    assert marks[-1]['count'] == marks[-2]['count'] == 2


def test_renderer_install_is_idempotent():
    plan, sol = fixture(74)
    renderer = NS(render_svg=lambda p, s, **kw: p.draw.angle_marks)
    assert install(renderer)
    assert not install(renderer)
    assert len(renderer.render_svg(plan, sol)) == 2
