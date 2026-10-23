#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Создать job с конкретным условием для отладки."""
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

row = con.execute(
    "SELECT user_id FROM figure_build_jobs ORDER BY id DESC LIMIT 1"
).fetchone()
user_id = row["user_id"] if row else 1

COND = sys.argv[1] if len(sys.argv) > 1 else (
    "В прямоугольном треугольнике \\(ABC\\) угол \\(C\\) равен \\(90^\\circ\\), "
    "\\(AC = 6\\), \\(BC = 8\\). Найдите расстояние от вершины \\(C\\) до гипотенузы."
)

mode = sys.argv[2] if len(sys.argv) > 2 else "base_only"

cur = con.execute(
    "INSERT INTO figure_build_jobs "
    "(user_id, problem_text, solution_text, generation_mode, status, "
    "model_name, priority, has_aux, credit_charged, created_at, updated_at) "
    "VALUES (?, ?, NULL, ?, 'queued', 'deepseek-v4-pro', 0, 0, 0, "
    "datetime('now'), datetime('now'))",
    (user_id, COND, mode),
)
con.commit()
print("job_id", cur.lastrowid)
