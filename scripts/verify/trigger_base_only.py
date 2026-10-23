#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Создать base_only job для проверки fast-path генерации."""
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

row = con.execute(
    "SELECT user_id FROM figure_build_jobs ORDER BY id DESC LIMIT 1"
).fetchone()
user_id = row["user_id"] if row else 1

COND = "В треугольнике ABC угол C равен 90°, AC = 6, BC = 8. Найдите гипотенузу AB."

cur = con.execute(
    "INSERT INTO figure_build_jobs "
    "(user_id, problem_text, solution_text, generation_mode, status, "
    "model_name, priority, has_aux, credit_charged, created_at, updated_at) "
    "VALUES (?, ?, NULL, 'base_only', 'queued', 'deepseek-v4-pro', 0, 0, 0, "
    "datetime('now'), datetime('now'))",
    (user_id, COND),
)
con.commit()
print("job_id", cur.lastrowid)
