# -*- coding: utf-8 -*-
"""scripts/ch19_batch_figures.py — пакетный прогон генерации SVG-чертежей (CH19).

Работает через РЕАЛЬНЫЙ внутренний pipeline:
  FigureBuildJob(generation_mode='condition_solution') -> _run_condition_solution_job.

Особенности:
  * Свой временный SQLite (не трогает прод instance/formyla.db).
  * Режимы окружения задаются процессу (не правя .env).
  * Идемпотентность: output/ch19/state.jsonl + --resume.
  * Инструментирование LLM-вызовов (обёртка, НЕ правка конвейера) для
    подсчёта cost/tokens/llm_calls/latency/provider/model.
  * Отказоустойчивость: падение задачи не останавливает прогон;
    5 подряд одинаковых error_code -> пауза 60с; 15 подряд -> стоп;
    превышение --max-cost-usd -> корректный стоп.

Не меняет: geometric_engine/, figure_plan_validator.py, figure_plan_schemas.py,
data/figures/*.txt, llm_router.py, кредиты, очередь, API-маршруты.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.ch19_lib import (  # noqa: E402
    aux_constructions,
    base_constructions,
    classify_solution_style,
    count_visible_points,
    error_code_from,
    has_aux_flag,
    loads,
    merge_base_aux_plan,
    visible_points,
)

DEFAULT_INPUT = "FORMYLA_geometry_7_11_chertezh_v13.jsonl"
DEFAULT_OUT = os.path.join("output", "ch19")
ALL_STYLES = ("constructive", "angle_chase", "area_ratio",
              "coordinate", "complex", "trig")

# ── env ────────────────────────────────────────────────────────────────────

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
    # CH15 двухслойный конвейер и CH16 семантические цвета — только процессу.
    os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
    os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
    # Пакетный прогон не должен зависеть от баланса служебного аккаунта:
    # кредиты не списываем (прод-дефолт true остаётся в routes/figures_generator).
    os.environ["FIGURE_CREDITS_ENFORCED"] = "false"
    # Лимиты LLM (если не заданы) — не правя прод .env.
    os.environ.setdefault("FIGURE_BASE_MAX_TOKENS", "4096")
    os.environ.setdefault("FIGURE_AUX_MAX_TOKENS", "4096")
    os.environ.setdefault("FIGURE_AUDIT_MAX_TOKENS", "4096")


# ── LLM instrumentation (обёртки, конвейер не меняется) ─────────────────────

_THREAD_LOCAL = threading.local()


def _stats():
    s = getattr(_THREAD_LOCAL, "s", None)
    if s is None:
        s = {
            "llm_calls": 0,
            "cost_usd": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": 0.0,
            "providers": set(),
            "models": set(),
            "base_attempts": 0,
            "aux_attempts": 0,
            "audit_attempts": 0,
            # CH24: метрики двухэтапного aux и SOFT-предупреждений движка.
            "extracted_steps": 0,
            "compiled_ops": 0,
            "base_soft_warnings": [],
        }
        _THREAD_LOCAL.s = s
    return s


def _reset_stats():
    _THREAD_LOCAL.s = None
    _THREAD_LOCAL.build_calls = 0


def _install_instrumentation(fg):
    """Обернуть call_llm и _plan_call для замера без правки pipeline."""
    orig_call_llm = fg.call_llm
    orig_plan_call = fg._plan_call
    base_p = fg._BASE_PLANNER_PROMPT
    aux_p = fg._AUX_PLANNER_PROMPT
    aud_p = fg._AUDITOR_PROMPT
    aux_ext_p = getattr(fg, "_AUX_EXTRACTOR_PROMPT", "") or ""

    def _wrap_call_llm(logical_model, messages, **kw):
        s = _stats()
        t0 = time.perf_counter()
        r = orig_call_llm(logical_model, messages, **kw)
        s["llm_calls"] += 1
        s["cost_usd"] += float(r.get("cost_usd", 0.0) or 0.0)
        u = r.get("usage") or {}
        s["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        s["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
        s["latency_ms"] += float(r.get("latency_ms", 0.0) or 0.0)
        if r.get("provider"):
            s["providers"].add(r["provider"])
        s["models"].add(r.get("model_id") or str(logical_model))
        return r

    def _wrap_plan_call(prompt_template, model_name, **kw):
        s = _stats()
        if prompt_template == base_p:
            s["base_attempts"] += 1
        elif prompt_template == aux_p or (aux_ext_p and prompt_template == aux_ext_p):
            s["aux_attempts"] += 1
        elif prompt_template == aud_p:
            s["audit_attempts"] += 1
        return orig_plan_call(prompt_template, model_name, **kw)

    fg.call_llm = _wrap_call_llm
    fg._plan_call = _wrap_plan_call


def _base_fail_codes(job) -> str:
    """CH24: извлечь коды отказа base из job.error + job.audit_json.

    Различает:
      * LLM_NO_JSON / LLM-ошибка / парс-фейл;
      * DEGENERATE_SEGMENT / MISSING_CONDITION_POINT (из строки ошибки);
      * HARD-проверки движка (границы/угол/площадь/отношение/расстояние);
      * невозможная геометрия (BASE_HARD с перечнем violation).
    Возвращает компактную строку кодов через '|'.
    """
    codes = []
    err = (job.error or "").strip()
    if not err:
        return ""

    if "LLM_NO_JSON" in err:
        codes.append("LLM_NO_JSON")
    elif "не удалось разобрать base-план" in err.lower():
        codes.append("BASE_PARSE")
    elif "не смогла создать корректный base-план" in err.lower():
        codes.append("BASE_VALIDATION")
    elif "Геометрические ограничения base-чертежа не выполнены" in err:
        # Текст violations из движка.
        head = err.split(":", 1)[1].strip() if ":" in err else ""
        if "DEGENERATE" in head or "соединяет точку саму с собой" in head:
            codes.append("DEGENERATE_SEGMENT")
        if "MISSING_CONDITION_POINT" in head:
            codes.append("MISSING_CONDITION_POINT")
        if "границы" in head:
            codes.append("HARD_BOUNDS")
        if "угол" in head:
            codes.append("HARD_ANGLE")
        if "площадь" in head or "почти вырожден" in head:
            codes.append("HARD_AREA")
        if "отношение сторон" in head:
            codes.append("HARD_SIDE_RATIO")
        if "слишком близко" in head:
            codes.append("HARD_POINT_DIST")
        if not codes:
            codes.append("ENGINE_HARD")
    elif "RUNNER_CRASH" in err:
        codes.append("RUNNER_CRASH")
    else:
        # LLM-ошибка провайдера и прочее.
        codes.append("LLM_ERROR" if not codes else codes[0])

    # Из audit_json: base_history содержит коды валидации.
    audit_json = job.audit_json or ""
    if "DEGENERATE_SEGMENT" in audit_json:
        codes.append("DEGENERATE_SEGMENT")
    if "MISSING_CONDITION_POINT" in audit_json:
        codes.append("MISSING_CONDITION_POINT")

    seen = []
    for c in codes:
        if c not in seen:
            seen.append(c)
    return "|".join(seen)


def _install_aux_engine_instrumentation():
    """CH24: боковые метрики двухэтапного aux и soft-warning'ов движка.

    Обёртки не меняют поведение — только копят в thread-local:
      * extracted_steps / compiled_ops — из compile_steps_to_aux;
      * base_soft_warnings — из первого вызова GeometricEngine.build_with_retry.
    """
    import services.aux_compiler as ac  # noqa: E402
    import geometric_engine.engine as eng  # noqa: E402

    _orig_compile = ac.compile_steps_to_aux

    def _wrap_compile(steps, base_plan):
        s = _stats()
        result, issues = _orig_compile(steps, base_plan)
        s["extracted_steps"] = len(steps) if isinstance(steps, list) else 0
        s["compiled_ops"] = (
            len(result.get("constructions", [])) if isinstance(result, dict) else 0
        )
        return result, issues

    ac.compile_steps_to_aux = _wrap_compile

    _orig_build_with_retry = eng.GeometricEngine.build_with_retry

    def _wrap_build_with_retry(self, description, seed=42):
        svg, ctx, attempts, violations = _orig_build_with_retry(self, description, seed)
        _THREAD_LOCAL.build_calls = getattr(_THREAD_LOCAL, "build_calls", 0) + 1
        if _THREAD_LOCAL.build_calls == 1:
            s = _stats()
            s["base_soft_warnings"] = list(violations)
        return svg, ctx, attempts, violations

    eng.GeometricEngine.build_with_retry = _wrap_build_with_retry


# ── чтение задач ───────────────────────────────────────────────────────────

def iter_records(path, styles_filter):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (rec.get("solution") or "").strip():
                continue
            if styles_filter:
                style = classify_solution_style(rec)
                if style not in styles_filter:
                    continue
            yield rec


# ── главная логика ─────────────────────────────────────────────────────────

def _safe_filename(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(uid))


class RunState:
    def __init__(self, path):
        self.path = path
        self.done = set()
        self.lock = threading.Lock()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("status") == "done":
                        self.done.add(row.get("task_uid"))

    def record(self, task_uid, status, attempt):
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "task_uid": task_uid,
                    "status": status,
                    "attempt": attempt,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            if status == "done":
                self.done.add(task_uid)


def _run_one(app, fg, user_id, rec, attempt, out_dir, run_state):
    """Создать job и синхронно прогнать pipeline.  Вернуть строку results.csv."""
    uid = str(rec.get("task_uid"))
    condition = (rec.get("statement") or "").strip()
    solution = (rec.get("solution") or "").strip()
    style = classify_solution_style(rec)

    run_state.record(uid, "started", attempt)

    from models import db, FigureBuildJob

    with app.app_context():
        job = FigureBuildJob(
            user_id=user_id,
            problem_text=condition,
            solution_text=solution or None,
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        jid = job.id

        t0 = time.perf_counter()
        _reset_stats()
        try:
            fg._run_condition_solution_job(jid, job)
        except Exception as e:  # noqa: BLE001 — защита от падения задачи
            db.session.rollback()
            try:
                job = FigureBuildJob.query.get(jid)
                if job and job.status not in ("done", "failed"):
                    job.status = "failed"
                    job.error = f"RUNNER_CRASH: {type(e).__name__}: {str(e)[:300]}"
                    db.session.commit()
            except Exception:
                db.session.rollback()
        total_ms = (time.perf_counter() - t0) * 1000.0

        job = FigureBuildJob.query.get(jid)
        if job is None:
            return None

        s = _stats()
        status = job.status or "failed"
        stage = job.current_stage or status
        error_code = error_code_from(job.error) if status == "failed" else ""

        # audit_executed: аудитор запускается только при has_aux и промпте.
        audit_executed = 0
        audit_json = job.audit_json or ""
        if job.has_aux and audit_json and "invariant_errors" not in audit_json:
            audit_executed = 1

        base_cs = base_constructions(job.base_plan_json)
        aux_cs = aux_constructions(job.aux_plan_json)
        base_ops = len(base_cs)
        aux_ops = len(aux_cs)

        base_points = count_visible_points(loads(job.base_plan_json))
        aux_points = 0
        if job.has_aux and job.aux_plan_json:
            merged = merge_base_aux_plan(loads(job.base_plan_json),
                                         loads(job.aux_plan_json))
            aux_points = max(0, count_visible_points(merged) - base_points)

        # Артефакты.
        svg_b = 0
        svg_a = 0
        try:
            os.makedirs(os.path.join(out_dir, "svg"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "plans"), exist_ok=True)
            if job.svg_path:
                pb = os.path.join(out_dir, "svg", f"{_safe_filename(uid)}_base.svg")
                with open(pb, "w", encoding="utf-8") as f:
                    f.write(job.svg_path)
                svg_b = len(job.svg_path.encode("utf-8"))
            if job.aux_svg_path:
                pa = os.path.join(out_dir, "svg", f"{_safe_filename(uid)}_aux.svg")
                with open(pa, "w", encoding="utf-8") as f:
                    f.write(job.aux_svg_path)
                svg_a = len(job.aux_svg_path.encode("utf-8"))
            if job.base_plan_json:
                pbj = os.path.join(out_dir, "plans", f"{_safe_filename(uid)}_base.json")
                with open(pbj, "w", encoding="utf-8") as f:
                    f.write(job.base_plan_json)
            if job.aux_plan_json:
                paj = os.path.join(out_dir, "plans", f"{_safe_filename(uid)}_aux.json")
                with open(paj, "w", encoding="utf-8") as f:
                    f.write(job.aux_plan_json)
        except OSError as e:
            print(f"  [warn] artifacts write failed for {uid}: {e}", flush=True)

        provider = ",".join(sorted(s["providers"]))
        model = ",".join(sorted(s["models"]))

        row = {
            "task_uid": uid,
            "grade": rec.get("grade", ""),
            "level": rec.get("level", ""),
            "theme_id": rec.get("theme_id", ""),
            "solution_style": style,
            "status": status,
            "current_stage": stage,
            "error_code": error_code,
            "provider": provider,
            "model": model,
            "llm_calls": s["llm_calls"],
            "fast_path_used": 0,
            "fallback_to_two_call": 0,
            "audit_executed": audit_executed,
            "structured_json_used": 0,
            "base_attempts": s["base_attempts"],
            "aux_attempts": s["aux_attempts"],
            "has_aux": 1 if job.has_aux else 0,
            "aux_reason": (job.aux_reason or "").replace("\n", " ")[:200],
            "aux_status": job.aux_status or "",
            "aux_fail_codes": (job.aux_fail_reason or "")[:300],
            "soft_warnings": "|".join(s["base_soft_warnings"])[:500],
            "base_fail_codes": _base_fail_codes(job) if status == "failed" else "",
            "extracted_steps_count": s["extracted_steps"],
            "compiled_ops_count": s["compiled_ops"],
            "base_ops_count": base_ops,
            "aux_ops_count": aux_ops,
            "base_points_count": base_points,
            "aux_points_count": aux_points,
            "svg_bytes_base": svg_b,
            "svg_bytes_aux": svg_a,
            "total_latency_ms": round(total_ms, 1),
            "cost_usd": round(s["cost_usd"], 8),
            "prompt_tokens": s["prompt_tokens"],
            "completion_tokens": s["completion_tokens"],
        }
        run_state.record(uid, status, attempt)
        return row


def main():
    ap = argparse.ArgumentParser(description="CH19 batch figures runner")
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--max-cost-usd", type=float, default=None)
    ap.add_argument("--styles", default=",".join(ALL_STYLES))
    args = ap.parse_args()

    _load_dotenv()
    _apply_process_env()

    os.makedirs(args.out, exist_ok=True)
    state_path = os.path.join(args.out, "state.jsonl")
    results_path = os.path.join(args.out, "results.csv")
    run_state = RunState(state_path)

    from flask import Flask
    from models import db, User

    # Свой временный SQLite — прод БД не трогаем.
    db_path = os.path.join(args.out, "_pilot.db")
    uri = "sqlite:///" + os.path.abspath(db_path).replace("\\", "/")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False, "timeout": 30},
    }
    app.config["SECRET_KEY"] = "ch19-batch"
    db.init_app(app)

    import routes.figures_generator as fg  # noqa: E402

    _install_instrumentation(fg)
    _install_aux_engine_instrumentation()

    with app.app_context():
        db.create_all()
        # WAL для конкурентного доступа из нескольких потоков.
        try:
            db.session.execute(db.text("PRAGMA journal_mode=WAL"))
            db.session.commit()
        except Exception:
            pass
        u = User(email="ch19-batch@example.invalid", nickname="ch19_batch",
                 is_guest=False, figure_credits=100000)
        db.session.add(u)
        db.session.commit()
        user_id = u.id
        balance_before = u.figure_credits

    styles_filter = set()
    if args.styles:
        styles_filter = {s.strip() for s in args.styles.split(",") if s.strip()}

    # Собираем задачи для прогона (с учётом --resume и --limit).
    pending = []
    seen = set()
    for rec in iter_records(args.input, styles_filter):
        uid = str(rec.get("task_uid"))
        if uid in seen:
            continue
        seen.add(uid)
        if args.resume and uid in run_state.done:
            continue
        pending.append(rec)
        if args.limit and len(pending) >= args.limit:
            break

    print(f"[ch19] pending tasks: {len(pending)} (resume={args.resume}, "
          f"workers={args.workers}, limit={args.limit})", flush=True)
    if args.dry_run:
        print("[ch19] DRY RUN — ничего не генерируется.")
        for rec in pending[:20]:
            print("  would-run:", rec.get("task_uid"), classify_solution_style(rec))
        return

    # results.csv: пишем заголовок, если файла нет.
    FIELD_NAMES = [
        "task_uid", "grade", "level", "theme_id", "solution_style",
        "status", "current_stage", "error_code", "provider", "model",
        "llm_calls", "fast_path_used", "fallback_to_two_call",
        "audit_executed", "structured_json_used",
        "base_attempts", "aux_attempts", "has_aux", "aux_reason",
        "aux_status", "aux_fail_codes", "soft_warnings", "base_fail_codes",
        "extracted_steps_count", "compiled_ops_count",
        "base_ops_count", "aux_ops_count", "base_points_count",
        "aux_points_count", "svg_bytes_base", "svg_bytes_aux",
        "total_latency_ms", "cost_usd", "prompt_tokens", "completion_tokens",
    ]
    new_file = not os.path.exists(results_path)
    csv_lock = threading.Lock()

    stop_event = threading.Event()
    cost_lock = threading.Lock()
    run_cost = {"usd": 0.0}

    # Отслеживание подряд идущих неудач.
    fail_lock = threading.Lock()
    consecutive = {"errors": [], "count": 0}
    cost_exceeded = {"flag": False}

    def cost_budget_ok():
        if args.max_cost_usd is None:
            return True
        with cost_lock:
            return run_cost["usd"] <= args.max_cost_usd

    def handle_failure(code):
        with fail_lock:
            consecutive["count"] += 1
            if code:
                consecutive["errors"].append(code)
                if len(consecutive["errors"]) > 5:
                    consecutive["errors"].pop(0)
            if len(consecutive["errors"]) >= 5 and len(set(consecutive["errors"])) == 1:
                print(f"[ch19] WARNING: 5 подряд одинаковых error_code={consecutive['errors'][0]}"
                      f" -> пауза 60с", flush=True)
                # Пауза вне lock, чтобы не блокировать другие потоки.
                should_pause = True
            else:
                should_pause = False
        if should_pause:
            time.sleep(60)
            with fail_lock:
                consecutive["errors"].clear()
            return
        with fail_lock:
            if consecutive["count"] >= 15:
                print("[ch19] STOP: 15 подряд неудач — остановка.", flush=True)
                stop_event.set()
        return

    def handle_success():
        with fail_lock:
            consecutive["errors"].clear()
            consecutive["count"] = 0

    def worker(task_queue):
        while not stop_event.is_set():
            try:
                rec = task_queue.pop(0)
            except IndexError:
                return
            if not cost_budget_ok():
                stop_event.set()
                return
            uid = str(rec.get("task_uid"))
            attempt = 1
            try:
                row = _run_one(app, fg, user_id, rec, attempt, args.out, run_state)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                run_state.record(uid, "runner_error", attempt)
                row = {
                    "task_uid": uid, "grade": rec.get("grade", ""),
                    "level": rec.get("level", ""), "theme_id": rec.get("theme_id", ""),
                    "solution_style": classify_solution_style(rec),
                    "status": "runner_error", "current_stage": "",
                    "error_code": "RUNNER_CRASH", "provider": "", "model": "",
                    "llm_calls": 0, "fast_path_used": 0,
                    "fallback_to_two_call": 0, "audit_executed": 0,
                    "structured_json_used": 0, "base_attempts": 0, "aux_attempts": 0,
                    "has_aux": 0, "aux_reason": "",
                    "aux_status": "", "aux_fail_codes": "", "soft_warnings": "",
                    "base_fail_codes": "RUNNER_CRASH",
                    "extracted_steps_count": 0, "compiled_ops_count": 0,
                    "base_ops_count": 0,
                    "aux_ops_count": 0, "base_points_count": 0,
                    "aux_points_count": 0, "svg_bytes_base": 0, "svg_bytes_aux": 0,
                    "total_latency_ms": 0.0, "cost_usd": 0.0,
                    "prompt_tokens": 0, "completion_tokens": 0,
                }
                handle_failure("RUNNER_CRASH")

            if row is None:
                handle_failure("RUNNER_NULL")
                continue

            with csv_lock:
                with open(results_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=FIELD_NAMES)
                    w.writerow(row)

            with cost_lock:
                run_cost["usd"] += float(row.get("cost_usd", 0.0) or 0.0)
                if args.max_cost_usd is not None and run_cost["usd"] > args.max_cost_usd:
                    if not cost_exceeded["flag"]:
                        cost_exceeded["flag"] = True
                        print(f"[ch19] STOP: превышен --max-cost-usd "
                              f"({run_cost['usd']:.6f} > {args.max_cost_usd})", flush=True)
                    stop_event.set()

            if row.get("status") == "done":
                handle_success()
                print(f"[ch19] done  {uid} aux={row['has_aux']} "
                      f"cost={row['cost_usd']:.6f} "
                      f"lat={row['total_latency_ms']:.0f}ms", flush=True)
            else:
                handle_failure(row.get("error_code") or "")
                print(f"[ch19] {row['status']} {uid} "
                      f"err={row.get('error_code')} "
                      f"cost={row['cost_usd']:.6f}", flush=True)

    if new_file:
        with open(results_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELD_NAMES)
            w.writeheader()

    threads = []
    for _ in range(args.workers):
        t = threading.Thread(target=worker, args=(pending,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    with app.app_context():
        u = User.query.get(user_id)
        balance_after = u.figure_credits if u else balance_before

    print("=" * 60, flush=True)
    print(f"[ch19] total cost: {run_cost['usd']:.6f} USD", flush=True)
    print(f"[ch19] credits before={balance_before} after={balance_after} "
          f"delta={balance_after - balance_before}", flush=True)
    print(f"[ch19] results: {results_path}", flush=True)
    print(f"[ch19] state: {state_path}", flush=True)
    if cost_exceeded["flag"]:
        print("[ch19] завершено по --max-cost-usd", flush=True)
    elif stop_event.is_set():
        print("[ch19] завершено по стоп-условию (15 подряд неудач)", flush=True)


if __name__ == "__main__":
    main()
