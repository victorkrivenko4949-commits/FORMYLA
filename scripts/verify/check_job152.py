#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block C/F: проверить problem_text job 152 и полей job'а."""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

# job 152 problem_text (полный, не substr)
r = con.execute(
    "SELECT id, problem_text, length(problem_text) AS len, status, "
    "generation_mode, trust_level, answer_verdict, solver_answer, "
    "measured_answer, aux_source, aux_usefulness, aux_dropped_reason "
    "FROM figure_build_jobs WHERE id=152"
).fetchone()

out = {}
if r:
    txt = r["problem_text"] or ""
    out = {
        "id": r["id"],
        "len": r["len"],
        "problem_text": txt,
        "has_latex_paren": "\\(" in txt,
        "has_dollar": "$" in txt,
        "has_degree_tex": "^\\circ" in txt,
        "has_degree_char": "°" in txt,
        "status": r["status"],
        "generation_mode": r["generation_mode"],
        "trust_level": r["trust_level"],
        "answer_verdict": r["answer_verdict"],
        "solver_answer": r["solver_answer"],
        "measured_answer": r["measured_answer"],
        "aux_source": r["aux_source"],
        "aux_usefulness": r["aux_usefulness"],
        "aux_dropped_reason": r["aux_dropped_reason"],
    }
else:
    out = {"error": "job 152 not found"}

with open(os.path.join(OUT, "c_job152_problem_text.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# сколько всего job'ов, сколько с LaTeX в problem_text
total = con.execute("SELECT COUNT(*) FROM figure_build_jobs").fetchone()[0]
with_latex = con.execute(
    "SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text LIKE '%\\(%' "
    "OR problem_text LIKE '%$%' OR problem_text LIKE '%°%'"
).fetchone()[0]

print(json.dumps({"total_jobs": total, "with_latex_or_degree": with_latex,
                  "job152_has_latex_paren": out.get("has_latex_paren")}, ensure_ascii=False))
