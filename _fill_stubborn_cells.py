#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Targeted one-task-at-a-time generation for the most stubborn L2 cells.
Instead of asking for N tasks in one JSON array, makes N separate API calls,
each requesting exactly 1 task. This drastically reduces JSON complexity
and avoids malformed multi-task arrays.

Usage:
    python _fill_stubborn_cells.py
"""

import json
import os
import sys
import re
import logging
from collections import defaultdict
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
TARGET = 5
MAX_ATTEMPTS_PER_TASK = 10

SYSTEM_PROMPT = """You are a mathematics olympiad problem generator. You MUST respond with ONLY a valid JSON object, no other text.

Generate exactly ONE olympiad-level mathematics problem. The response must be a valid JSON object with exactly these fields:
- "statement": the problem text (may include LaTeX with $$...$$)
- "answer": the correct answer
- "solution": a brief solution or explanation

Example:
{"statement": "Find all integers $$n$$ such that $$n^2 + 3n + 2$$ is a perfect square.", "answer": "n = -1, -2", "solution": "Factor as (n+1)(n+2). For product of two consecutive integers to be a square..."}

IMPORTANT: Output ONLY the JSON object. No markdown, no code fences, no explanations."""


def _fix_invalid_escapes(text: str) -> str:
    """Fix invalid JSON escapes, run iteratively until stable.
    
    The API often returns doubled backslashes before LaTeX commands,
    e.g. \\\\leq (two backslashes). Single pass only removes one:
    \\\\leq -> \\leq (still has \\l which is invalid JSON).
    Iterating until stable handles this correctly:
    \\\\leq -> \\leq -> leq
    """
    replacements = {
        '\\(': '(', '\\)': ')', '\\[': '[', '\\]': ']',
        '\\{': '{', '\\}': '}', '\\<': '<', '\\>': '>',
        '\\|': '|', '\\`': '`', '\\_': '_', '\\*': '*',
    }
    # Run multiple passes to handle doubled backslashes
    prev = None
    while prev != text:
        prev = text
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)
    return text


def _strip_control_chars(text: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def safe_parse_single_object(text: str) -> Optional[dict]:
    """Parse a single JSON object {{...}} from model response, ultra-robust."""
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

    # Find outermost { ... } with brace-depth tracking
    # CRITICAL: Do this BEFORE _fix_invalid_escapes, because the model
    # outputs \{ and \} (LaTeX set notation) inside JSON string values.
    # After _fix_invalid_escapes converts \{ -> {, these would corrupt
    # brace-depth tracking and JSON parsing.
    brace_depth = 0
    obj_start = -1
    obj_end = -1
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
                obj_end = i + 1
                break
        i += 1

    if obj_start < 0 or obj_end <= obj_start:
        return None

    json_str = text[obj_start:obj_end]
    json_str = _fix_invalid_escapes(json_str)
    json_str = _strip_control_chars(json_str)

    # Try multiple parsing strategies
    strategies = [
        lambda s: json.loads(s),
        lambda s: json.loads(s.replace("'", '"')),
        lambda s: json.loads(re.sub(r',\s*([\]}])', r'\1', s.replace("'", '"'))),
    ]

    for strategy in strategies:
        try:
            result = strategy(json_str)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def load_db():
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_cells_with_holes(tasks):
    """Get all L2 cells with <5 tasks."""
    cells = defaultdict(list)
    for t in tasks:
        key = (t['grade'], t['topic'])
        cells[key].append(t)

    result = []
    for (grade, topic), cell_tasks in sorted(cells.items()):
        count = len(cell_tasks)
        if count < TARGET:
            needed = TARGET - count
            result.append({
                'grade': grade,
                'topic': topic,
                'count': count,
                'needed': needed,
                'existing': cell_tasks,
            })
    return result


def build_single_prompt(cell: dict) -> str:
    """Build prompt asking for exactly 1 task, providing existing tasks for context."""
    grade = cell['grade']
    topic = cell['topic']
    existing = cell['existing']

    prompt = f"""Generate one olympiad-level mathematics problem for grade {grade}, topic: "{topic}".

This is for an olympiad training system. The problem should be challenging but appropriate for grade {grade} students.
Include the problem statement, answer, and solution.

"""
    if existing:
        prompt += "Existing problems in this cell (generate something DIFFERENT):\n"
        for i, t in enumerate(existing, 1):
            stmt = t.get('statement', '')[:120]
            prompt += f"  {i}. {stmt}\n"
        prompt += "\n"

    prompt += "Respond with ONLY a valid JSON object."
    return prompt


def main():
    db = load_db()
    l2 = [t for t in db if t.get('level') == 2]
    logger.info(f"Loaded {len(db)} total tasks (L2: {len(l2)})")

    cells = get_cells_with_holes(l2)
    total_needed = sum(c['needed'] for c in cells)
    logger.info(f"Found {len(cells)} L2 cells with holes, need {total_needed} tasks total")

    if not cells:
        logger.info("All L2 cells are full! [OK]")
        return

    for c in cells:
        logger.info(f"  L2|g{c['grade']}|{c['topic']} — {c['count']}/{TARGET} (need {c['needed']})")

    client = DeepSeekClient()

    all_new_tasks = []
    total_generated = 0

    for cell_idx, cell in enumerate(cells):
        grade = cell['grade']
        topic = cell['topic']
        needed = cell['needed']
        cell_key = f"L2|g{grade}|{topic}"

        logger.info(f"\n[{cell_idx+1}/{len(cells)}] {cell_key} — need {needed} task(s)")

        tasks_for_cell = 0
        for task_idx in range(needed):
            logger.info(f"  Task {task_idx+1}/{needed} for {cell_key}")
            success = False

            for attempt in range(MAX_ATTEMPTS_PER_TASK):
                try:
                    prompt = build_single_prompt(cell)
                    raw = client.generate(
                        prompt=prompt,
                        system_prompt=SYSTEM_PROMPT,
                        max_tokens=4000,
                        temperature=0.7,
                    )

                    task = safe_parse_single_object(raw)
                    if task is not None:
                        # Validate required fields
                        if not task.get('statement') or not task.get('answer'):
                            logger.warning(f"    Attempt {attempt+1}: missing required fields, retrying...")
                            continue

                        # Add metadata
                        task['level'] = 2
                        task['grade'] = grade
                        task['topic'] = topic
                        task['section'] = cell.get('existing', [{}])[0].get('section', '') if cell.get('existing') else ''
                        task['subject'] = 'math'

                        all_new_tasks.append(task)
                        tasks_for_cell += 1
                        total_generated += 1
                        success = True
                        logger.info(f"    [OK] Generated task {task_idx+1} (attempt {attempt+1})")
                        break
                    else:
                        # Log raw output for debugging
                        preview = raw[:300].replace('\n', '\\n')
                        logger.warning(f"    Attempt {attempt+1}: JSON parse failed. Raw preview: {preview}...")

                except Exception as e:
                    logger.error(f"    Attempt {attempt+1}: {e}")

            if not success:
                logger.error(f"     Failed to generate task {task_idx+1} after {MAX_ATTEMPTS_PER_TASK} attempts")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Generation complete!")
    logger.info(f"  Generated {total_generated} new tasks")

    if total_generated > 0:
        # Save to file
        new_tasks_file = "adaptive_data/_stubborn_fill_tasks.json"
        with open(new_tasks_file, 'w', encoding='utf-8') as f:
            json.dump(all_new_tasks, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved to {new_tasks_file}")

        # Merge into DB
        db = load_db()
        existing_texts = set()
        for t in db:
            stmt = t.get('statement', '').strip()
            if stmt:
                existing_texts.add(stmt[:100].lower().replace(' ', ''))

        added = 0
        skipped = 0
        for t in all_new_tasks:
            stmt = t.get('statement', '').strip()
            if not stmt:
                continue
            fingerprint = stmt[:100].lower().replace(' ', '')
            if fingerprint in existing_texts:
                skipped += 1
                continue
            existing_texts.add(fingerprint)
            max_id = max((int(x.get('id', 0)) for x in db if str(x.get('id', '')).isdigit()), default=0)
            t['id'] = max_id + 1 + added
            db.append(t)
            added += 1

        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        logger.info(f"Merged: +{added} new tasks, skipped {skipped} duplicates")
        logger.info(f"DB total: {len(db)} tasks")

        # Final check
        l2_after = [t for t in db if t.get('level') == 2]
        cells_after = defaultdict(list)
        for t in l2_after:
            cells_after[(t['grade'], t['topic'])].append(t)
        
        remaining = {k: v for k, v in cells_after.items() if len(v) < TARGET}
        if remaining:
            logger.info(f"\n[!]️  {len(remaining)} L2 cells STILL with holes:")
            for (g, tp), ts in sorted(remaining.items()):
                logger.info(f"  L2|g{g}|{tp} — {len(ts)}/{TARGET} (need {TARGET-len(ts)})")
        else:
            logger.info(f"\n[OK] ALL L2 CELLS FILLED! ({len(l2_after)}/{len(l2_after)} cells complete)")
    else:
        logger.info("No tasks generated.")


if __name__ == '__main__':
    main()
