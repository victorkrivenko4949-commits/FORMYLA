# -*- coding: utf-8 -*-
"""scripts/figures_smoke_ch15.py — реальный прогон condition_solution pipeline.

Создаёт FigureBuildJob с generation_mode="condition_solution" на ВРЕМЕННОЙ
SQLite-БД (не трогает прод instance/formyla.db), дожидается терминального
статуса через синхронный _run_condition_solution_job, собирает артефакты.

Не рендерит изображения, не использует vision, не делает SVG->PNG.
Включает FIGURE_SEMANTIC_COLORS_ENABLED=true на время прогона (env процесса).
"""
import json
import logging
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

# ── 1. Загрузить .env вручную ─────────────────────────────────────────────
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


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_load_dotenv()
# ── 2. Включить семантические цвета ТОЛЬКО для этого процесса ─────────────
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"

# ── 3. Импорты после установки env ────────────────────────────────────────
from flask import Flask  # noqa: E402
from models import db, User, FigureBuildJob  # noqa: E402
import models  # noqa: E402  (загрузить все модели)
import routes.figures_generator as fg  # noqa: E402


TASKS = {
    "task_a_altitude_foot": {
        "condition": (
            "В равнобедренном треугольнике ABC известно, что AB = AC "
            "и угол BAC равен 40°. Найдите углы ABC и ACB."
        ),
        "solution": (
            "1. Проведём высоту AH из вершины A на сторону BC.\n"
            "2. Высота к основанию является биссектрисой, поэтому "
            "угол BAH равен 20°.\n"
            "3. В прямоугольном треугольнике ABH угол ABH равен 70°.\n"
            "4. Следовательно, углы ABC и ACB равны 70°."
        ),
    },
    "task_b_target_circle": {
        "condition": (
            "В прямоугольном треугольнике ABC угол ACB равен 90°.\n"
            "Точка M — середина гипотенузы AB. Докажите, что MA = MB = MC."
        ),
        "solution": (
            "1. Проведём окружность с диаметром AB.\n"
            "2. Так как угол ACB прямой, точка C лежит на этой окружности.\n"
            "3. Центром окружности является середина AB, то есть M.\n"
            "4. Значит, MA, MB и MC — радиусы одной окружности."
        ),
    },
    "task_c_explicit_segment": {
        "condition": (
            "В треугольнике ABC точка M — середина стороны AB.\n"
            "Докажите, что площадь треугольника AMC равна половине "
            "площади треугольника ABC."
        ),
        "solution": (
            "1. Проведём отрезок MC.\n"
            "2. Треугольники AMC и BMC имеют равные основания AM и MB.\n"
            "3. Они имеют общую высоту из вершины C.\n"
            "4. Значит, площадь AMC равна половине площади ABC."
        ),
    },
    "task_d_no_aux": {
        "condition": (
            "В треугольнике ABC проведена медиана AM к стороне BC.\n"
            "Известно, что AB = 6, AC = 8 и AM = 5. Найдите BC."
        ),
        "solution": (
            "1. По формуле медианы 4·AM² = 2·AB² + 2·AC² − BC².\n"
            "2. Подставим: 100 = 72 + 128 − BC².\n"
            "3. Значит, BC² = 100 и BC = 10."
        ),
    },
}

OUT_DIR = os.path.join(_ROOT, "output", "figures_smoke")
os.makedirs(OUT_DIR, exist_ok=True)

NS = "{http://www.w3.org/2000/svg}"


def count_svg_elements(svg_text):
    """Посчитать point/line/circle/text элементы в SVG."""
    if not svg_text:
        return {"points": 0, "lines": 0, "circles": 0, "texts": 0, "strokes": []}
    try:
        root = ET.fromstring(svg_text)
    except Exception:
        return {"points": 0, "lines": 0, "circles": 0, "texts": 0, "strokes": []}
    circles = list(root.iter(NS + "circle"))
    points = [c for c in circles if float(c.get("r", 0)) <= 5]
    geo_circles = [c for c in circles if float(c.get("r", 0)) > 5]
    lines = list(root.iter(NS + "line"))
    texts = list(root.iter(NS + "text"))
    strokes = sorted(set(
        el.get("stroke") for el in root.iter()
        if el.get("stroke")
    ))
    return {
        "points": len(points),
        "lines": len(lines),
        "circles": len(geo_circles),
        "texts": len(texts),
        "strokes": strokes,
    }


def ops_from_plan(plan_json):
    if not plan_json:
        return []
    try:
        plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    except Exception:
        return []
    if not isinstance(plan, dict):
        return []
    root = plan.get("base", plan) if isinstance(plan.get("base"), dict) else plan
    cs = root.get("constructions", []) if isinstance(root, dict) else []
    return [c.get("type") for c in cs if isinstance(c, dict)]


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def main():
    # Настроить логгер-захват для подсчёта 404 / repair retry.
    capture = _Capture()
    for name in ("routes.figures_generator", "services.llm_router"):
        lg = logging.getLogger(name)
        lg.addHandler(capture)
        lg.setLevel(logging.INFO)

    tmpdir = tempfile.mkdtemp(prefix="formyla_smoke_")
    db_path = os.path.join(tmpdir, "smoke.db")
    uri = "sqlite:///" + db_path.replace("\\", "/")

    test_app = Flask(__name__)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = uri
    test_app.config["SECRET_KEY"] = "smoke-secret"
    db.init_app(test_app)

    with test_app.app_context():
        db.create_all()
        user = User(email="smoke_ch15@example.invalid",
                    nickname="smoke_ch15", is_guest=False,
                    figure_credits=20)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        credits_before = int(getattr(user, "figure_credits", 0))

        report_lines = ["# CH15 smoke run", ""]
        done_count = 0
        failed_count = 0

        for name, spec in TASKS.items():
            print("=" * 70)
            print("TASK", name)
            job = FigureBuildJob(
                user_id=user_id,
                problem_text=spec["condition"],
                solution_text=spec["solution"],
                generation_mode="condition_solution",
                status="queued",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

            t0 = time.perf_counter()
            fg._run_condition_solution_job(job_id, job)
            elapsed = time.perf_counter() - t0

            job = FigureBuildJob.query.get(job_id)
            error_code = ""
            if job.error:
                error_code = job.error.split(":", 1)[0].strip()

            base_ops = ops_from_plan(job.base_plan_json)
            aux_ops = ops_from_plan(job.aux_plan_json)
            base_svg = job.svg_path or ""
            aux_svg = job.aux_svg_path or ""

            base_counts = count_svg_elements(base_svg)
            aux_counts = count_svg_elements(aux_svg)

            # сохранить артефакты
            base_path = os.path.join(OUT_DIR, f"{name}_base.svg")
            aux_path = os.path.join(OUT_DIR, f"{name}_aux.svg")
            if base_svg:
                with open(base_path, "w", encoding="utf-8") as f:
                    f.write(base_svg)
            if aux_svg:
                with open(aux_path, "w", encoding="utf-8") as f:
                    f.write(aux_svg)

            if job.status == "done":
                done_count += 1
            elif job.status == "failed":
                failed_count += 1

            row = {
                "name": name,
                "job_id": job_id,
                "status": job.status,
                "current_stage": job.current_stage or job.status,
                "error_code": error_code,
                "base_model": job.base_model,
                "aux_model": job.aux_model,
                "has_aux": bool(job.has_aux),
                "aux_reason": job.aux_reason,
                "base_ops": base_ops,
                "aux_ops": aux_ops,
                "base_svg_bytes": len(base_svg),
                "aux_svg_bytes": len(aux_svg),
                "base_counts": base_counts,
                "aux_counts": aux_counts,
                "latency_s": round(elapsed, 2),
                "credit_charged": bool(job.credit_charged),
            }
            print(json.dumps(row, ensure_ascii=False, indent=2))

            report_lines.append(f"## {name}")
            report_lines.append("")
            report_lines.append(f"- job_id: {job_id}")
            report_lines.append(f"- status: {job.status}")
            report_lines.append(f"- current_stage: {job.current_stage or job.status}")
            report_lines.append(f"- error_code: {error_code or '-'}")
            report_lines.append(f"- base_model: {job.base_model}")
            report_lines.append(f"- aux_model: {job.aux_model}")
            report_lines.append(f"- has_aux: {bool(job.has_aux)}")
            report_lines.append(f"- aux_reason: {job.aux_reason or '-'}")
            report_lines.append(f"- base_ops: {base_ops}")
            report_lines.append(f"- aux_ops: {aux_ops}")
            report_lines.append(f"- base SVG bytes: {len(base_svg)}")
            report_lines.append(f"- aux SVG bytes: {len(aux_svg)}")
            report_lines.append(f"- base counts: {base_counts}")
            report_lines.append(f"- aux counts: {aux_counts}")
            report_lines.append(f"- latency_s: {round(elapsed, 2)}")
            report_lines.append(f"- credit_charged: {bool(job.credit_charged)}")
            report_lines.append("")

        # Итог
        user = User.query.get(user_id)
        credits_after = int(getattr(user, "figure_credits", 0))

        model_not_found = sum(
            1 for r in capture.records
            if "MODEL_NOT_FOUND" in r or "LLM_MODEL_NOT_FOUND" in r
        )
        repair_retries = [r for r in capture.records
                          if "aux repair retry" in r]

        summary = {
            "done": done_count,
            "failed": failed_count,
            "credits_before": credits_before,
            "credits_after": credits_after,
            "credits_spent": credits_before - credits_after,
            "model_not_found_logs": model_not_found,
            "repair_retries": repair_retries,
        }
        print("=" * 70)
        print("SUMMARY", json.dumps(summary, ensure_ascii=False, indent=2))

        report_lines.append("## SUMMARY")
        report_lines.append("")
        for k, v in summary.items():
            report_lines.append(f"- {k}: {v}")

        with open(os.path.join(OUT_DIR, "figures_smoke_report.md"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        print("report written to", os.path.join(OUT_DIR, "figures_smoke_report.md"))


if __name__ == "__main__":
    main()
