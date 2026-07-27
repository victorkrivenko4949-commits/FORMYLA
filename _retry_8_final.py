#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retry regeneration for the 8 permanently failed tasks from _regenerated_675_tasks.json.

These 8 tasks failed due to NameResolutionError (DNS issue) that has since resolved.
However, deepseek-reasoner model persistently returns "empty content field" errors,
so we use generate() (deepseek-chat) instead of generate_with_reasoning().

Usage:
    python _retry_8_final.py
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
from _audit_150_pilot import safe_parse_json
from _regenerate_675_failed import REGENERATE_SYSTEM_PROMPT, build_regeneration_prompt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

REGENERATED_FILE = "_regenerated_675_tasks.json"
OUTPUT_FILE = "_retry_8_final_results.json"

CURATED_BANK = r"c:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\runs\selection_1080_20260712_134037\curated_bank_L1_L5_pre_live.json"

# Using generate() (deepseek-chat) instead of generate_with_reasoning() (deepseek-reasoner)
# because reasoner model persistently returns "empty content field" errors.
# deepseek-chat is more reliable for structured JSON output.
CHAT_TIMEOUT = 180
CHAT_MAX_TOKENS = 4096
MAX_ATTEMPTS = 3
CHAT_TEMPERATURE = 0.3


def get_failed_tasks(regenerated: dict) -> list:
    """Extract the 8 tasks that failed (success=false)."""
    results = regenerated.get("results", [])
    failed = [r for r in results if not r.get("success")]
    logger.info(f"Found {len(failed)} failed tasks out of {len(results)} total")
    return failed


def regenerate_single_task(client: DeepSeekClient, task_entry: dict) -> dict:
    """
    Attempt regeneration of a single failed task using deepseek-chat (generate).

    Returns:
        dict with keys: success, original_id, task_index, fixed_task, changes_made, error
    """
    source_task = task_entry.get("source_task", {})
    audit_record = task_entry.get("audit_record", {})
    original_id = task_entry.get("original_id", "?")
    task_index = task_entry.get("task_index", "?")

    prompt = build_regeneration_prompt(audit_record, source_task)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            logger.info(f"[{original_id}] Attempt {attempt+1}/{MAX_ATTEMPTS} (deepseek-chat)...")
            response = client.generate(
                prompt=prompt,
                system_prompt=REGENERATE_SYSTEM_PROMPT,
                temperature=CHAT_TEMPERATURE,
                max_tokens=CHAT_MAX_TOKENS,
            )

            parsed = safe_parse_json(response)
            if not parsed:
                raise ValueError("safe_parse_json returned empty dict")

            fixed_task = parsed.get("fixed_task", {})
            changes_made = parsed.get("changes_made", [])

            if not fixed_task.get("statement"):
                raise ValueError("fixed_task missing 'statement'")

            logger.info(f"[{original_id}] SUCCESS")
            return {
                "success": True,
                "original_id": original_id,
                "task_index": task_index,
                "source_task": source_task,
                "audit_record": audit_record,
                "fixed_task": fixed_task,
                "changes_made": changes_made,
                "error": None,
            }

        except (DeepSeekAPIError, ValueError, Exception) as e:
            last_error = str(e)
            logger.warning(f"[{original_id}] Attempt {attempt+1} failed: {type(e).__name__}: {str(e)[:150]}")
            if attempt < MAX_ATTEMPTS - 1:
                wait = 5 * (2 ** attempt)
                logger.info(f"[{original_id}] Waiting {wait}s before retry...")
                time.sleep(wait)

    logger.error(f"[{original_id}] ALL {MAX_ATTEMPTS} ATTEMPTS FAILED: {last_error}")
    return {
        "success": False,
        "original_id": original_id,
        "task_index": task_index,
        "source_task": source_task,
        "audit_record": audit_record,
        "fixed_task": None,
        "changes_made": None,
        "error": last_error,
    }


def main():
    logger.info("=" * 60)
    logger.info("RETRY 8 FINAL - Regenerating 8 permanently failed tasks (deepseek-chat)")
    logger.info("=" * 60)

    # Load regenerated tasks data
    logger.info(f"Loading {REGENERATED_FILE}...")
    with open(REGENERATED_FILE, "r", encoding="utf-8") as f:
        regenerated = json.load(f)

    failed_tasks = get_failed_tasks(regenerated)

    if not failed_tasks:
        logger.info("No failed tasks found! Nothing to retry.")
        return

    original_ids = [t.get("original_id", "?") for t in failed_tasks]
    logger.info(f"Tasks to retry: {original_ids}")

    # Init DeepSeek client
    client = DeepSeekClient()
    # Override timeout for chat model to be safe for complex regeneration
    client.timeout = CHAT_TIMEOUT

    # Process each task sequentially (to be conservative with API)
    results = []
    successes = 0
    failures = 0

    for i, task_entry in enumerate(failed_tasks):
        orig_id = task_entry.get("original_id", "?")
        logger.info(f"\n--- [{i+1}/{len(failed_tasks)}] Processing {orig_id} ---")

        result = regenerate_single_task(client, task_entry)
        results.append(result)

        if result["success"]:
            successes += 1
        else:
            failures += 1

        # Save intermediate checkpoint after each task
        checkpoint = {
            "summary": {
                "total": len(failed_tasks),
                "processed": i + 1,
                "successful": successes,
                "failed": failures,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "results": results,
        }
        tmp = OUTPUT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OUTPUT_FILE)
        logger.info(f"Checkpoint saved ({i+1}/{len(failed_tasks)} processed)")

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info(f"FINAL RESULTS: {successes} succeeded, {failures} failed out of {len(failed_tasks)}")
    logger.info("=" * 60)

    final = {
        "summary": {
            "total": len(failed_tasks),
            "successful": successes,
            "failed": failures,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    logger.info(f"Final results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
