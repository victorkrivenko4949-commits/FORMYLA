#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Текущее состояние: свежие job'ы с timestamp и статусом, активные worker-потоки."""
import json
import os
import sqlite3
import time

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

now = time.time()

out = {}

# свежие job'ы
rows = con.execute(
    "SELECT id, status, current_stage, generation_mode, created_at, updated_at, error "
    "FROM figure_build_jobs ORDER BY id DESC LIMIT 15"
).fetchall()
out["recent"] = []
for r in rows:
    d = dict(r)
    # возраст в минутах
    try:
        from datetime import datetime
        created = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S.%f")
        age_min = (datetime.utcnow() - created).total_seconds() / 60
        d["age_min"] = round(age_min, 1)
    except Exception:
        d["age_min"] = None
    out["recent"].append(d)

# любые незавершённые
stuck = con.execute(
    "SELECT id, status, current_stage, created_at, updated_at FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed') ORDER BY id DESC LIMIT 30"
).fetchall()
out["active_nonfinal"] = [dict(r) for r in stuck]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                       "current_state.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)

print("recent:", len(out["recent"]), "active_nonfinal:", len(out["active_nonfinal"]))
