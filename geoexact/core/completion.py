"""Conservative completion of supports already implied by drawn intersections."""
import copy
import numpy as np


def complete_intersection_support(plan, solution):
    """Extend an existing segment to its explicitly constructed intersection.

    Never introduce new mathematical points/constraints or an unrelated line.
    The caller retains the unmodified plan if no extension is needed.
    """
    plan = copy.deepcopy(plan)
    coords = solution.coords
    messages = []
    aux_points = set(plan.draw.aux_points)
    # An angle/length mark must not float on an invisible supporting segment.
    # Draw only supports explicitly referenced by an existing requested mark.
    def supported(a,b):
        for field in ("segments","aux_segments","lines","aux_lines","rays","aux_rays"):
            for u,v in getattr(plan.draw,field):
                A,B=(np.asarray(coords[n],float) for n in (u,v))
                direction=B-A
                den=float(direction@direction)
                if den<1e-20:
                    continue
                valid=True
                for name in (a,b):
                    p=np.asarray(coords[name],float)-A
                    t=float(p@direction)/den
                    if abs(float(direction[0]*p[1]-direction[1]*p[0]))>1e-8*den:
                        valid=False
                    if field.endswith("segments") and not -1e-8<=t<=1+1e-8:
                        valid=False
                    if field.endswith("rays") and t < -1e-8:
                        valid=False
                if valid:
                    return True
        return False
    entries=[]
    for m in plan.draw.angle_marks:
        a,b,c=m["pts"]
        entries.extend((([a,b],m.get("layer","main")),([b,c],m.get("layer","main"))))
    for a,b,c in plan.draw.right_angles:
        layer="aux" if any(n in aux_points for n in (a,b,c)) else "main"
        entries.extend((([a,b],layer),([b,c],layer)))
    for m in plan.draw.length_marks+plan.draw.equal_marks:
        entries.append((m["pts"],m.get("layer","main")))
    for pair,layer in entries:
        if not supported(*pair):
            field="aux_segments" if layer=="aux" or any(n in aux_points for n in pair) else "segments"
            getattr(plan.draw,field).append(list(pair))
            messages.append(f"MARK_SUPPORT: добавлен отрезок {''.join(pair)} для явно заданной метки")
    for c in plan.constructions:
        if c.op != "line_intersect":
            continue
        for a, b in (c.args[:2], c.args[2:]):
            source = frozenset((a, b))
            layer = None
            for name in ("segments", "aux_segments"):
                if any(frozenset(s) == source for s in getattr(plan.draw, name)):
                    layer = name
                    break
            if layer is None:
                continue
            if any(frozenset(s) == source for s in plan.draw.lines + plan.draw.aux_lines):
                continue
            A, B, X = (np.asarray(coords[n], dtype=float) for n in (a, b, c.out))
            v = B-A
            den = float(v @ v)
            if den < 1e-20:
                continue
            t = float((X-A) @ v) / den
            if -1e-8 <= t <= 1+1e-8:
                continue
            end = a if t < 0 else b
            target = "aux_segments" if c.out in aux_points else layer
            pair = [end, c.out]
            items = getattr(plan.draw, target)
            if not any(frozenset(s) == frozenset(pair) for s in items):
                items.append(pair)
                messages.append(f"DRAW_COMPLETED: отрезок {a}{b} продолжен до пересечения {c.out}")
    return plan, messages
