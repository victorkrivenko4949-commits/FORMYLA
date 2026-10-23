# -*- coding: utf-8 -*-
"""Сгенерировать последнюю сложную задачу (девятиточечная окружность) через реальный pipeline."""
import os, sys, time, json, tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass

_load_dotenv()
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"

from flask import Flask  # noqa: E402
from models import db, User, FigureBuildJob  # noqa: E402
import models  # noqa: E402
import routes.figures_generator as fg  # noqa: E402

condition = ("Дан остроугольный треугольник ABC. Докажите, что основания его "
             "высот, середины сторон и середины отрезков, соединяющих вершины "
             "с ортоцентром, лежат на одной окружности.")
solution = ("1. Проведём высоты AD, BE и CF, где D на BC, E на CA, F на AB. Обозначим через H точку их пересечения.\n"
            "2. Обозначим через M, N, L середины сторон AB, BC, CA.\n"
            "3. Обозначим через X, Y, Z середины отрезков AH, BH, CH.\n"
            "4. Построим описанную окружность треугольника ABC с центром O.\n"
            "5. Обозначим через K середину отрезка OH.\n"
            "6. Построим окружность с центром K, проходящую через M.\n"
            "7. Все девять точек лежат на этой окружности.")

tmpdir = tempfile.mkdtemp(prefix="formyla_hard_")
uri = "sqlite:///" + os.path.join(tmpdir, "hard.db").replace("\\", "/")
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = uri
app.config["SECRET_KEY"] = "x"
db.init_app(app)

with app.app_context():
    db.create_all()
    u = User(email="hard@example.invalid", nickname="hard", is_guest=False, figure_credits=5)
    db.session.add(u); db.session.commit()

    job = FigureBuildJob(user_id=u.id, problem_text=condition, solution_text=solution,
                         generation_mode="condition_solution", status="queued")
    db.session.add(job); db.session.commit()
    jid = job.id

    t0 = time.perf_counter()
    fg._run_condition_solution_job(jid, job)
    total = time.perf_counter() - t0

    job = FigureBuildJob.query.get(jid)
    print("=" * 60)
    print("status:", job.status)
    print("stage:", job.current_stage)
    print("error:", job.error)
    print("has_aux:", job.has_aux)
    print("aux_reason:", job.aux_reason)
    print("total_time_sec:", round(total, 2))
    print("base_svg_len:", len(job.svg_path or ""))
    print("aux_svg_len:", len(job.aux_svg_path or ""))
    print("base_plan:", (job.base_plan_json or "")[:300])
    print("aux_plan:", (job.aux_plan_json or "")[:600])

    if job.svg_path:
        open(os.path.join(_ROOT, "output", "figures_bench", "task6_nine_point_base.svg"),
             "w", encoding="utf-8").write(job.svg_path)
    if job.aux_svg_path:
        open(os.path.join(_ROOT, "output", "figures_bench", "task6_nine_point_aux.svg"),
             "w", encoding="utf-8").write(job.aux_svg_path)
    print("saved base/aux SVG")
