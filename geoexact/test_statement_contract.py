"""Coordinate-level contract regressions; no model, network or solver required."""
import math

from geoexact.core.statement_contract import Requirement as R, audit


def facts():
    return [R('tri','triangle',('A','B','C'),'треугольник ABC'),
            R('mid','midpoint',('D','B','C'),'AD — медиана'),
            R('bis','bisector',('B','E','A','C'),'BE — биссектриса'),
            R('on','on_segment',('E','A','C'),'E лежит на AC'),
            R('perp','perpendicular',('A','D','B','E'),'AD перпендикулярна BE'),
            R('ad','length',('A','D'),'AD = 12',12),
            R('be','length',('B','E'),'BE = 12',12)]


def coordinates():
    return dict(A=(-6.,9.),B=(0.,0.),C=(12.,18.),D=(6.,9.),E=(0.,12.))


def test_complete_valid_figure():
    assert audit(facts(),coordinates())['ok']


def test_moved_median_foot_fails():
    p=coordinates();p['D']=(3.,1.)
    report=audit(facts(),p)
    assert not report['ok']
    failed={r['id'] for r in report['requirements'] if r['status']=='violated'}
    assert {'mid','perp','ad'} <= failed


def test_missing_point_fails():
    p=coordinates();del p['E']
    report=audit(facts(),p)
    assert not report['ok']
    assert any(r['status']=='missing_point' for r in report['requirements'])


def test_unsupported_and_empty_contracts_fail():
    assert not audit([],coordinates())['ok']
    row=audit([R('x','unimplemented',(),'source')],coordinates())['requirements'][0]
    assert row['status']=='unsupported'


def test_duplicate_ids_fail():
    assert not audit([facts()[0],facts()[0]],coordinates())['ok']


def test_invariance_under_renaming_rotation_reflection_translation():
    for reflected in (1,-1):
        for degrees in (0,37,90,173):
            t=math.radians(degrees);c,s=math.cos(t),math.sin(t)
            names=dict(zip('ABCDE','PQRST'))
            p={names[n]:(c*x-s*y*reflected+100,s*x+c*y*reflected-70)
               for n,(x,y) in coordinates().items()}
            requirements=[R(r.id,r.kind,tuple(names[n] for n in r.points),r.source,r.value)
                          for r in facts()]
            assert audit(requirements,p)['ok']


def test_flat_triangle_rejected():
    assert not audit([facts()[0]],dict(A=(0,0),B=(1,0),C=(2,0)))['ok']
