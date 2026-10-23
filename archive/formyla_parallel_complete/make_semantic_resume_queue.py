import json, glob, shutil, re
from pathlib import Path

queue_dir = Path("semantic_replace_queue")
results_dir = Path("semantic_replace_results")
resume_dir = Path("semantic_replace_queue_resume")

all_jobs = []
for p in sorted(queue_dir.glob("formyla_worker_*_jobs.json")):
    obj = json.loads(p.read_text(encoding="utf-8"))
    all_jobs.extend(obj.get("jobs", []))

done = set()
failed = set()
bad_lines = 0

for p in sorted(results_dir.glob("worker_*_results.jsonl")):
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            bad_lines += 1
            continue
        jid = rec.get("job_id") or rec.get("job", {}).get("job_id")
        if not jid:
            continue
        if rec.get("status") == "ok":
            done.add(jid)
        else:
            failed.add(jid)

pending = [j for j in all_jobs if j.get("job_id") not in done]

if resume_dir.exists():
    shutil.rmtree(resume_dir)
resume_dir.mkdir()

for k in range(20):
    part = pending[k::20]
    Path(resume_dir, f"formyla_worker_{k+1:02d}_jobs.json").write_text(
        json.dumps({"jobs": part}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

print("ALL_JOBS", len(all_jobs))
print("DONE_OK", len(done))
print("FAILED_SEEN", len(failed))
print("BAD_LINES", bad_lines)
print("PENDING_FOR_RESUME", len(pending))
print("RESUME_QUEUE", "semantic_replace_queue_resume")
