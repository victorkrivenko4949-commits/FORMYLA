# -*- coding: utf-8 -*-
"""scripts/batch/run_batch.py — пакетный прогон датасета через конвейер чертежей.

БЛОК 2. Идемпотентный раннер через РЕАЛЬНЫЙ API (не в обход конвейера):
    POST /figures/generate/start
    GET  /figures/generate/status/<id>

Проверяется реальный путь, включая in-process очередь и воркер
(routes.figures_generator._queue_worker_loop + _run_build_job + LLM + engine).

Требования (блок 2.1):
  * идемпотентность — повторный запуск не дублирует job'ы, task_id уже в
    results.jsonl пропускается, orphan-job'ы из progress.jsonl подхватываются;
  * чекпоинт после каждой задачи в out/progress.jsonl;
  * graceful stop по Ctrl+C с сохранением прогресса;
  * параллелизм — задаётся самой очередью (MAX_CONCURRENT_JOBS, сейчас 2);
  * таймаут на задачу — FIGURE_JOB_DEADLINE_SEC + 15 с;
  * исключение при опросе — запись в out/failed.jsonl, прогон продолжается.

Собранные поля (блок 2.3) записываются в out/results.jsonl (одна строка/задача).

Запуск:
    python scripts/batch/run_batch.py [--limit N] [--deadline-sec SEC]

`--limit N` ограничивает число задач (для smoke-прогона).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
from typing import Any, Dict, List, Optional

# Windows-консоль: UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OUT_DIR = os.path.join(_SCRIPT_DIR, "out")
SAMPLE_PATH = os.path.join(OUT_DIR, "sample_100.jsonl")
PROGRESS_PATH = os.path.join(OUT_DIR, "progress.jsonl")
RESULTS_PATH = os.path.join(OUT_DIR, "results.jsonl")
FAILED_PATH = os.path.join(OUT_DIR, "failed.jsonl")

POLL_INTERVAL = 2.0


def _load_dotenv(path: Optional[str] = None) -> None:
    """Загрузить .env (без перезаписи уже установленных переменных)."""
    p = path or os.path.join(_ROOT, ".env")
    try:
        with open(p, "r", encoding="utf-8") as f:
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


def _apply_process_env(deadline_sec: float) -> None:
    """Настройки процесса (не правят прод .env и логику конвейера)."""
    # Не списываем кредиты служебного аккаунта.
    os.environ.setdefault("FIGURE_CREDITS_ENFORCED", "false")
    # Таймаут задания (мягкий лимит раннера; сам конвейер его не enforce'ит,
    # но задача требует формулу FIGURE_JOB_DEADLINE_SEC + 15).
    os.environ.setdefault("FIGURE_JOB_DEADLINE_SEC", str(int(deadline_sec)))


# ── Телеметрия template_id (инструментирование, НЕ правка pipeline) ────────
# _run_solver_aux_job делает `from services.aux_templates import match_template`
# на КАЖДЫЙ вызов, поэтому патч атрибута модуля подхватывается.  template_id
# нигде не персистится в БД, поэтому фиксируем его здесь (ключ — нормализованное
# условие).
_TEMPLATE_HITS: Dict[str, Optional[str]] = {}
_TEMPLATE_LOCK = threading.Lock()


def _normalize_condition_key(condition: str) -> str:
    return " ".join((condition or "").split()).lower()


def _install_template_instrumentation() -> None:
    import services.aux_templates as AT
    orig = AT.match_template

    def _wrapped(base_plan, condition, ctx):
        res = orig(base_plan, condition, ctx)
        key = _normalize_condition_key(condition)
        with _TEMPLATE_LOCK:
            _TEMPLATE_HITS[key] = (res.get("template_id") if res else None)
        return res

    AT.match_template = _wrapped


def _template_id_for(condition_text: str) -> Optional[str]:
    key = _normalize_condition_key(condition_text)
    with _TEMPLATE_LOCK:
        return _TEMPLATE_HITS.get(key)


# ── Чтение/запись чекпоинтов ────────────────────────────────────────────────

def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _append_jsonl(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ── Сбор телеметрии из БД после завершения job ─────────────────────────────

def _collect_job_telemetry(app, job_id: int, task: dict, group: str,
                           generation_mode: str, total_ms: float,
                           runner_status: str) -> dict:
    """Собрать полную запись по задаче (блок 2.3) из FigureBuildJob/Stage."""
    from models import db, FigureBuildJob, FigureBuildStage

    rec: Dict[str, Any] = {
        "task_id": task.get("task_id"),
        "grade": task.get("grade"),
        "group": group,
        "job_id": job_id,
        "status": runner_status,          # done | failed | timeout
        "generation_mode": generation_mode,
        "trust_level": None,
        "answer_verdict": None,
        "solver_answer": None,
        "measured_answer": None,
        "dataset_answer": task.get("answer"),
        "aux_source": None,
        "aux_usefulness": None,
        "aux_dropped_reason": None,
        "aux_status": None,
        "has_aux": None,
        "aux_template_id": None,
        "coverage_score": None,
        "visual_score": None,
        "total_ms": round(total_ms, 1),
        "stages": [],
        "total_cost_usd": 0.0,
        "error_codes": [],
        "job_error": None,
        "svg_path": None,
    }

    with app.app_context():
        job = db.session.get(FigureBuildJob, job_id)
        if job is not None:
            rec["status"] = job.status if runner_status not in ("timeout",) else "timeout"
            rec["trust_level"] = job.trust_level
            rec["answer_verdict"] = job.answer_verdict
            rec["solver_answer"] = job.solver_answer
            rec["measured_answer"] = job.measured_answer
            rec["aux_source"] = job.aux_source
            rec["aux_usefulness"] = job.aux_usefulness
            rec["aux_dropped_reason"] = job.aux_dropped_reason
            rec["aux_status"] = job.aux_status
            rec["has_aux"] = bool(job.has_aux)
            rec["svg_path"] = job.svg_path
            rec["job_error"] = job.error
            rec["generation_mode"] = job.generation_mode or generation_mode
            if job.error:
                rec["error_codes"].append(_error_code_from(job.error))

        stages = (
            FigureBuildStage.query.filter_by(job_id=job_id)
            .order_by(FigureBuildStage.id).all()
        )
        cost = 0.0
        for s in stages:
            codes = []
            if s.error_codes:
                try:
                    codes = json.loads(s.error_codes)
                    if isinstance(codes, list):
                        codes = [c for c in codes if c]
                except Exception:
                    codes = [s.error_codes]
            for c in codes:
                if c and c not in rec["error_codes"]:
                    rec["error_codes"].append(c)
            est = float(s.estimated_cost_usd or 0.0)
            cost += est
            rec["stages"].append({
                "stage": s.stage,
                "role": s.role,
                "provider": s.provider,
                "model": s.model,
                "attempt": s.attempt,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "reasoning_tokens": s.reasoning_tokens,
                "latency_ms": s.latency_ms,
                "coverage_score": s.coverage_score,
                "visual_score": s.visual_score,
                "validation_passed": s.validation_passed,
                "estimated_cost_usd": est,
                "fallback_used": bool(s.fallback_used),
                "timeout_hit": bool(s.timeout_hit),
                "label_collisions": s.label_collisions,
                "autofix_applied": bool(s.autofix_applied),
                "error_codes": codes,
            })
            if s.stage == "coverage_check" and s.coverage_score is not None:
                rec["coverage_score"] = s.coverage_score
            if s.stage == "visual_check" and s.visual_score is not None:
                rec["visual_score"] = s.visual_score
        rec["total_cost_usd"] = round(cost, 8)
        rec["aux_template_id"] = _template_id_for(task.get("condition") or "")
    return rec


def _error_code_from(error: str) -> str:
    """Извлечь код ошибки из job.error (первое слово, если похоже на код)."""
    if not error:
        return "UNKNOWN"
    code = error.split(":", 1)[0].strip()
    if code.startswith(("LLM_", "MISSING_", "INVALID_", "CONDITION_", "LABEL_",
                        "AUX_", "SOLVER_", "ENGINE_", "GEO_")):
        return code
    # Иначе — краткая сигнатура.
    return (code[:40] if code else "UNKNOWN")


# ── Главный цикл ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Пакетный прогон чертежей")
    parser.add_argument("--sample", default=SAMPLE_PATH)
    parser.add_argument("--limit", type=int, default=0, help="0 = весь датасет")
    parser.add_argument("--deadline-sec", type=float, default=240.0,
                        help="FIGURE_JOB_DEADLINE_SEC (мягкий лимит раннера)")
    parser.add_argument("--out-dir", default=OUT_DIR)
    args = parser.parse_args()

    _load_dotenv()
    _apply_process_env(args.deadline_sec)

    # Пути вывода.
    progress_path = os.path.join(args.out_dir, "progress.jsonl")
    results_path = os.path.join(args.out_dir, "results.jsonl")
    failed_path = os.path.join(args.out_dir, "failed.jsonl")
    os.makedirs(args.out_dir, exist_ok=True)

    # Импорт приложения (запускает очередь-воркер в этом же процессе).
    import app as A
    import routes.figures_generator as fg

    # ── Служебный batch-пользователь с ролью teacher ──
    # before_request (force_intake_completion) редиректит студентов без
    # пройденной анкеты на /intake.  Роль teacher/parent его обходит.
    from models import db as _db, User as _User
    with A.app.app_context():
        _u = _User.query.filter_by(email="batch@formyla.local").first()
        if _u is None:
            _u = _User(
                email="batch@formyla.local",
                name="Batch Runner",
                role="teacher",
                figure_credits=10_000,
                figures_built=0,
                onboarding_completed=1,
                plan_expires_at=None,
            )
            _db.session.add(_u)
            _db.session.commit()
        _BATCH_USER_ID = _u.id

    # Обход per-user rate limit (10/час) для служебного прогона — константа
    # модуля читается на каждый вызов _rate_check, поэтому патч корректен.
    fg.RATE_LIMIT_MAX = 10 ** 9

    _install_template_instrumentation()

    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(_BATCH_USER_ID)
        sess["_fresh"] = True

    # ── Загрузка выборки ──
    if not os.path.exists(args.sample):
        print(f"[run_batch] Выборка не найдена: {args.sample}", file=sys.stderr)
        print("[run_batch] Сначала: python scripts/batch/load_dataset.py --sample", file=sys.stderr)
        return 1
    sample = _read_jsonl(args.sample)
    if args.limit > 0:
        sample = sample[: args.limit]

    # Идемпотентность: уже обработанные task_id (финальный статус).
    done_results = _read_jsonl(results_path)
    final_task_ids = {r.get("task_id") for r in done_results if r.get("task_id")}
    # orphan-job'ы из progress.jsonl (job создан, но результат не записан).
    progress_rows = _read_jsonl(progress_path)
    progress_map: Dict[str, dict] = {}
    for r in progress_rows:
        tid = r.get("task_id")
        if tid:
            progress_map[tid] = r

    print(f"[run_batch] выборка: {len(sample)} задач; "
          f"уже обработано: {len(final_task_ids)}; "
          f"в прогрессе: {len(progress_map)}")

    # ── Этап 1: создать (или подхватить) job для каждой задачи ──
    jobs: List[dict] = []   # {task, job_id, start_ts, deadline_ts}
    new_count = 0
    for task in sample:
        tid = task.get("task_id")
        if tid in final_task_ids:
            continue
        if tid in progress_map and progress_map[tid].get("job_id"):
            jobs.append({
                "task": task,
                "job_id": progress_map[tid]["job_id"],
                "start_ts": progress_map[tid].get("start_ts", time.time()),
                "active_since": progress_map[tid].get("active_since"),
                "deadline_ts": progress_map[tid].get("deadline_ts"),
            })
            continue

        payload = {"problem_text": task.get("condition") or ""}
        group = task.get("group", "B")
        if group == "A":
            payload["mode"] = "condition_solution"
            payload["solution_text"] = task.get("solution") or ""
        else:
            # Решения НЕТ: solver генерирует его сам.
            payload["mode"] = "solver_aux"

        try:
            resp = client.post("/figures/generate/start", json=payload)
        except Exception as e:
            _append_jsonl(failed_path, {
                "task_id": tid, "error": f"POST_START_EXCEPTION: {e}",
                "status": "failed",
            })
            continue
        data = resp.get_json(silent=True) or {}
        if resp.status_code not in (200,) or not data.get("job_id"):
            err = data.get("error") or f"HTTP {resp.status_code}"
            _append_jsonl(failed_path, {
                "task_id": tid, "error": f"START_REJECTED: {err}",
                "status": "failed",
            })
            continue
        job_id = data["job_id"]
        now = time.time()
        rec = {
            "task": task,
            "job_id": job_id,
            "start_ts": now,
            # Таймаут стартует, когда воркер реально взял job из очереди
            # (статус перестал быть "queued"), а не с момента создания.
            "active_since": None,
            "deadline_ts": None,
        }
        jobs.append(rec)
        _append_jsonl(progress_path, {
            "task_id": tid,
            "job_id": job_id,
            "start_ts": now,
            "active_since": None,
            "deadline_ts": None,
        })
        new_count += 1

    print(f"[run_batch] job'ов к обработке: {len(jobs)} "
          f"(новых создано: {new_count})")

    # ── Этап 2: опрос до финального статуса / таймаута ──
    remaining = {j["task"]["task_id"]: j for j in jobs}
    deadline_sec = fg.FIGURE_JOB_DEADLINE_SEC + 15
    interrupted = False
    try:
        while remaining:
            for tid in list(remaining.keys()):
                job = remaining[tid]
                try:
                    resp = client.get(f"/figures/generate/status/{job['job_id']}")
                except Exception as e:
                    _append_jsonl(failed_path, {
                        "task_id": tid, "job_id": job["job_id"],
                        "error": f"STATUS_EXCEPTION: {e}", "status": "failed",
                    })
                    _append_jsonl(results_path, _collect_job_telemetry(
                        A.app, job["job_id"], job["task"],
                        job["task"].get("group", "B"),
                        job["task"].get("group", "B") == "A" and "condition_solution" or "solver_aux",
                        time.time() - job["start_ts"], "failed",
                    ))
                    del remaining[tid]
                    continue

                st = (resp.get_json(silent=True) or {}).get("status")
                # Старт таймаута — момент, когда воркер взял задачу.
                if job["active_since"] is None and st not in ("queued", None):
                    job["active_since"] = time.time()
                    job["deadline_ts"] = job["active_since"] + deadline_sec

                if job["deadline_ts"] is not None and time.time() > job["deadline_ts"]:
                    _append_jsonl(failed_path, {
                        "task_id": tid, "job_id": job["job_id"],
                        "error": f"TIMEOUT (> {deadline_sec:.0f} s active)",
                        "status": "timeout",
                    })
                    _append_jsonl(results_path, _collect_job_telemetry(
                        A.app, job["job_id"], job["task"],
                        job["task"].get("group", "B"),
                        job["task"].get("group", "B") == "A" and "condition_solution" or "solver_aux",
                        time.time() - job["start_ts"], "timeout",
                    ))
                    del remaining[tid]
                    continue

                if st in ("done", "failed"):
                    _append_jsonl(results_path, _collect_job_telemetry(
                        A.app, job["job_id"], job["task"],
                        job["task"].get("group", "B"),
                        job["task"].get("group", "B") == "A" and "condition_solution" or "solver_aux",
                        time.time() - job["start_ts"], st,
                    ))
                    if st == "failed":
                        _append_jsonl(failed_path, {
                            "task_id": tid, "job_id": job["job_id"],
                            "error": (resp.get_json(silent=True) or {}).get("error"),
                            "status": "failed",
                        })
                    del remaining[tid]
            if remaining:
                time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        interrupted = True
        print("\n[run_batch] Ctrl+C: сохраняю прогресс и завершаюсь.")
        # Прогресс уже сохранён построчно в progress.jsonl.

    done = _read_jsonl(results_path)
    print(f"[run_batch] завершено. Итог: {len(done)} записей в results.jsonl, "
          f"осталось незавершённых: {len(remaining)}")
    print(f"[run_batch] results: {results_path}")
    print(f"[run_batch] failed:  {failed_path}")
    print(f"[run_batch] progress:{progress_path}")
    return 0 if not interrupted else 130


if __name__ == "__main__":
    raise SystemExit(main())
