"""Quick status check for the difficulty validation run."""
import json, os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSONL = os.path.join(ROOT, "scripts", "_validation", "difficulty.jsonl")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

conn = sqlite3.connect(os.path.join(ROOT, "instance", "formyla.db"))
total_db = conn.execute("SELECT COUNT(*) FROM adaptive_tasks").fetchone()[0]
conn.close()

if not os.path.exists(JSONL):
    print("difficulty.jsonl not found")
    sys.exit(0)

verdicts = {}
n = 0
last_id = None
confidence_split = {}
for line in open(JSONL, encoding="utf-8"):
    try:
        o = json.loads(line)
        v = o.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        c = o.get("confidence", "?")
        confidence_split.setdefault(v, {})[c] = \
            confidence_split.setdefault(v, {}).get(c, 0) + 1
        n += 1
        last_id = o.get("id")
    except Exception:
        continue

print(f"DB tasks total:   {total_db}")
print(f"JSONL records:    {n} ({n/max(total_db,1)*100:.1f}%)")
print(f"Last id written:  {last_id}\n")

print("Verdict breakdown:")
for k in sorted(verdicts.keys(), key=lambda x: -verdicts[x]):
    pct = verdicts[k] / max(n, 1) * 100
    print(f"  {k:12} {verdicts[k]:5}  ({pct:5.1f}%)")

print("\nVerdict × confidence:")
for v in sorted(verdicts.keys(), key=lambda x: -verdicts[x]):
    parts = " ".join(
        f"{c}={confidence_split[v].get(c, 0)}"
        for c in ("high", "medium", "low")
    )
    print(f"  {v:12} | {parts}")
