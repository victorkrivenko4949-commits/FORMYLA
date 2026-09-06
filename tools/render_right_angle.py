# -*- coding: utf-8 -*-
"""Полный конвейер: base_plan + DeepSeek v4-pro (окружность Фалеса) → compile → render."""
import sys, json, io, xml.etree.ElementTree as ET, cairosvg
sys.path.insert(0, "/home/user/workspace/formyla_final")
from geometric_engine import engine as E
from services.aux_compiler import compile_solver_aux
from services.base_normalizer import normalize_base_plan

solver_result = json.load(open("/home/user/workspace/e2e_out2/solver_right_angle.json", encoding="utf-8"))
base_plan = normalize_base_plan(json.load(open("/home/user/workspace/e2e_out2/base_plan_right_angle.json", encoding="utf-8")))

print("=== solver (DeepSeek v4-pro) ===")
print(f"  solvable={solver_result.get('solvable')} aux_needed={solver_result.get('aux_needed')} confidence={solver_result.get('confidence')}")
for s in solver_result.get("steps", []):
    print(f"    {s.get('no')}. {s.get('text','')}")

aux_plan, issues = compile_solver_aux(solver_result, base_plan)
print(f"\n=== compile === has_aux={aux_plan.get('has_aux')} issues={issues}")
for c in aux_plan.get("constructions", []):
    print(f"    {c.get('type')} id={c.get('id')} center={c.get('center')} radius_point={c.get('radius_point')} p1={c.get('p1')} p2={c.get('p2')}")

merged = {"constructions": base_plan["constructions"] + aux_plan.get("constructions", [])}
ctx = E.BuildContext(); fails=[]
for c2 in merged["constructions"]:
    try: E.execute_construction(ctx, c2)
    except Exception as e:
        msg=str(e)
        if "уже существует" in msg:
            print(f"  skip duplicate: {msg}")
            continue
        fails.append((c2.get("id") or c2.get("type"), msg))
_s=E.EngineSettings(); _s.auto_fit=True
W=620; H=460
svg=E.render_svg(ctx,W,H,_s)
open("/home/user/workspace/e2e_out2/right_angle_full.svg","w",encoding="utf-8").write(svg)
print(f"\n=== render === points={list(ctx.points.keys())} fails={fails}")

ET.register_namespace('',"http://www.w3.org/2000/svg")
tree=ET.parse("/home/user/workspace/e2e_out2/right_angle_full.svg"); root=tree.getroot()
for t in root.iter("{http://www.w3.org/2000/svg}text"):
    for a in list(t.attrib):
        if a in ("stroke","stroke-width","paint-order"): del t.attrib[a]
buf=io.BytesIO(); tree.write(buf,encoding="utf-8",xml_declaration=True)
cairosvg.svg2png(bytestring=buf.getvalue(),write_to="/home/user/workspace/e2e_out2/right_angle_full.png",output_width=W,output_height=H)
print("  PNG written")
