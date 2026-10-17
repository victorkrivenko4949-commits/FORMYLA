"""SVG contract regressions; no live model, solver, or production renderer."""
import copy
import math
from types import SimpleNamespace as S
import xml.etree.ElementTree as ET

from geoexact.core.svg_presentation import finish_svg


def fixture(degrees=66, rotation=0, reflected=1, scale=16):
    theta = math.radians(degrees)
    p = dict(A=(0.,0.),B=(23.,0.),C=(8*math.cos(theta),8*math.sin(theta)),D=(-11.5,0.))
    p['L'] = tuple((8*p['D'][i]+11.5*p['C'][i])/19.5 for i in (0,1))
    p['M'] = tuple((p['B'][i]+p['C'][i])/2 for i in (0,1))
    p['R'] = tuple(p['M'][i]+p['L'][i] for i in (0,1))
    p['K'] = (15.5,0.)
    t = math.radians(rotation);c,s = math.cos(t),math.sin(t)
    p = {n:(c*x-s*y*reflected+2,s*x+c*y*reflected-3) for n,(x,y) in p.items()}
    draw = S(segments=[['A','B'],['B','C'],['C','A'],['M','K']],lines=[['A','L']],rays=[],
             hide_labels=['D','L','R'],extensions=[['B','A']],
             angle_marks=[{'pts':['B','A','L'],'reverse_first':True,'count':1},
                          {'pts':['L','A','C'],'count':1}],
             length_marks=[{'pts':['A','L'],'text':'ℓ'}],equal_marks=[])
    cons = [S(op='free_point',out=n,args=[]) for n in 'ABC'] + [
            S(op='divide_segment',out='D',args=['B','A'],value=1.5),
            S(op='bisector_point',out='L',args=['A','D','C']),
            S(op='translate',out='R',args=['M','A','L'])]
    plan = S(points=list(p),draw=draw,constructions=cons,constraints=[],target=S(args=['A','K']))
    sol = S(coords=p)
    q = {n:(100+scale*x,350-scale*y) for n,(x,y) in p.items()}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="560" height="500" viewBox="0 0 560 500">',
             '<!-- PRESERVE_DIAGNOSTICS --><g id="main">']
    for kind,pairs in [('segments',draw.segments),('lines',draw.lines)]:
        for a,b in pairs:
            x,y = q[a];z,w = q[b]
            parts.append(f'<line class="seg" data-kind="{kind}" x1="{x}" y1="{y}" x2="{z}" y2="{w}"/>')
    parts.append('</g><g id="labels">')
    for n in 'ABCMKL':
        x,y = q[n]
        parts.append(f'<circle class="pt" data-point="{n}" cx="{x}" cy="{y}" r="3.2"/>')
    parts.append('</g><g id="marks">')
    for m in draw.angle_marks:
        a,o,b = [q[n] for n in m['pts']]
        u,v = (a[0]-o[0],a[1]-o[1]),(b[0]-o[0],b[1]-o[1])
        if m.get('reverse_first'):
            u = (-u[0],-u[1])
        start = math.atan2(u[1],u[0])
        delta = math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])
        a,b = [(o[0]+25*math.cos(t),o[1]+25*math.sin(t)) for t in (start,start+delta)]
        parts.append(f'<path class="arc" data-layer="main" d="M {a[0]} {a[1]} A 25 25 0 0 {int(delta>0)} {b[0]} {b[1]}"/>')
    parts.append('</g></svg>')
    return plan,sol,''.join(parts)


def items(svg,kind):
    return [e for e in ET.fromstring(svg).iter() if e.get('data-kind')==kind]


def test_three_presentation_defects():
    plan,sol,svg = fixture()
    result = finish_svg(svg,plan,sol)
    dots = {e.get('data-point') for e in ET.fromstring(result).iter() if e.get('data-point')}
    assert dots == set('ABCMK')
    assert len(items(result,'angle-equality-tick')) == 2
    assert len(items(result,'parallel-mark')) == 2


def test_no_input_mutation_or_viewport_change():
    plan,sol,svg = fixture()
    before = copy.deepcopy((plan,sol))
    result = finish_svg(svg,plan,sol)
    assert (plan,sol) == before
    for attr in ('width','height','viewBox'):
        assert ET.fromstring(result).get(attr)==ET.fromstring(svg).get(attr)
    assert 'PRESERVE_DIAGNOSTICS' in result
    assert finish_svg(result,plan,sol)==result


def test_transformations_and_different_angles():
    for angle in (28,53,74,90,112,147):
        for rotation in (0,37,173):
            for reflected in (1,-1):
                plan,sol,svg = fixture(angle,rotation,reflected)
                result = finish_svg(svg,plan,sol)
                assert len(items(result,'angle-equality-tick')) == 2
                assert len(items(result,'parallel-mark')) == 2


def test_bad_parallel_not_marked():
    plan,sol,svg = fixture()
    sol.coords['R'] = (8.,22.)
    assert not items(finish_svg(svg,plan,sol),'parallel-mark')


def test_accidental_parallel_not_marked():
    plan,sol,svg = fixture()
    plan.constructions = [c for c in plan.constructions if c.op!='translate']
    assert not items(finish_svg(svg,plan,sol),'parallel-mark')


def test_parallel_constraint_in_reverse_order():
    plan,sol,svg = fixture()
    plan.constructions = [c for c in plan.constructions if c.op!='translate']
    plan.constraints = [S(type='parallel',args=['L','A','K','M'])]
    assert len(items(finish_svg(svg,plan,sol),'parallel-mark')) == 2


def test_missing_drawn_partner_leaves_no_orphan_arrow():
    plan,sol,svg = fixture()
    root = ET.fromstring(svg)
    main = next(e for e in root.iter() if e.get('id')=='main')
    main.remove(list(main)[3])
    assert not items(finish_svg(ET.tostring(root,encoding='unicode'),plan,sol),'parallel-mark')


def test_unlabelled_vertex_is_not_a_helper():
    plan,sol,svg = fixture()
    plan.draw.hide_labels.append('A')
    assert any(e.get('data-point')=='A' for e in ET.fromstring(finish_svg(svg,plan,sol)).iter())


def test_measured_helper_endpoint_is_preserved():
    plan,sol,svg = fixture()
    plan.draw.length_marks = [{'pts':['A','L'],'text':'5'}]
    assert any(e.get('data-point')=='L' for e in ET.fromstring(finish_svg(svg,plan,sol)).iter())


def test_ordinary_angle_annotations_get_no_equality_ticks():
    plan,sol,svg = fixture()
    for mark in plan.draw.angle_marks:
        del mark['count']
    assert not items(finish_svg(svg,plan,sol),'angle-equality-tick')


def test_unknown_transform_is_unchanged():
    plan,sol,svg = fixture()
    sol.coords['C'] = (100.,100.)
    assert finish_svg(svg,plan,sol)==svg


def test_mock_renderer_return_is_preserved():
    assert finish_svg(['mock'],None,None)==['mock']


def test_unequal_declared_angles_get_no_ticks():
    plan,sol,svg = fixture()
    plan.draw.angle_marks[1]['pts'] = ['L','A','B']
    assert not items(finish_svg(svg,plan,sol),'angle-equality-tick')


def test_existing_renderer_wrapper_calls_finisher():
    from geoexact.core.bisector_marks import install
    plan,sol,svg = fixture()
    renderer = S(render_svg=lambda p,s,**kw: svg)
    assert install(renderer) and not install(renderer)
    result = renderer.render_svg(plan,sol)
    assert len(items(result,'angle-equality-tick')) == 2
    assert len(items(result,'parallel-mark')) == 2


def test_unrecognised_coordinates_preserve_original_svg():
    plan,sol,svg = fixture()
    sol.coords['R'] = 1.0
    assert finish_svg(svg,plan,sol)==svg
