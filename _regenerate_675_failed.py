#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Regenerate tasks that failed L1-L5 audit (675 audit) using DeepSeek-reasoner.

Pipeline:
  1. Load audit_675_full_results.json (output from _audit_675_full.py)
  2. Load curated_bank_L1_L5_pre_live.json (source tasks)
  3. For each task where audit_result.overall == "FAIL":
     - Build prompt with original task + detailed audit feedback
     - Send to DeepSeek-reasoner requesting correction
  4. Save regenerated tasks to _regenerated_675_tasks.json

Usage:
    python _regenerate_675_failed.py
"""

import json
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from _audit_150_pilot import safe_parse_json
from _audit_675_full import LEVEL_RUBRIC
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print_lock = Lock()

# ─── Paths ──────────────────────────────────────────────────────────
AUDIT_RESULTS_FILE = "audit_675_full_results.json"
CURATED_BANK = r"c:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\runs\selection_1080_20260712_134037\curated_bank_L1_L5_pre_live.json"
OUTPUT_FILE = "_regenerated_675_tasks.json"
CHECKPOINT_FILE = "_regenerate_675_checkpoint.json"

MAX_WORKERS = 2
MAX_RETRIES = 3

# ─── Loaders ────────────────────────────────────────────────────────

def load_audit_results() -> dict:
    """Load audit results JSON."""
    with open(AUDIT_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Loaded audit results from {AUDIT_RESULTS_FILE}")
    return data


def load_curated_bank() -> list:
    """Load all tasks from curated bank."""
    with open(CURATED_BANK, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    logger.info(f"Loaded {len(tasks)} tasks from curated bank")
    return tasks


def get_failed_tasks(audit_data: dict) -> list:
    """Extract tasks where audit_result.overall == 'FAIL'."""
    results = audit_data.get("results", [])
    failed = []
    for r in results:
        audit = r.get("audit_result")
        if audit and audit.get("overall") == "FAIL":
            failed.append(r)
    logger.info(f"Found {len(failed)} failed tasks out of {len(results)} total")
    return failed


def load_checkpoint() -> Optional[dict]:
    """Load regeneration checkpoint if exists."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded checkpoint: {len(data.get('results', []))} tasks already done")
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load checkpoint: {e}")
        return None


def save_checkpoint(output: dict):
    """Save intermediate checkpoint."""
    tmp = CHECKPOINT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)
    logger.info(f"Checkpoint saved ({len(output.get('results', []))} tasks)")


# ─── Prompt Construction ────────────────────────────────────────────

REGENERATE_SYSTEM_PROMPT = f"""Ты — эксперт-методист по созданию математических задач для системы адаптивного обучения Формула.

Твоя задача — проанализировать задачу, которая не прошла аудит, и исправить её в соответствии с замечаниями аудитора.

## Рубрика уровней (L1-L5):
{LEVEL_RUBRIC}

## Требования к задаче:
1. Условие должно быть логически непротиворечивым, полным и однозначным.
2. Уровень сложности должен строго соответствовать заявленному L1, L2, L3, L4 или L5.
3. Задача должна соответствовать указанному классу школьной программы.
4. Тема должна быть указана корректно.
5. Если в задаче требуется рисунок или график — условие должно быть самодостаточным (описано словами).
6. Ответ и решение должны быть приложены.

## Формат ответа:
Ты ДОЛЖЕН ответить строго в следующем JSON-формате (без markdown, без обрамления):

{{{{"fixed_task":{{"statement":"...","answer":"...","solution":"...","level":1,"grade":5,"topic":"..."}},"changes_made":["...","..."],"reasoning":"..."}}}}

Где:
- fixed_task: исправленная версия задачи (statement — условие, answer — ответ, solution — решение, level — уровень 1-5, grade — класс, topic — тема)
- changes_made: массив строк с описанием каждого изменения
- reasoning: краткое обоснование исправлений

ВАЖНО: Ответь ТОЛЬКО JSON-объектом, без пояснений, без markdown-обрамления.
"""


def build_regeneration_prompt(audit_record: dict, source_task: dict) -> str:
    """Build user prompt for regeneration based on failed audit result."""
    task_text = audit_record.get("task_text", source_task.get("task_text", ""))
    target_level = audit_record.get("target_level", source_task.get("target_level", "?"))
    class_level = audit_record.get("class_level", source_task.get("class_level", "?"))
    topic = audit_record.get("topic", source_task.get("topic", "?"))
    task_index = audit_record.get("task_index", "?")
    original_id = source_task.get("original_id", "?")

    audit_result = audit_record.get("audit_result", {})

    # Extract per-criterion verdicts
    level_v = audit_result.get("level_match", {}).get("verdict", "?")
    level_r = audit_result.get("level_match", {}).get("reasoning", "")
    level_suggested = audit_result.get("level_match", {}).get("suggested_level", "")

    class_v = audit_result.get("class_match", {}).get("verdict", "?")
    class_r = audit_result.get("class_match", {}).get("reasoning", "")
    class_suggested = audit_result.get("class_match", {}).get("suggested_class", "")

    topic_v = audit_result.get("topic_match", {}).get("verdict", "?")
    topic_r = audit_result.get("topic_match", {}).get("reasoning", "")
    topic_suggested = audit_result.get("topic_match", {}).get("suggested_topic", "")

    cond_v = audit_result.get("condition_correctness", {}).get("verdict", "?")
    cond_r = audit_result.get("condition_correctness", {}).get("reasoning", "")

    issues = audit_result.get("issues", [])
    summary = audit_result.get("summary", "")

    # Build suggested corrections section
    suggestions = []
    if level_suggested:
        suggestions.append(f"  - Уровень: предлагается {level_suggested}")
    if class_suggested:
        suggestions.append(f"  - Класс: предлагается {class_suggested}")
    if topic_suggested:
        suggestions.append(f"  - Тема: предлагается '{topic_suggested}'")
    suggestions_str = "\n".join(suggestions) if suggestions else "  - Нет предложений"

    prompt = f"""Проанализируй и исправь задачу, не прошедшую аудит.

## Исходные данные задачи:
- Индекс: {task_index}
- Original ID: {original_id}
- Условие: {task_text}
- Заявленный уровень: {target_level}
- Класс: {class_level}
- Тема: {topic}

## Результаты аудита по каждому критерию:

### 1. УРОВЕНЬ (level_match)
Вердикт: {level_v}
Обоснование: {level_r}

### 2. КЛАСС (class_match)
Вердикт: {class_v}
Обоснование: {class_r}

### 3. ТЕМА (topic_match)
Вердикт: {topic_v}
Обоснование: {topic_r}

### 4. КОРРЕКТНОСТЬ УСЛОВИЯ (condition_correctness)
Вердикт: {cond_v}
Обоснование: {cond_r}

### Предложения аудитора по исправлению:
{suggestions_str}

### Замечания:
{chr(10).join('- ' + i for i in issues) if issues else 'Нет замечаний'}

### Итоговое заключение аудитора:
{summary}

## Задача:
Исправь задачу так, чтобы она прошла аудит по всем критериям.
Сохрани общую тематику, но исправь все выявленные несоответствия.

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Если уровень не соответствует — измени задачу так, чтобы она строго соответствовала заявленному уровню {target_level}
2. Если класс не соответствует — сделай задачу доступной для указанного класса {class_level}
3. Если тема не соответствует — скорректируй тему или задачу
4. Если условие некорректно — исправь ошибки, сделай условие полным и однозначным
5. ОБЯЗАТЕЛЬНО добавь ответ (answer) и решение (solution)
6. Если в задаче подразумевается рисунок — опиши его словами в условии

Ответь JSON-объектом в формате, указанном в system prompt.
"""
    return prompt


# ─── Regeneration ───────────────────────────────────────────────────

def regenerate_single_task(
    client: DeepSeekClient,
    audit_record: dict,
    source_task: dict,
    index: int,
) -> dict:
    """Send failed task to DeepSeek-reasoner for regeneration."""
    user_prompt = build_regeneration_prompt(audit_record, source_task)
    task_index = audit_record.get("task_index", "?")
    original_id = source_task.get("original_id", "?")

    try:
        logger.info(f"[{index}] Regenerating task_index={task_index} (oid={original_id})...")

        content = client.generate_with_reasoning(
            prompt=user_prompt,
            system_prompt=REGENERATE_SYSTEM_PROMPT,
            max_tokens=8192,
            timeout=120,
            return_reasoning=False,
        )

        result = safe_parse_json(content)
        fixed_task = result.get("fixed_task", {})
        changes = result.get("changes_made", [])

        logger.info(f"[{index}] Regeneration OK: {len(changes)} changes made")
        return {
            "index": index,
            "task_index": task_index,
            "original_id": original_id,
            "source_task": source_task,
            "audit_record": audit_record,
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
            "task_index": task_index,
            "original_id": original_id,
            "source_task": source_task,
            "audit_record": audit_record,
            "fixed_task": None,
            "changes_made": [],
            "reasoning": "",
            "success": False,
            "error": str(e),
        }


def retry_failed(
    client: DeepSeekClient,
    failed_records: list,
    source_tasks: list,
    max_retries: int = MAX_RETRIES,
) -> list:
    """Retry tasks that failed regeneration."""
    all_final = list(failed_records)
    for attempt in range(1, max_retries + 1):
        still_failed = [r for r in all_final if not r.get("success")]
        if not still_failed:
            break
        logger.info(f"Retry attempt {attempt}/{max_retries}: {len(still_failed)} tasks to retry")
        for rec in still_failed:
            idx = rec.get("index", len(all_final))
            task_idx = rec.get("task_index", "?")
            original_id = rec.get("original_id", "?")
            source_task = rec.get("source_task", {})
            audit_record = rec.get("audit_record", {})
            logger.info(f"  Retrying task_index={task_idx} (oid={original_id})...")
            time.sleep(2)  # brief delay before retry
            new_result = regenerate_single_task(client, audit_record, source_task, idx)
            # Replace in list
            for i, r in enumerate(all_final):
                if r.get("task_index") == task_idx:
                    all_final[i] = new_result
                    break
    return all_final


# ─── Main ──────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("FORMYLA 675 FAILED TASK REGENERATION via DeepSeek-reasoner")
    logger.info("=" * 60)

    # ─── Load data ─────────────────────────────────────────────────
    audit_data = load_audit_results()
    source_tasks = load_curated_bank()

    # Build task_index -> source_task mapping
    source_map = {}
    for st in source_tasks:
        idx = st.get("source_index")
        if idx is not None:
            source_map[idx] = st

    # Get failed audit records
    failed_audit_records = get_failed_tasks(audit_data)
    if not failed_audit_records:
        logger.warning("No failed tasks found. Nothing to regenerate.")
        return

    n_total = len(failed_audit_records)
    logger.info(f"Total failed tasks to regenerate: {n_total}")

    # ─── Check for checkpoint ──────────────────────────────────────
    checkpoint = load_checkpoint()
    completed_indices = set()
    saved_results = []

    if checkpoint:
        saved_results = checkpoint.get("results", [])
        for r in saved_results:
            ti = r.get("task_index")
            if ti is not None:
                completed_indices.add(ti)
        logger.info(f"Resuming from checkpoint: {len(completed_indices)} tasks already done")

    # Filter out already completed
    pending = [
        r for r in failed_audit_records
        if r.get("task_index") not in completed_indices
    ]
    logger.info(f"Pending tasks to process: {len(pending)}")

    if not pending and saved_results:
        logger.info("All tasks already processed in checkpoint. Using checkpoint results.")
        output = checkpoint
    else:
        # ─── Init client ───────────────────────────────────────────
        client = DeepSeekClient()

        # ─── Process with ThreadPoolExecutor (2 workers) ──────────
        new_results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_idx = {}
            batch_start = 0

            for i, audit_rec in enumerate(pending):
                task_index = audit_rec.get("task_index", 0)
                source_task = source_map.get(task_index, {})
                if not source_task:
                    logger.warning(f"[{i}] No source task found for task_index={task_index}, using audit record data")
                    source_task = {
                        "task_text": audit_rec.get("task_text", ""),
                        "class_level": audit_rec.get("class_level", ""),
                        "target_level": audit_rec.get("target_level", ""),
                        "topic": audit_rec.get("topic", ""),
                        "original_id": f"task_{task_index}",
                    }
                future = executor.submit(
                    regenerate_single_task, client, audit_rec, source_task, i
                )
                future_to_idx[future] = (i, task_index)

            # Collect results as they complete
            for future in as_completed(future_to_idx):
                idx, task_index = future_to_idx[future]
                try:
                    result = future.result()
                    new_results.append(result)
                    status = "OK" if result["success"] else "FAIL"
                    with print_lock:
                        logger.info(f"[{idx}] task_index={task_index} done: status={status}")
                except Exception as e:
                    with print_lock:
                        logger.error(f"[{idx}] task_index={task_index} Exception: {e}")
                    new_results.append({
                        "index": idx,
                        "task_index": task_index,
                        "success": False,
                        "error": str(e),
                    })

                # Save checkpoint every 10 tasks
                processed_so_far = len(new_results)
                if processed_so_far % 10 == 0 and processed_so_far > 0:
                    partial_output = build_output(
                        saved_results + new_results, n_total, in_progress=True
                    )
                    save_checkpoint(partial_output)

        # ─── Retry failed ──────────────────────────────────────────
        new_results = retry_failed(client, new_results, source_tasks)

        # ─── Merge with checkpoint results ─────────────────────────
        all_results = saved_results + new_results
        all_results.sort(key=lambda r: (
            r.get("task_index", 0) if isinstance(r.get("task_index"), (int, float)) else 0
        ))

        # ─── Build final output ────────────────────────────────────
        output = build_output(all_results, n_total, in_progress=False)
        save_checkpoint(output)

    # ─── Save final output ─────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ─── Summary ───────────────────────────────────────────────────
    summary = output["summary"]
    logger.info("=" * 60)
    logger.info("REGENERATION COMPLETE")
    logger.info(f"  Total failed tasks:      {summary['total_failed_audit']}")
    logger.info(f"  Successfully regenerated: {summary['successfully_regenerated']}")
    logger.info(f"  Still failed:             {summary['still_failed']}")
    logger.info(f"  Results saved to:         {OUTPUT_FILE}")
    logger.info("=" * 60)


def build_output(all_results: list, n_total: int, in_progress: bool = False) -> dict:
    """Build the output dict with summary."""
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
        "source_audit_file": AUDIT_RESULTS_FILE,
        "in_progress": in_progress,
        "summary": summary,
        "results": all_results,
    }
    return output


if __name__ == "__main__":
    main()
