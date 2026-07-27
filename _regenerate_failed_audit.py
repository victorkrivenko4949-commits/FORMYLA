#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Regenerate tasks that failed L1-L3 audit using DeepSeek-reasoner.

Pipeline:
  1. Load audit_l1_l3_failed.json (output from _audit_l1_l3_full.py)
  2. For each failed task, send original + audit feedback to DeepSeek-reasoner
  3. Request a corrected/fixed version of the task
  4. Save regenerated tasks to _regenerated_tasks.json

Usage:
    python _regenerate_failed_audit.py
"""

import json
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from _audit_150_pilot import safe_parse_json, LEVEL_RUBRIC
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────
FAILED_LOG = "audit_l1_l3_failed.json"
OUTPUT_FILE = "_regenerated_tasks.json"
ADAPTIVE_DB = "adaptive_data/adaptive_full_9120_fixed.json"

MAX_WORKERS = 10
MAX_RETRIES = 3


def load_failed_tasks() -> list:
    """Load failed tasks from audit output."""
    with open(FAILED_LOG, "r", encoding="utf-8") as f:
        data = json.load(f)
    tasks = data.get("failed_tasks", [])
    logger.info(f"Loaded {len(tasks)} failed tasks from {FAILED_LOG}")
    return tasks


def load_original_task(source_id) -> Optional[dict]:
    """Load original task from adaptive database by source_id."""
    with open(ADAPTIVE_DB, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        if item.get("id") == source_id:
            return item
    return None


REGENERATE_SYSTEM_PROMPT = f"""Ты — эксперт-методист по созданию математических задач для системы адаптивного обучения Формула.

Твоя задача — проанализировать задачу, которая не прошла аудит, и исправить её в соответствии с замечаниями аудитора.

## Рубрика уровней (L1-L5):
{LEVEL_RUBRIC}

## Требования к задаче:
1. Условие должно быть логически непротиворечивым, полным и однозначным.
2. Уровень сложности должен строго соответствовать заявленному L1, L2 или L3.
3. Задача должна соответствовать указанному классу школьной программы.
4. Тема должна быть указана корректно.
5. Если в задаче требуется рисунок или график — условие должно быть самодостаточным.
6. Ответ и решение должны быть приложены.

## Формат ответа:
Ты ДОЛЖЕН ответить строго в следующем JSON-формате (без markdown, без обрамления):

{{{{"fixed_task":{{"statement":"...","answer":"...","solution":"...","level":1,"grade":5,"topic":"..."}},"changes_made":["...","..."],"reasoning":"..."}}}}

Где:
- fixed_task: исправленная версия задачи (statement — условие, answer — ответ, solution — решение, level — уровень 1/2/3, grade — класс, topic — тема)
- changes_made: массив строк с описанием каждого изменения
- reasoning: краткое обоснование исправлений

ВАЖНО: Ответь ТОЛЬКО JSON-объектом, без пояснений, без markdown-обрамления.
"""


def build_regeneration_prompt(task_record: dict) -> str:
    """Build user prompt for regeneration based on failed audit result."""
    task_text = task_record.get("task_text", "")
    target_level = task_record.get("target_level", "?")
    class_level = task_record.get("class_level", "?")
    topic = task_record.get("topic", "?")
    source_id = task_record.get("source_id", "?")
    subject = task_record.get("subject", "?")

    audit_result = task_record.get("audit_result", {})
    issues = audit_result.get("issues", [])
    audit_summary = audit_result.get("summary", "")
    level_verdict = audit_result.get("level_match", {}).get("verdict", "?")
    class_verdict = audit_result.get("class_match", {}).get("verdict", "?")
    topic_verdict = audit_result.get("topic_match", {}).get("verdict", "?")
    cond_verdict = audit_result.get("condition_correctness", {}).get("verdict", "?")

    prompt = f"""Проанализируй и исправь задачу, не прошедшую аудит.

## Исходные данные задачи:
- ID: {source_id}
- Условие: {task_text}
- Заявленный уровень: {target_level}
- Класс: {class_level}
- Тема: {topic}
- Предмет: {subject}

## Результаты аудита:
- Уровень: {level_verdict}
- Класс: {class_verdict}
- Тема: {topic_verdict}
- Корректность условия: {cond_verdict}
- Замечания аудитора: {'; '.join(issues) if issues else 'Нет'}
- Итоговое заключение: {audit_summary}

## Задача:
Исправь задачу так, чтобы она прошла аудит по всем критериям.
Сохрани предмет (subject) и общую тематику, но исправь:
1. Уровень сложности — приведи к заявленному {target_level} (или предложи подходящий)
2. Класс — сделай соответствующим указанному {class_level}
3. Тему — скорректируй если нужно
4. Условие — сделай полным, однозначным, без ошибок
5. Добавь ответ и решение

Ответь JSON-объектом в формате, указанном в system prompt.
"""
    return prompt


def regenerate_single_task(client: DeepSeekClient, task_record: dict, index: int) -> dict:
    """Send failed task to DeepSeek-reasoner for regeneration."""
    user_prompt = build_regeneration_prompt(task_record)
    source_id = task_record.get("source_id", "?")

    try:
        logger.info(f"[{index}] Regenerating task source_id={source_id}...")

        content = client.generate_with_reasoning(
            prompt=user_prompt,
            system_prompt=REGENERATE_SYSTEM_PROMPT,
            max_tokens=8192,
            timeout=300,
            return_reasoning=False,
        )

        result = safe_parse_json(content)
        fixed_task = result.get("fixed_task", {})
        changes = result.get("changes_made", [])

        logger.info(f"[{index}] Regeneration OK: {len(changes)} changes made")
        return {
            "index": index,
            "source_id": source_id,
            "original_task": task_record,
            "fixed_task": fixed_task,
            "changes_made": changes,
            "reasoning": result.get("reasoning", ""),
            "success": True,
            "error": None,
        }

    except (DeepSeekAPIError, json.JSONDecodeError, ValueError, Exception) as e:
        logger.error(f"[{index}] Regeneration FAIL: {e}")
        return {
            "index": index,
            "source_id": source_id,
            "original_task": task_record,
            "fixed_task": None,
            "changes_made": [],
            "reasoning": "",
            "success": False,
            "error": str(e),
        }


def main():
    logger.info("=" * 60)
    logger.info("FORMYLA L1-L3 Failed Task Regeneration via DeepSeek-reasoner")
    logger.info("=" * 60)

    # Load failed tasks from audit output
    failed_tasks = load_failed_tasks()
    if not failed_tasks:
        logger.warning(f"No failed tasks found in {FAILED_LOG}. Run _audit_l1_l3_full.py first.")
        return

    n_total = len(failed_tasks)
    logger.info(f"Found {n_total} failed tasks to regenerate")

    # Init client
    client = DeepSeekClient()

    # ─── Phase 1: Initial regeneration ─────────────────────────────
    all_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {}
        for i, task_rec in enumerate(failed_tasks):
            future = executor.submit(regenerate_single_task, client, task_rec, i)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                all_results.append(result)
                status = "OK" if result["success"] else "FAIL"
                with print_lock:
                    logger.info(f"[{idx}] done: status={status}")
            except Exception as e:
                with print_lock:
                    logger.error(f"[{idx}] Exception: {e}")
                all_results.append({
                    "index": idx,
                    "success": False,
                    "error": str(e),
                })

    # Sort
    all_results.sort(key=lambda r: r.get("index", 0))

    # ─── Summary ──────────────────────────────────────────────────
    regenerated = sum(1 for r in all_results if r.get("success"))
    failed = sum(1 for r in all_results if not r.get("success"))

    summary = {
        "total_failed_audit": n_total,
        "successfully_regenerated": regenerated,
        "still_failed": failed,
    }

    output = {
        "regeneration_timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-reasoner",
        "source_failed_log": FAILED_LOG,
        "summary": summary,
        "results": all_results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("REGENERATION COMPLETE")
    logger.info(f"  Total failed tasks: {n_total}")
    logger.info(f"  Regenerated:        {regenerated}")
    logger.info(f"  Still failed:       {failed}")
    logger.info(f"  Results saved to:   {OUTPUT_FILE}")
    logger.info("=" * 60)


# Need print_lock for thread-safe logging
from threading import Lock
print_lock = Lock()


if __name__ == "__main__":
    main()