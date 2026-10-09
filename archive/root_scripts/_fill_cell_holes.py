#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Two-stage generation to fill cell holes in L1 and L2 topic cells.

Strategy:
  1. Load DB, identify all (grade, topic) cells with <5 tasks (holes).
  2. For each hole cell, send ONE deepseek-reasoner call requesting N diverse tasks
     (N = 5 - current_count). Provide existing tasks as context for diversity.
  3. Parse & validate JSON response.
  4. Check diversity against existing cell tasks.
  5. Save to checkpoint file.
  6. Merge into DB after completion.

Usage:
  python _fill_cell_holes.py [--level L1] [--max-cells N] [--dry-run]
"""

import json
import os
import sys
import re
import time
import logging
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── config ────────────────────────────────────────────────────────────────
DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
CHECKPOINT_PATH = "fill_cell_holes_checkpoint.json"
OUTPUT_FILE = "adaptive_data/adaptive_full_9120_fixed.json"  # same = merge in place
NEW_TASKS_FILE = "adaptive_data/_new_fill_tasks.json"
TARGET = 5
MAX_WORKERS = 3
MAX_RETRIES_PER_CELL = 5
CELL_TIMEOUT = 900  # max seconds to wait for a single cell (15 min)

SYSTEM_PROMPT = """Ты — профессиональный составитель олимпиадных задач по математике.
Твоя задача — создать максимально разнообразные задачи строго по указанным параметрам.

Правила:
1. Каждая задача должна быть строго на указанный уровень (уровень сложности), класс и тему.
2. Задачи в одной ячейке должны быть РАЗНЫМИ по:
   - Типу (вычислительная, доказательная, логическая, на конструкцию, олимпиадная)
   - Математическому подходу (индукция, инвариант, оценка+пример, и т.д.)
   - Формулировке и контексту
3. Каждая задача должна иметь:
   - statement (условие)
   - answer (ответ — число или выражение)
   - solution (решение с пояснениями)
   - subject = "math"
   - Правильные level, grade, topic, section
4. Ответы должны быть ЧИСЛОВЫМИ (число, дробь, выражение). Не должно быть "да/нет" или качественных ответов.
5. Не повторять существующие задачи из контекста!"""

def _fix_invalid_escapes(text: str) -> str:
    """Fix common invalid escape sequences in model JSON output.
    
    The DeepSeek API often returns doubled backslashes before LaTeX commands,
    e.g. \\\\leq (two backslashes in the raw string). A single pass of the
    regex only removes one backslash: \\\\leq -> \\leq (still has \\l which is
    an invalid JSON escape). Iterating until stable handles this:
    \\\\leq -> \\leq -> leq. Same for \\\\in, \\\\cup, \\\\infty, etc.
    """
    import re
    replacements = {
        '\\(': '(',
        '\\)': ')',
        '\\[': '[',
        '\\]': ']',
        '\\{': '{',
        '\\}': '}',
        '\\<': '<',
        '\\>': '>',
        '\\|': '|',
        '\\`': '`',
        '\\_': '_',
        '\\*': '*',
    }
    # Run multiple passes to handle doubled backslashes (e.g. \\\\leq)
    prev = None
    while prev != text:
        prev = text
        for old, new in replacements.items():
            text = text.replace(old, new)
        # Fix remaining unknown escapes by removing the backslash
        text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)
    return text


def _strip_control_chars(text: str) -> str:
    """Strip control characters except tab, newline, carriage return."""
    import re
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def _try_parse_single_object(obj_str: str) -> Optional[dict]:
    """Try multiple strategies to parse a single JSON object string."""
    obj_str = _fix_invalid_escapes(obj_str)
    obj_str = _strip_control_chars(obj_str)
    
    strategies = [
        lambda s: json.loads(s),
        lambda s: json.loads(s.replace("'", '"')),
        lambda s: json.loads(re.sub(r',\s*([\]}])', r'\1', s.replace("'", '"'))),
        lambda s: _try_ast(s),
    ]
    for strategy in strategies:
        try:
            result = strategy(obj_str)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError, SyntaxError, MemoryError):
            continue
    return None


def _try_ast(s: str):
    import ast
    return ast.literal_eval(s)


def _extract_individual_objects(text: str) -> Optional[list]:
    """Extract individual {{...}} JSON objects from text when array parsing fails.
    
    Uses brace-depth tracking to find top-level {{...}} blocks, then tries
    to parse each one individually. This recovers tasks even when the full
    output is malformed JSON.
    
    CRITICAL: Brace tracking is done BEFORE _fix_invalid_escapes, because the
    model outputs \{ and \} (LaTeX set notation) inside JSON string values.
    We skip escaped braces \{ and \} during tracking to avoid counting them
    as structure characters.
    """
    brace_depth = 0
    obj_start = -1
    objects = []
    
    i = 0
    while i < len(text):
        ch = text[i]
        # Skip escaped braces \{ and \} — they are inside JSON string values
        if ch == '\\' and i + 1 < len(text) and text[i+1] in '{}':
            i += 2
            continue
        if ch == '{':
            if brace_depth == 0:
                obj_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and obj_start >= 0:
                obj_str = text[obj_start:i+1]
                obj = _try_parse_single_object(obj_str)
                if obj is not None:
                    objects.append(obj)
                obj_start = -1
        i += 1
    
    return objects if objects else None


def safe_parse_json(text: str) -> Optional[list]:
    """Extract JSON array from model response, ultra-robust."""
    if not text:
        return None
    
    text = text.strip()
    
    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()
    
    # Find outermost [ ... ] with bracket-depth tracking
    # CRITICAL: Do this BEFORE _fix_invalid_escapes and _strip_control_chars,
    # because the model outputs \[ and \] (LaTeX notation) inside JSON strings.
    # After _fix_invalid_escapes converts \[ -> [ and \] -> ], these would
    # corrupt bracket-depth tracking. Same for \{ and \}.
    bracket_depth = 0
    json_start = -1
    json_end = -1
    i = 0
    while i < len(text):
        ch = text[i]
        # Skip escaped brackets and braces — they are inside JSON string values
        if ch == '\\' and i + 1 < len(text) and text[i+1] in '[]{}':
            i += 2
            continue
        if ch == '[':
            if bracket_depth == 0:
                json_start = i
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
            if bracket_depth == 0 and json_start >= 0:
                json_end = i + 1
                break
        i += 1
    
    if json_start < 0 or json_end <= json_start:
        return None
    
    json_str = text[json_start:json_end]
    json_str = _fix_invalid_escapes(json_str)
    json_str = _strip_control_chars(json_str)
    
    # Fix potential double brackets
    if json_str.startswith("[["):
        # Check if it's a nested array
        try:
            inner = json.loads(json_str)
            if isinstance(inner, list):
                return inner
        except json.JSONDecodeError:
            pass
        # Try unwrapping one level of brackets
        if json_str.startswith("[[") and json_str.endswith("]]"):
            json_str = json_str[1:-1]
    
    # Try standard parse
    try:
        result = json.loads(json_str)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Handle single quotes -> double quotes
    import re
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
        result = json.loads(json_fixed)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Fix trailing commas
    json_fixed2 = re.sub(r',\s*([\]}])', r'\1', json_fixed)
    try:
        result = json.loads(json_fixed2)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Try ast.literal_eval for Python-style output
    import ast
    try:
        result = ast.literal_eval(json_fixed)
        if isinstance(result, list):
            return result
    except (ValueError, SyntaxError, MemoryError):
        pass
    
    # FINAL FALLBACK: extract individual {{...}} objects from raw text
    # This handles cases where the model returns malformed JSON that
    # contains valid task objects scattered throughout.
    individual = _extract_individual_objects(text)
    if individual:
        logger.debug(f"Recovered {len(individual)} task(s) via individual object extraction")
        return individual
    
    return None


def load_db():
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_checkpoint(data: dict):
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Checkpoint saved: {len(data.get('generated_tasks', []))} tasks so far")


def load_checkpoint() -> Optional[dict]:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def get_cells_with_holes(tasks, level: int):
    """Return list of (grade, topic, section, existing_tasks, needed_count)."""
    by_topic = defaultdict(list)
    by_section = {}
    
    for t in tasks:
        grade = t.get('grade')
        topic = t.get('topic', '')
        section = t.get('section', '')
        by_topic[(grade, topic)].append(t)
        by_section[(grade, topic)] = section  # store section for this topic
    
    cells = []
    for (grade, topic), existing in by_topic.items():
        count = len(existing)
        if count < TARGET:
            needed = TARGET - count
            section = by_section.get((grade, topic), '')
            cells.append({
                'level': level,
                'grade': grade,
                'topic': topic,
                'section': section,
                'existing_tasks': existing,
                'count': count,
                'needed': needed,
                'cell_key': f"L{level}|{grade}|{topic}"
            })
    
    # Sort by most urgent first (fewest existing tasks)
    cells.sort(key=lambda c: c['count'])
    return cells


def build_generation_prompt(cell: dict) -> str:
    """Build prompt requesting N diverse tasks for this cell."""
    level = cell['level']
    grade = cell['grade']
    topic = cell['topic']
    section = cell['section']
    needed = cell['needed']
    existing = cell['existing_tasks']
    
    prompt_parts = [f"Сгенерируй {needed} олимпиадных задач(и) по математике для ячейки:"]
    prompt_parts.append(f"- Уровень: L{level}")
    prompt_parts.append(f"- Класс: {grade}")
    prompt_parts.append(f"- Раздел (section): {section}")
    prompt_parts.append(f"- Тема (topic): {topic}")
    prompt_parts.append(f"- Количество задач: {needed}")
    prompt_parts.append("")
    
    if existing:
        prompt_parts.append(f"В этой ячейке УЖЕ ЕСТЬ следующие {len(existing)} задач(и).")
        prompt_parts.append("НОВЫЕ задачи должны быть МАКСИМАЛЬНО РАЗНЫМИ от них!")
        prompt_parts.append("")
        for i, t in enumerate(existing, 1):
            stmt = t.get('statement', '')[:200]
            prompt_parts.append(f"Существующая задача {i}: {stmt}...")
        prompt_parts.append("")
    
    prompt_parts.append("ВАЖНЫЕ ТРЕБОВАНИЯ:")
    prompt_parts.append("1. Каждая задача должна быть уникальной и не похожей на существующие.")
    prompt_parts.append("2. Задачи должны быть разного типа (вычислительные, доказательные, логические, на конструкцию).")
    prompt_parts.append("3. Ответ должен быть ЧИСЛОВЫМ (число, дробь, выражение).")
    prompt_parts.append("4. Решение должно быть подробным, с пояснениями.")
    prompt_parts.append("5. Уровень сложности строго L" + str(level) + ".")
    prompt_parts.append("")
    
    prompt_parts.append("Формат ответа — JSON-массив объектов:")
    prompt_parts.append("""[
  {
    "statement": "Условие задачи",
    "answer": "Числовой ответ",
    "solution": "Подробное решение"
  }
]""")
    
    prompt_parts.append("")
    prompt_parts.append(f"Сгенерируй ровно {needed} задач(и). Не больше и не меньше.")
    prompt_parts.append("ВЕРНИ ТОЛЬКО JSON, без дополнительного текста и размышлений.")
    
    return "\n".join(prompt_parts)


def generate_cell_tasks(client: DeepSeekClient, cell: dict) -> list:
    """Generate N tasks for a single cell. Returns list of task dicts."""
    prompt = build_generation_prompt(cell)
    
    for attempt in range(MAX_RETRIES_PER_CELL):
        try:
            # deepseek-reasoner has systemic "empty content field" issues for L2+
            # Use deepseek-chat (client.generate) for level >= 2 as it's reliable
            if cell['level'] >= 2:
                raw = client.generate(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=4000,
                    temperature=0.3,
                )
            else:
                raw = client.generate_with_reasoning(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=4000,
                    timeout=300,
                )
            
            tasks = safe_parse_json(raw)
            if not tasks:
                logger.warning(f"[{cell['cell_key']}] Attempt {attempt+1}: JSON parse failed, retrying...")
                time.sleep(3)
                continue
            
            if len(tasks) != cell['needed']:
                logger.warning(f"[{cell['cell_key']}] Got {len(tasks)} tasks, expected {cell['needed']}. Truncating/padding.")
                tasks = tasks[:cell['needed']]
            
            # Validate each task has required fields
            validated = []
            for t in tasks:
                t['level'] = cell['level']
                t['grade'] = cell['grade']
                t['topic'] = cell['topic']
                t['section'] = cell['section']
                t['subject'] = 'math'
                
                # Ensure required fields
                if not t.get('statement') or not t.get('answer'):
                    logger.warning(f"Task missing statement or answer, skipping")
                    continue
                if not t.get('solution'):
                    t['solution'] = t.get('answer', '')
                
                validated.append(t)
            
            if validated:
                logger.info(f"[{cell['cell_key']}] [OK] Generated {len(validated)}/{cell['needed']} tasks")
                return validated
            else:
                logger.warning(f"[{cell['cell_key']}] Attempt {attempt+1}: No valid tasks, retrying...")
                time.sleep(3)
                continue
                
        except Exception as e:
            logger.error(f"[{cell['cell_key']}] Attempt {attempt+1}: {e}")
            time.sleep(5)
            continue
    
    logger.error(f"[{cell['cell_key']}] All {MAX_RETRIES_PER_CELL} attempts failed!")
    return []


def merge_into_db(db: list, new_tasks: list) -> list:
    """Merge new tasks into DB, avoiding duplicates by text similarity."""
    existing_texts = set()
    for t in db:
        stmt = t.get('statement', '').strip()
        if stmt:
            # Use first 100 chars as fingerprint
            existing_texts.add(stmt[:100].lower().replace(' ', ''))
    
    added = 0
    skipped = 0
    for t in new_tasks:
        stmt = t.get('statement', '').strip()
        if not stmt:
            continue
        fingerprint = stmt[:100].lower().replace(' ', '')
        if fingerprint in existing_texts:
            skipped += 1
            continue
        existing_texts.add(fingerprint)
        # Assign new ID
        max_id = max((int(x.get('id', 0)) for x in db if str(x.get('id', '')).isdigit()), default=0)
        t['id'] = max_id + 1 + added
        db.append(t)
        added += 1
    
    logger.info(f"Merged: +{added} new tasks, skipped {skipped} duplicates")
    return db


def main():
    parser = argparse.ArgumentParser(description="Fill cell holes in L1/L2")
    parser.add_argument('--level', type=int, choices=[1, 2], default=None,
                        help='Fill only L1 or L2 (default: both)')
    parser.add_argument('--max-cells', type=int, default=None,
                        help='Max cells to process (for testing)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only list cells without generating')
    parser.add_argument('--resume', action='store_true',
                        help='Resume from checkpoint')
    args = parser.parse_args()
    
    # Load DB
    db = load_db()
    logger.info(f"Loaded {len(db)} total tasks")
    
    l1 = [t for t in db if t.get('level') == 1]
    l2 = [t for t in db if t.get('level') == 2]
    logger.info(f"L1: {len(l1)} tasks, L2: {len(l2)} tasks")
    
    # Get cells with holes
    all_cells = []
    if args.level is None or args.level == 1:
        all_cells.extend(get_cells_with_holes(l1, 1))
    if args.level is None or args.level == 2:
        all_cells.extend(get_cells_with_holes(l2, 2))
    
    if not all_cells:
        logger.info("No holes found! All cells are full or overfilled.")
        return
    
    total_needed = sum(c['needed'] for c in all_cells)
    logger.info(f"Found {len(all_cells)} cells with holes, need {total_needed} tasks total")
    
    # Show distribution
    by_need = defaultdict(int)
    for c in all_cells:
        by_need[c['needed']] += 1
    logger.info(f"Need distribution: {dict(sorted(by_need.items()))}")
    
    if args.dry_run:
        logger.info("DRY RUN — showing first 20 cells:")
        for c in all_cells[:20]:
            logger.info(f"  L{c['level']} | {c['grade']} | {c['topic']} — {c['count']}/{TARGET} (need {c['needed']})")
        logger.info(f"  ... and {len(all_cells)-20} more cells")
        return
    
    # Load checkpoint if resuming
    checkpoint = None
    completed_keys = set()
    all_generated_tasks = []
    
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            completed_keys = set(checkpoint.get('completed_cells', []))
            all_generated_tasks = checkpoint.get('generated_tasks', [])
            logger.info(f"Resumed: {len(completed_keys)} cells already completed, {len(all_generated_tasks)} tasks generated")
    
    # Filter out already completed cells
    cells_to_process = [c for c in all_cells if c['cell_key'] not in completed_keys]
    logger.info(f"Cells to process: {len(cells_to_process)} (skipping {len(all_cells) - len(cells_to_process)} completed)")
    
    if args.max_cells:
        cells_to_process = cells_to_process[:args.max_cells]
        logger.info(f"Limiting to {args.max_cells} cells")
    
    if not cells_to_process:
        logger.info("All cells already processed!")
    else:
        # Initialize client
        client = DeepSeekClient()
        
        # Process cells with thread pool
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {}
            for cell in cells_to_process:
                future = executor.submit(generate_cell_tasks, client, cell)
                future_map[future] = cell
            
            completed = 0
            total = len(future_map)
            
            for future in as_completed(future_map):
                cell = future_map[future]
                completed += 1
                
                try:
                    new_tasks = future.result(timeout=CELL_TIMEOUT)
                    if new_tasks:
                        all_generated_tasks.extend(new_tasks)
                        completed_keys.add(cell['cell_key'])
                        logger.info(f"[{completed}/{total}] [OK] {cell['cell_key']} — +{len(new_tasks)} tasks")
                    else:
                        logger.error(f"[{completed}/{total}]  {cell['cell_key']} — FAILED")
                except Exception as e:
                    logger.error(f"[{completed}/{total}]  {cell['cell_key']} — {e}")
                
                # Save checkpoint every 5 cells
                if completed % 5 == 0 or completed == total:
                    save_checkpoint({
                        'completed_cells': list(completed_keys),
                        'generated_tasks': all_generated_tasks,
                        'timestamp': datetime.now().isoformat(),
                    })
        
        # Final checkpoint
        save_checkpoint({
            'completed_cells': list(completed_keys),
            'generated_tasks': all_generated_tasks,
            'timestamp': datetime.now().isoformat(),
        })
    
    # Save new tasks to separate file
    with open(NEW_TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_generated_tasks, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(all_generated_tasks)} new tasks to {NEW_TASKS_FILE}")
    
    # Merge into main DB
    if all_generated_tasks and not args.dry_run:
        db = load_db()  # Reload in case of changes
        db = merge_into_db(db, all_generated_tasks)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        logger.info(f"Merged into {OUTPUT_FILE} — total {len(db)} tasks")
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Generation complete!")
    logger.info(f"  Cells processed: {len(completed_keys)}")
    logger.info(f"  New tasks generated: {len(all_generated_tasks)}")
    
    # Check remaining holes
    remaining = [c for c in all_cells if c['cell_key'] not in completed_keys]
    if remaining:
        logger.info(f"  Cells STILL with holes: {len(remaining)}")
        remaining_needed = sum(c['needed'] for c in remaining)
        logger.info(f"  Remaining tasks needed: {remaining_needed}")
    else:
        logger.info(f"  All cells filled! [OK]")


if __name__ == '__main__':
    main()
