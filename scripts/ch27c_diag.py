# -*- coding: utf-8 -*-
"""CH27c: диагностика base-repair для GEN-fill_0452 с полным логом feedback.

Перехватывает _plan_call (base), логирует каждый вызов: attempt, feedback,
и точки, которые LLM вернул в ответе.

Запуск: python scripts/ch27c_diag.py
"""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INPUT = os.path.join(_ROOT, "FORMYLA_geometry_7_11_chertezh_v13.jsonl")

os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
os.environ["FIGURE_AUX_LEGACY_PLANNER"] = "false"
os.environ["FIGURE_DISABLE_NOVITA"] = "1"


def _load_env(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _find_task(uid):
    with open(_INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("task_uid", "").startswith(uid):
                return d
    return None


def main():
    _load_env()

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg
    from services.figure_plan_schemas import parse_base_plan

    task = _find_task("GEN-fill_0452")
    assert task, "task not found"

    tmpdir = tempfile.mkdtemp(prefix="ch27c_diag_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    # Перехват _plan_call для логирования.
    orig_plan_call = fg._plan_call
    base_prompt = fg._BASE_PLANNER_PROMPT
    call_log = []

    def wrapped(prompt_template, model_name, **kw):
        resp, json_str = orig_plan_call(prompt_template, model_name, **kw)
        if prompt_template == base_prompt:
            points = []
            if json_str:
                try:
                    plan = parse_base_plan(json_str)
                    points = sorted(
                        c.get("id") for c in plan.get("constructions", [])
                        if isinstance(c, dict) and c.get("id")
                    )
                except Exception:
                    points = []
            call_log.append({
                "feedback": kw.get("repair_feedback", ""),
                "role": kw.get("role", ""),
                "points": points,
                "json_str": json_str,
            })
        return resp, json_str

    fg._plan_call = wrapped

    with app.app_context():
        db.create_all()
        u = User(email="ch27c@example.invalid", nickname="ch27c",
                 is_guest=False, figure_credits=100)
        db.session.add(u)
        db.session.commit()

        job = FigureBuildJob(
            user_id=u.id,
            problem_text=task["statement"],
            solution_text=task.get("solution") or "",
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        jid = job.id

        fg._run_condition_solution_job(jid, job)
        job = FigureBuildJob.query.get(jid)

    print(f"status={job.status}")
    print(f"error={job.error}")
    print(f"base_plan_json={'YES' if job.base_plan_json else 'NO'}")
    if job.base_plan_json:
        plan = parse_base_plan(job.base_plan_json)
        print("FINAL base points:", sorted(
            c.get("id") for c in plan.get("constructions", [])
            if isinstance(c, dict) and c.get("id")
        ))

    print(f"\nВсего base-вызовов: {len(call_log)}")
    for i, c in enumerate(call_log):
        print(f"\n=== base-вызов #{i} (role={c['role']}) ===")
        print("FEEDBACK (полностью):")
        print(repr(c["feedback"]))
        print("Точки в ответе LLM:", c["points"])
        print("raw JSON:", (c["json_str"] or "")[:400])


if __name__ == "__main__":
    main()
