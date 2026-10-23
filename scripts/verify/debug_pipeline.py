# -*- coding: utf-8 -*-
"""Точно воспроизвести путь конвейера для job 611: merge_base_aux -> build_with_retry -> evaluate_usefulness."""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from geometric_engine.engine import GeometricEngine
from services import aux_templates
from services.aux_usefulness import evaluate_usefulness
from services.figure_plan_validator import merge_base_aux

con = sqlite3.connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = sqlite3.Row
r = con.execute("SELECT base_plan_json, problem_text FROM figure_build_jobs WHERE id=611").fetchone()
base_plan = json.loads(r["base_plan_json"])
cond = r["problem_text"]

engine = GeometricEngine()
base_svg, base_ctx, _, base_viol = engine.build_with_retry(base_plan)
print("base build ok:", bool(base_svg), "viol:", base_viol)

tpl = aux_templates.match_template(base_plan, cond, base_ctx)
print("template:", tpl["template_id"] if tpl else None)

aux_plan = {"has_aux": True, "reason": "типовое построение",
            "constructions": tpl["constructions"]}
merged = merge_base_aux(base_plan, aux_plan)
print("merged constructions count:", len(merged.get("constructions", [])))
print("merged aux types:", [c.get("type") for c in merged["constructions"][-3:]])

try:
    aux_svg, aux_ctx, _, aux_viol = engine.build_with_retry(merged)
    print("aux build ok:", bool(aux_svg), "viol:", aux_viol)
except Exception as e:
    print("aux build EXCEPTION:", repr(e))
    aux_ctx = None

u = evaluate_usefulness(base_ctx, aux_ctx or base_ctx,
                        aux_plan.get("constructions", []), settings=engine.settings)
print("usefulness:", json.dumps(u, ensure_ascii=False))
