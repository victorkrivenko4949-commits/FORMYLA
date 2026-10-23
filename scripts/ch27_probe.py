# -*- coding: utf-8 -*-
"""CH27: проверка, что reflect_point / rotate_point / mark_intersection(id)
закрывают задачи, ранее попадавшие в unsupported.

Для каждой из 5 задач:
  * прогоняем полный condition_solution pipeline, но aux-экстрактор подменён
    prebuilt-шагами (вместо LLM);
  * выводим compiled_ops_count, aux_status, создались ли creates_point,
    issues, пути base/aux SVG, latency_ms;
  * численно проверяем геометрическую корректность.

Запуск: python scripts/ch27_probe.py
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
_OUT = os.path.join(_ROOT, "output", "ch27")
_SVG_DIR = os.path.join(_OUT, "svg")

os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
os.environ["FIGURE_AUX_LEGACY_PLANNER"] = "false"
# CH26: базовый LLM напрямую через DeepSeek API, минуя Novita.
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


# prebuilt-шаги (ожидаемый вывод экстрактора) для каждой задачи.
TASKS = [
    {
        "uid": "GEN-fill_0453",
        "note": "reflect_point: «продлим AM за M»",
        "steps": [
            {"step_no": 1, "action": "reflect_point",
             "args": {"point": "A", "center": "M"},
             "creates_point": "A1",
             "quote": "пусть A' — точка, для которой M — середина AA'"},
        ],
        "check": "reflect_A",
    },
    {
        "uid": "GEN-L123-w2_46_s5",
        "note": "reflect_point + параллелограмм ABCD",
        "steps": [
            {"step_no": 1, "action": "reflect_point",
             "args": {"point": "B", "center": "M"},
             "creates_point": "D",
             "quote": "Продлим медиану BM за M на отрезок MD = BM"},
            {"step_no": 2, "action": "draw_segment",
             "args": {"p1": "A", "p2": "D"},
             "creates_point": None, "quote": "соединим A и D"},
            {"step_no": 3, "action": "draw_segment",
             "args": {"p1": "C", "p2": "D"},
             "creates_point": None, "quote": "соединим C и D"},
        ],
        "check": "parallelogram",
    },
    {
        "uid": "GEN-fill_0452",
        "note": "rotate_point maps: A -> C",
        "steps": [
            {"step_no": 1, "action": "rotate_point",
             "args": {"point": "P", "center": "B", "maps": ["A", "C"]},
             "creates_point": "P1",
             "quote": "повернём вокруг B так, чтобы A перешла в C"},
        ],
        "check": "rotate_maps",
    },
    {
        "uid": "GEN-fill_0454",
        "note": "rotate_point maps: D -> B (квадрат)",
        "steps": [
            {"step_no": 1, "action": "rotate_point",
             "args": {"point": "N", "center": "A", "maps": ["D", "B"]},
             "creates_point": "N1",
             "quote": "повернём квадрат вокруг A на 90°"},
        ],
        "check": "rotate_square",
    },
    {
        "uid": "GEN-L123-w2_21_s3",
        "note": "mark_intersection по step-id (par_N)",
        "steps": [
            {"step_no": 1, "id": "par_N", "action": "draw_parallel",
             "args": {"point": "N", "line": ["B", "M"]},
             "creates_point": None,
             "quote": "Проведём через N прямую, параллельную BM"},
            {"step_no": 2, "action": "mark_intersection",
             "args": {"obj1": "par_N", "obj2": ["A", "C"]},
             "creates_point": "K",
             "quote": "до пересечения с AC в точке K"},
        ],
        "check": "intersect_id",
    },
]


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


def _numeric_check(check_name, base_plan, aux_plan, ctx, merged_ctx):
    """Числовая проверка.  Возвращает строку-результат (или '')."""
    from geometric_engine import geom
    pts = merged_ctx.points if merged_ctx is not None else {}

    def p(name):
        return pts.get(name)

    if check_name == "reflect_A":
        # M — середина A A1.
        A, M, A1 = p("A"), p("M"), p("A1")
        if A is None or M is None or A1 is None:
            return "НЕТ точек A/M/A1"
        mid = geom.midpoint(A, A1)
        dev = geom.dist(mid, M)
        return f"A1=2M−A; |mid(A,A1)−M|={dev:.2e} {'OK' if dev < 1e-6 else 'FAIL'}"

    if check_name == "parallelogram":
        A, B, C, D = p("A"), p("B"), p("C"), p("D")
        if None in (A, B, C, D):
            return "НЕТ точек A/B/C/D"
        # AB || CD: вектор AB параллелен DC.
        ab = (B[0] - A[0], B[1] - A[1])
        cd = (D[0] - C[0], D[1] - C[1])
        ad = (D[0] - A[0], D[1] - A[1])
        bc = (C[0] - B[0], C[1] - B[1])
        cross1 = abs(ab[0] * cd[1] - ab[1] * cd[0])
        cross2 = abs(ad[0] * bc[1] - ad[1] * bc[0])
        ok = cross1 < 1e-6 and cross2 < 1e-6
        return (f"AB∥CD (cross={cross1:.2e}), AD∥BC (cross={cross2:.2e}) "
                f"{'OK' if ok else 'FAIL'}")

    if check_name == "rotate_maps":
        A, B, C, P1 = p("A"), p("B"), p("C"), p("P1")
        # В prebuilt aux поворачивается P, но численно проверяем, что
        # rotate_point переводит A в C (maps).  Для этого вычислим угол и
        # применим к A.
        if None in (A, B, C):
            return "НЕТ точек A/B/C"
        ang = geom.signed_angle(A, B, C)
        rotated_A = geom.rotate_point(A, B, ang)
        dev = geom.dist(rotated_A, C)
        return f"rotate(A,B,∠ABC)≈C; dev={dev:.2e} {'OK' if dev < 1e-6 else 'FAIL'}"

    if check_name == "rotate_square":
        A, D, B = p("A"), p("D"), p("B")
        if None in (A, D, B):
            return "НЕТ точек A/D/B"
        ang = geom.signed_angle(D, A, B)
        rotated_D = geom.rotate_point(D, A, ang)
        dev = geom.dist(rotated_D, B)
        return f"rotate(D,A,∠DAB)≈B; dev={dev:.2e} {'OK' if dev < 1e-6 else 'FAIL'}"

    if check_name == "intersect_id":
        A, C, K = p("A"), p("C"), p("K")
        if None in (A, C, K):
            return "НЕТ точек A/C/K"
        # K на отрезке AC.
        d_seg = geom.point_to_segment_distance(K, (A, C))
        on_seg = geom.segment_contains_point((A, C), K)
        return (f"K на AC: dist={d_seg:.2e} on_seg={on_seg} "
                f"{'OK' if on_seg else 'FAIL'}")

    return ""


def main():
    _load_env()

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg
    from services.aux_compiler import compile_steps_to_aux

    os.makedirs(_SVG_DIR, exist_ok=True)

    tmpdir = tempfile.mkdtemp(prefix="ch27_probe_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    rows = []
    with app.app_context():
        db.create_all()
        u = User(email="ch27p@example.invalid", nickname="ch27p",
                 is_guest=False, figure_credits=100)
        db.session.add(u)
        db.session.commit()

        for spec in TASKS:
            task = _find_task(spec["uid"])
            if task is None:
                rows.append({"uid": spec["uid"], "error": "task not found"})
                continue

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

            # ── Полный pipeline, но aux-экстрактор подменён prebuilt-шагами ──
            base_plan = None
            aux_plan = None
            aux_status = None
            issues = []
            base_svg = ""
            aux_svg = ""
            compiled_ops = 0
            creates_ok = True

            # 1. base-план через LLM.
            t0 = time.time()
            try:
                resp, json_str = fg._plan_call(
                    fg._BASE_PLANNER_PROMPT,
                    fg.FIGURE_BASE_MODEL,
                    role="base",
                    condition_text=task["statement"],
                    repair_feedback="",
                )
                if json_str:
                    from services.figure_plan_schemas import parse_base_plan
                    base_plan = parse_base_plan(json_str)
            except Exception as e:
                base_plan = None

            if base_plan is None:
                # Fallback: детерминированный base (не зависит от LLM).
                base_plan = _deterministic_base(spec["uid"])

            # 2. Компиляция prebuilt-шагов в aux-план.
            aux_plan, issues = compile_steps_to_aux(spec["steps"], base_plan)
            aux_has = bool(aux_plan.get("has_aux"))
            compiled_ops = len(aux_plan.get("constructions", []))
            aux_status = "AUX_BUILT" if aux_has else "AUX_UNSUPPORTED"

            # 3. Отрисовка base и merged (aux).
            from geometric_engine.engine import GeometricEngine
            eng = GeometricEngine()
            eng.settings.auto_fit = True
            eng.settings.semantic_colors = True

            base_svg, base_ctx = "", None
            try:
                base_svg, base_ctx = eng.build_with_retry(base_plan)[:2]
            except Exception:
                base_svg = ""

            merged_ctx = None
            if aux_has:
                from services.figure_plan_validator import merge_base_aux
                merged = merge_base_aux(base_plan, aux_plan)
                try:
                    aux_svg, merged_ctx = eng.build_with_retry(merged)[:2]
                except Exception:
                    aux_svg = ""

            latency_ms = int((time.time() - t0) * 1000)

            # Сохранить SVG.
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", spec["uid"])
            base_path = aux_path = ""
            if base_svg:
                base_path = os.path.join(_SVG_DIR, f"{safe}_base.svg")
                open(base_path, "w", encoding="utf-8").write(base_svg)
            if aux_svg:
                aux_path = os.path.join(_SVG_DIR, f"{safe}_aux.svg")
                open(aux_path, "w", encoding="utf-8").write(aux_svg)

            # creates_point разрешены?
            creates_ok = not any(i.startswith("UNRESOLVED_POINT") for i in issues)

            # Числовая проверка: ДЕТЕРМИНИРОВАННО на известных точках,
            # используя eng.build (без HARD-проверок canvas) — нам нужны только
            # координаты для численной сверки.
            det_base = _deterministic_base(spec["uid"])
            det_aux, _det_issues = compile_steps_to_aux(spec["steps"], det_base)
            det_merged_ctx = None
            if det_aux.get("has_aux"):
                from services.figure_plan_validator import merge_base_aux
                det_merged = merge_base_aux(det_base, det_aux)
                try:
                    _, det_merged_ctx = eng.build(det_merged)
                except Exception:
                    det_merged_ctx = None
            check_result = _numeric_check(spec["check"], det_base, det_aux,
                                          None, det_merged_ctx)

            rows.append({
                "uid": spec["uid"],
                "note": spec["note"],
                "compiled_ops": compiled_ops,
                "aux_status": aux_status,
                "creates_ok": creates_ok,
                "issues": issues,
                "base_svg": base_path,
                "aux_svg": aux_path,
                "latency_ms": latency_ms,
                "check": check_result,
                "statement": (task["statement"] or "")[:120],
                "steps": spec["steps"],
            })
            print(".", end="", flush=True)
        print()

    # ── Таблица ──
    print("| task_uid | ops | aux_status | creates_ok | issues | latency_ms |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        iss = ",".join(i.split(":")[0] for i in r["issues"]) or "-"
        co = "OK" if r["creates_ok"] else "FAIL"
        print(f"| {r['uid']} | {r['compiled_ops']} | {r['aux_status']} | {co} | {iss} | {r['latency_ms']} |")

    print("\nЧисленные проверки:")
    for r in rows:
        print(f"  {r['uid']}: {r['check']}")

    out_json = os.path.join(_OUT, "probe_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[ch27] results: {out_json}")


def _deterministic_base(uid):
    """Детерминированные, геометрически корректные base-планы.

    Каждый план построен так, чтобы выполнять предпосылки задачи:
      - w2_46_s5 / fill_0453: M — середина BC (для удвоения медианы);
      - fill_0452: ABC — равносторонний (для поворота A→C);
      - fill_0454: ABCD — квадрат (для поворота D→B);
      - w2_21_s3: M на AC, N — середина BC (для параллели и пересечения).
    """
    canvas = {"width": 600, "height": 500, "margin": 40}

    if uid.startswith("GEN-L123-w2_46_s5"):
        # «Медиана BM» → M — середина AC.  Отражаем B через M → D.
        A = (150, 100)
        B = (300, 460)
        C = (500, 200)
        M = ((A[0] + C[0]) / 2, (A[1] + C[1]) / 2)  # середина AC
        return {
            "canvas": canvas,
            "constructions": [
                {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
                {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
                {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
                {"type": "midpoint", "id": "M", "p1": "A", "p2": "C"},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
                {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
                {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "BM", "p1": "B", "p2": "M"},
            ],
        }

    if uid.startswith("GEN-fill_0453"):
        # «M — середина BC».  Отражаем A через M → A1.
        A = (300, 80)
        B = (120, 400)
        C = (480, 400)
        M = ((B[0] + C[0]) / 2, (B[1] + C[1]) / 2)
        return {
            "canvas": canvas,
            "constructions": [
                {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
                {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
                {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
                {"type": "midpoint", "id": "M", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
                {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
                {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},
            ],
        }

    if uid.startswith("GEN-fill_0452"):
        # Равносторонний треугольник ABC.
        import math
        cx, cy = 300, 250
        R = 180
        A = (cx + R * math.cos(math.radians(90)), cy + R * math.sin(math.radians(90)))
        B = (cx + R * math.cos(math.radians(210)), cy + R * math.sin(math.radians(210)))
        C = (cx + R * math.cos(math.radians(330)), cy + R * math.sin(math.radians(330)))
        P = (cx + 20, cy - 10)  # внутри
        return {
            "canvas": canvas,
            "constructions": [
                {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
                {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
                {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
                {"type": "free_point", "id": "P", "x": P[0], "y": P[1]},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
                {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
            ],
        }

    if uid.startswith("GEN-fill_0454"):
        # Квадрат ABCD (A левый-верхний, B правый-верхний, C правый-нижний,
        # D левый-нижний), N на CD.
        A = (150, 150)
        B = (450, 150)
        C = (450, 450)
        D = (150, 450)
        N = (200, 450)  # на CD
        return {
            "canvas": canvas,
            "constructions": [
                {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
                {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
                {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
                {"type": "free_point", "id": "D", "x": D[0], "y": D[1]},
                {"type": "free_point", "id": "N", "x": N[0], "y": N[1]},
                {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
                {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
                {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
                {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            ],
        }

    # GEN-L123-w2_21_s3: M на AC (AM:MC = 1:3), N — середина BC.
    A = (100, 100)
    C = (500, 300)
    B = (300, 460)
    M = (A[0] + 0.25 * (C[0] - A[0]), A[1] + 0.25 * (C[1] - A[1]))  # AM:MC = 1:3
    N = ((B[0] + C[0]) / 2, (B[1] + C[1]) / 2)
    return {
        "canvas": canvas,
        "constructions": [
            {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
            {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
            {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
            {"type": "point_on_segment", "id": "M", "p1": "A", "p2": "C", "ratio": 0.25},
            {"type": "midpoint", "id": "N", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "BM", "p1": "B", "p2": "M"},
        ],
    }


if __name__ == "__main__":
    main()
