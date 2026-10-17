"""Independent coordinate audit of an explicit mandatory statement contract.

This module does not extract facts from prose and does not repair geometry.
The caller must supply every mandatory fact. Unsupported facts fail closed.
It is deliberately not wired into production until integration tests exist.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Requirement:
    id: str
    kind: str
    points: tuple[str, ...]
    source: str
    value: float | None = None


ARITY = {"length": 2, "equal_length": 4, "midpoint": 3,
         "on_segment": 3, "perpendicular": 4, "parallel": 4,
         "bisector": 4, "triangle": 3}


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1]


def _norm(v):
    return math.hypot(*v)


def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]


def _cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def _segment(p, a, b, tol):
    v, w = _sub(b,a), _sub(p,a)
    length = _norm(v)
    if length <= 0:
        return False
    t = _dot(w,v)/(length*length)
    return abs(_cross(v,w))/(length*length) <= tol and -tol <= t <= 1+tol


def _holds(kind, p, value, tol):
    if kind == "length":
        if isinstance(value, bool) or value is None or not math.isfinite(value) or value <= 0:
            raise ValueError("positive finite length required")
        return abs(_norm(_sub(p[1],p[0]))-value) <= tol*value
    if kind == "equal_length":
        x, y = _norm(_sub(p[1],p[0])), _norm(_sub(p[3],p[2]))
        return min(x,y)>0 and abs(x-y) <= tol*max(x,y)
    if kind in ("on_segment", "midpoint"):
        x,a,b = p
        if not _segment(x,a,b,tol):
            return False
        if kind == "on_segment":
            return True
        middle = ((a[0]+b[0])/2,(a[1]+b[1])/2)
        return _norm(_sub(x,middle)) <= tol*_norm(_sub(b,a))
    if kind in ("parallel", "perpendicular"):
        u,v = _sub(p[1],p[0]), _sub(p[3],p[2])
        scale = _norm(u)*_norm(v)
        if scale <= 0:
            return False
        error = _dot(u,v) if kind == "perpendicular" else _cross(u,v)
        return abs(error) <= tol*scale
    if kind == "triangle":
        a,b,c = p
        u,v,w = _sub(b,a),_sub(c,a),_sub(c,b)
        scale = max(_norm(u),_norm(v),_norm(w))
        return scale>0 and abs(_cross(u,v)) > tol*scale*scale
    if kind == "bisector":
        # (vertex, point on INTERNAL bisector, first side point, second side point)
        a,e,b,c = p
        u,v,w = _sub(b,a),_sub(c,a),_sub(e,a)
        nu,nv,nw = _norm(u),_norm(v),_norm(w)
        if min(nu,nv,nw)<=0 or abs(_cross(u,v)) <= tol*nu*nv:
            return False
        direction = (u[0]/nu+v[0]/nv,u[1]/nu+v[1]/nv)
        return (_dot(direction,w)>0 and
                abs(_cross(direction,w)) <= tol*_norm(direction)*nw)
    raise ValueError("unsupported kind")


def audit(requirements, coords, tol=1e-4):
    """Report one verdict per fact. Never equate absent/unsupported with passed."""
    if not math.isfinite(tol) or tol<=0:
        raise ValueError("tol must be positive and finite")
    rows=[]
    seen=set()
    for r in requirements:
        status="invalid_requirement"
        if not r.id or r.id in seen or not r.source.strip():
            pass
        elif r.kind not in ARITY:
            status="unsupported"
        elif len(r.points)!=ARITY[r.kind]:
            pass
        elif any(n not in coords for n in r.points):
            status="missing_point"
        else:
            try:
                p=[tuple(float(x) for x in coords[n]) for n in r.points]
                if any(len(q)!=2 or not all(math.isfinite(x) for x in q) for q in p):
                    status="invalid_coordinates"
                else:
                    status="passed" if _holds(r.kind,p,r.value,tol) else "violated"
            except (ValueError,TypeError,OverflowError):
                status="invalid_requirement"
        seen.add(r.id)
        rows.append({"id":r.id,"kind":r.kind,"source":r.source,"status":status})
    return {"ok":bool(rows) and all(r["status"]=="passed" for r in rows),
            "requirements":rows}
