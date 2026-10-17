"""Presentation-only SVG finishing. Keep world coordinates and layout intact.

Called by the installed bisector renderer wrapper. Unrecognised transforms
are left untouched. No LLM, solver, network or task-specific measurements.
"""
import math
import re
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def _hidden(plan):
    d = plan.draw
    keep = {c.out for c in plan.constructions if c.op == "free_point"}
    keep.update(getattr(getattr(plan,"target",None),"args",[]))
    for name in ("segments","aux_segments","circles","aux_circles","extensions","aux_extensions"):
        for pair in getattr(d,name,[]):
            keep.update(pair)
    for name in ("rays","aux_rays"):
        keep.update(pair[0] for pair in getattr(d,name,[]) if pair)
    carriers = {frozenset(pair) for name in ("lines","aux_lines","rays","aux_rays")
                for pair in getattr(d,name,[])}
    for name in ("length_marks","equal_marks"):
        for mark in getattr(d,name,[]):
            pts = mark.get("pts",[])
            label = (name=="length_marks" and frozenset(pts) in carriers and
                     re.fullmatch(r"[ℓlmn](?:[0-9₀-₉′']+)?",mark.get("text","").strip()))
            if not label:
                keep.update(pts)
    for mark in getattr(d,"angle_marks",[]):
        if len(mark.get("pts",[]))==3:
            keep.add(mark["pts"][1])
    for pts in getattr(d,"right_angles",[]):
        if len(pts)==3:
            keep.add(pts[1])
    for arc in getattr(d,"arcs",[]):
        keep.update(arc[k] for k in ("center","start","end"))
    return set(getattr(d,"hide_labels",[])) - keep


def _sub(a,b):
    return a[0]-b[0],a[1]-b[1]


def _cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def _unit(pair,p):
    if len(pair)!=2 or any(n not in p for n in pair):
        return None
    v = _sub(p[pair[1]],p[pair[0]])
    length = math.hypot(*v)
    return (v[0]/length,v[1]/length) if math.isfinite(length) and length>1e-12 else None


def _same_line(pair,ref,p):
    u,v = _unit(pair,p),_unit(ref,p)
    if u is None or v is None or abs(_cross(u,v))>1e-7:
        return False
    scale = max(math.dist(p[pair[0]],p[pair[1]]),math.dist(p[ref[0]],p[ref[1]]),1e-12)
    return all(abs(_cross(v,_sub(p[n],p[ref[0]])))<=1e-7*scale for n in pair)


def _frame(root,p):
    dots = {e.get("data-point"):(float(e.get("cx")),float(e.get("cy")))
            for e in root.iter("{"+NS+"}circle") if e.get("data-point") in p}
    names = list(dots)
    if len(names)<2:
        return None
    a,b = max(((a,b) for i,a in enumerate(names) for b in names[i+1:]),
              key=lambda q:math.dist(p[q[0]],p[q[1]]))
    length = math.dist(p[a],p[b])
    if length<=1e-12:
        return None
    scale = math.dist(dots[a],dots[b])/length
    ox,oy = dots[a][0]-scale*p[a][0],dots[a][1]+scale*p[a][1]
    q = {n:(ox+scale*v[0],oy-scale*v[1]) for n,v in p.items()}
    if scale<=0 or any(math.dist(q[n],v)>1e-4 for n,v in dots.items()):
        return None
    return q,dots


def _angles(plan,q):
    groups = {}
    for m in plan.draw.angle_marks:
        if "count" not in m:
            continue
        a,o,b = m["pts"]
        u,v = _unit((o,a),q),_unit((o,b),q)
        if u is None or v is None:
            continue
        if m.get("reverse_first",False):
            u = (-u[0],-u[1])
        delta = math.atan2(_cross(u,v),u[0]*v[0]+u[1]*v[1])
        if m.get("reflex",False):
            delta -= math.copysign(2*math.pi,delta)
        groups.setdefault(m["count"],[]).append((q[o],u,v,delta,m["count"]))
    return [item for group in groups.values() if len(group)>=2
            and min(abs(g[3]) for g in group)>1e-6
            and max(abs(g[3]) for g in group)-min(abs(g[3]) for g in group)<=math.radians(.01)
            for item in group]


def _drawn(plan,root,q):
    drawn = []
    for e in root.iter("{"+NS+"}line"):
        kind = e.get("data-kind")
        if kind not in ("segments","lines","rays"):
            continue
        layer = "aux" if "aux-seg" in e.get("class","").split() else "main"
        a,b = (float(e.get("x1")),float(e.get("y1"))),(float(e.get("x2")),float(e.get("y2")))
        for pair in getattr(plan.draw,("aux_" if layer=="aux" else "")+kind,[]):
            if any(n not in q for n in pair):
                continue
            p = {"a":a,"b":b,"p":q[pair[0]],"q":q[pair[1]]}
            if not _same_line(("p","q"),("a","b"),p):
                continue
            if kind=="segments" and min(math.dist(a,p["p"])+math.dist(b,p["q"]),
                                         math.dist(a,p["q"])+math.dist(b,p["p"]))>1e-4:
                continue
            drawn.append((tuple(pair),layer,a,b))
    return drawn


def _parallel_groups(plan,p,drawn):
    claims = [(c.args[:2],c.args[2:]) for c in getattr(plan,"constraints",[])
              if c.type=="parallel" and len(c.args)==4]
    claims += [([c.args[0],c.out],c.args[1:]) for c in plan.constructions
               if c.op in ("translate","parallel_point") and len(c.args)==3]
    parent = list(range(len(drawn)))
    def root(i):
        while parent[i]!=i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    active = set()
    for left,right in claims:
        u,v = _unit(left,p),_unit(right,p)
        if u is None or v is None or abs(_cross(u,v))>1e-7 or _same_line(left,right,p):
            continue
        one = [i for i,d in enumerate(drawn) if _same_line(d[0],left,p)]
        two = [i for i,d in enumerate(drawn) if _same_line(d[0],right,p)]
        for i in one:
            for j in two:
                parent[root(j)] = root(i)
                active.update((i,j))
    groups = {}
    for i in sorted(active):
        groups.setdefault(root(i),[]).append(i)
    return list(groups.values())[:3]


def _path(parent,points,kind,layer,count=1):
    fmt = lambda p:" ".join(f"{float(v):.6f}" for v in p)
    data = "M "+fmt(points[0])+"".join(" L "+fmt(p) for p in points[1:])
    ET.SubElement(parent,"{"+NS+"}path",{"class":"arc","data-kind":kind,
                  "data-layer":layer,"data-group":str(count),"d":data})


def _finish_svg(svg,plan,sol):
    if not isinstance(svg,str) or not svg.lstrip().startswith("<svg"):
        return svg
    root = ET.fromstring(svg,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if root.get("data-presentation-v1")=="1":
        return svg
    marks = next((e for e in root.iter() if e.get("id")=="marks"),None)
    if marks is None:
        return svg
    p = {n:tuple(map(float,v[:2])) for n,v in sol.coords.items()
         if len(v)>=2 and all(math.isfinite(float(x)) for x in v[:2])}
    frame = _frame(root,p)
    if frame is None:
        return svg
    q,dots = frame
    hidden,angles = _hidden(plan),_angles(plan,q)
    for arc in list(root.iter("{"+NS+"}path")):
        t = arc.get("d","").split()
        if "arc" not in arc.get("class","").split() or len(t)!=11 or t[0]!="M" or t[3]!="A":
            continue
        start,end = (float(t[1]),float(t[2])),(float(t[9]),float(t[10]))
        r = float(t[4])
        if r<=0 or abs(r-float(t[5]))>1e-5 or float(t[6])!=0:
            continue
        for o,u,v,delta,group in angles:
            expected = [(o[0]+r*w[0],o[1]+r*w[1]) for w in (u,v)]
            error = min(math.dist(start,expected[0])+math.dist(end,expected[1]),
                        math.dist(start,expected[1])+math.dist(end,expected[0]))
            if error>1e-4 or int(t[7])!=int(abs(delta)>math.pi+1e-12):
                continue
            begin,stop = math.atan2(start[1]-o[1],start[0]-o[0]),math.atan2(end[1]-o[1],end[0]-o[0])
            sweep = (stop-begin)%(2*math.pi) if int(t[8]) else -((begin-stop)%(2*math.pi))
            mid = begin+sweep/2
            half = min(2.5,r*.18)
            ends = [(o[0]+s*math.cos(mid),o[1]+s*math.sin(mid)) for s in (r-half,r+half)]
            _path(marks,ends,"angle-equality-tick",arc.get("data-layer","main"),group)
            break
    obstacles = [v for n,v in dots.items() if n not in hidden]
    for text in root.iter("{"+NS+"}text"):
        if text.get("x") is not None and text.get("y") is not None:
            obstacles.append((float(text.get("x")),float(text.get("y"))))
    drawn = _drawn(plan,root,q)
    for count,indices in enumerate(_parallel_groups(plan,p,drawn),1):
        indices = [i for i in indices if math.dist(drawn[i][2],drawn[i][3])>=18+6*count]
        if not any(not _same_line(drawn[i][0],drawn[j][0],p) for i in indices for j in indices):
            continue
        seen = set()
        for i in indices:
            pair,layer,a,b = drawn[i]
            key = (frozenset(pair),layer)
            if key in seen:
                continue
            seen.add(key)
            length = math.dist(a,b)
            u = ((b[0]-a[0])/length,(b[1]-a[1])/length)
            if u[0]<-1e-9 or (abs(u[0])<=1e-9 and u[1]<0):
                u = (-u[0],-u[1])
            n = (-u[1],u[0])
            choices = [(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])) for t in (.5,.35,.65,.25,.75)]
            center = max(choices,key=lambda v:min((math.dist(v,o) for o in obstacles),default=1000))
            for j in range(count):
                shift = (j-(count-1)/2)*6
                tip = (center[0]+u[0]*shift,center[1]+u[1]*shift)
                ends = [(tip[0]-4*u[0]+3*n[0],tip[1]-4*u[1]+3*n[1]),tip,
                        (tip[0]-4*u[0]-3*n[0],tip[1]-4*u[1]-3*n[1])]
                _path(marks,ends,"parallel-mark",layer,count)
    for parent in root.iter():
        for child in list(parent):
            if child.tag=="{"+NS+"}circle" and child.get("data-point") in hidden:
                parent.remove(child)
    root.set("data-presentation-v1","1")
    return ET.tostring(root,encoding="unicode")


def finish_svg(svg,plan,sol):
    try:
        return _finish_svg(svg,plan,sol)
    except (ET.ParseError, TypeError, ValueError, OverflowError, KeyError, IndexError):
        # An unknown renderer/coordinate format must not break a usable SVG.
        return svg
