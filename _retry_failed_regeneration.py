#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retry 68 failed L1-L3 regenerations using deepseek-chat (non-reasoner).

deepseek-reasoner often produces malformed JSON (invalid escape sequences,
control characters, truncated responses). deepseek-chat produces cleaner,
more predictable JSON output.

Strategy:
  1. Load _regenerated_tasks.json — extract the 68 failed results
  2. For each, reconstruct original task from audit_l1_l3_failed.json
  3. Retry using client.generate() (deepseek-chat) + ultra-robust JSON parser
  4. Patch results back into _regenerated_tasks.json
  5. Re-run merge to apply newly-fixed tasks to DB

Usage:
    python _retry_failed_regeneration.py
"""

import json
import os
import sys
import re
import logging
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from _audit_150_pilot import LEVEL_RUBRIC
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
print_lock = Lock()

# ─── Paths ──────────────────────────────────────────────────────────
REGENERATED_FILE = "_regenerated_tasks.json"
FAILED_LOG = "audit_l1_l3_failed.json"
ADAPTIVE_DB = "adaptive_data/adaptive_full_9120_fixed.json"

MAX_WORKERS = 5  # slower to avoid rate limits + ensure quality
MAX_RETRIES = 3


# ─── Ultra-robust JSON parser ──────────────────────────────────────

def _fix_invalid_escapes(text: str) -> str:
    """Fix invalid escape sequences (like \\d, \\s, backslash+cyrillic etc.) in JSON strings.

    In JSON, only valid escapes are: \\, \\/, \\", \\b, \\f, \\n, \\r, \\t, \\uXXXX.
    All other backslash-X sequences are invalid. This function removes the backslash
    before invalid escape chars inside JSON string values.
    """
    VALID_ESCAPES = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch in VALID_ESCAPES:
                result.append(text[i])
                result.append(text[i + 1])
                i += 2
            else:
                # Invalid escape — strip the backslash, keep the char
                result.append(next_ch)
                i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _strip_control_chars(text: str) -> str:
    """Strip control characters (0x00-0x1F except \t, \n, \r) from JSON."""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def safe_parse_json_ultra(text: str) -> dict:
    """Ultra-robust JSON parser for model-generated JSON.

    Built on top of the existing safe_parse_json logic but adds:
    - Invalid escape sequence fixing
    - Control character stripping
    - More aggressive truncation handling
    """
    text = text.strip()

    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # Find outermost { ... }
    brace_depth = 0
    json_start = -1
    json_end = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and json_start >= 0:
                json_end = i + 1
                break

    if json_start < 0:
        raise ValueError(f"No valid JSON object found: {text[:300]}")

    # Handle truncation: close unterminated strings and braces
    if json_end <= json_start and brace_depth > 0:
        quote_count = text.count('"')
        if quote_count % 2 == 1:
            text = text + '"'
        text = text + "}" * brace_depth
        json_end = len(text)
    elif json_end <= json_start:
        raise ValueError(f"No valid JSON object found: {text[:300]}")

    json_str = text[json_start:json_end]

    # Normalize double braces
    if json_str.startswith("{{") and json_str.endswith("}}"):
        json_str = json_str[1:-1]
    json_str = json_str.replace("{{", "{").replace("}}", "}")

    # ── NEW: Fix invalid escape sequences ──
    json_str = _fix_invalid_escapes(json_str)

    # ── NEW: Strip control characters ──
    json_str = _strip_control_chars(json_str)

    # Try standard parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Single quotes → double quotes
    fixed = []
    in_double = False
    in_single = False
    escape = False
    for ch in json_str:
        if escape:
            fixed.append(ch)
            escape = False
            continue
        if ch == '\\':
            fixed.append(ch)
            escape = True
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            fixed.append(ch)
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            fixed.append('"')
            continue
        fixed.append(ch)
    json_fixed = "".join(fixed)

    try:
        return json.loads(json_fixed)
    except json.JSONDecodeError:
        pass

    # Fix trailing commas
    json_fixed = re.sub(r',\s*([}\]])', r'\1', json_fixed)
    try:
        return json.loads(json_fixed)
    except json.JSONDecodeError:
        pass

    # ast.literal_eval fallback
    try:
        result = ast.literal_eval(json_fixed)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError, MemoryError):
        pass

    # Last resort: strip non-JSON prefix/suffix
    json_str_clean = re.sub(r'^[^{]*', '', json_str)
    json_str_clean = re.sub(r'[^}]*$', '', json_str_clean)
    try:
        return json.loads(json_str_clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"safe_parse_json_ultra: {e}\nExtracted: {json_str[:500]}")


# ─── Prompt (simplified for chat model) ────────────────────────────

CHAT_REGENERATE_PROMPT = f"""Ты — эксперт-методист по математике. Исправь задачу по замечаниям аудита.

## Рубрика уровней:
{LEVEL_RUBRIC}

## Формат ответа (строгий JSON, БЕЗ markdown, БЕЗ пояснений):
{{"fixed_task":{{"statement":"...","answer":"...","solution":"...","level":1,"grade":5,"topic":"..."}},"changes_made":["..."],"reasoning":"..."}}

ВАЖНО: Ответь ТОЛЬКО JSON. Никаких ```, никаких пояснений до или после.
"""


def build_retry_prompt(task_record: dict) -> str:
    """Build prompt for retry from original task record."""
    task_text = task_record.get("task_text", "")
    target_level = task_record.get("target_level", "?")
    class_level = task_record.get("class_level", "?")
    topic = task_record.get("topic", "?")
    source_id = task_record.get("source_id", "?")
    subject = task_record.get("subject", "?")

    audit_result = task_record.get("audit_result", {})
    issues = audit_result.get("issues", [])
    audit_summary = audit_result.get("summary", "")

    return f"""Исправь задачу, которая не прошла аудит:

## Исходные данные:
- ID: {source_id}
- Условие: {task_text}
- Уровень: {target_level}
- Класс: {class_level}
- Тема: {topic}
- Предмет: {subject}

## Замечания аудитора: {'; '.join(issues) if issues else 'Нет'}
## Заключение: {audit_summary}

Исправь все замечания. Ответь строгим JSON-объектом.
"""


# ─── Main retry logic ──────────────────────────────────────────────

def load_failed_records() -> list:
    """Extract the 68 failed records from _regenerated_tasks.json."""
    with open(REGENERATED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    # Also load original failed task log for fallback
    failed_log = {}
    try:
        with open(FAILED_LOG, "r", encoding="utf-8") as f:
            fl = json.load(f)
        for t in fl.get("failed_tasks", []):
            sid = t.get("source_id")
            if sid is not None:
                failed_log[str(sid)] = t
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning(f"Could not load {FAILED_LOG} for fallback lookups")

    failed = []
    for r in results:
        if not r.get("success"):
            sid = r.get("source_id")
            original_task = r.get("original_task")

            # If original_task is empty/missing, try to look up from failed log
            if not original_task or not isinstance(original_task, dict) or not original_task.get("task_text"):
                if sid is not None and str(sid) in failed_log:
                    original_task = failed_log[str(sid)]
                    r["original_task"] = original_task
                    logger.info(f"  Restored original_task for source_id={sid} from failed log")
                else:
                    logger.warning(f"  No original_task available for source_id={sid}, will try DB lookup")

            failed.append(r)

    logger.info(f"Loaded {len(failed)} failed records from {REGENERATED_FILE}")
    return failed, data, failed_log


def lookup_original_from_db(source_id) -> Optional[dict]:
    """Try to reconstruct original task data from DB."""
    try:
        with open(ADAPTIVE_DB, "r", encoding="utf-8") as f:
            db = json.load(f)
        for t in db:
            if t.get("id") == source_id:
                return {
                    "source_id": source_id,
                    "task_text": t.get("statement", ""),
                    "target_level": str(t.get("level", "?")),
                    "class_level": str(t.get("grade", "?")),
                    "topic": t.get("topic", "?"),
                    "subject": t.get("subject", "?"),
                    "audit_result": {
                        "issues": [],
                        "summary": "No audit data available — retrying from scratch",
                        "level_match": {"verdict": "?"},
                        "class_match": {"verdict": "?"},
                        "topic_match": {"verdict": "?"},
                        "condition_correctness": {"verdict": "?"},
                    }
                }
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def retry_single_task(client: DeepSeekClient, failed_record: dict, index: int) -> dict:
    """Retry regeneration using deepseek-chat (non-reasoner)."""
    source_id = failed_record.get("source_id", "?")
    original_task = failed_record.get("original_task", {})

    # If original_task is empty, try DB
    if not original_task or not isinstance(original_task, dict) or not original_task.get("task_text"):
        db_task = lookup_original_from_db(source_id)
        if db_task:
            original_task = db_task
            logger.info(f"  [{index}] Used DB lookup for source_id={source_id}")
        else:
            return {
                "index": index,
                "source_id": source_id,
                "fixed_task": None,
                "changes_made": [],
                "reasoning": "",
                "success": False,
                "error": "No original task data available (not in failed log or DB)",
            }

    user_prompt = build_retry_prompt(original_task)

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"[{index}] Retry attempt {attempt+1}/{MAX_RETRIES} for source_id={source_id} (deepseek-chat)...")

            content = client.generate(
                prompt=user_prompt,
                system_prompt=CHAT_REGENERATE_PROMPT,
                max_tokens=8192,
            )

            result = safe_parse_json_ultra(content)
            fixed_task = result.get("fixed_task", {})
            changes = result.get("changes_made", [])

            if not fixed_task or not isinstance(fixed_task, dict):
                raise ValueError(f"fixed_task is empty or not a dict: {fixed_task}")

            # Validate required fields
            required = ["statement", "answer", "solution", "level", "grade", "topic"]
            missing = [k for k in required if k not in fixed_task]
            if missing:
                raise ValueError(f"fixed_task missing fields: {missing}")

            logger.info(f"[{index}] Retry OK: source_id={source_id}, {len(changes)} changes")
            return {
                "index": index,
                "source_id": source_id,
                "original_task": original_task,
                "fixed_task": fixed_task,
                "changes_made": changes,
                "reasoning": result.get("reasoning", ""),
                "success": True,
                "error": None,
            }

        except (DeepSeekAPIError, json.JSONDecodeError, ValueError, Exception) as e:
            err_msg = str(e)
            logger.warning(f"[{index}] Attempt {attempt+1} failed: {err_msg[:120]}")
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(5 * (attempt + 1))

    return {
        "index": index,
        "source_id": source_id,
        "original_task": original_task,
        "fixed_task": None,
        "changes_made": [],
        "reasoning": "",
        "success": False,
        "error": f"Retry failed after {MAX_RETRIES} attempts with deepseek-chat",
    }


def patch_regenerated_file(data: dict, new_results: list) -> dict:
    """Patch successful retries back into _regenerated_tasks.json."""
    results = data.get("results", [])
    patched = 0
    still_failed = 0

    # Build index by source_id for O(1) lookup
    new_by_sid = {}
    for nr in new_results:
        sid = nr.get("source_id")
        if sid is not None:
            new_by_sid[str(sid)] = nr

    for i, r in enumerate(results):
        sid = r.get("source_id")
        if sid is not None and str(sid) in new_by_sid:
            nr = new_by_sid[str(sid)]
            if nr.get("success"):
                results[i] = nr
                patched += 1
            else:
                still_failed += 1

    summary = data.get("summary", {})
    summary["successfully_regenerated"] = summary.get("successfully_regenerated", 0) + patched
    summary["still_failed"] = still_failed
    summary["retry_timestamp"] = datetime.now(timezone.utc).isoformat()
    summary["retry_model"] = "deepseek-chat"
    summary["retry_patched"] = patched
    summary["retry_still_failed"] = still_failed

    data["summary"] = summary
    data["results"] = results

    # Save back
    with open(REGENERATED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return summary


def main():
    logger.info("=" * 60)
    logger.info("RETRY: 68 failed regenerations via deepseek-chat")
    logger.info("=" * 60)

    # Load failed records
    failed_records, full_data, failed_log = load_failed_records()
    if not failed_records:
        logger.info("No failed records found — nothing to retry!")
        return

    logger.info(f"Will retry {len(failed_records)} failed tasks")

    # Init client (uses deepseek-chat by default)
    client = DeepSeekClient()

    # Run retries with thread pool
    all_new_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {}
        for i, rec in enumerate(failed_records):
            future = executor.submit(retry_single_task, client, rec, i)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                all_new_results.append(result)
                status = "OK" if result["success"] else "FAIL"
                with print_lock:
                    logger.info(f"[{idx}] done: source_id={result.get('source_id')} status={status}")
            except Exception as e:
                with print_lock:
                    logger.error(f"[{idx}] Exception: {e}")
                all_new_results.append({
                    "index": idx,
                    "success": False,
                    "error": str(e),
                })

    # Sort by index
    all_new_results.sort(key=lambda r: r.get("index", 0))

    # Stats
    ok_count = sum(1 for r in all_new_results if r.get("success"))
    fail_count = sum(1 for r in all_new_results if not r.get("success"))

    logger.info("=" * 60)
    logger.info(f"Retry results: {ok_count} OK, {fail_count} still failed (out of {len(all_new_results)})")

    # Patch into _regenerated_tasks.json
    if ok_count > 0:
        summary = patch_regenerated_file(full_data, all_new_results)
        logger.info(f"Patched {summary['retry_patched']} fixes into {REGENERATED_FILE}")
        logger.info(f"Updated summary: successfully_regenerated={summary.get('successfully_regenerated')}, still_failed={summary.get('still_failed')}")

        # Auto-run merge
        logger.info("=" * 60)
        logger.info("Now running merge to apply fixes to DB...")
        logger.info("=" * 60)
        try:
            from _merge_regenerated import main as merge_main
            merge_main()
        except ImportError:
            logger.warning("Could not auto-run merge. Run manually: python _merge_regenerated.py")
    else:
        logger.warning("No successful retries — nothing to patch")
        # Still save retry results so we can inspect
        with open(REGENERATED_FILE.replace(".json", "_retry_attempt.json"), "w", encoding="utf-8") as f:
            json.dump({
                "retry_timestamp": datetime.now(timezone.utc).isoformat(),
                "model": "deepseek-chat",
                "total_attempted": len(all_new_results),
                "successful": ok_count,
                "failed": fail_count,
                "results": all_new_results,
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"Retry results saved for inspection")

    logger.info("=" * 60)
    logger.info("DONE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
