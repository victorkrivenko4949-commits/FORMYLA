# -*- coding: utf-8 -*-
"""Отладка visual_check для aux-чертежа с удвоением медианы."""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from geometric_engine.engine import GeometricEngine
from services import aux_templates
from services.figure_plan_validator import merge_base_aux
from services.visual_audit import audit_rendered_figure

con = sqlite3.connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = sqlite3.Row
r = con.execute("SELECT base_plan_json, problem_text FROM figure_build_jobs WHERE id=612").fetchone()
base_plan = json.loads(r["base_plan_json"])
cond = r["problem_text"]

engine = GeometricEngine()
engine.settings.auto_fit = True
base_svg, base_ctx = engine.build(base_plan)

tpl = aux_templates.match_template(base_plan, cond, base_ctx)
aux_plan = {"has_aux": True, "constructions": tpl["constructions"]}
merged = merge_base_aux(base_plan, aux_plan)
aux_svg, aux_ctx = engine.build(merged)

print("aux_svg len:", len(aux_svg))
# Найдём bbox вспомогательной точки
for k, v in aux_ctx.points.items():
    if "aux" in k:
        print("aux point", k, v)

res = audit_rendered_figure(aux_svg, aux_ctx, merged, cond, settings=engine.settings)
print("\naudit result:")
print(json.dumps(res, ensure_ascii=False, indent=1))
