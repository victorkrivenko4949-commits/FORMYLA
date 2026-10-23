import json, glob
from pathlib import Path

job_id = "fill-0310"
found = None

for p in sorted(Path(".").glob("formyla_worker_*_jobs.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    for job in data.get("jobs", []):
        if job.get("job_id") == job_id:
            found = job
            print("FOUND_IN", p)
            print(json.dumps(job, ensure_ascii=False, indent=2))
            break
    if found:
        break

if not found:
    raise SystemExit("NOT FOUND")

retry_dir = Path("retry_failed_4")
retry_dir.mkdir(exist_ok=True)

for old in retry_dir.glob("formyla_worker_*_jobs.json"):
    old.unlink()

for i in range(1, 21):
    jobs = [found] if i == 1 else []
    Path(retry_dir, f"formyla_worker_{i:02d}_jobs.json").write_text(
        json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

print("retry queue 4 ready")
