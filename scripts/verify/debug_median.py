# -*- coding: utf-8 -*-
"""Отладка: что возвращает шаблон median_doubling для реального base-плана job 611."""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from geometric_engine.engine import GeometricEngine
from services import aux_templates
from services.aux_usefulness import evaluate_usefulness

con = sqlite3.connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = sqlite3.Row
r = con.execute("SELECT base_plan_json FROM figure_build_jobs WHERE id=611").fetchone()
plan = json.loads(r["base_plan_json"])

print("=== constructions ===")
for c in plan.get("constructions", []):
    print(c.get("type"), c.get("id"), "|", {k: v for k, v in c.items()
          if k in ("p1", "p2", "p3", "point", "center", "vertex", "side_a", "side_b", "foot_id")})

engine = GeometricEngine()
svg, ctx = engine.build(plan)

print("\n=== ctx.points ===")
for k, v in ctx.points.items():
    print(k, tuple(round(x, 1) for x in v))

cons = aux_templates._t_median_doubling(plan, "В треугольнике ABC медиана AM...", ctx)
print("\n=== template result ===")
print(json.dumps(cons, ensure_ascii=False, indent=1) if cons else "None")

if cons:
    merged = dict(plan)
    merged["constructions"] = plan["constructions"] + cons
    _, aux_ctx = engine.build(merged)
    print("\n=== aux points ===")
    for k, v in aux_ctx.points.items():
        print(k, tuple(round(x, 1) for x in v))
    r = evaluate_usefulness(ctx, aux_ctx, cons)
    print("\n=== usefulness ===")
    print(json.dumps(r, ensure_ascii=False, indent=1))
