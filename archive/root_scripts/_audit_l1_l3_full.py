#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Параллельный аудит базы L1-L3 (5114 задач) через DeepSeek-reasoner, 10 потоков.

Источник: adaptive_data/adaptive_full_9120_fixed.json (фильтр level ∈ {1,2,3})
Аудитор: deepseek-reasoner, 10 параллельных потоков, автоматический retry.

Запуск:
    python _audit_l1_l3_full.py
"""

import json
import os
import sys
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# Import safe_parse_json and SYSTEM_PROMPT from the pilot module
sys.path.insert(0, os.path.dirname(__file__))
from _audit_150_pilot import safe_parse_json, SYSTEM_PROMPT, LEVEL_RUBRIC, logger
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────
ADAPTIVE_DB = "adaptive_data/adaptive_full_9120_fixed.json"
OUTPUT_FILE = "audit_l1_l3_results.json"
FAILED_LOG = "audit_l1_l3_failed.json"
RETRY_CHECKPOINT = "audit_l1_l3_retry_checkpoint.json"
print_lock = threading.Lock()


def load_l1_l3_tasks():
    """Load tasks with level 1, 2, or 3 from adaptive database."""
    with open(ADAPTIVE_DB, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = []
    skipped = 0
    for item in data:
        level = item.get("level")
        if level in (1, 2, 3):
            # Map fields to audit format
            task = {
                "task_text": item.get("statement", ""),
                "class_level": item.get("grade", "?"),
                "target_level": f"L{level}",
                "topic": item.get("topic", "?"),
                "source_id": item.get("id", "?"),
                "subject": item.get("subject", "?"),
                "level_int": level,
            }
            tasks.append(task)
        else:
            skipped += 1

    logger.info(f"Loaded {len(tasks)} L1-L3 tasks (skipped {skipped} L4+)")
    return tasks


def audit_single_task(client: DeepSeekClient, task: dict, task_index: int) -> dict:
    """Audit a single task via DeepSeek-reasoner."""
    task_text = task.get("task_text", "")
    class_level = task.get("class_level", "?")
    target_level = task.get("target_level", "?")
    topic = task.get("topic", "?")
    source_id = task.get("source_id", "?")
    subject = task.get("subject", "?")

    user_prompt = f"""Проверь задачу на соответствие всем критериям.

## Данные задачи:
- Условие: {task_text}
- Заявленный уровень: {target_level}
- Класс: {class_level}
- Тема: {topic}

## Инструкция:
1. Проанализируй условие задачи.
2. Определи, какому уровню по рубрике L1-L5 она соответствует.
3. Определи, для какого класса она подходит.
4. Определи, к какой теме она относится.
5. Проверь корректность условия.
6. Сравни с заявленными: уровень={target_level}, класс={class_level}, тема={topic}.
7. Выдай структурированный вердикт в JSON-формате, как указано в system prompt.
"""

    try:
        logger.info(f"[{task_index}] Sending to DeepSeek-reasoner: "
                     f"level={target_level}, class={class_level}, "
                     f"topic={topic[:30]}...")

        content = client.generate_with_reasoning(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=4096,
            timeout=300,
            return_reasoning=False,
        )

        audit_result = safe_parse_json(content)

        logger.info(f"[{task_index}] OK: overall={audit_result.get('overall', '?')}")
        return {
            "task_index": task_index,
            "source_id": source_id,
            "task_text": task_text,
            "class_level": class_level,
            "target_level": target_level,
            "topic": topic,
            "subject": subject,
            "audit_result": audit_result,
            "success": True,
            "error": None,
        }

    except (DeepSeekAPIError, json.JSONDecodeError, ValueError, Exception) as e:
        logger.error(f"[{task_index}] FAIL: {e}")
        return {
            "task_index": task_index,
            "source_id": source_id,
            "task_text": task_text,
            "class_level": class_level,
            "target_level": target_level,
            "topic": topic,
            "subject": subject,
            "audit_result": None,
            "success": False,
            "error": str(e),
        }


def retry_failed(client: DeepSeekClient, failed_results: list, max_retries: int = 3) -> list:
    """Retry all failed tasks up to max_retries times."""
    retried = []
    for r in failed_results:
        task_index = r["task_index"]
        task = {
            "task_text": r.get("task_text", ""),
            "class_level": r.get("class_level", "?"),
            "target_level": r.get("target_level", "?"),
            "topic": r.get("topic", "?"),
            "source_id": r.get("source_id", "?"),
            "subject": r.get("subject", "?"),
        }
        for attempt in range(1, max_retries + 1):
            logger.info(f"[{task_index}] Retry attempt {attempt}/{max_retries}...")
            result = audit_single_task(client, task, task_index)
            if result["success"]:
                retried.append(result)
                break
            if attempt < max_retries:
                time.sleep(5 * attempt)  # Exponential backoff
        else:
            # All retries exhausted
            retried.append(r)
    return retried


def main():
    logger.info("=" * 60)
    logger.info("FORMYLA L1-L3 Full Audit — DeepSeek-reasoner, 10 threads")
    logger.info("=" * 60)

    # Load L1-L3 tasks
    tasks = load_l1_l3_tasks()
    n_total = len(tasks)

    # Init client
    client = DeepSeekClient()

    # ─── Phase 1: Initial audit ────────────────────────────────────
    results_batch = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {}
        for i in range(n_total):
            future = executor.submit(audit_single_task, client, tasks[i], i)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results_batch.append(result)
                overall = result.get("audit_result", {}).get("overall", "?") if result.get("success") else "FAIL"
                with print_lock:
                    logger.info(f"[{idx}] done: overall={overall}, success={result['success']}")
            except Exception as e:
                with print_lock:
                    logger.error(f"[{idx}] Exception: {e}")
                results_batch.append({
                    "task_index": idx,
                    "success": False,
                    "error": str(e),
                })

    # Sort
    results_batch.sort(key=lambda r: r.get("task_index", 0))

    # ─── Phase 2: Auto-retry failed ────────────────────────────────
    failed = [r for r in results_batch if not r.get("success")]
    if failed:
        logger.info(f"Retrying {len(failed)} failed tasks...")
        retried = retry_failed(client, failed, max_retries=3)
        # Merge retried back
        retry_map = {r["task_index"]: r for r in retried}
        final_results = []
        for r in results_batch:
            if r["task_index"] in retry_map and retry_map[r["task_index"]]["success"]:
                final_results.append(retry_map[r["task_index"]])
            else:
                final_results.append(r)
        results_batch = final_results
        # Sort again
        results_batch.sort(key=lambda r: r.get("task_index", 0))

    # ─── Summary ──────────────────────────────────────────────────
    passed = sum(1 for r in results_batch if r.get("success") and r["audit_result"].get("overall") == "PASS")
    minor = sum(1 for r in results_batch if r.get("success") and r["audit_result"].get("overall") == "MINOR")
    failed_audit = sum(1 for r in results_batch if r.get("success") and r["audit_result"].get("overall") == "FAIL")
    api_fail = sum(1 for r in results_batch if not r.get("success"))

    level_mismatches = []
    class_mismatches = []
    topic_mismatches = []
    cond_issues = []

    for r in results_batch:
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

    summary = {
        "total": n_total,
        "passed": passed,
        "minor": minor,
        "failed_audit": failed_audit,
        "api_failures": api_fail,
        "level_mismatches": len(level_mismatches),
        "class_mismatches": len(class_mismatches),
        "topic_mismatches": len(topic_mismatches),
        "condition_issues": len(cond_issues),
    }

    output = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-reasoner",
        "source_db": ADAPTIVE_DB,
        "summary": summary,
        "level_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in level_mismatches],
        "class_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in class_mismatches],
        "topic_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in topic_mismatches],
        "condition_issues": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in cond_issues],
        "results": results_batch,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Also save failed separately for regeneration
    truly_failed = [r for r in results_batch if not r.get("success") or r.get("audit_result", {}).get("overall") in ("FAIL", "MINOR")]
    failed_output = {
        "audit_timestamp": output["audit_timestamp"],
        "model": "deepseek-reasoner",
        "source_db": ADAPTIVE_DB,
        "summary": summary,
        "failed_count": len(truly_failed),
        "total_count": n_total,
        "failed_tasks": truly_failed,
    }
    with open(FAILED_LOG, "w", encoding="utf-8") as f:
        json.dump(failed_output, f, ensure_ascii=False, indent=2)

    # ─── Print summary ──────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("AUDIT COMPLETE")
    logger.info(f"  Total:     {n_total}")
    logger.info(f"  Passed:    {passed}")
    logger.info(f"  Minor:     {minor}")
    logger.info(f"  Failed:    {failed_audit}")
    logger.info(f"  API fail:  {api_fail}")
    logger.info(f"  Level mismatches:  {len(level_mismatches)}")
    logger.info(f"  Class mismatches:  {len(class_mismatches)}")
    logger.info(f"  Topic mismatches:  {len(topic_mismatches)}")
    logger.info(f"  Condition issues:  {len(cond_issues)}")
    logger.info(f"  Results saved to:  {OUTPUT_FILE}")
    logger.info(f"  Failed log saved to: {FAILED_LOG}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
