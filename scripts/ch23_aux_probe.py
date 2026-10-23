# -*- coding: utf-8 -*-
"""CH23 PART B5: live probe двухэтапного aux на 10 constructive-задачах.

Для каждой задачи прогоняет полный condition_solution-конвейер
(base + двухэтапный aux + audit) и собирает метрики:
  task_uid, extracted_steps_count, compiled_ops_count, aux_status,
  has_aux, issues, latency_ms.

Для первых 3 задач дополнительно печатает полный steps (извлечённые
экстрактором) и скомпилированный aux_plan.

Запуск:  python scripts/ch23_aux_probe.py
"""
import io
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from services.solution_style import classify_solution_style  # noqa: E402

os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
os.environ["FIGURE_AUX_LEGACY_PLANNER"] = "false"

_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "ch23",
)


def _write_progress(rows):
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        out_path = os.path.join(_OUT_DIR, "probe_results.json")
        payload = []
        for r in rows:
            payload.append({
                "task_uid": r["task_uid"],
                "steps_count": r["steps_count"],
                "ops_count": r["ops_count"],
                "aux_status": r["aux_status"],
                "has_aux": r["has_aux"],
                "issues": r["issues"],
                "latency_ms": r["latency_ms"],
                "steps": r["steps"],
                "constructions": r["constructions"],
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Глобальный накопитель метрик компилятора (заполняется обёрткой ниже).
_probe_metrics = []


def _wrap_compiler():
    """Обернуть compile_steps_to_aux для сбора steps/issues."""
    import services.aux_compiler as ac

    original = ac.compile_steps_to_aux

    def wrapped(steps, base_plan):
        aux_plan, issues = original(steps, base_plan)
        _probe_metrics.append({
            "steps": steps if isinstance(steps, list) else [],
            "issues": list(issues) if isinstance(issues, list) else [],
            "constructions": list(aux_plan.get("constructions", []))
            if isinstance(aux_plan, dict) else [],
        })
        return aux_plan, issues

    ac.compile_steps_to_aux = wrapped
    return wrapped


def load_env(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main():
    load_env()
    _wrap_compiler()

    recs = []
    with open("output/ch19/pilot_100.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if classify_solution_style(d) == "constructive":
                recs.append(d)
            if len(recs) >= 10:
                break

    if not recs:
        print("Нет constructive-задач в pilot_100.jsonl")
        return

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg

    tmpdir = tempfile.mkdtemp(prefix="ch23_aux_probe_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    rows = []
    with app.app_context():
        db.create_all()
        u = User(email="ch23p@example.invalid", nickname="ch23p",
                 is_guest=False, figure_credits=100)
        db.session.add(u)
        db.session.commit()

        for d in recs:
            _probe_metrics.clear()
            job = FigureBuildJob(
                user_id=u.id,
                problem_text=d["statement"],
                solution_text=d["solution"],
                generation_mode="condition_solution",
                status="queued",
            )
            db.session.add(job)
            db.session.commit()
            jid = job.id

            t0 = time.time()
            fg._run_condition_solution_job(jid, job)
            latency_ms = int((time.time() - t0) * 1000)

            job = FigureBuildJob.query.get(jid)

            metric = _probe_metrics[-1] if _probe_metrics else {}
            steps = metric.get("steps", [])
            issues = metric.get("issues", [])
            compiled = metric.get("constructions", [])

            rows.append({
                "task_uid": d.get("task_uid", "?")[:32],
                "steps_count": len(steps),
                "ops_count": len(compiled),
                "aux_status": job.aux_status or "-",
                "has_aux": 1 if job.has_aux else 0,
                "issues": issues,
                "latency_ms": latency_ms,
                "steps": steps,
                "constructions": compiled,
                "record": d,
            })
            _write_progress(rows)
            print(".", end="", flush=True)
        print()

    # ── Итоговая таблица ──
    print("| task_uid | steps | ops | aux_status | has_aux | issues | latency_ms |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        issues_brief = ",".join(i.split(":")[0] for i in r["issues"]) or "-"
        print(
            f"| {r['task_uid']} | {r['steps_count']} | {r['ops_count']} | "
            f"{r['aux_status']} | {r['has_aux']} | {issues_brief} | {r['latency_ms']} |"
        )

    # ── Полный steps + aux_plan для первых 3 ──
    print("\n" + "=" * 72)
    print("ПОЛНЫЙ steps + aux_plan ДЛЯ ПЕРВЫХ 3 ЗАДАЧ")
    print("=" * 72)
    for r in rows[:3]:
        print(f"\n### {r['task_uid']}")
        print("УСЛОВИЕ:", (r["record"].get("statement") or "")[:160])
        print("РЕШЕНИЕ:", (r["record"].get("solution") or "")[:240])
        print("STEPS:")
        print(json.dumps(r["steps"], ensure_ascii=False, indent=2))
        print("AUX_PLAN constructions:")
        print(json.dumps(r["constructions"], ensure_ascii=False, indent=2))
        print("ISSUES:", r["issues"])


if __name__ == "__main__":
    main()
