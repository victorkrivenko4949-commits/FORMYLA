#!/usr/bin/env python
"""Fix audit fields for the 4 G2|L1 fill tasks that have None audit fields.

Sets the same deterministic_pre_live audit values as all other L1-L3 tasks.
Creates a backup before modification.
"""
import json
import datetime
from pathlib import Path

BANK_PATH = "curated_bank_L1_L5_fixed.json"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

FILL_IDS = {"SEL1080-1066", "SEL1080-1067", "SEL1080-1068", "SEL1080-1069"}

# Standard audit values used by all other L1-L3 tasks
STANDARD_AUDIT = {
    "audit_mode": "deterministic_pre_live",
    "decision_status": "candidate",
    "final_court_status": "pending_live_audit",
    "evidence_source": "deterministic_rules",
    "confidence": "medium",  # conservative for AI-filled tasks
}


def main():
    # Load bank
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)

    total = len(bank)
    print(f"Loaded {total} tasks from {BANK_PATH}")

    # Create backup
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"curated_bank_before_fix_g2_l1_audit_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    print(f"Backup saved to {backup_path}")

    # Find and fix the 4 G2|L1 tasks
    found = []
    modified_count = 0
    for t in bank:
        oid = t.get("original_id", "")
        if oid in FILL_IDS:
            found.append(oid)
            print(f"\n  Found: {oid}  grade={t.get('grade')}  level={t.get('level')}")

            # Check current state
            old_audit = t.get("audit_mode")
            old_decision = t.get("decision_status")
            old_court = t.get("final_court_status")
            old_evidence = t.get("evidence_source")
            old_pending = t.get("pending_live_audit")

            print(f"    Before: audit_mode={old_audit}, decision_status={old_decision}, "
                  f"final_court_status={old_court}, evidence_source={old_evidence}, "
                  f"pending_live_audit={old_pending}")

            # Set standard audit fields
            for key, val in STANDARD_AUDIT.items():
                t[key] = val

            # Remove the temporary pending_live_audit flag if present
            if "pending_live_audit" in t:
                del t["pending_live_audit"]

            # Verify
            print(f"    After:  audit_mode={t['audit_mode']}, decision_status={t['decision_status']}, "
                  f"final_court_status={t['final_court_status']}, evidence_source={t['evidence_source']}, "
                  f"pending_live_audit={t.get('pending_live_audit', '<removed>')}")

            modified_count += 1

    # Summary
    missing = FILL_IDS - set(found)
    if missing:
        print(f"\nWARNING: {len(missing)} tasks not found in bank: {missing}")
    else:
        print(f"\nAll 4 G2|L1 fill tasks found and processed.")

    if modified_count == 0:
        print("No tasks modified. Exiting without saving.")
        return

    # Save updated bank
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"\nSaved updated bank to {BANK_PATH}")
    print(f"Total tasks: {total}")
    print(f"Tasks modified: {modified_count}")

    # Write change log
    log_path = f"_fix_g2_l1_audit_log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"G2|L1 Audit Field Fix Log\n")
        f.write(f"=========================\n")
        f.write(f"Date: {ts}\n")
        f.write(f"Bank: {BANK_PATH}\n")
        f.write(f"Total tasks: {total}\n")
        f.write(f"Tasks modified: {modified_count}\n\n")
        f.write(f"Standard audit values applied:\n")
        for k, v in STANDARD_AUDIT.items():
            f.write(f"  {k}: {v}\n")
        f.write(f"\nTasks modified:\n")
        for oid in sorted(found):
            f.write(f"  {oid}\n")

    print(f"Change log saved to {log_path}")


if __name__ == "__main__":
    main()
