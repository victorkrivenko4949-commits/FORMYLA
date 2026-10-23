#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merge 675 regenerated tasks back into the curated bank.

Pipeline:
  1. Load curated_bank_L1_L5_pre_live.json (674 tasks with original_id, task_text)
  2. Load _regenerated_675_tasks.json (481 successful + 28 failed)
  3. For each successful regeneration, find matching curated bank entry by original_id
  4. Apply fixed_task fields (statement, answer, solution, level, grade, topic)
  5. Save updated curated bank with fixed fields added

Usage:
    python _merge_675_into_curated.py
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Paths ---
CURATED_BANK = r"c:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\runs\selection_1080_20260712_134037\curated_bank_L1_L5_pre_live.json"
REGENERATED = "_regenerated_675_tasks.json"
OUTPUT_FILE = "curated_bank_L1_L5_fixed.json"
BACKUP_DIR = "backups"


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_curated():
    """Create a timestamped backup of the curated bank."""
    Path(BACKUP_DIR).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(BACKUP_DIR) / f"curated_bank_before_merge_{timestamp}.json"
    shutil.copy2(CURATED_BANK, backup_path)
    logger.info(f"Backup saved: {backup_path}")
    return backup_path


def build_curated_index(curated: list) -> dict:
    """Build {original_id: index_in_list} mapping."""
    idx = {}
    for i, task in enumerate(curated):
        oid = task.get("original_id")
        if oid:
            idx[oid] = i
    return idx


def main():
    logger.info("=" * 60)
    logger.info("MERGE 675 REGENERATED TASKS INTO CURATED BANK")
    logger.info("=" * 60)

    # 1. Backup
    backup_curated()

    # 2. Load curated bank
    logger.info(f"Loading curated bank: {CURATED_BANK}")
    curated = load_json(CURATED_BANK)
    logger.info(f"  Total curated tasks: {len(curated)}")

    # 3. Build index
    curated_idx = build_curated_index(curated)
    logger.info(f"  Index has {len(curated_idx)} entries")

    # 4. Load regenerated tasks
    logger.info(f"Loading regenerated tasks: {REGENERATED}")
    regen = load_json(REGENERATED)
    results = regen.get("results", [])
    summary = regen.get("summary", {})
    logger.info(f"  Successfully regenerated: {summary.get('successfully_regenerated')}")
    logger.info(f"  Still failed: {summary.get('still_failed')}")

    # 5. Apply successful regenerations
    merged = 0
    not_found = 0
    already_merged = 0
    for res in results:
        if not res.get("success"):
            continue
        fixed = res.get("fixed_task", {})
        if not fixed:
            continue
        original_id = res.get("original_id", "")
        if not original_id:
            continue
        idx = curated_idx.get(original_id)
        if idx is None:
            logger.warning(f"  original_id {original_id} not found in curated bank")
            not_found += 1
            continue

        task = curated[idx]
        # Check if already merged
        if task.get("fixed_by_ai"):
            already_merged += 1
            continue

        # Apply fixed fields
        for field in ["statement", "answer", "solution", "level", "grade", "topic"]:
            if field in fixed:
                task[field] = fixed[field]
        task["fixed_by_ai"] = True
        task["fix_timestamp"] = datetime.now(timezone.utc).isoformat()
        task["changes_made"] = res.get("changes_made", [])
        merged += 1

    # 6. Save
    logger.info(f"  Merged: {merged} tasks")
    logger.info(f"  Not found: {not_found}")
    logger.info(f"  Already merged: {already_merged}")
    logger.info(f"Saving to: {OUTPUT_FILE}")
    save_json(OUTPUT_FILE, curated)
    logger.info("Done!")


if __name__ == "__main__":
    main()
