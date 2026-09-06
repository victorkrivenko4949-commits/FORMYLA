# -*- coding: utf-8 -*-
"""Верификация фиксов E8/E9/E10 на задаче о параллелограмме."""
import sys, json, io, xml.etree.ElementTree as ET, cairosvg
sys.path.insert(0, "/home/user/workspace/formyla_final")
from geometric_engine import engine as E
from services.aux_compiler import compile_solver_aux, fidelity_report
from services.base_normalizer import normalize_base_plan

solver_result = json.load(open("/home/user/workspace/e2e_out2/solver_parallelogram.json", encoding="utf-8"))
base_plan_raw = json.load(open("/home/user/workspace/e2e_out2/base_plan_parallelogram.json", encoding="utf-8"))

# E10: нормализация base-плана — все данное становится solid (style:base)
base_plan = normalize_base_plan(base_plan_raw)

print("=== Проверка E10: base-стиль ===")
bad_style = [c for c in base_plan["constructions"] if c.get("style") == "aux" or c.get("dashed")]
print(f"  base-объектов с style=aux/dashed: {len(bad_style)} (должно быть 0)")
bm = next((c for c in base_plan["constructions"] if c.get("id") == "BM"), None)
if bm:
    print(f"  BM: style={bm.get('style')} dashed={bm.get('dashed')} (должно base/False)")

print("\n=== Проверка E8: compile_solver_aux (нет краша на дубле медианы) ===")
aux_plan, issues = compile_solver_aux(solver_result, base_plan)
print(f"  has_aux={aux_plan.get('has_aux')} constructions={len(aux_plan.get('constructions',[]))}")
print(f"  issues={issues}")
fulfilled = [i for i in issues if "FULFILLED_BY_BASE" in str(i)]
print(f"  FULFILLED_BY_BASE (пере-диктованное данное пропущено): {fulfilled}")

print("\n=== Проверка E9: эмит отрезка продления для reflect_point ===")
ext_segs = [c for c in aux_plan.get("constructions", []) if c.get("id", "").startswith("aux_ext_")]
print(f"  отрезков продления: {len(ext_segs)} (должно быть >=1)")
for s in ext_segs:
    print(f"    {s.get('id')}: {s.get('p1')}-{s.get('p2')} style={s.get('style')}")

print("\n=== Рендер с auto_fit ===")
merged = {"constructions": base_plan["constructions"] + aux_plan.get("constructions", [])}
ctx = E.BuildContext(); fails=[]
for c2 in merged["constructions"]:
    try: E.execute_construction(ctx, c2)
    except Exception as e:
        msg=str(e)
        if "уже существует" in msg:
            print(f"  E8 FAIL: повторное создание точки: {msg}")
            continue
        fails.append((c2.get("id") or c2.get("type"), msg))
_s=E.EngineSettings(); _s.auto_fit=True
W=620; H=460
svg=E.render_svg(ctx,W,H,_s)
open("/home/user/workspace/e2e_out2/parallelogram_fixed.svg","w",encoding="utf-8").write(svg)
print(f"  points={list(ctx.points.keys())} render_fails={fails}")
print(f"  K в точках: {'K' in ctx.points}  K={ctx.points.get('K')}")

ET.register_namespace('',"http://www.w3.org/2000/svg")
tree=ET.parse("/home/user/workspace/e2e_out2/parallelogram_fixed.svg"); root=tree.getroot()
for t in root.iter("{http://www.w3.org/2000/svg}text"):
    for a in list(t.attrib):
        if a in ("stroke","stroke-width","paint-order"): del t.attrib[a]
buf=io.BytesIO(); tree.write(buf,encoding="utf-8",xml_declaration=True)
cairosvg.svg2png(bytestring=buf.getvalue(),write_to="/home/user/workspace/e2e_out2/parallelogram_fixed.png",output_width=W,output_height=H)
print("  PNG written")
