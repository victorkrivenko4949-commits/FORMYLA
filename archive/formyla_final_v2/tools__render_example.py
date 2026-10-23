# -*- coding: utf-8 -*-
"""tools/render_example.py — пример полного конвейера ФОРМУЛА с фиксированным кодом.

Показывает, как соединить base_plan (base_planner) + solver_result (DeepSeek)
через compile_solver_aux → normalize_base_plan → geometric_engine с auto_fit.

Запуск:
  python tools/render_example.py
(использует готовые JSON из e2e_out2; для свежего прогона запустите solver_only.py)
"""
import sys, json, io, xml.etree.ElementTree as ET, cairosvg
sys.path.insert(0, "/home/user/workspace/formyla_final")
from geometric_engine import engine as E
from services.aux_compiler import compile_solver_aux
from services.base_normalizer import normalize_base_plan

SOLVER = "/home/user/workspace/e2e_out2/solver_parallelogram.json"
BASE = "/home/user/workspace/e2e_out2/base_plan_parallelogram.json"
OUT_SVG = "/home/user/workspace/e2e_out2/parallelogram_fixed.svg"
OUT_PNG = "/home/user/workspace/e2e_out2/parallelogram_fixed.png"

solver_result = json.load(open(SOLVER, encoding="utf-8"))
base_plan_raw = json.load(open(BASE, encoding="utf-8"))

# E10: нормализация — всё данное становится solid (style:base, dashed=False).
base_plan = normalize_base_plan(base_plan_raw)

# E8/E9: компиляция aux. Пере-диктованное данное пропускается (FULFILLED_BY_BASE),
# для line_extension→reflect_point эмитится видимый отрезок продления.
aux_plan, issues = compile_solver_aux(solver_result, base_plan)
print(f"compile: has_aux={aux_plan.get('has_aux')} issues={issues}")

merged = {"constructions": base_plan["constructions"] + aux_plan.get("constructions", [])}
ctx = E.BuildContext()
for c in merged["constructions"]:
    try:
        E.execute_construction(ctx, c)
    except Exception as e:
        msg = str(e)
        if "уже существует" not in msg:  # E8: дубль данного уже пропущен компилятором
            print(f"  render warn {c.get('id')}: {msg}")

# auto_fit обязательно — иначе aux-точки (K) уходят за кадр.
_s = E.EngineSettings(); _s.auto_fit = True
W, H = 620, 460
svg = E.render_svg(ctx, W, H, _s)
open(OUT_SVG, "w", encoding="utf-8").write(svg)

# cairosvg не поддерживает paint-order → убираем stroke у text, иначе фон съедает буквы.
ET.register_namespace('', "http://www.w3.org/2000/svg")
tree = ET.parse(OUT_SVG); root = tree.getroot()
for t in root.iter("{http://www.w3.org/2000/svg}text"):
    for a in list(t.attrib):
        if a in ("stroke", "stroke-width", "paint-order"):
            del t.attrib[a]
buf = io.BytesIO(); tree.write(buf, encoding="utf-8", xml_declaration=True)
cairosvg.svg2png(bytestring=buf.getvalue(), write_to=OUT_PNG, output_width=W, output_height=H)
print(f"PNG written: {OUT_PNG}")
