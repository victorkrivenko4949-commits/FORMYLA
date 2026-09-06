# -*- coding: utf-8 -*-
"""CH21 Problem B: диагностика aux-retry («Модель не смогла исправить aux»).

Извлекает из output/ch19/_pilot.db задачи с error «...исправить aux-план...»
и показывает: коды ошибок валидатора по попыткам, repair_feedback (если
сохранён в audit_json), aux_plan_json, менялся ли план.
"""
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DB = os.path.join("output", "ch19", "_pilot.db")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for r in con.execute(
        "SELECT id, problem_text, aux_plan_json, audit_json, error, status "
        "FROM figure_build_jobs WHERE error LIKE ?",
        ("%aux-план%",),
    ):
        print("=" * 100)
        print(f"job_id={r['id']} status={r['status']}")
        print(f"error: {r['error']}")
        print(f"problem: {(r['problem_text'] or '')[:80]}")
        print("--- aux_plan_json (последняя попытка) ---")
        aux = r["aux_plan_json"]
        if aux:
            try:
                d = json.loads(aux)
                print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
            except Exception:
                print(aux[:1500])
        print("--- audit_json ---")
        aud = r["audit_json"]
        if aud:
            try:
                d = json.loads(aud)
                print(json.dumps(d, ensure_ascii=False, indent=1)[:2000])
            except Exception:
                print(aud[:2000])
    con.close()


if __name__ == "__main__":
    main()
