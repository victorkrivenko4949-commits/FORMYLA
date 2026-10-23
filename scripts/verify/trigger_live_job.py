#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Block F: создать solver_aux job с условием job 152 в БД запущенного сервера.

Запущенный сервер (python app.py) крутит queue worker, который поллит
figure_build_jobs каждые ~1 сек.  Вставка queued-job приведёт к реальному
LLM-прогону (base через Gemini/OdiRouter, solver через DeepSeek).

НЕ меняет логику — только вставляет строку данных.
"""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

CONDITION = (
    "В остроугольном треугольнике ABC угол \\(A\\) равен \\(45^\\circ\\). "
    "Точка O — центр описанной окружности. Прямая BO пересекает сторону AC "
    "в точке D, а прямая CO пересекает сторону AB в точке E. "
    "Оказалось, что \\(BD = CE\\). Найдите угол B."
)


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

    # Найти валидного user_id (из существующих job'ов, иначе любой user).
    row = con.execute(
        "SELECT user_id FROM figure_build_jobs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None or not row["user_id"]:
        u = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        user_id = u["id"] if u else 1
    else:
        user_id = row["user_id"]

    cur = con.execute(
        "INSERT INTO figure_build_jobs "
        "(user_id, problem_text, solution_text, generation_mode, status, "
        "model_name, priority, has_aux, credit_charged, created_at, updated_at) "
        "VALUES (?, ?, NULL, 'solver_aux', 'queued', 'deepseek-v4-pro', 0, 0, 0, "
        "datetime('now'), datetime('now'))",
        (user_id, CONDITION),
    )
    con.commit()
    job_id = cur.lastrowid

    with open(os.path.join(OUT, "f_live_job_id.txt"), "w", encoding="utf-8") as f:
        f.write(str(job_id))

    print(json.dumps({"job_id": job_id, "user_id": user_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
