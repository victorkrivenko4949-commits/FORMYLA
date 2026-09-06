#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL-проверки для верификации REC-1..REC-8 (Block C и Block E).

Пишет результаты в scripts/verify/out/.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)


def db_path():
    candidates = [
        os.path.join(BASE, "instance", "formyla.db"),
        os.path.join(BASE, "formyla.db"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("formyla.db not found")


def run():
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row

    # ── Block C1: сохранность problem_text (колонка называется problem_text,
    #    а НЕ condition_text — см. models.py:1797) ──
    rows = con.execute(
        "SELECT id, substr(problem_text,1,150) AS stored, "
        "length(problem_text) AS len "
        "FROM figure_build_jobs ORDER BY id DESC LIMIT 5"
    ).fetchall()

    out_c = {
        "db": db_path(),
        "rows": [
            {"id": r["id"], "stored": r["stored"], "len": r["len"]}
            for r in rows
        ],
    }
    # Признаки LaTeX-разметки в поле.
    for r in rows:
        txt = r["stored"] or ""
        r_d = dict(r)
        r_d["has_latex_paren"] = "\\(" in txt or "\\)" in txt
        r_d["has_dollar"] = "$" in txt
        r_d["has_degree"] = "^\\circ" in txt or "°" in txt
        out_c["rows"].append({
            "id": r_d["id"], "stored": r_d["stored"], "len": r_d["len"],
            "has_latex_paren": r_d.get("has_latex_paren"),
            "has_dollar": r_d.get("has_dollar"),
            "has_degree": r_d.get("has_degree"),
        })
    with open(os.path.join(OUT, "c1_condition_text.json"), "w", encoding="utf-8") as f:
        json.dump(out_c, f, ensure_ascii=False, indent=2)

    # ── Block E1: метрики по ролям ──
    try:
        erows = con.execute(
            "SELECT role, provider, model, COUNT(*) AS calls, "
            "AVG(coverage_score) AS avg_cov, AVG(visual_score) AS avg_vis, "
            "AVG(latency_ms) AS avg_ms, "
            "SUM(CASE WHEN validation_passed THEN 0 ELSE 1 END) AS fails, "
            "SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END) AS fallbacks, "
            "SUM(estimated_cost_usd) AS cost_usd "
            "FROM figure_build_stages "
            "GROUP BY role, provider, model ORDER BY role"
        ).fetchall()
        out_e = {"rows": [dict(r) for r in erows]}
        with open(os.path.join(OUT, "e1_metrics.json"), "w", encoding="utf-8") as f:
            json.dump(out_e, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        with open(os.path.join(OUT, "e1_metrics_error.txt"), "w", encoding="utf-8") as f:
            f.write(str(e))

    # ── Block C: колонки таблицы figure_build_jobs ──
    cols = con.execute("PRAGMA table_info(figure_build_jobs)").fetchall()
    out_cols = [dict(c) for c in cols]
    with open(os.path.join(OUT, "c_job_columns.json"), "w", encoding="utf-8") as f:
        json.dump(out_cols, f, ensure_ascii=False, indent=2, default=str)

    # ── Block E: колонки figure_build_stages ──
    scols = con.execute("PRAGMA table_info(figure_build_stages)").fetchall()
    out_scols = [dict(c) for c in scols]
    with open(os.path.join(OUT, "e_stage_columns.json"), "w", encoding="utf-8") as f:
        json.dump(out_scols, f, ensure_ascii=False, indent=2, default=str)

    print("DB:", db_path())
    print("condition rows:", len(rows))
    print("metrics rows:", len(erows) if 'erows' in dir() else "ERR")
    print("written to", OUT)


if __name__ == "__main__":
    run()
