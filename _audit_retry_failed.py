#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Retry failed audit tasks (11 failed from initial 150-task run).

Loads existing results, re-runs only failed tasks with the fixed
safe_parse_json() that handles double-brace {{...}} responses, then
merges results and recomputes summary statistics.
"""

import json
import os
import sys
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from copy import deepcopy

sys.path.insert(0, os.path.dirname(__file__))

# Reuse the fixed safe_parse_json and audit_single_task from the main script
from _audit_150_pilot import (
    DeepSeekClient, DeepSeekAPIError,
    load_curated_bank, load_checkpoint,
    safe_parse_json, audit_single_task,
    LEVEL_RUBRIC, SYSTEM_PROMPT,
    CURATED_BANK, CHECKPOINT,
)

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "audit_150_results.json")
RETRY_LOG = os.path.join(os.path.dirname(__file__), "audit_retry_log.json")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_summary(results):
    """Recompute summary stats from results list."""
    passed = sum(1 for r in results if r.get("success") and r.get("audit_result", {}).get("overall") == "PASS")
    minor = sum(1 for r in results if r.get("success") and r["audit_result"].get("overall") == "MINOR")
    failed_audit = sum(1 for r in results if r.get("success") and r["audit_result"].get("overall") == "FAIL")
    api_fail = sum(1 for r in results if not r.get("success"))

    level_mismatches = []
    class_mismatches = []
    topic_mismatches = []
    cond_issues = []

    for r in results:
        if r.get("success") and r.get("audit_result"):
            ar = r["audit_result"]
            lm = ar.get("level_match", {})
            cm = ar.get("class_match", {})
            tm = ar.get("topic_match", {})
            cd = ar.get("condition_correctness", {})
            if lm.get("verdict") in ("MAJOR", "MINOR"):
                level_mismatches.append((r["task_index"], lm["verdict"], lm.get("reasoning", "")))
            if cm.get("verdict") in ("MAJOR", "MINOR"):
                class_mismatches.append((r["task_index"], cm["verdict"], cm.get("reasoning", "")))
            if tm.get("verdict") in ("MAJOR", "MINOR"):
                topic_mismatches.append((r["task_index"], tm["verdict"], tm.get("reasoning", "")))
            if cd.get("verdict") in ("MAJOR", "MINOR"):
                cond_issues.append((r["task_index"], cd["verdict"], cd.get("reasoning", "")))

    return {
        "total": len(results),
        "passed": passed,
        "minor": minor,
        "failed_audit": failed_audit,
        "api_failures": api_fail,
        "level_mismatches": len(level_mismatches),
        "class_mismatches": len(class_mismatches),
        "topic_mismatches": len(topic_mismatches),
        "condition_issues": len(cond_issues),
    }, level_mismatches, class_mismatches, topic_mismatches, cond_issues


def main():
    logger.info("=" * 60)
    logger.info("FORMYLA Pilot Audit — Retry Failed Tasks")
    logger.info("=" * 60)

    # 1. Load existing results
    if not os.path.exists(OUTPUT_FILE):
        logger.error(f"Results file not found: {OUTPUT_FILE}")
        sys.exit(1)

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        existing_data = json.load(f)

    existing_results = existing_data.get("results", [])
    logger.info(f"Loaded {len(existing_results)} existing results from {OUTPUT_FILE}")

    # 2. Find failed tasks
    failed_indices = [r["task_index"] for r in existing_results if not r.get("success")]
    successful_results = [r for r in existing_results if r.get("success")]

    logger.info(f"Found {len(failed_indices)} failed tasks to retry: {failed_indices}")
    logger.info(f"Already have {len(successful_results)} successful results")

    if not failed_indices:
        logger.info("No failed tasks to retry. Nothing to do.")
        return

    # 3. Load source data
    tasks = load_curated_bank(150)
    checkpoint = load_checkpoint()
    checkpoint_map = {}
    for idx, entry in checkpoint.items():
        if idx < 150:
            checkpoint_map[idx] = entry

    # 4. Init DeepSeek client
    client = DeepSeekClient()

    # 5. Re-run only failed tasks (up to 10 concurrent)
    retry_results = []
    print_lock = type('', (), {'__enter__': lambda s: None, '__exit__': lambda s, *a: None})()

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {}
        for idx in failed_indices:
            if idx < len(tasks):
                task = tasks[idx]
                cp_entry = checkpoint_map.get(idx)
                future = executor.submit(audit_single_task, client, task, idx, cp_entry)
                future_to_idx[future] = idx
            else:
                logger.warning(f"Task index {idx} out of range (tasks len={len(tasks)})")

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                retry_results.append(result)
                status = "✓" if result.get("success") else "✗"
                overall = result.get("audit_result", {}).get("overall", "?") if result.get("success") else "FAIL"
                logger.info(f"[{idx}] {status} overall={overall}, success={result['success']}")
            except Exception as e:
                logger.error(f"[{idx}] Exception: {e}")
                retry_results.append({
                    "task_index": idx,
                    "success": False,
                    "error": str(e),
                })

    # 6. Merge retry results into existing successful results
    #    Build a dict by task_index, retry overwrites existing failed entries
    merged = {r["task_index"]: r for r in successful_results}
    for r in retry_results:
        merged[r["task_index"]] = r

    merged_results = [merged[i] for i in range(len(tasks)) if i in merged]
    merged_results.sort(key=lambda r: r.get("task_index", 0))

    # 7. Recompute summary
    summary_stats, level_mm, class_mm, topic_mm, cond_iss = compute_summary(merged_results)

    # Count retry results
    retry_success = sum(1 for r in retry_results if r.get("success"))
    retry_fail = sum(1 for r in retry_results if not r.get("success"))

    # 8. Build output preserving existing structure
    output = {
        "audit_timestamp": existing_data.get("audit_timestamp", ""),
        "retry_timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-reasoner",
        "summary": summary_stats,
        "level_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in level_mm],
        "class_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in class_mm],
        "topic_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in topic_mm],
        "condition_issues": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in cond_iss],
        "retry_info": {
            "failed_before": len(failed_indices),
            "retried": len(retry_results),
            "retry_succeeded": retry_success,
            "retry_failed": retry_fail,
            "still_failing": [r["task_index"] for r in retry_results if not r.get("success")],
        },
        "results": merged_results,
    }

    # 9. Save merged results
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 10. Save retry log
    retry_log = {
        "retry_timestamp": output["retry_timestamp"],
        "failed_before": failed_indices,
        "retry_results": retry_results,
    }
    with open(RETRY_LOG, "w", encoding="utf-8") as f:
        json.dump(retry_log, f, ensure_ascii=False, indent=2)

    # Print summary
    logger.info("=" * 60)
    logger.info(f"RETRY COMPLETE")
    logger.info(f"  Failed before:          {len(failed_indices)}")
    logger.info(f"  Retry succeeded:        {retry_success}")
    logger.info(f"  Retry failed:           {retry_fail}")
    if retry_fail > 0:
        still_failing = [r["task_index"] for r in retry_results if not r.get("success")]
        logger.info(f"  Still failing indices:  {still_failing}")
    logger.info(f"")
    logger.info(f"FINAL SUMMARY (merged {len(merged_results)} tasks):")
    logger.info(f"  PASS:            {summary_stats['passed']}")
    logger.info(f"  MINOR:           {summary_stats['minor']}")
    logger.info(f"  FAIL (audit):    {summary_stats['failed_audit']}")
    logger.info(f"  FAIL (API):      {summary_stats['api_failures']}")
    logger.info(f"  Level mism.:     {summary_stats['level_mismatches']}")
    logger.info(f"  Class mism.:     {summary_stats['class_mismatches']}")
    logger.info(f"  Topic mism.:     {summary_stats['topic_mismatches']}")
    logger.info(f"  Condition iss.:  {summary_stats['condition_issues']}")
    logger.info(f"Results saved to: {OUTPUT_FILE}")
    logger.info(f"Retry log saved to: {RETRY_LOG}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
