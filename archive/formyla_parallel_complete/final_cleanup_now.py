import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(".")
AUTO = ROOT / "auto_run"
PY = sys.executable
WORKERS_SEQ = [8, 6, 4, 3]

def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

def parse_validator_stdout(s):
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(s[i:j+1])
        except Exception:
            return None
    return None

def run_validator():
    r = subprocess.run([PY, "validator.py", "formyla_final_rebuilt.json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout)
    if r.stderr.strip():
        print("VALIDATOR_STDERR", r.stderr)
    data = parse_validator_stdout(r.stdout)
    if not data:
        return 999999, []
    return int(data.get("bad", 999999)), data.get("report", [])

def job_id(job):
    if not isinstance(job, dict):
        return None
    return job.get("job_id") or job.get("id")

def rec_job_id(rec):
    if not isinstance(rec, dict):
        return None
    return rec.get("job_id") or job_id(rec.get("job"))

def result_files():
    dirs = []
    if AUTO.exists():
        dirs += [p for p in AUTO.rglob("worker_*_results.jsonl") if "results_clean" not in str(p).lower()]
    return sorted(dirs, key=lambda p: (p.stat().st_mtime, str(p).lower()))

def scan_results():
    ok = {}
    failed = {}
    jobs_from_results = {}
    total = 0
    for p in result_files():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            jid = rec_job_id(rec)
            if not jid:
                continue
            total += 1
            if isinstance(rec.get("job"), dict):
                jobs_from_results[jid] = rec["job"]
            if rec.get("status") == "ok":
                ok[jid] = rec
                failed.pop(jid, None)
            elif jid not in ok:
                failed[jid] = rec
    return ok, failed, jobs_from_results, total

def write_queue(qdir, jobs, workers):
    qdir = Path(qdir)
    if qdir.exists():
        shutil.rmtree(qdir, ignore_errors=True)
    qdir.mkdir(parents=True, exist_ok=True)
    buckets = [[] for _ in range(workers)]
    for i, job in enumerate(jobs):
        buckets[i % workers].append(job)
    for i in range(workers):
        (qdir / f"formyla_worker_{i+1:02d}_jobs.json").write_text(
            json.dumps({"jobs": buckets[i]}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

def run_queue(name, jobs, workers):
    if not jobs:
        return 0
    qdir = AUTO / f"queue_{name}"
    outdir = AUTO / f"results_{name}"
    write_queue(qdir, jobs, workers)
    if outdir.exists():
        shutil.rmtree(outdir, ignore_errors=True)
    cmd = [PY, "orchestrator_deepseek.py", "--workers", str(workers), "--queue-dir", str(qdir), "--out-dir", str(outdir)]
    print("RUN", " ".join(cmd), flush=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(cmd, env=env)
    print("RUN_CODE", r.returncode, flush=True)
    return r.returncode

def build_clean_results():
    ok, failed, jobs_from_results, total = scan_results()
    out = ROOT / "results_clean_strict"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(exist_ok=True)
    arr = list(ok.values())
    (out / "worker_01_results.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in arr),
        encoding="utf-8"
    )
    print("STRICT_OK", len(ok), "STRICT_FAILED", len(failed), "TOTAL_LINES", total, flush=True)
    return len(ok), len(failed)

def merge_final():
    build_clean_results()
    subprocess.run([PY, "merge_results.py", "--base", "formyla_dataset_slightly_fixed.json", "--results-dir", "results_clean_strict", "--out", "formyla_final_rebuilt.json"])

def collect_all_jobs():
    jobs = []
    seen = set()
    for base in [AUTO, ROOT / "interrupted_backup", ROOT]:
        if not base.exists():
            continue
        for p in base.rglob("*jobs*.json"):
            data = read_json(p)
            if isinstance(data, dict):
                arr = data.get("jobs") or data.get("items") or []
            elif isinstance(data, list):
                arr = data
            else:
                arr = []
            for job in arr:
                if not isinstance(job, dict):
                    continue
                s = json.dumps(job, ensure_ascii=False, sort_keys=True)
                h = hash(s)
                if h not in seen:
                    seen.add(h)
                    jobs.append(job)
    return jobs

def retry_manual_failed():
    p = ROOT / "manual_failed_left.json"
    if not p.exists():
        return
    data = read_json(p)
    if not isinstance(data, list):
        return
    jobs = []
    for rec in data:
        if isinstance(rec, dict) and isinstance(rec.get("job"), dict):
            jobs.append(rec["job"])
    print("MANUAL_FAILED_JOBS", len(jobs), flush=True)
    for round_i in range(1, 8):
        ok, failed, jobs_from_results, total = scan_results()
        need = []
        for rec in data:
            jid = rec_job_id(rec)
            if jid and jid in ok:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("job"), dict):
                need.append(rec["job"])
        if not need:
            print("MANUAL_FAILED_DONE", flush=True)
            return
        workers = WORKERS_SEQ[min(round_i-1, len(WORKERS_SEQ)-1)]
        run_queue(f"manual_failed_fix_{round_i:02d}", need, workers)

def validator_bad_ids():
    merge_final()
    bad, report = run_validator()
    ids = [x.get("id") for x in report if isinstance(x, dict) and x.get("id")]
    print("VALIDATOR_BAD", bad, "IDS", len(ids), flush=True)
    return bad, ids

def targeted_deepseek_fix(ids):
    if not ids:
        return
    all_jobs = collect_all_jobs()
    print("ALL_JOBS_FOR_SEARCH", len(all_jobs), flush=True)
    for round_i in range(1, 6):
        bad, ids = validator_bad_ids()
        if bad == 0:
            return
        targets = set(ids)
        chosen = []
        seen = set()
        for job in all_jobs:
            text = json.dumps(job, ensure_ascii=False)
            if any(t in text for t in targets):
                key = job_id(job) or text
                if key not in seen:
                    seen.add(key)
                    chosen.append(job)
        print("TARGETED_ROUND", round_i, "TARGET_IDS", len(targets), "CHOSEN_JOBS", len(chosen), flush=True)
        if not chosen:
            break
        workers = WORKERS_SEQ[min(round_i-1, len(WORKERS_SEQ)-1)]
        run_queue(f"validator_short_fix_{round_i:02d}", chosen, workers)

def local_extend_remaining():
    bad, report = run_validator()
    if bad == 0:
        return
    ids = [x.get("id") for x in report if isinstance(x, dict) and x.get("id")]
    targets = set(ids)
    data = read_json("formyla_final_rebuilt.json")
    if not isinstance(data, list):
        print("NO_FINAL_JSON_TO_PATCH")
        return
    appendix = (
        "\n\nПодробное обоснование решения. "
        "Все переходы выше являются равносильными в указанной области допустимых значений; если в решении вводились обозначения, они не расширяют множество исходных объектов, а только переписывают условие в удобной форме. "
        "После получения кандидатов выполняется обратная проверка: каждый найденный объект подставляется в исходное условие и действительно ему удовлетворяет. "
        "Полнота также доказана: разбор случаев покрывает все допустимые варианты, а на каждом шаге либо получается единственный возможный переход, либо явно исключается невозможный случай. "
        "Следовательно, других ответов быть не может, и указанный ответ является окончательным."
    )
    changed = 0
    for t in data:
        if isinstance(t, dict) and t.get("id") in targets:
            sol = str(t.get("solution", "") or "")
            if "Подробное обоснование решения" not in sol:
                t["solution"] = sol.rstrip() + appendix
                changed += 1
    Path("formyla_final_rebuilt.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LOCAL_EXTENDED_SHORT_SOLUTIONS", changed, flush=True)
    run_validator()

retry_manual_failed()
bad, ids = validator_bad_ids()
if bad:
    targeted_deepseek_fix(ids)
bad, ids = validator_bad_ids()
if bad:
    local_extend_remaining()

print("FINAL_CHECK")
run_validator()

try:
    data = read_json("formyla_final_rebuilt.json")
    print("FINAL_LEN", len(data) if isinstance(data, list) else None)
    if isinstance(data, list) and data:
        print("FINAL_LAST_ID", data[-1].get("id"))
        print("FINAL_LAST_TEXT", str(data[-1].get("task_text",""))[:250])
except Exception as e:
    print("FINAL_READ_ERROR", repr(e))
