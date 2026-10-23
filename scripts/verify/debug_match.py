# -*- coding: utf-8 -*-
"""Отладка: какой шаблон реально матчит match_template для job 611."""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from geometric_engine.engine import GeometricEngine
from services import aux_templates

con = sqlite3.connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = sqlite3.Row
r = con.execute("SELECT base_plan_json, problem_text FROM figure_build_jobs WHERE id=611").fetchone()
plan = json.loads(r["base_plan_json"])
cond = r["problem_text"]

engine = GeometricEngine()
svg, ctx = engine.build(plan)

m = aux_templates.match_template(plan, cond, ctx)
print("match_template result:")
print(json.dumps(m, ensure_ascii=False, indent=1) if m else "None")

# Пройдёмся по каждому шаблону вручную, чтобы увидеть кто сработал.
print("\n=== per-template ===")
for tpl in aux_templates.AUX_TEMPLATES:
    try:
        res = tpl(plan, cond, ctx)
    except Exception as e:
        res = f"ERR: {e}"
    if res:
        print(tpl.__name__, "->", json.dumps(res, ensure_ascii=False)[:200])
