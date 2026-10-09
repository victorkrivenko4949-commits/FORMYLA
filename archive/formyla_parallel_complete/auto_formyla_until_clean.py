import json, glob, shutil, subprocess, sys, re, time
from pathlib import Path

WORKERS = 20
MAX_RETRY_ROUNDS = 12
MAX_AUDIT_CYCLES = 6
BASE = Path("formyla_dataset_slightly_fixed.json")
FINAL = Path("formyla_final_rebuilt.json")
AUTO = Path("auto_run")
LOG = AUTO / "auto_log.txt"

AUTO.mkdir(exist_ok=True)

def log(msg):
    s = str(msg)
    print(s, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(s + "\n")

def run(cmd):
    log("RUN: " + " ".join(map(str, cmd)))
    p = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if p.stdout:
        log(p.stdout.rstrip())
    if p.stderr:
        log("STDERR: " + p.stderr.rstrip())
    if p.returncode != 0:
        raise SystemExit(f"COMMAND FAILED: {' '.join(map(str, cmd))}")
    return p.stdout + "\n" + p.stderr

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def load_original_jobs():
    jobs = {}
    for p in sorted(Path(".").glob("formyla_worker_*_jobs.json")):
        try:
            data = read_json(p)
        except Exception:
            continue
        for job in data.get("jobs", []):
            jid = job.get("job_id")
            if jid:
                jobs[jid] = job
    return jobs

ORIGINAL_JOBS = load_original_jobs()

def valid_job(job):
    if not isinstance(job, dict):
        return False
    need = ["job_id", "mode", "grade", "difficulty", "theme", "subtopic"]
    return all(k in job and job[k] not in [None, ""] for k in need)

def result_dirs():
    dirs = []
    for name in ["results", "results_retry", "results_retry_2", "results_retry_3", "results_retry_4"]:
        if Path(name).exists():
            dirs.append(Path(name))
    for p in sorted(AUTO.glob("results_*")):
        if p.is_dir():
            dirs.append(p)
    return dirs

def iter_records(dirs):
    for d in dirs:
        for p in sorted(d.glob("worker_*_results.jsonl")):
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    yield d, rec
                except Exception:
                    continue

def job_id_of(rec):
    return rec.get("job_id") or rec.get("job", {}).get("job_id")

def pending_failed(dirs):
    ok = set()
    pending = {}
    for d, rec in iter_records(dirs):
        jid = job_id_of(rec)
        if not jid:
            continue
        if rec.get("status") == "ok":
            ok.add(jid)
            pending.pop(jid, None)
        else:
            if jid not in ok:
                job = ORIGINAL_JOBS.get(jid) or rec.get("job")
                if valid_job(job):
                    pending[jid] = job
    return [job for jid, job in pending.items() if jid not in ok]

def write_queue(jobs, qdir):
    qdir = Path(qdir)
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    buckets = [[] for _ in range(WORKERS)]
    for i, job in enumerate(jobs):
        buckets[i % WORKERS].append(job)
    for i, bucket in enumerate(buckets, start=1):
        (qdir / f"formyla_worker_{i:02d}_jobs.json").write_text(
            json.dumps({"jobs": bucket}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

def run_orchestrator(qdir, outdir):
    outdir = Path(outdir)
    if outdir.exists():
        shutil.rmtree(outdir)
    run([sys.executable, "orchestrator_deepseek.py", "--workers", str(WORKERS), "--queue-dir", str(qdir), "--out-dir", str(outdir)])

def count_jobs_in_queue(qdir):
    n = 0
    for p in Path(qdir).glob("formyla_worker_*_jobs.json"):
        try:
            n += len(read_json(p).get("jobs", []))
        except Exception:
            pass
    return n

def count_lines(folder):
    n = 0
    for p in Path(folder).glob("worker_*_results.jsonl"):
        n += sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
    return n

def ensure_main_run():
    total_jobs = count_jobs_in_queue(".")
    current = count_lines("results") if Path("results").exists() else 0
    log(f"MAIN_QUEUE_JOBS={total_jobs}")
    log(f"MAIN_RESULTS_LINES={current}")
    if total_jobs and current < total_jobs:
        log("MAIN RUN IS INCOMPLETE: starting full main run")
        run_orchestrator(".", "results")
    else:
        log("MAIN RUN EXISTS: skipping full rerun")

def retry_until_no_failed():
    for round_i in range(1, MAX_RETRY_ROUNDS + 1):
        dirs = result_dirs()
        failed = pending_failed(dirs)
        log(f"RETRY_ROUND={round_i} PENDING_FAILED={len(failed)}")
        if not failed:
            return True
        qdir = AUTO / f"queue_retry_{round_i:02d}"
        outdir = AUTO / f"results_retry_{round_i:02d}"
        write_queue(failed, qdir)
        run_orchestrator(qdir, outdir)
    return len(pending_failed(result_dirs())) == 0

def write_results_clean():
    latest_by_task_id = {}
    latest_by_job_id = {}
    for d, rec in iter_records(result_dirs()):
        if rec.get("status") != "ok":
            continue
        task = rec.get("task")
        if not isinstance(task, dict):
            continue
        tid = task.get("id")
        jid = job_id_of(rec)
        if tid:
            latest_by_task_id[tid] = rec
        if jid:
            latest_by_job_id[jid] = rec

    out = Path("results_clean")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    records = list(latest_by_task_id.values())
    (out / "worker_01_results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8"
    )
    log(f"CLEAN_TASK_RECORDS={len(records)}")
    log(f"CLEAN_JOB_RECORDS={len(latest_by_job_id)}")
    return records

def merge_final():
    write_results_clean()
    run([sys.executable, "merge_results.py", "--base", str(BASE), "--results-dir", "results_clean", "--out", str(FINAL)])

def validator_bad_count():
    if not Path("validator.py").exists():
        log("NO validator.py FOUND")
        return 0, ""
    out = run([sys.executable, "validator.py", str(FINAL)])
    m = re.search(r"\bbad\b\D+(\d+)", out, flags=re.I)
    bad = int(m.group(1)) if m else 0
    log(f"VALIDATOR_BAD={bad}")
    return bad, out

def mojibake(s):
    return isinstance(s, str) and any(x in s for x in ["Р", "СЃ", "С‚", "С‡", "Рё", "вЂ"])

def task_issues(t):
    issues = []
    req = ["id", "grade", "method_code", "difficulty", "task_text", "correct_answer", "solution", "theme", "subtopic", "method"]
    for k in req:
        if k not in t or t[k] in [None, ""]:
            issues.append("missing_" + k)
    blob = " ".join(str(t.get(k, "")) for k in req)
    low = blob.lower()
    bad_phrases = ["не удалось", "условие противоречиво", "решение не найдено", "заменим задачу", "placeholder", "undefined"]
    for phrase in bad_phrases:
        if phrase in low:
            issues.append("bad_phrase_" + phrase)
    if mojibake(blob):
        issues.append("mojibake")
    if str(t.get("task_text", "")).count("$") % 2:
        issues.append("odd_dollar_task")
    if str(t.get("solution", "")).count("$") % 2:
        issues.append("odd_dollar_solution")
    if int(t.get("difficulty", 0) or 0) >= 8:
        if len(str(t.get("solution", ""))) < 350:
            issues.append("L8_solution_too_short")
        easy = ["найдите значение", "вычислите", "сколько процентов", "среднее арифметическое", "остаток от деления"]
        if any(x in str(t.get("task_text", "")).lower() for x in easy) and len(str(t.get("solution", ""))) < 700:
            issues.append("L8_probably_too_easy")
    return issues

def audit_generated_tasks():
    records = write_results_clean()
    bad_jobs = []
    seen_text = {}
    for rec in records:
        t = rec.get("task", {})
        issues = task_issues(t)
        txt = str(t.get("task_text", "")).strip()
        if txt:
            if txt in seen_text:
                issues.append("duplicate_task_text")
            seen_text[txt] = t.get("id")
        if issues:
            bad_jobs.append({
                "job_id": f"audit-{len(bad_jobs)+1:04d}-{t.get('id','noid')}",
                "mode": "replace_bad",
                "id": t.get("id"),
                "grade": t.get("grade"),
                "difficulty": t.get("difficulty"),
                "theme": t.get("theme"),
                "subtopic": t.get("subtopic"),
                "method_code": t.get("method_code"),
                "reasons": ", ".join(issues),
                "quality_target": "исправить все ошибки аудита; сохранить тему, подтему, класс и уровень"
            })
    bad_jobs = [j for j in bad_jobs if valid_job(j) and j.get("id")]
    log(f"AUDIT_BAD_GENERATED={len(bad_jobs)}")
    return bad_jobs

def run_audit_cycles():
    for cycle in range(1, MAX_AUDIT_CYCLES + 1):
        merge_final()
        vbad, vout = validator_bad_count()
        audit_jobs = audit_generated_tasks()
        if vbad == 0 and not audit_jobs:
            log("AUTO_STATUS=CLEAN")
            return True
        if not audit_jobs:
            log("VALIDATOR_HAS_BAD_BUT_NO_PARSEABLE_AUDIT_JOBS")
            return False
        qdir = AUTO / f"queue_audit_fix_{cycle:02d}"
        outdir = AUTO / f"results_audit_fix_{cycle:02d}"
        write_queue(audit_jobs, qdir)
        run_orchestrator(qdir, outdir)
        if not retry_until_no_failed():
            return False
    return False

def final_report():
    if FINAL.exists():
        data = read_json(FINAL)
        log(f"FINAL_LEN={len(data)}")
        if data:
            log(f"FINAL_LAST_ID={data[-1].get('id')}")
            log(f"FINAL_LAST_TEXT={str(data[-1].get('task_text',''))[:200]}")
    log("DONE")

def main():
    LOG.write_text("", encoding="utf-8")
    if not BASE.exists():
        raise SystemExit("NO BASE FILE: formyla_dataset_slightly_fixed.json")
    ensure_main_run()
    ok = retry_until_no_failed()
    if not ok:
        log("AUTO_STATUS=FAILED_RETRY_LEFT")
        final_report()
        raise SystemExit(1)
    ok = run_audit_cycles()
    final_report()
    if not ok:
        log("AUTO_STATUS=NEEDS_MANUAL_CHECK")
        raise SystemExit(2)

if __name__ == "__main__":
    main()
