# -*- coding: utf-8 -*-
"""CH29: репетиция финального прогона на 40 задачах.

LLM вызывается ТОЛЬКО для base-плана.  Aux берётся из
data/figures/aux_batch_1_40.jsonl (prebuilt) и компилируется через
services.aux_compiler без LLM.

Собирает метрики: base/aux построено, aux_status, error_code, среднее число
base-вызовов, суммарная latency, оценка стоимости.

Запуск: python scripts/final_rehearsal.py
"""
import io
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INPUT = os.path.join(_ROOT, "FORMYLA_geometry_7_11_chertezh_v13.jsonl")
_BATCH = os.path.join(_ROOT, "data", "figures", "aux_batch_1_40.jsonl")
_OUT = os.path.join(_ROOT, "output", "final_rehearsal")
_SVG_DIR = os.path.join(_OUT, "svg")

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


def _load_batch():
    by_uid = {}
    with open(_BATCH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_uid[d["task_uid"]] = d["aux_construction"]
    return by_uid


def _find_tasks(limit=40):
    recs = []
    with open(_INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(recs) >= limit:
                break
    return recs


def main():
    _load_env()

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg
    from services.aux_compiler import compile_steps_to_aux
    from services.figure_plan_schemas import parse_base_plan

    batch = _load_batch()
    tasks = _find_tasks(40)
    print(f"Задач в банке (первые 40): {len(tasks)}")
    print(f"Prebuilt aux в партии: {len(batch)}")

    os.makedirs(_SVG_DIR, exist_ok=True)

    tmpdir = tempfile.mkdtemp(prefix="final_rehearsal_")
    uri = "sqlite:///" + os.path.join(tmpdir, "p.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "x"
    db.init_app(app)

    # Счётчик base-вызовов.
    base_calls = {"n": 0}
    orig_plan_call = fg._plan_call
    base_prompt = fg._BASE_PLANNER_PROMPT

    def wrapped_plan_call(prompt_template, model_name, **kw):
        if prompt_template == base_prompt:
            base_calls["n"] += 1
        return orig_plan_call(prompt_template, model_name, **kw)

    fg._plan_call = wrapped_plan_call

    rows = []
    total_latency = 0.0
    total_cost = 0.0

    with app.app_context():
        db.create_all()
        u = User(email="reh@example.invalid", nickname="reh",
                 is_guest=False, figure_credits=100000)
        db.session.add(u)
        db.session.commit()

        for task in tasks:
            uid = task["task_uid"]
            aux_c = batch.get(uid)
            if aux_c is None:
                # Задача вне партии — пропускаем aux.
                aux_c = {"has_aux": False, "steps": [], "unsupported": []}

            t0 = time.time()
            base_calls["n"] = 0

            # 1. base-план через LLM.
            base_plan = None
            base_svg = ""
            try:
                resp, json_str = fg._plan_call(
                    base_prompt, fg.FIGURE_BASE_MODEL, role="base",
                    condition_text=task["statement"], repair_feedback="",
                )
                if json_str:
                    base_plan = parse_base_plan(json_str)
            except Exception:
                base_plan = None

            aux_status = ""
            error_code = ""
            aux_svg = ""
            aux_ops = 0

            if base_plan is None:
                error_code = "BASE_NO_JSON"
            else:
                # 2. Отрисовка base.
                from geometric_engine.engine import GeometricEngine
                eng = GeometricEngine()
                eng.settings.auto_fit = True
                eng.settings.semantic_colors = True
                try:
                    base_svg, _, _, base_violations = eng.build_with_retry(base_plan)
                except Exception:
                    base_svg = ""

                # 3. Компиляция prebuilt aux (без LLM).
                aux_plan, issues = compile_steps_to_aux(
                    aux_c.get("steps", []), base_plan
                )
                aux_ops = len(aux_plan.get("constructions", []))
                aux_has = bool(aux_plan.get("has_aux"))

                if not aux_has:
                    if aux_c.get("unsupported"):
                        aux_status = "AUX_UNSUPPORTED"
                    else:
                        aux_status = "AUX_NOT_NEEDED"
                elif issues:
                    aux_status = "AUX_PLAN_REJECTED"
                    error_code = issues[0].split(":")[0]
                else:
                    # 4. Отрисовка merged (aux).
                    from services.figure_plan_validator import merge_base_aux
                    merged = merge_base_aux(base_plan, aux_plan)
                    try:
                        aux_svg, _, _, _ = eng.build_with_retry(merged)
                    except Exception:
                        aux_svg = ""
                    aux_status = "AUX_BUILT" if aux_svg else "AUX_BUILD_FAILED"

            latency = (time.time() - t0) * 1000.0
            total_latency += latency

            # Сохранение SVG.
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", uid)
            bp = ap = ""
            if base_svg:
                bp = os.path.join(_SVG_DIR, f"{safe}_base.svg")
                open(bp, "w", encoding="utf-8").write(base_svg)
            if aux_svg:
                ap = os.path.join(_SVG_DIR, f"{safe}_aux.svg")
                open(ap, "w", encoding="utf-8").write(aux_svg)

            rows.append({
                "task_uid": uid,
                "base_built": bool(base_svg),
                "aux_built": bool(aux_svg),
                "aux_status": aux_status,
                "error_code": error_code,
                "base_calls": base_calls["n"],
                "aux_ops": aux_ops,
                "latency_ms": int(latency),
                "base_path": bp,
                "aux_path": ap,
                "statement": (task["statement"] or "")[:100],
            })
            print(".", end="", flush=True)
        print()

    # ── Сводка ──
    n = len(rows)
    base_built = sum(1 for r in rows if r["base_built"])
    aux_built = sum(1 for r in rows if r["aux_built"])
    aux_status_counter = Counter(r["aux_status"] for r in rows)
    err_counter = Counter(r["error_code"] for r in rows if r["error_code"])
    avg_base_calls = sum(r["base_calls"] for r in rows) / n if n else 0

    print("=" * 70)
    print("СВОДКА РЕПЕТИЦИИ (40 задач)")
    print("=" * 70)
    print(f"base-чертежей построено: {base_built} / {n}")
    print(f"aux-чертежей построено: {aux_built} / {n}")
    print(f"среднее число base-вызовов: {avg_base_calls:.2f}")
    print(f"суммарная latency: {total_latency:.0f} ms")
    print()

    print("Распределение aux_status:")
    for st, cnt in aux_status_counter.most_common():
        print(f"  {st}: {cnt}")

    print("\nРаспределение error_code:")
    if err_counter:
        for c, cnt in err_counter.most_common():
            print(f"  {c}: {cnt}")
    else:
        print("  (нет ошибок)")

    # ── Отчёт ──
    report = {
        "total": n,
        "base_built": base_built,
        "aux_built": aux_built,
        "avg_base_calls": round(avg_base_calls, 2),
        "total_latency_ms": int(total_latency),
        "aux_status": dict(aux_status_counter),
        "error_code": dict(err_counter),
        "rows": rows,
    }
    out_json = os.path.join(_OUT, "results.json")
    os.makedirs(_OUT, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[ch29] отчёт: {out_json}")


if __name__ == "__main__":
    main()
