import json, glob, shutil, re
from pathlib import Path

src_dir = Path("results")
retry_dir = Path("retry_failed")
retry_results = Path("results_retry")
retry_dir.mkdir(exist_ok=True)
retry_results.mkdir(exist_ok=True)

failed = []
for p in sorted(src_dir.glob("worker_*_results.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("status") != "ok":
            job = rec.get("job")
            if job:
                failed.append(job)

print("failed_jobs", len(failed))

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

print("retry queue ready")
