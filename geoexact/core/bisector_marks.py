"""Verified external-bisector marks, independent of LLM drawing annotations."""
import copy
import functools
import math

import numpy as np


def _angle(u, v):
    nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    if min(nu, nv) < 1e-12:
        return None
    return math.degrees(math.atan2(abs(float(u[0]*v[1]-u[1]*v[0])), float(u @ v)))


def decorate(plan, sol):
    """Copy the plan; mark only a drawn, numerically verified external bisector.

    Recognizes native external_bisector_point and bisector_point(A,D,C)
    where D is an explicit continuation of BA beyond A. No coordinates,
    constraints or target measurements are changed.
    """
    P = {k: np.asarray(v, float) for k, v in sol.coords.items()}
    by_out = {c.out: c for c in plan.constructions}
    result = copy.deepcopy(plan)
    d = result.draw
    primitives = list(d.segments) + list(d.lines) + list(d.rays)
    candidates = []
    for c in plan.constructions:
        if c.op == "external_bisector_point" and len(c.args) == 3:
            a, b, z = c.args
            candidates.append((a, b, z, c.out))
        elif c.op == "bisector_point" and len(c.args) == 3:
            a, x, y = c.args
            for e, z in ((x, y), (y, x)):
                ext = by_out.get(e)
                if (ext is not None and ext.op == "divide_segment"
                        and len(ext.args) == 2 and ext.args[1] == a
                        and ext.value is not None and ext.value > 1):
                    candidates.append((a, ext.args[0], z, c.out))
    for a, b, c, l in candidates:
        if len({a,b,c,l}) != 4 or not all(n in P for n in (a,b,c,l)):
            continue
        if not any(set(pair) == {a,l} for pair in primitives):
            continue
        u, v, w = -(P[b]-P[a]), P[c]-P[a], P[l]-P[a]
        # A native external intersection may point into the opposite half-plane.
        if _angle(u, w) is not None and _angle(u, w) > 90:
            continue
        alpha, beta, total = _angle(u,w), _angle(w,v), _angle(u,v)
        if any(t is None for t in (alpha,beta,total)):
            continue
        if min(alpha,beta) < 0.1 or abs(alpha-beta) > 0.01 or abs(alpha+beta-total) > 0.01:
            continue
        first = {"pts":[b,a,l], "reverse_first":True, "layer":"main"}
        second = {"pts":[l,a,c], "layer":"main"}
        def matches(m, wanted):
            pts = m.get("pts", [])
            return (pts == wanted["pts"] and not m.get("reflex",False)
                    and bool(m.get("reverse_first",False)) == bool(wanted.get("reverse_first",False)))
        others = [m for m in d.angle_marks if not matches(m,first) and not matches(m,second)]
        used = {m["count"] for m in others if "count" in m}
        count = next((n for n in (1,2,3) if n not in used), None)
        if count is None:
            continue
        first["count"] = second["count"] = count
        d.angle_marks = others + [first,second]
        if [b,a] not in d.extensions:
            d.extensions.append([b,a])
    return result


def install(renderer):
    original = renderer.render_svg
    if getattr(original, "_external_bisector_marks", False):
        return False
    @functools.wraps(original)
    def render_svg(plan, sol, *args, **kwargs):
        from .svg_presentation import finish_svg
        decorated = decorate(plan, sol)
        return finish_svg(original(decorated, sol, *args, **kwargs), decorated, sol)
    render_svg._external_bisector_marks = True
    renderer.render_svg = render_svg
    return True
