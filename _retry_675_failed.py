#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retry 28 network-failed tasks from _regenerated_675_tasks.json.

Pipeline:
  1. Load _regenerated_675_tasks.json (509 entries: 481 OK + 28 failed)
  2. Extract the 28 entries where success == False
  3. For each failed entry, call regenerate_single_task() from _regenerate_675_failed.py
  4. Patch successful results back into the results list
  5. Update summary counts
  6. Save updated _regenerated_675_tasks.json

Usage:
    python _retry_675_failed.py
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from _regenerate_675_failed import regenerate_single_task, build_output
from ai.deepseek_client import DeepSeekClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Paths ---
REGENERATED_FILE = "_regenerated_675_tasks.json"
MAX_RETRIES_PER_TASK = 3
DELAY_BETWEEN_RETRIES = 3  # seconds


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    logger.info("=" * 60)
    logger.info("RETRY 28 NETWORK-FAILED TASKS")
    logger.info("=" * 60)

    # 1. Load regenerated output
    logger.info(f"Loading: {REGENERATED_FILE}")
    regen = load_json(REGENERATED_FILE)
    results = regen.get("results", [])
    summary = regen.get("summary", {})

    total = len(results)
    successful = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))
    logger.info(f"  Total entries: {total}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")

    if failed == 0:
        logger.info("No failed tasks to retry. Done.")
        return

    # 2. Extract failed entries
    failed_indices = [i for i, r in enumerate(results) if not r.get("success")]
    logger.info(f"Found {len(failed_indices)} failed tasks to retry")

    # 3. Initialize client
    client = DeepSeekClient()

    # 4. Retry each failed task
    retried = 0
    recovered = 0
    for idx_in_list in failed_indices:
        entry = results[idx_in_list]
        task_index = entry.get("task_index", "?")
        original_id = entry.get("original_id", "?")
        source_task = entry.get("source_task", {})
        audit_record = entry.get("audit_record", {})

        logger.info(f"  [{idx_in_list}] Retrying task_index={task_index} (oid={original_id})...")

        for attempt in range(1, MAX_RETRIES_PER_TASK + 1):
            logger.info(f"    Attempt {attempt}/{MAX_RETRIES_PER_TASK}")
            time.sleep(DELAY_BETWEEN_RETRIES)  # delay before each attempt

            result = regenerate_single_task(client, audit_record, source_task, idx_in_list)

            if result.get("success"):
                # Patch into results list
                results[idx_in_list] = result
                recovered += 1
                logger.info(f"    -> RECOVERED on attempt {attempt}")
                break
            else:
                error = result.get("error", "unknown")
                logger.warning(f"    -> Still failed: {error[:120]}")
                if attempt < MAX_RETRIES_PER_TASK:
                    logger.info(f"    Waiting {DELAY_BETWEEN_RETRIES}s before next attempt...")

        retried += 1

        # Save checkpoint after every 5 tasks
        if retried % 5 == 0:
            checkpoint_output = build_output(results, summary.get("total_failed_audit", 509), in_progress=True)
            save_json(REGENERATED_FILE, checkpoint_output)
            logger.info(f"  Checkpoint saved after {retried} retries")

    # 5. Build final output with updated summary
    logger.info(f"Retry complete: {recovered}/{retried} recovered")

    # Update results and summary in regen dict
    regen["results"] = results
    regen["summary"]["successfully_regenerated"] = sum(1 for r in results if r.get("success"))
    regen["summary"]["still_failed"] = sum(1 for r in results if not r.get("success"))
    regen["retry_timestamp"] = datetime.now(timezone.utc).isoformat()
    regen["retry_recovered"] = recovered
    regen["retry_attempted"] = retried

    # 6. Save
    logger.info(f"Saving updated {REGENERATED_FILE}...")
    save_json(REGENERATED_FILE, regen)

    logger.info("=" * 60)
    logger.info("RETRY COMPLETE")
    logger.info(f"  Total entries:     {len(results)}")
    logger.info(f"  Successful:        {regen['summary']['successfully_regenerated']}")
    logger.info(f"  Still failed:      {regen['summary']['still_failed']}")
    logger.info(f"  Recovered this run: {recovered}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
