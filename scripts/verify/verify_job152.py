#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block A1 + F3: прогнать check_condition_coverage на РЕАЛЬНОМ плане job 152
и измерить углы/длины численно.  Без LLM, без сети, без БД-записи.

Пишет результат в scripts/verify/out/.
"""
import json
import math
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

from geometric_engine.engine import GeometricEngine
from geometric_engine import geom
from services.condition_coverage import check_condition_coverage
from services.answer_verifier import verify_answer


def db_path():
    for c in (
        os.path.join(BASE, "instance", "formyla.db"),
        os.path.join(BASE, "formyla.db"),
    ):
        if os.path.exists(c):
            return c
    raise FileNotFoundError


def main():
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT id, problem_text, base_plan_json, solution_json, status "
        "FROM figure_build_jobs WHERE id=152"
    ).fetchone()
    if row is None:
        print(json.dumps({"error": "job 152 not found"}, ensure_ascii=False))
        return

    condition = row["problem_text"]
    plan = json.loads(row["base_plan_json"])
    solution = json.loads(row["solution_json"]) if row["solution_json"] else None

    engine = GeometricEngine()
    engine.settings.auto_fit = False
    svg, ctx = engine.build(plan)

    # ── A1: CONDITION_NOT_REALIZED на реальном плане ──
    cov = check_condition_coverage(condition, plan, build_context=ctx,
                                   settings=engine.settings)
    cov_codes = [e.split(":")[0] for e in cov.get("errors", [])]

    # ── F3: численные измерения ──
    pts = ctx.points
    def ang(a, b, c):
        if a in pts and b in pts and c in pts:
            return math.degrees(geom.angle_between_three(pts[a], pts[b], pts[c]))
        return None

    def dist(a, b):
        if a in pts and b in pts:
            return geom.dist(pts[a], pts[b])
        return None

    measures = {
        "BAC": ang("B", "A", "C"),
        "ABC": ang("A", "B", "C"),
        "BCA": ang("A", "C", "B"),
        "BOC": ang("B", "O", "C"),
    }
    dists = {
        "AB": dist("A", "B"), "AC": dist("A", "C"),
        "BD": dist("B", "D"), "CE": dist("C", "E"),
        "OA": dist("O", "A"), "OB": dist("O", "B"), "OC": dist("O", "C"),
    }
    # отношения
    ratios = {}
    if dists.get("AB") and dists.get("AC"):
        ratios["AB/AC"] = dists["AB"] / dists["AC"]
    if dists.get("BD") and dists.get("CE"):
        ratios["BD/CE"] = dists["BD"] / dists["CE"]

    # ── A3: solver-v2 — содержимое solution_json job 152 (старый solver-v1) ──
    sol = {}
    if solution:
        sol = {
            "aux_needed": solution.get("aux_needed"),
            "answer_value": (solution.get("answer") or {}).get("value"),
            "aux_constructions": solution.get("aux_constructions"),
            "steps": solution.get("steps"),
        }

    out = {
        "job_id": 152,
        "status": row["status"],
        "A1_errors": cov.get("errors"),
        "A1_has_CONDITION_NOT_REALIZED": "CONDITION_NOT_REALIZED" in cov_codes,
        "A1_complete": cov.get("complete"),
        "A1_repair_feedback": cov.get("repair_feedback"),
        "F3_measures_deg": measures,
        "F3_dists_px": dists,
        "F3_ratios": ratios,
        "A3_solution_json_job152": sol,
    }

    with open(os.path.join(OUT, "a1_f3_job152.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps({
        "A1_has_CONDITION_NOT_REALIZED": out["A1_has_CONDITION_NOT_REALIZED"],
        "A1_complete": out["A1_complete"],
        "BAC": round(measures["BAC"], 2),
        "ABC": round(measures["ABC"], 2),
        "BOC": round(measures["BOC"], 2),
        "BD/CE": round(ratios.get("BD/CE"), 4) if ratios.get("BD/CE") else None,
        "A3_aux_needed": sol.get("aux_needed"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
