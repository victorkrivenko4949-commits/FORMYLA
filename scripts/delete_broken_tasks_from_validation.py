"""Delete tasks marked as broken by DeepSeek validator.

Reads scripts/_validation/validation.jsonl produced by
validate_tasks_with_deepseek.py and removes tasks that the AI confidently
flagged as broken.

Default policy: delete only verdict == 'broken' AND confidence == 'high'.
Override via --include-medium or --include-unclear if you want to be more
aggressive.

Backups deleted rows to adaptive_data/_backups/deleted_validator_<ts>.json.
"""
import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")
VAL_PATH = os.path.join(ROOT, "scripts", "_validation", "validation.jsonl")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-medium", action="store_true",
                    help="Also delete broken with confidence=medium")
    ap.add_argument("--include-unclear-high", action="store_true",
                    help="Also delete unclear with confidence=high")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(VAL_PATH):
        print(f"No validation file at {VAL_PATH}. Run validator first.")
        return

    bad_ids: dict[int, dict] = {}
    counts = {"ok": 0, "broken": 0, "unclear": 0, "error": 0}
    with open(VAL_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            v = obj.get("verdict")
            counts[v] = counts.get(v, 0) + 1
            tid = obj.get("id")
            if not isinstance(tid, int):
                continue
            conf = obj.get("confidence", "medium")
            if v == "broken":
                if conf == "high" or (args.include_medium and conf == "medium"):
                    bad_ids[tid] = obj
            elif v == "unclear" and args.include_unclear_high and conf == "high":
                bad_ids[tid] = obj

    print(f"Validation summary: {counts}")
    print(f"Tasks selected for deletion: {len(bad_ids)}")

    if not bad_ids:
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    placeholders = ",".join("?" * len(bad_ids))
    cur.execute(
        f"SELECT * FROM adaptive_tasks WHERE id IN ({placeholders})",
        list(bad_ids.keys()),
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"Found in DB: {len(rows)}")

    for r in rows[:30]:
        info = bad_ids.get(r["id"], {})
        snippet = (r["task_text"] or "")[:120].replace("\n", " ")
        print(f"  id={r['id']} cl={r['class_level']} L={r['difficulty_level']} "
              f"[{info.get('confidence', '?')}]: {snippet}...")
        print(f"     reason: {info.get('reason', '')[:200]}")
    if len(rows) > 30:
        print(f"  ... +{len(rows) - 30} more")

    if args.dry_run:
        print("\nDry-run: no deletions made.")
        conn.close()
        return

    # Backup
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"deleted_validator_{ts}.json")
    backup_payload = []
    for r in rows:
        rec = dict(r)
        rec["_validator"] = bad_ids.get(r["id"])
        backup_payload.append(rec)
    with open(backup_path, "w", encoding="utf-8") as fp:
        json.dump(backup_payload, fp, ensure_ascii=False, indent=2)
    print(f"\nBackup: {backup_path}")

    cur.execute(
        f"DELETE FROM adaptive_tasks WHERE id IN ({placeholders})",
        list(bad_ids.keys()),
    )
    conn.commit()
    print(f"Deleted: {cur.rowcount}")

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    print(f"Remaining tasks: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
