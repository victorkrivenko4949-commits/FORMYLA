#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Показать base_plan_json последних упавших job'ов (диагностика Claude-планов)."""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT id, status, current_stage, generation_mode, base_model, "
    "model_name, error, base_plan_json "
    "FROM figure_build_jobs WHERE status='failed' ORDER BY id DESC LIMIT 12"
).fetchall()

out = []
for r in rows:
    plan_raw = r["base_plan_json"]
    plan = None
    plan_len = len(plan_raw) if plan_raw else 0
    if plan_raw:
        try:
            plan = json.loads(plan_raw)
        except Exception as e:
            plan = {"parse_error": str(e)}
    out.append({
        "id": r["id"],
        "stage": r["current_stage"],
        "mode": r["generation_mode"],
        "base_model": r["base_model"],
        "model_name": r["model_name"],
        "error": r["error"],
        "plan_len": plan_len,
        "plan_keys": list(plan.keys()) if isinstance(plan, dict) else None,
        "plan_constructions_count": len(plan.get("constructions", [])) if isinstance(plan, dict) else None,
    })

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                       "failed_plans.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)

print(json.dumps(out, ensure_ascii=False, default=str)[:4000])
