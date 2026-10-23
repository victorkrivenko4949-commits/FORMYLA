import json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(".")
AUTO = ROOT / "auto_run"
BACKUP = ROOT / "interrupted_backup"
PY = sys.executable
WORKERS_SEQ = [8, 6, 4, 3]
MAX_EXTRA_ROUNDS = 20

def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

def iter_job_files():
    bases = [ROOT, AUTO, BACKUP]
    seen = set()
    for base in bases:
        if not base.exists():
            continue
        for p in base.rglob("*jobs*.json"):
            sp = str(p.resolve()).lower()
            if sp in seen:
                continue
            seen.add(sp)
            yield p

def iter_result_files():
    bases = [AUTO, ROOT, BACKUP]
    seen = set()
    for base in bases:
        if not base.exists():
            continue
        for p in base.rglob("worker_*_results.jsonl"):
            sp = str(p.resolve()).lower()
            if sp in seen:
                continue
            if "results_clean" in sp:
                continue
            seen.add(sp)
            yield p

def job_id_of_job(job):
    if not isinstance(job, dict):
        return None
    return job.get("job_id") or job.get("id")

def job_id_of_rec(rec):
    if not isinstance(rec, dict):
        return None
    return rec.get("job_id") or job_id_of_job(rec.get("job"))

def scan_jobs():
    jobs = {}
    for p in iter_job_files():
        data = load_json(p)
        if isinstance(data, dict):
            arr = data.get("jobs") or data.get("items") or []
        elif isinstance(data, list):
            arr = data
        else:
            arr = []
        for job in arr:
            jid = job_id_of_job(job)
            if jid and isinstance(job, dict):
                jobs[jid] = job
    return jobs

def scan_results():
    ok = {}
    failed = {}
    jobs_from_results = {}
    total = 0
    for p in sorted(iter_result_files(), key=lambda x: str(x)):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            jid = job_id_of_rec(rec)
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
    for i, bucket in enumerate(buckets, 1):
        (qdir / f"worker_{i:02d}_jobs.json").write_text(
            json.dumps({"jobs": bucket}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

def run_orchestrator(qdir, outdir, workers):
    outdir = Path(outdir)
    if outdir.exists():
        shutil.rmtree(outdir, ignore_errors=True)
    cmd = [
        PY, "orchestrator_deepseek.py",
        "--workers", str(workers),
        "--queue-dir", str(qdir),
        "--out-dir", str(outdir)
    ]
    print("RUN_EXTRA:", " ".join(cmd), flush=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, env=env).returncode

def build_results_clean():
    ok, failed, jobs_from_results, total = scan_results()
    out = ROOT / "results_clean"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(exist_ok=True)
    arr = list(ok.values())
    (out / "worker_01_results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in arr),
        encoding="utf-8"
    )
    return len(ok), len(failed), total

jobs = scan_jobs()
print("JOBS_FOUND", len(jobs), flush=True)

for round_i in range(1, MAX_EXTRA_ROUNDS + 1):
    ok, failed, jobs_from_results, total = scan_results()
    print(f"EXTRA_ROUND={round_i} OK={len(ok)} FAILED_LEFT={len(failed)} RESULT_LINES={total}", flush=True)

    if not failed:
        break

    retry_jobs = []
    missing = []
    for jid, rec in sorted(failed.items()):
        job = jobs.get(jid) or jobs_from_results.get(jid) or rec.get("job")
        if isinstance(job, dict) and job_id_of_job(job):
            retry_jobs.append(job)
        else:
            missing.append(jid)

    if missing:
        Path("manual_missing_jobs.json").write_text(
            json.dumps(missing, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print("MISSING_JOB_DEFS", len(missing), "saved manual_missing_jobs.json", flush=True)

    if not retry_jobs:
        print("NO_RETRY_JOBS_LEFT", flush=True)
        break

    workers = WORKERS_SEQ[min(round_i - 1, len(WORKERS_SEQ) - 1)]
    qdir = AUTO / f"queue_retry_extra_{round_i:02d}"
    outdir = AUTO / f"results_retry_extra_{round_i:02d}"

    write_queue(qdir, retry_jobs, workers)
    code = run_orchestrator(qdir, outdir, workers)

    if code != 0 and workers != 3:
        print("ORCH_CODE", code, "will continue with lower workers", flush=True)
    elif code != 0:
        print("ORCH_CODE", code, "at minimum workers", flush=True)

ok_count, failed_count, total_lines = build_results_clean()
print("RESULTS_CLEAN_OK", ok_count, flush=True)
print("RESULTS_CLEAN_FAILED_LEFT", failed_count, flush=True)
print("RESULT_LINES_SCANNED", total_lines, flush=True)

subprocess.run([
    PY, "merge_results.py",
    "--base", "formyla_dataset_slightly_fixed.json",
    "--results-dir", "results_clean",
    "--out", "formyla_final_rebuilt.json"
])

subprocess.run([PY, "validator.py", "formyla_final_rebuilt.json"])

try:
    data = json.loads(Path("formyla_final_rebuilt.json").read_text(encoding="utf-8", errors="replace"))
    print("FINAL_LEN", len(data))
    print("FINAL_LAST_ID", data[-1].get("id") if data else None)
    print("FINAL_LAST_TEXT", (data[-1].get("task_text", "") if data else "")[:300])
except Exception as e:
    print("FINAL_READ_ERROR", repr(e))

if failed_count:
    ok, failed, jobs_from_results, total = scan_results()
    Path("manual_failed_left.json").write_text(
        json.dumps(list(failed.values()), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print("NEEDS_MANUAL_CHECK manual_failed_left.json")
else:
    print("AUTO_RESCUE_DONE")
