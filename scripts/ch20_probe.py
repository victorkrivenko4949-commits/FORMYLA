# -*- coding: utf-8 -*-
"""scripts/ch20_probe.py — probe: 8 ранее упавших LLM_NO_JSON задач заново.

CH20: прогоняет 8 задач из output/ch19/pilot_100.jsonl, которые в пилоте
CH19 упали с LLM_NO_JSON, через реальный condition_solution pipeline в
изолированном временном SQLite.  Служебный прогон не списывает кредиты
(FIGURE_CREDITS_ENFORCED=false) и включает CH20-политику max_tokens/thinking.

Выводит таблицу:
  task_uid, status, error_code, thinking_mode, max_tokens,
  prompt_tokens, completion_tokens, reasoning_tokens, finish_reason,
  latency_ms, has_aux, aux_ops_count, cost_usd.
"""
import csv
import io
import json
import os
import sys
import tempfile
import time

_RO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RO not in sys.path:
    sys.path.insert(0, _RO)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


def _apply_process_env():
    os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
    os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
    # Служебный прогон не зависит от баланса аккаунта.
    os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
    # CH20: планировщики без thinking, умеренные max_tokens.
    os.environ.setdefault("FIGURE_BASE_THINKING", "disabled")
    os.environ.setdefault("FIGURE_AUX_THINKING", "disabled")
    os.environ.setdefault("FIGURE_AUDIT_THINKING", "disabled")


def _previously_failed_uids():
    """task_uid задач, упавших с LLM_NO_JSON в CH19 results.csv."""
    results_path = os.path.join("output", "ch19", "results.csv")
    uids = []
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("status") != "done" and "LLM_NO_JSON" in (r.get("error_code") or ""):
                    uids.append(r["task_uid"])
    return uids


def main():
    _load_dotenv()
    _apply_process_env()

    from flask import Flask
    from models import db, User, FigureBuildJob
    import routes.figures_generator as fg

    failed_uids = _previously_failed_uids()
    # Берём 8 ранее упавших задач (по приоритету из списка).
    target_uids = failed_uids[:8]

    # Подгружаем записи из pilot_100.jsonl.
    records = {}
    pilot_path = os.path.join("output", "ch19", "pilot_100.jsonl")
    if os.path.exists(pilot_path):
        with open(pilot_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                records[str(rec.get("task_uid"))] = rec

    if not target_uids:
        print("Нет ранее упавших LLM_NO_JSON задач в results.csv")
        return

    tmpdir = tempfile.mkdtemp(prefix="formyla_ch20_probe_")
    uri = "sqlite:///" + os.path.join(tmpdir, "probe.db").replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SECRET_KEY"] = "ch20-probe"
    db.init_app(app)

    print("| task_uid | status | error_code | thinking_mode | max_tokens | "
          "prompt_tokens | completion_tokens | reasoning_tokens | finish_reason | "
          "latency_ms | has_aux | aux_ops_count | cost_usd |")

    # Инструментируем _call_deepseek для снятия метрик последнего вызова.
    orig_call = fg._call_deepseek
    metrics = {"thinking_mode": "-", "max_tokens": "-",
               "prompt_tokens": 0, "completion_tokens": 0,
               "reasoning_tokens": 0, "finish_reason": "-",
               "cost_usd": 0.0}

    def instrumented(messages, model_name=None, role="legacy_reasoner"):
        nonlocal metrics
        resp = orig_call(messages, model_name=model_name, role=role)
        u_ = resp.get("usage") or {}
        metrics = {
            "thinking_mode": resp.get("thinking_mode", "-"),
            "max_tokens": "-",
            "prompt_tokens": int(u_.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(u_.get("completion_tokens", 0) or 0),
            "reasoning_tokens": int(resp.get("reasoning_tokens", 0) or 0),
            "finish_reason": resp.get("finish_reason") or "-",
            "cost_usd": float(resp.get("cost_usd", 0.0) or 0.0),
        }
        return resp
    fg._call_deepseek = instrumented

    with app.app_context():
        db.create_all()
        u = User(email="ch20-probe@example.invalid", nickname="ch20_probe",
                 is_guest=False, figure_credits=5)
        db.session.add(u)
        db.session.commit()

        for uid in target_uids:
            rec = records.get(uid)
            if not rec:
                print(f"| {uid} | skipped | | | | | | | | | | | |")
                continue
            condition = (rec.get("statement") or "").strip()
            solution = (rec.get("solution") or "").strip()

            job = FigureBuildJob(
                user_id=u.id,
                problem_text=condition,
                solution_text=solution or None,
                generation_mode="condition_solution",
                status="queued",
            )
            db.session.add(job)
            db.session.commit()
            jid = job.id

            t0 = time.perf_counter()
            try:
                fg._run_condition_solution_job(jid, job)
            except Exception as e:  # noqa: BLE001
                job = FigureBuildJob.query.get(jid)
                if job and job.status not in ("done", "failed"):
                    job.status = "failed"
                    job.error = f"PROBE_CRASH: {type(e).__name__}: {str(e)[:200]}"
                    db.session.commit()
            total_ms = (time.perf_counter() - t0) * 1000.0

            job = FigureBuildJob.query.get(jid)
            if job is None:
                continue
            error_code = ""
            if job.status == "failed" and job.error:
                error_code = job.error.split(":", 1)[0].strip()

            aux_ops = 0
            if job.aux_plan_json:
                try:
                    aux_ops = len(json.loads(job.aux_plan_json).get("constructions", []))
                except Exception:
                    aux_ops = 0

            print(
                f"| {uid} | {job.status} | {error_code or '-'} | "
                f"{metrics['thinking_mode']} | {metrics['max_tokens']} | "
                f"{metrics['prompt_tokens']} | {metrics['completion_tokens']} | "
                f"{metrics['reasoning_tokens']} | {metrics['finish_reason']} | "
                f"{total_ms:.0f} | {1 if job.has_aux else 0} | {aux_ops} | "
                f"{metrics['cost_usd']:.6f} |"
            )


if __name__ == "__main__":
    main()
