#!/usr/bin/env python
"""Merge regenerated tasks back into adaptive_full_9120_fixed.json.

Takes successfully regenerated tasks from _regenerated_tasks.json
and applies them to the source database, replacing original fields.
Creates a backup before modifying.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SOURCE_DB = "adaptive_data/adaptive_full_9120_fixed.json"
REGENERATED = "_regenerated_tasks.json"
BACKUP_DIR = "backups"


def load_json(path: str) -> list | dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: list | dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_source():
    """Create a timestamped backup of the source DB."""
    Path(BACKUP_DIR).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(BACKUP_DIR) / f"adaptive_full_9120_fixed_before_merge_{timestamp}.json"
    shutil.copy2(SOURCE_DB, backup_path)
    logger.info(f"Backup saved: {backup_path}")
    return backup_path


def build_id_index(db: list) -> dict:
    """Build {id: index_in_list} mapping."""
    idx = {}
    for i, task in enumerate(db):
        tid = task.get("id")
        if tid is not None:
            idx[tid] = i
    return idx


def merge_regenerated(db: list, regen_results: list, id_index: dict) -> dict:
    """Apply fixed_task fields back to DB entries. Returns stats."""
    stats = {
        "total_regen_success": len(regen_results),
        "found_in_db": 0,
        "not_found_in_db": 0,
        "fields_updated": 0,
        "skipped_unchanged": 0,
    }

    # Fields mapping: fixed_task_key -> db_task_key
    field_map = {
        "statement": "statement",
        "answer": "answer",
        "solution": "solution",
        "level": "level",
        "grade": "grade",
        "topic": "topic",
    }

    for result in regen_results:
        if not result.get("success"):
            continue

        source_id = result.get("source_id")
        fixed = result.get("fixed_task", {})

        if source_id not in id_index:
            stats["not_found_in_db"] += 1
            logger.warning(f"source_id={source_id} not found in DB, skipping")
            continue

        db_idx = id_index[source_id]
        task = db[db_idx]

        # Apply each field if it differs
        changed = False
        for fixed_key, db_key in field_map.items():
            if fixed_key not in fixed:
                continue
            new_val = fixed[fixed_key]
            old_val = task.get(db_key)

            # Normalize for comparison (ensure same type for level)
            if isinstance(new_val, int) and isinstance(old_val, (int, float)):
                if int(new_val) == int(old_val):
                    continue
            elif new_val == old_val:
                continue

            task[db_key] = new_val
            changed = True
            stats["fields_updated"] += 1

        if changed:
            stats["found_in_db"] += 1
        else:
            stats["skipped_unchanged"] += 1

    return stats


def main():
    logger.info("=" * 60)
    logger.info("MERGE REGENERATED TASKS INTO SOURCE DB")
    logger.info("=" * 60)

    # Load data
    logger.info(f"Loading source DB: {SOURCE_DB}")
    db = load_json(SOURCE_DB)
    logger.info(f"  Total tasks in DB: {len(db)}")

    logger.info(f"Loading regenerated tasks: {REGENERATED}")
    regen = load_json(REGENERATED)
    results = regen.get("results", [])
    summary = regen.get("summary", {})
    logger.info(f"  Successfully regenerated: {summary.get('successfully_regenerated')}")
    logger.info(f"  Still failed: {summary.get('still_failed')}")
    logger.info(f"  Total results entries: {len(results)}")

    # Filter only successful
    successful = [r for r in results if r.get("success")]
    logger.info(f"  Successful entries to merge: {len(successful)}")

    # Build index
    id_index = build_id_index(db)
    logger.info(f"  DB id index built: {len(id_index)} entries")

    # Create backup
    backup_path = backup_source()
    logger.info(f"Backup created at: {backup_path}")

    # Merge
    stats = merge_regenerated(db, successful, id_index)

    # Summary
    logger.info("=" * 60)
    logger.info("MERGE STATS")
    logger.info(f"  Total successful regenerations: {stats['total_regen_success']}")
    logger.info(f"  Found in DB and updated: {stats['found_in_db']}")
    logger.info(f"  Not found in DB (skipped):  {stats['not_found_in_db']}")
    logger.info(f"  Already matching (skipped):  {stats['skipped_unchanged']}")
    logger.info(f"  Individual fields updated:  {stats['fields_updated']}")

    # Save updated DB
    logger.info(f"Saving updated DB to {SOURCE_DB}...")
    save_json(SOURCE_DB, db)
    logger.info("Done!")

    # Final counts
    logger.info("=" * 60)
    logger.info("FINAL TASK COUNTS (L1-L3 in adaptive_full_9120_fixed.json)")
    from collections import Counter
    levels = Counter(t.get("level") for t in db if t.get("level") in (1, 2, 3))
    logger.info(f"  Level 1: {levels.get(1, 0)}")
    logger.info(f"  Level 2: {levels.get(2, 0)}")
    logger.info(f"  Level 3: {levels.get(3, 0)}")
    logger.info(f"  Total L1-L3: {sum(levels.values())}")


if __name__ == "__main__":
    main()
