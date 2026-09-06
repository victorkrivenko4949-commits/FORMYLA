# -*- coding: utf-8 -*-
"""Прогнать completeness audit напрямую для job 618 и показать raw ответ Gemini."""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from services.figure_completeness_audit import audit_figure_completeness

con = sqlite3.connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = sqlite3.Row
r = con.execute(
    "SELECT problem_text, aux_svg_path, svg_path FROM figure_build_jobs WHERE id=618"
).fetchone()
cond = r["problem_text"]
svg = r["aux_svg_path"] or r["svg_path"] or ""

res = audit_figure_completeness(svg, cond)
out = {
    "complete": res.get("complete"),
    "skipped": res.get("skipped"),
    "missing": res.get("missing"),
    "repair_plan": res.get("repair_plan"),
    "raw": res.get("raw"),
}
with open(os.path.join(BASE, "scripts", "verify", "out", "job618_audit_result.json"),
          "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])
