# -*- coding: utf-8 -*-
"""CH26: живая перепроверка инцидентности на 6 задачах.

Отбирает детерминированно 6 задач из FORMYLA_geometry_7_11_chertezh_v13.jsonl,
где в условии есть «вписан», «лежит на окружности» или «на одной окружности».

Для каждой задачи прогоняет реальный base-планировщик + валидатор
(MISSING_INCIDENCE) + движок (INCIDENCE_VIOLATED), выводит:
  task_uid, использован ли inscribed_polygon/point_on_circle,
  число incidences, пройдена ли INCIDENCE_VIOLATED,
  максимальное отклонение точки от окружности, status, путь к SVG.

Запуск: python scripts/ch26_probe.py
"""
import io
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INPUT = os.path.join(_ROOT, "FORMYLA_geometry_7_11_chertezh_v13.jsonl")
_OUT = os.path.join(_ROOT, "output", "ch26")
_SVG_DIR = os.path.join(_OUT, "svg")

# env до импорта routes
os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
os.environ["FIGURE_AUX_LEGACY_PLANNER"] = "false"
# Маршрутизировать base/aux/audit (v4-flash) напрямую через DeepSeek API,
# минуя недоступный Novita.
os.environ["FIGURE_DISABLE_NOVITA"] = "1"

_INCIDENCE_RE = re.compile(
    r"(вписан|лежит\s+на\s+окружност|на\s+одной\s+окружност)",
    re.IGNORECASE,
)


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


def _select_tasks(limit=6):
    recs = []
    with open(_INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            cond = (d.get("statement") or "")
            if _INCIDENCE_RE.search(cond):
                recs.append(d)
            if len(recs) >= limit:
                break
    return recs


def _analyze_plan(plan_json):
    """Извлечь: использован ли inscribed_polygon/point_on_circle, число incidences."""
    data = plan_json if isinstance(plan_json, dict) else json.loads(plan_json)
    cs = data.get("constructions", [])
    used_inscribed = any(c.get("type") == "inscribed_polygon" for c in cs)
    used_point_on_circle = any(c.get("type") == "point_on_circle" for c in cs)
    n_incidences = len(data.get("incidences", []) or [])
    return used_inscribed, used_point_on_circle, n_incidences


def _max_circle_deviation(base_plan_json):
    """Максимальное отклонение точек от их окружностей (в пикселях)."""
    from geometric_engine.engine import GeometricEngine
    from geometric_engine import geom
    data = base_plan_json if isinstance(base_plan_json, dict) else json.loads(base_plan_json)
    eng = GeometricEngine()
    try:
        svg, ctx = eng.build(data)
    except Exception:
        return None
    max_dev = 0.0
    for inc in ctx.incidences:
        if inc.get("on") != "circle":
            continue
        circle = ctx.circles.get(inc.get("object"))
        if circle is None or inc.get("point") not in ctx.points:
            continue
        center, radius = circle
        dev = abs(geom.dist(center, ctx.points[inc["point"]]) - radius)
        max_dev = max(max_dev, dev)
    return max_dev


def main():
    _load_env()
    recs = _select_tasks(6)
    if not recs:
        print("Не найдено 6 задач с инцидентностью в условии.")
        return

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg

    os.makedirs(_SVG_DIR, exist_ok=True)

    tmpdir = tempfile.mkdtemp(prefix="ch26_probe_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    rows = []
    with app.app_context():
        db.create_all()
        u = User(email="ch26p@example.invalid", nickname="ch26p",
                 is_guest=False, figure_credits=100)
        db.session.add(u)
        db.session.commit()

        for d in recs:
            job = FigureBuildJob(
                user_id=u.id,
                problem_text=d["statement"],
                solution_text=d.get("solution") or "",
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
            uid = str(d.get("task_uid", "?"))[:28]
            base_plan_json = job.base_plan_json
            used_inscribed = used_point = n_inc = None
            max_dev = None
            incidence_passed = None

            if base_plan_json:
                used_inscribed, used_point, n_inc = _analyze_plan(base_plan_json)
                max_dev = _max_circle_deviation(base_plan_json)

            # INCIDENCE_VIOLATED считается «пройденной», если job не упал на
            # base с сообщением про инцидентность.
            incidence_passed = "INCIDENCE_VIOLATED" not in (job.error or "") \
                and "MISSING_INCIDENCE" not in (job.audit_json or "")

            # Сохранить SVG.
            svg_path = ""
            if job.svg_path:
                fn = f"{re.sub(r'[^A-Za-z0-9_.-]', '_', uid)}_base.svg"
                p = os.path.join(_SVG_DIR, fn)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(job.svg_path)
                svg_path = p

            rows.append({
                "task_uid": uid,
                "used_inscribed": used_inscribed,
                "used_point_on_circle": used_point,
                "n_incidences": n_inc,
                "incidence_passed": incidence_passed,
                "max_dev": max_dev,
                "status": job.status,
                "svg_path": svg_path,
                "latency_ms": latency_ms,
                "condition": (d.get("statement") or "")[:80],
            })
            print(".", end="", flush=True)
        print()

    # ── Таблица ──
    print("| task_uid | inscribed | point_on_circle | incidences | inc_passed | max_dev(px) | status | latency_ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md = "-" if r["max_dev"] is None else f"{r['max_dev']:.6f}"
        ui = "-" if r["used_inscribed"] is None else ("1" if r["used_inscribed"] else "0")
        up = "-" if r["used_point_on_circle"] is None else ("1" if r["used_point_on_circle"] else "0")
        ip = "-" if r["incidence_passed"] is None else ("1" if r["incidence_passed"] else "0")
        ni = "-" if r["n_incidences"] is None else str(r["n_incidences"])
        print(f"| {r['task_uid']} | {ui} | {up} | {ni} | {ip} | {md} | {r['status']} | {r['latency_ms']} |")

    # ── Сохранить результаты JSON ──
    out_json = os.path.join(_OUT, "probe_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"\n[ch26] results: {out_json}")
    print(f"[ch26] svg dir: {_SVG_DIR}")


if __name__ == "__main__":
    main()
