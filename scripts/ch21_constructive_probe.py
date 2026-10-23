# -*- coding: utf-8 -*-
"""CH21 PART 1.5: probe на 5 constructive-задачах — проверка has_aux/aux_ops."""
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


def load_env(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip(); v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main():
    load_env()
    # Отбираем 5 constructive-задач из pilot_100.
    recs = []
    with open("output/ch19/pilot_100.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if classify_solution_style(d) == "constructive":
                recs.append(d)
            if len(recs) >= 5:
                break

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg

    tmpdir = tempfile.mkdtemp(prefix="ch21_constructive_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    print("| task_uid | style | has_aux | aux_ops | aux_reason |")
    with app.app_context():
        db.create_all()
        u = User(email="ch21c@example.invalid", nickname="ch21c", is_guest=False, figure_credits=5)
        db.session.add(u); db.session.commit()

        for d in recs:
            job = FigureBuildJob(
                user_id=u.id,
                problem_text=d["statement"],
                solution_text=d["solution"],
                generation_mode="condition_solution",
                status="queued",
            )
            db.session.add(job); db.session.commit()
            jid = job.id
            fg._run_condition_solution_job(jid, job)
            job = FigureBuildJob.query.get(jid)
            aux_ops = 0
            if job.aux_plan_json:
                try:
                    aux_ops = len(json.loads(job.aux_plan_json).get("constructions", []))
                except Exception:
                    aux_ops = 0
            print(f"| {d['task_uid'][:20]} | constructive | {1 if job.has_aux else 0} | "
                  f"{aux_ops} | {(job.aux_reason or '')[:40]} |")


if __name__ == "__main__":
    main()
