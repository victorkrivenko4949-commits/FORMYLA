import json, glob, shutil
from pathlib import Path

src_dir = Path("results_retry")
retry_dir = Path("retry_failed_2")
retry_dir.mkdir(exist_ok=True)

failed = []
for p in sorted(src_dir.glob("worker_*_results.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("status") != "ok" and rec.get("job"):
            failed.append(rec["job"])

print("failed_jobs_2", len(failed))

for old in retry_dir.glob("formyla_worker_*_jobs.json"):
    old.unlink()

buckets = [[] for _ in range(20)]
for i, job in enumerate(failed):
    buckets[i % 20].append(job)

for i, jobs in enumerate(buckets, start=1):
    Path(retry_dir, f"formyla_worker_{i:02d}_jobs.json").write_text(
        json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

print("retry queue 2 ready")
