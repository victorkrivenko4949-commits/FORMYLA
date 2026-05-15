"""Apply the difficulty-validation verdicts produced by
[scripts/validate_difficulty_levels.py].

For each task with a high-confidence mismatch:
  • If we can RE-LABEL it (move to its predicted_level cell for the same
    grade+topic) — do that. The cell becomes (class_level, topic, predicted_level).
  • Otherwise — DELETE it (or just report, depending on flags).

Low/medium confidence mismatches are NEVER touched by default; they only get
written to a report file so a human can review.

USAGE:
    # Dry run (default): no DB writes, only print what would happen.
    python scripts/relabel_or_delete_difficulty.py

    # Apply re-labels only (safe-ish):
    python scripts/relabel_or_delete_difficulty.py --apply --relabel-only

    # Apply both re-labels and deletions (full cleanup):
    python scripts/relabel_or_delete_difficulty.py --apply --delete

    # Only act on verdicts with confidence == high (default).
    # Add --include-medium to also act on medium-confidence ones.
    python scripts/relabel_or_delete_difficulty.py --apply --delete --include-medium
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB = os.path.join(ROOT, "instance", "formyla.db")
JSONL_PATH = os.path.join(ROOT, "scripts", "_validation", "difficulty.jsonl")
REPORT_PATH = os.path.join(ROOT, "scripts", "_validation",
                           "difficulty_apply_report.txt")


def load_verdicts() -> list[dict]:
    if not os.path.exists(JSONL_PATH):
        print(f"ERROR: {JSONL_PATH} not found. Run validate_difficulty_levels.py first.")
        sys.exit(1)
    out = []
    with open(JSONL_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj.get("id"), int):
                out.append(obj)
    # Deduplicate (last wins) in case of resumed runs.
    by_id = {o["id"]: o for o in out}
    return list(by_id.values())


def fetch_tasks(conn, ids):
    if not ids:
        return {}
    cur = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        f"SELECT id, class_level, difficulty_level, topic, task_text "
        f"FROM adaptive_tasks WHERE id IN ({placeholders})",
        list(ids),
    )
    return {r[0]: {
        "id": r[0], "class_level": r[1], "difficulty_level": r[2],
        "topic": r[3], "task_text": r[4],
    } for r in cur.fetchall()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually write to DB. Without it, dry-run only.")
    ap.add_argument("--delete", action="store_true",
                    help="Allow deletion when re-labeling is not possible.")
    ap.add_argument("--relabel-only", action="store_true",
                    help="Only re-label, never delete.")
    ap.add_argument("--include-medium", action="store_true",
                    help="Also act on medium-confidence verdicts "
                         "(default: high-only).")
    ap.add_argument("--max-delta", type=int, default=99,
                    help="Skip mismatches where |delta| > max_delta "
                         "(default: 99 = no cap)")
    args = ap.parse_args()

    if args.relabel_only and args.delete:
        print("ERROR: --relabel-only and --delete are mutually exclusive.")
        sys.exit(2)

    verdicts = load_verdicts()
    print(f"Loaded {len(verdicts)} verdicts from {JSONL_PATH}")

    # Filter to actionable mismatches
    allowed_conf = {"high"} | ({"medium"} if args.include_medium else set())
    actionable = [
        v for v in verdicts
        if v.get("verdict") in ("too_easy", "too_hard")
        and v.get("confidence") in allowed_conf
        and abs(v.get("delta", 0)) <= args.max_delta
    ]
    print(f"Actionable mismatches "
          f"(confidence in {sorted(allowed_conf)}): {len(actionable)}")

    if not actionable:
        print("Nothing to do.")
        return

    conn = sqlite3.connect(DB)
    tasks_map = fetch_tasks(conn, [v["id"] for v in actionable])

    # Pre-compute current cell occupancy: (class_level, topic, level) -> count
    cur = conn.cursor()
    cur.execute(
        "SELECT class_level, topic, difficulty_level, COUNT(*) "
        "FROM adaptive_tasks GROUP BY class_level, topic, difficulty_level"
    )
    occ = defaultdict(int)
    for cl, tp, lv, cnt in cur.fetchall():
        occ[(cl, tp, lv)] = cnt

    plan_relabel = []   # (id, old_level, new_level, task_dict)
    plan_delete = []    # (id, task_dict, verdict)
    skipped = []        # (id, reason)

    for v in actionable:
        t = tasks_map.get(v["id"])
        if not t:
            skipped.append((v["id"], "task no longer in DB"))
            continue
        new_lvl = v["predicted_level"]
        if new_lvl == t["difficulty_level"]:
            # Shouldn't happen because verdict said mismatch, but just in case.
            skipped.append((v["id"], "predicted == labeled"))
            continue
        if 1 <= new_lvl <= 7:
            plan_relabel.append((t["id"], t["difficulty_level"], new_lvl, t, v))
        else:
            plan_delete.append((t["id"], t, v))

    # Apply --relabel-only: convert any planned deletions to skipped
    if args.relabel_only:
        for d in plan_delete:
            skipped.append((d[0], "delete suppressed by --relabel-only"))
        plan_delete = []

    # Apply default: if --delete not set, drop deletions to skipped
    if not args.delete and not args.relabel_only:
        for d in plan_delete:
            skipped.append((d[0], "delete not enabled (use --delete)"))
        plan_delete = []

    print(f"\nPlan:")
    print(f"  re-label: {len(plan_relabel)}")
    print(f"  delete:   {len(plan_delete)}")
    print(f"  skipped:  {len(skipped)}")

    # Per-direction breakdown
    by_dir = defaultdict(int)
    for _, old, new, _, _ in plan_relabel:
        by_dir[(old, new)] += 1
    if by_dir:
        print("\nRe-label moves (old → new : count):")
        for (o, n), c in sorted(by_dir.items()):
            print(f"  L{o} → L{n} : {c}")

    # Write a human-readable report regardless of apply mode
    with open(REPORT_PATH, "w", encoding="utf-8") as rep:
        rep.write(f"Difficulty re-label / delete plan\n")
        rep.write(f"Apply mode: {args.apply}, delete={args.delete}, "
                  f"relabel-only={args.relabel_only}, "
                  f"include-medium={args.include_medium}\n\n")
        rep.write(f"=== RE-LABEL ({len(plan_relabel)}) ===\n")
        for tid, old, new, t, v in plan_relabel[:500]:
            rep.write(
                f"  id={tid} cl={t['class_level']} topic={t['topic']!r} "
                f"L{old} → L{new}  ({v.get('confidence')})\n"
                f"    reason: {v.get('reason')}\n"
                f"    text:   {(t.get('task_text') or '')[:160]}\n\n"
            )
        if len(plan_relabel) > 500:
            rep.write(f"  ... and {len(plan_relabel) - 500} more\n\n")
        rep.write(f"=== DELETE ({len(plan_delete)}) ===\n")
        for tid, t, v in plan_delete[:500]:
            rep.write(
                f"  id={tid} cl={t['class_level']} topic={t['topic']!r} "
                f"L{t['difficulty_level']} (predicted L{v['predicted_level']}) "
                f"({v.get('confidence')})\n"
                f"    reason: {v.get('reason')}\n"
                f"    text:   {(t.get('task_text') or '')[:160]}\n\n"
            )
        if len(plan_delete) > 500:
            rep.write(f"  ... and {len(plan_delete) - 500} more\n\n")
    print(f"\nWritten plan report: {REPORT_PATH}")

    if not args.apply:
        print("\nDRY-RUN: no DB changes. Re-run with --apply to commit.")
        conn.close()
        return

    # ---- APPLY ----
    print("\nAPPLYING changes to DB ...")
    cur = conn.cursor()
    n_rel = 0
    for tid, old, new, t, v in plan_relabel:
        cur.execute(
            "UPDATE adaptive_tasks SET difficulty_level = ? WHERE id = ?",
            (new, tid),
        )
        n_rel += 1
    n_del = 0
    for tid, t, v in plan_delete:
        cur.execute("DELETE FROM adaptive_tasks WHERE id = ?", (tid,))
        n_del += 1
    conn.commit()
    conn.close()
    print(f"  re-labeled: {n_rel}")
    print(f"  deleted:    {n_del}")
    print(f"  skipped:    {len(skipped)}")

    # Final cell occupancy snapshot
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM adaptive_tasks"
    )
    total = cur.fetchone()[0]
    print(f"\nDB now has {total} adaptive tasks.")
    conn.close()


if __name__ == "__main__":
    main()
