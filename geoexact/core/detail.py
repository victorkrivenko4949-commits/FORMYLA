"""Optional labelled detail view for a small circular cluster with far intersections."""
import copy
from types import SimpleNamespace
import numpy as np
from .render import render_svg


def detail_view(plan, sol, *, show_aux=True):
    p={n:np.asarray(v,dtype=float) for n,v in sol.coords.items()}
    if len(p)<6:
        return None
    span=float(np.ptp(np.array(list(p.values())),axis=0).max())
    circles=plan.draw.circles+(plan.draw.aux_circles if show_aux else [])
    for o,a in circles:
        rad=float(np.linalg.norm(p[o]-p[a]))
        if rad<=0 or 2*rad>=span*.4:
            continue
        inside={n:v for n,v in p.items() if np.linalg.norm(v-p[o])<=rad*1.15}
        if len(inside)<5:
            continue
        fragment=copy.deepcopy(plan)
        fragment.points=[n for n in plan.points if n in inside]
        d=fragment.draw
        for key in ("segments","aux_segments","lines","rays","aux_lines","aux_rays",
                    "circles","aux_circles","right_angles"):
            setattr(d,key,[s for s in getattr(d,key) if all(n in inside for n in s)])
        for key in ("angle_marks","length_marks","equal_marks"):
            setattr(d,key,[m for m in getattr(d,key) if all(n in inside for n in m["pts"])])
        d.arcs=[m for m in d.arcs if all(m[k] in inside for k in ("center","start","end"))]
        d.aux_points=[n for n in d.aux_points if n in inside]
        d.hide_labels=[n for n in d.hide_labels if n in inside]
        return render_svg(fragment,SimpleNamespace(coords=inside),show_aux=show_aux,width=700)
    return None
