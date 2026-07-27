import json, glob
from pathlib import Path

src_dir = Path("results_retry_2")
retry_dir = Path("retry_failed_3")
retry_dir.mkdir(exist_ok=True)

failed = []
for p in sorted(src_dir.glob("worker_*_results.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("status") != "ok" and rec.get("job"):
            failed.append(rec["job"])

print("failed_jobs_3", len(failed))
print(json.dumps(failed, ensure_ascii=False, indent=2)[:2000])

for old in retry_dir.glob("formyla_worker_*_jobs.json"):
    old.unlink()

for i in range(1, 21):
    jobs = failed if i == 1 else []
    Path(retry_dir, f"formyla_worker_{i:02d}_jobs.json").write_text(
        json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

print("retry queue 3 ready")
