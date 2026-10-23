#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 6: Targeted Generation — Fill remaining 188 holes across 41 cells.

Reads generation_plan.csv, filters cells with adjusted_needed > 0,
and uses DeepSeek API to generate original olympiad-level tasks
for each specific cell (grade, level, theme, subtopic).

Outputs:
  - stage6_generated_tasks.json   : all generated tasks with metadata
  - stage6_checkpoint.json        : checkpoint for resume
  - stage6_generation_report.txt  : summary report

Usage:
  cd l4_l5_completion_work
  python _stage6_targeted_generation.py
"""

import os
import sys
import json
import csv
import time
import hashlib
import logging
import traceback
from datetime import datetime

# === Force UTF-8 output for Windows cp1251 ===
if sys.stdout.encoding is None or sys.stdout.encoding.lower() != 'utf-8':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# === Add project root to path ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# === Imports ===
from ai.deepseek_client import DeepSeekClient
from _fill_l4_l5_pipeline import THEMES, GRADE_THEMES

# === Paths ===
WORK_DIR = SCRIPT_DIR
PLAN_CSV = os.path.join(WORK_DIR, "generation_plan.csv")
OUTPUT_TASKS = os.path.join(WORK_DIR, "stage6_generated_tasks.json")
CHECKPOINT_FILE = os.path.join(WORK_DIR, "stage6_checkpoint.json")
REPORT_FILE = os.path.join(WORK_DIR, "stage6_generation_report.txt")

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(WORK_DIR, "stage6_log.txt"), encoding="utf-8")
    ]
)
logger = logging.getLogger("stage6")

# === Constants ===
CELLS_PER_CHECKPOINT = 1  # Save checkpoint after each cell
MAX_RETRIES_PER_CELL = 5
RETRY_BASE_DELAY = 30
GENERATION_TEMPERATURE = 0.3
GENERATION_MAX_TOKENS = 8192

# Level descriptions for prompts
LEVEL_DESCRIPTIONS = {
    4: "Стандартный олимпиадный уровень (L4): задачи средней сложности, требуют нестандартного мышления, "
       "но доступны участнику, знакомому с основными олимпиадными идеями для данного класса.",
    5: "Продвинутый олимпиадный уровень (L5): сложные задачи, требующие глубокого понимания, "
       "комбинации нескольких идей и изобретательности. Подходят для финальных этапов олимпиад."
}

# === Helper Functions ===


def load_generation_plan(csv_path):
    """Load generation_plan.csv and return list of cell dicts with adjusted_needed > 0."""
    cells = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            adjusted = int(row["adjusted_needed"])
            if adjusted > 0:
                cells.append({
                    "cell_key": row["cell_key"],
                    "grade": int(row["grade"]),
                    "level": int(row["level"]),
                    "theme_id": row["theme_id"],
                    "theme_name": row["theme_name"],
                    "subtopic_idx": int(row["subtopic_idx"]),
                    "subtopic": row["subtopic"],
                    "current_count": int(row["current_count"]),
                    "needed": int(row["needed"]),
                    "adjusted_needed": adjusted
                })
    logger.info(f"Loaded {len(cells)} cells needing generation (total adjusted_needed={sum(c['adjusted_needed'] for c in cells)})")
    return cells


def load_checkpoint(path):
    """Load checkpoint dict or return empty."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded checkpoint with {len(data.get('completed_cells', []))} completed cells")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load checkpoint: {e}. Starting fresh.")
    return {"completed_cells": [], "generated_tasks": [], "errors": []}


def save_checkpoint(path, data):
    """Save checkpoint dict to file atomically."""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        logger.info(f"Checkpoint saved: {len(data['completed_cells'])} cells done, {len(data['generated_tasks'])} tasks")
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")


# Valid JSON escape characters (the character after \ in a JSON string)
# NOTE: 'n', 't', 'r', 'b', 'f' are intentionally EXCLUDED. In DeepSeek
# responses, \n, \t, \r, \b, \f as two-char sequences inside JSON strings
# are almost always LaTeX commands (\notin, \times, \rightarrow, \begin,
# \frac) rather than JSON escape sequences. The sanitizer handles literal
# newlines/tabs/carriage returns separately (lines 175-183). Literal
# backspace (0x08) and form feed (0x0C) never appear in responses, so
# \b and \f are safe to exclude. Only keep actual JSON structural escapes.
_VALID_JSON_ESCAPES = frozenset({'"', '\\', '/', 'u'})


def sanitize_json_string(text):
    r"""Pre-process JSON text to fix common LLM output issues.
    
    Handles:
    1. Unescaped backslashes before LaTeX commands (\(, \), \[, \], \phi, \ker, \cap, etc.)
       — ANY \ followed by a non-valid-JSON-escape character inside a JSON string
    2. Unescaped control characters (literal newlines, tabs) inside string values
    3. Unescaped " characters inside JSON string values (literal quotes in text content)
       — uses look-ahead heuristic: if " is followed by , } ] : or EOF -> structural close
       — otherwise -> literal quote, escape as \"
    4. Trailing commas before ] and }
    5. Truncation: ensure the JSON ends with proper closing brackets
    """
    import re
    
    # Process the text char by char, tracking whether we're inside a JSON string.
    # When we see \ inside a string, look at the next character:
    #   - if it's a valid JSON escape (", \, /, u) -> keep as-is
    #   - if it's NOT valid (e.g., n, t, r, b, f, (, ), [, ], p, etc.) -> double the backslash
    # NOTE: n, t, r, b, f are intentionally excluded because they represent
    # LaTeX commands (\notin, \times, \rightarrow, \begin, \frac) in practice.
    #
    # When we see " inside a string, look ahead at the next non-whitespace character:
    #   - if it's , } ] : or EOF -> this " closes the JSON string (structural)
    #   - otherwise -> literal quote inside content, escape as \"
    result = []
    in_string = False
    pending_backslash = False
    for i, ch in enumerate(text):
        if pending_backslash:
            # Previous char was \ inside a string — decide what to do with it
            if ch in _VALID_JSON_ESCAPES:
                # Valid JSON escape — output the backslash as-is
                result.append('\\')
            else:
                # Invalid JSON escape (LaTeX \phi, \(, \cap, etc.) — double it
                result.append('\\\\')
            result.append(ch)
            pending_backslash = False
            continue
        if ch == '\\' and in_string:
            # Backslash inside a string — defer decision until next character
            pending_backslash = True
            continue
        if ch == '"':
            if in_string:
                # Inside a string — determine if this " is structural close or literal content.
                # Look ahead past whitespace: if next non-whitespace char is a JSON
                # structural delimiter, this is the closing quote. Otherwise, it's
                # a literal quote character inside the string content and needs escaping.
                j = i + 1
                while j < len(text) and text[j] in (' ', '\t', '\n', '\r'):
                    j += 1
                if j >= len(text) or text[j] in (',', '}', ']', ':'):
                    # Structural close — this " terminates the JSON string value
                    in_string = False
                    result.append('"')
                else:
                    # Literal quote inside string content — escape it as \"
                    result.append('\\"')
            else:
                # Opening a new JSON string (key or value)
                in_string = True
                result.append('"')
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            elif ord(ch) < 0x20 and ch not in ('\n', '\r', '\t'):
                # Other control characters — escape
                result.append(f'\\u{ord(ch):04x}')
            else:
                result.append(ch)
        else:
            result.append(ch)
    
    text = ''.join(result)
    
    # Remove trailing commas before closing brackets (outside strings)
    text = re.sub(r',\s*([\]}])', r'\1', text)
    
    # Find the true structural closing brace by tracking depth OUTSIDE strings.
    # This avoids the bug where rfind('}') finds } inside string values
    # (e.g., LaTeX \frac{1}{2}, set notation {1,2,3}, answer text containing }).
    in_str = False
    escaped = False
    depth = 0
    last_structural_brace = -1
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_str:
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    last_structural_brace = i
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    last_structural_brace = i
    
    # Only truncate if the text extends beyond the last structural closing brace
    if last_structural_brace > 0 and last_structural_brace < len(text) - 1:
        text = text[:last_structural_brace + 1]
    
    return text


def save_failed_response(text, cell_key):
    """Save failed JSON response to file for diagnostic purposes."""
    import hashlib
    dump_dir = os.path.join(WORK_DIR, "stage6_failed_responses")
    os.makedirs(dump_dir, exist_ok=True)
    h = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    path = os.path.join(dump_dir, f"failed_{cell_key.replace('|', '_')}_{h}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"Saved failed response to {path}")
    return path


def _find_structural_end(text):
    """Find the position of the LAST structural closing bracket (outside strings).
    
    Returns (end_pos, needs_completion) where:
      - end_pos: position of last structural } or ], or -1 if none found
      - needs_completion: list of closing brackets needed to complete JSON
    """
    in_str = False
    escaped = False
    depth = 0
    last_struct_end = -1
    needs = []
    
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_str:
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == '{':
                depth += 1
                needs.append('}')
            elif ch == '}':
                depth -= 1
                if needs and needs[-1] == '}':
                    needs.pop()
                if depth == 0:
                    last_struct_end = i
            elif ch == '[':
                depth += 1
                needs.append(']')
            elif ch == ']':
                depth -= 1
                if needs and needs[-1] == ']':
                    needs.pop()
                if depth == 0:
                    last_struct_end = i
    
    return last_struct_end, needs


def _try_parse_json(raw):
    """Try to parse raw text as JSON directly."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    return None


def _try_parse_with_completion(raw):
    """Try to parse by completing truncated JSON (appending missing closing brackets)."""
    end_pos, needs = _find_structural_end(raw)
    if end_pos > 0:
        candidate = raw[:end_pos + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # Try appending missing closing brackets
    if needs:
        candidate = raw + ''.join(reversed(needs))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


def _extract_tasks_known_structure(text):
    """Strategy 6: Extract tasks using known JSON structure patterns.
    
    When the JSON is unparseable due to unescaped quotes inside string values,
    this function uses regex to find task objects by matching known key patterns
    ("statement", "answer", "solution") and extracting their values.
    
    Returns parsed dict with "tasks" list, or None if extraction fails.
    """
    import re
    
    # Find all task objects using the known key pattern.
    # A task looks like: {"statement": "...", "answer": "...", "solution": "..."}
    # We need to find the content between { and } at the task level.
    
    # Strategy: find the outer {"tasks": [...]} first, or individual task objects.
    
    # First, try to find the tasks array: "tasks": [...]
    tasks_start = text.find('"tasks"')
    if tasks_start < 0:
        return None
    
    # Find the [ that opens the tasks array
    bracket_start = text.find('[', tasks_start)
    if bracket_start < 0:
        return None
    
    # Now find each task object within the array using structural depth tracking.
    # Walk through the array content, tracking {} depth, extracting complete objects.
    extracted_tasks = []
    
    i = bracket_start + 1
    array_depth = 1  # We're inside the outer [...]
    
    while i < len(text) and array_depth > 0:
        ch = text[i]
        if ch == ']':
            array_depth -= 1
            if array_depth == 0:
                break
            i += 1
            continue
        if ch == '[':
            array_depth += 1
            i += 1
            continue
        if ch == '{':
            # Found a task object — extract it using depth tracking
            obj_start = i
            obj_depth = 1
            j = i + 1
            in_str = False
            escaped = False
            while j < len(text) and obj_depth > 0:
                c = text[j]
                if escaped:
                    escaped = False
                    j += 1
                    continue
                if c == '\\' and in_str:
                    escaped = True
                    j += 1
                    continue
                if c == '"':
                    if in_str:
                        # Look ahead for structural delimiter (same heuristic as sanitizer)
                        k = j + 1
                        while k < len(text) and text[k] in (' ', '\t', '\n', '\r'):
                            k += 1
                        if k >= len(text) or text[k] in (',', '}', ']', ':'):
                            in_str = False  # Structural close
                        # else: literal quote inside string — keep in_str=True
                    else:
                        in_str = True  # Opening string
                    j += 1
                    continue
                if not in_str:
                    if c == '{':
                        obj_depth += 1
                    elif c == '}':
                        obj_depth -= 1
                j += 1
            
            if obj_depth == 0:
                obj_text = text[obj_start:j]
                # Now extract statement, answer, solution from this object text
                task = _extract_fields_from_task_obj(obj_text)
                if task and task.get("statement"):
                    extracted_tasks.append(task)
                i = j
            else:
                # Truncated/partial object at end of text — still try to extract fields.
                # The model may have stopped generation mid-sentence, so the closing "
                # (for the solution value) and } (for the task object) are missing.
                # _extract_fields_from_task_obj has a fallback for missing closing quotes.
                if obj_depth > 0:
                    obj_text = text[obj_start:]
                    task = _extract_fields_from_task_obj(obj_text)
                    if task and task.get("statement"):
                        extracted_tasks.append(task)
                i += 1
        else:
            i += 1
    
    if extracted_tasks:
        return {"tasks": extracted_tasks}
    return None


def _extract_fields_from_task_obj(obj_text):
    """Extract statement, answer, solution from a task object text using regex.
    
    Works with known keys: "statement", "answer", "solution".
    Finds the value between the key's opening " and the structural closing "
    (followed by , or } or whitespace-then-one-of-those).
    """
    import re
    task = {}
    
    for key in ("statement", "answer", "solution"):
        # Find the key: "key":
        pattern = rf'"\s*{re.escape(key)}\s*"\s*:\s*"'
        match = re.search(pattern, obj_text)
        if not match:
            continue
        
        value_start = match.end()  # Position after the opening "
        
        # Now find the structural closing " by scanning for " that is
        # followed by , } or whitespace-then-one-of-those
        i = value_start
        in_string = True  # We're inside the value string
        found_close = False
        
        while i < len(obj_text):
            ch = obj_text[i]
            if ch == '\\':
                # Skip escaped character
                i += 2
                continue
            if ch == '"':
                # Check if this " is a structural close
                j = i + 1
                while j < len(obj_text) and obj_text[j] in (' ', '\t', '\n', '\r'):
                    j += 1
                if j >= len(obj_text) or obj_text[j] in (',', '}', ']'):
                    # Structural close
                    value = obj_text[value_start:i]
                    task[key] = value
                    found_close = True
                    break
                # Otherwise, this is a literal quote — keep scanning
            i += 1
        
        if not found_close:
            # Try the rest of the text as the value if no proper close found
            task[key] = obj_text[value_start:]
    
    return task


def parse_json_response(response_text, save_on_failure=True):
    """Try to parse JSON from DeepSeek response. Handles markdown fences & common issues.
    
    Args:
        response_text: Raw response text from the API.
        save_on_failure: If True (default), saves failed responses to disk via save_failed_response().
                         Set to False for diagnostic scripts to avoid polluting the failed_responses dir.
    """
    text = response_text.strip()
    import re

    # Strategy 1: Direct parse
    result = _try_parse_json(text)
    if result is not None:
        return result

    # Strategy 2: Sanitized parse (handles newlines, trailing commas, LaTeX backslashes, unescaped quotes)
    sanitized = sanitize_json_string(text)
    result = _try_parse_json(sanitized)
    if result is not None:
        return result

    # Strategy 3: Sanitized + completion (handles truncated JSON)
    result = _try_parse_with_completion(sanitized)
    if result is not None:
        return result

    # Strategy 4: Handle markdown code fences
    pattern = r'```(?:json)?\s*([\s\S]*?)```'
    matches = re.findall(pattern, text)
    for match in matches:
        cleaned = match.strip()
        result = _try_parse_json(cleaned)
        if result is not None:
            return result
        sanitized = sanitize_json_string(cleaned)
        result = _try_parse_json(sanitized)
        if result is not None:
            return result
        result = _try_parse_with_completion(sanitized)
        if result is not None:
            return result

    # Strategy 5: Find JSON array or object with proper structural end
    for delimiter in ['[', '{']:
        start = text.find(delimiter)
        if start >= 0:
            segment = text[start:]
            end_pos, _ = _find_structural_end(segment)
            if end_pos > 0:
                segment = segment[:end_pos + 1]
                result = _try_parse_json(segment)
                if result is not None:
                    return result
                sanitized = sanitize_json_string(segment)
                result = _try_parse_json(sanitized)
                if result is not None:
                    return result
                result = _try_parse_with_completion(sanitized)
                if result is not None:
                    return result

    # Strategy 6: Extract tasks using known JSON structure patterns
    # Handles cases where unescaped " inside string values break standard parsing
    result = _extract_tasks_known_structure(text)
    if result is not None:
        return result
    sanitized = sanitize_json_string(text)
    result = _extract_tasks_known_structure(sanitized)
    if result is not None:
        return result

    # Save failed response for diagnosis (opt-in to avoid polluting dir during diagnostics)
    if save_on_failure:
        save_failed_response(response_text, "unknown")

    raise ValueError(f"Could not parse JSON from response. First 200 chars: {text[:200]}")


def compute_task_identifier(statement):
    """Compute SHA-256 hash of statement, return first 12 hex chars."""
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()[:12]


def normalize_text(text):
    """Normalize text for comparison: strip, lowercase, remove non-alphanumeric."""
    if not text:
        return ""
    import re
    text = text.strip().lower()
    text = re.sub(r'[^a-zа-яё0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def build_generation_prompt(cell):
    """Build the DeepSeek prompt for generating tasks for a specific cell."""
    grade = cell["grade"]
    level = cell["level"]
    count = cell["adjusted_needed"]
    theme_name = cell["theme_name"]
    subtopic = cell["subtopic"]
    theme_id = cell["theme_id"]
    level_desc = LEVEL_DESCRIPTIONS.get(level, "Олимпиадный уровень")

    # Build theme context: show all subtopics for the theme
    theme_data = THEMES.get(theme_id, {})
    all_subtopics = theme_data.get("subtopics", [])
    subtopics_str = "\n".join([f"  {i}. {s}" for i, s in enumerate(all_subtopics)])

    prompt = f"""Ты — составитель олимпиадных задач по математике. Твоя задача — создать {count} оригинальных олимпиадных задач, соответствующих указанным параметрам.

ПАРАМЕТРЫ ЗАДАЧ:
- Класс: {grade}
- Уровень: {level_desc}
- Тема: {theme_name} (ID: {theme_id})
- Подтема: {subtopic}
- Количество задач: {count}

ТЕМАТИЧЕСКИЙ КОНТЕКСТ:
Все подтемы темы "{theme_name}":
{subtopics_str}

Требуемая подтема: "{subtopic}" (индекс {cell['subtopic_idx']})

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Каждая задача должна быть ОРИГИНАЛЬНОЙ — не копировать существующие олимпиадные задачи
2. Задача должна соответствовать указанному классу ({grade}) по сложности и используемому материалу
3. Задача должна быть олимпиадного уровня ({'L4' if level == 4 else 'L5'}) — требовать нестандартного мышления
4. Задача должна точно соответствовать указанной подтеме "{subtopic}"
5. Используй LaTeX для математических формул (обрамляй в \\( ... \\) для инлайн и \\[ ... \\] для выносных)
6. Решение должно быть полным, подробным и математически корректным
7. Ответ должен быть чётким и однозначным

ФОРМАТ ОТВЕТА (строго JSON):
```json
{{
  "tasks": [
    {{
      "statement": "Условие задачи с LaTeX-формулами",
      "answer": "Краткий ответ",
      "solution": "Подробное решение с обоснованием"
    }}
  ]
}}
```

Убедись, что сгенерировано ровно {count} задач. Каждая задача должна быть уникальной по формулировке и идее решения."""
    return prompt


def build_system_prompt():
    """Build system prompt for the generation."""
    return """Ты — эксперт-составитель олимпиадных задач по математике для школьников 5-11 классов.

ТВОЯ ЗАДАЧА: Создавать оригинальные, качественные олимпиадные задачи строго по указанным параметрам (класс, уровень, тема, подтема).

ПРИНЦИПЫ:
1. ОРИГИНАЛЬНОСТЬ: Каждая задача должна быть уникальной, не копировать известные олимпиадные задачи
2. СООТВЕТСТВИЕ: Задача должна точно соответствовать указанному классу и подтеме
3. КАЧЕСТВО: Условие должно быть чётким, решение — полным и математически строгим
4. СЛОЖНОСТЬ: L4 — средняя олимпиадная сложность, L5 — высокая олимпиадная сложность
5. ОФОРМЛЕНИЕ: Используй LaTeX для всех математических формул

Всегда выводи результат строго в формате JSON."""


def validate_generated_tasks(tasks, cell, expected_count):
    """Validate generated tasks have required fields. Returns (valid_tasks, errors)."""
    valid = []
    errors = []

    if not isinstance(tasks, list):
        # Maybe it's wrapped in {"tasks": [...]}
        if isinstance(tasks, dict) and "tasks" in tasks:
            tasks = tasks["tasks"]
        else:
            errors.append(f"Response is not a list or {{'tasks': [...]}}")
            return valid, errors

    for i, task in enumerate(tasks):
        task_errors = []

        if not isinstance(task, dict):
            task_errors.append(f"Task {i} is not a dict")
            continue

        statement = task.get("statement", "").strip()
        answer = task.get("answer", "").strip()
        solution = task.get("solution", "").strip()

        if not statement:
            task_errors.append(f"Task {i}: missing or empty 'statement'")
        if not answer:
            task_errors.append(f"Task {i}: missing or empty 'answer'")
        if not solution:
            task_errors.append(f"Task {i}: missing or empty 'solution'")

        if task_errors:
            errors.append("; ".join(task_errors))
            continue

        # Attach cell metadata
        task_id = compute_task_identifier(statement)
        task["task_id"] = task_id
        task["cell_key"] = cell["cell_key"]
        task["grade"] = cell["grade"]
        task["level"] = cell["level"]
        task["theme_id"] = cell["theme_id"]
        task["theme_name"] = cell["theme_name"]
        task["subtopic"] = cell["subtopic"]
        task["subtopic_idx"] = cell["subtopic_idx"]
        task["source"] = "deepseek_generation_stage6"
        task["generated_at"] = datetime.now().isoformat()

        valid.append(task)

    if len(valid) < expected_count:
        logger.warning(f"Only {len(valid)}/{expected_count} valid tasks for {cell['cell_key']}")

    return valid, errors


def generate_for_cell(client, cell):
    """Generate tasks for one cell. Returns (generated_tasks, error_message).

    Accumulates tasks across retry attempts. If a response is truncated (partial
    JSON with fewer tasks than adjusted_needed), we retry up to MAX_RETRIES times.
    Each retry calls the API again with the same prompt; the model may produce
    different tasks or a more complete response.
    """
    count = cell["adjusted_needed"]
    cell_key = cell["cell_key"]
    logger.info(f"Generating {count} tasks for {cell_key} ({cell['theme_name']} / {cell['subtopic']})")

    prompt = build_generation_prompt(cell)
    system_prompt = build_system_prompt()

    all_valid_tasks = []

    for attempt in range(MAX_RETRIES_PER_CELL):
        try:
            remaining = count - len(all_valid_tasks)
            if remaining <= 0:
                break

            logger.info(f"  Attempt {attempt + 1}/{MAX_RETRIES_PER_CELL} (need {remaining} more)...")

            response_text = client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=GENERATION_TEMPERATURE,
                max_tokens=GENERATION_MAX_TOKENS,
                response_format={"type": "json_object"}
            )

            # Save raw response for diagnostics (first attempt only)
            if attempt == 0:
                dump_dir = os.path.join(WORK_DIR, "stage6_failed_responses")
                os.makedirs(dump_dir, exist_ok=True)
                safe_key = cell_key.replace("|", "_")
                raw_path = os.path.join(dump_dir, f"raw_{safe_key}.txt")
                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(response_text)
                logger.info(f"  Raw response saved to {raw_path}")

            # Parse response
            parsed = parse_json_response(response_text)

            # Validate — collect any valid tasks
            valid_tasks, validation_errors = validate_generated_tasks(parsed, cell, count)
            all_valid_tasks.extend(valid_tasks)

            if len(all_valid_tasks) >= count:
                logger.info(f"  [OK] Collected {len(all_valid_tasks)} valid tasks for {cell_key}")
                return all_valid_tasks, None
            elif len(valid_tasks) > 0:
                logger.info(f"  -> Got {len(valid_tasks)} tasks this attempt. Total collected: {len(all_valid_tasks)}/{count}")
                # Retry to collect more
                if attempt < MAX_RETRIES_PER_CELL - 1:
                    wait = RETRY_BASE_DELAY * (attempt + 1)
                    logger.info(f"  Retrying for remaining {count - len(all_valid_tasks)} tasks in {wait}s...")
                    time.sleep(wait)
            else:
                error_msg = f"No valid tasks this attempt: {validation_errors}"
                logger.warning(f"   {error_msg}")
                if attempt < MAX_RETRIES_PER_CELL - 1:
                    wait = RETRY_BASE_DELAY * (attempt + 1)
                    logger.info(f"  Retrying in {wait}s...")
                    time.sleep(wait)

        except Exception as e:
            error_msg = f"Exception: {e}"
            logger.warning(f"   {error_msg}")
            traceback.print_exc()
            if attempt < MAX_RETRIES_PER_CELL - 1:
                wait = RETRY_BASE_DELAY * (attempt + 1)
                logger.info(f"  Retrying in {wait}s...")
                time.sleep(wait)

    if len(all_valid_tasks) > 0:
        logger.warning(f"  [!] Only collected {len(all_valid_tasks)}/{count} tasks for {cell_key} after {MAX_RETRIES_PER_CELL} attempts")
        return all_valid_tasks, None

    return [], f"Failed after {MAX_RETRIES_PER_CELL} attempts"


def write_report(report_path, cells, generated_tasks, errors_by_cell, elapsed):
    """Write generation report."""
    total_needed = sum(c["adjusted_needed"] for c in cells)
    total_generated = len(generated_tasks)
    total_errors = sum(len(e) for e in errors_by_cell.values())

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 6: TARGETED GENERATION REPORT\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
        f.write(f"DURATION: {elapsed:.1f}s\n\n")

        f.write("SUMMARY:\n")
        f.write(f"  Cells needing generation: {len(cells)}\n")
        f.write(f"  Total adjusted_needed:   {total_needed}\n")
        f.write(f"  Total generated:          {total_generated}\n")
        f.write(f"  Total errors:             {total_errors}\n")
        f.write(f"  Coverage:                 {total_generated}/{total_needed} ({100*total_generated/max(total_needed,1):.1f}%)\n\n")

        f.write("PER-CELL RESULTS:\n")
        f.write(f"{'Cell Key':24s} {'Need':5s} {'Got':5s} {'Status':12s}\n")
        f.write("-" * 70 + "\n")

        generated_by_cell = {}
        for t in generated_tasks:
            ck = t["cell_key"]
            generated_by_cell.setdefault(ck, []).append(t)

        for cell in cells:
            ck = cell["cell_key"]
            got = len(generated_by_cell.get(ck, []))
            need = cell["adjusted_needed"]
            errs = errors_by_cell.get(ck, [])
            if got >= need:
                status = "OK"
            elif got > 0:
                status = "PARTIAL"
            else:
                status = "FAILED" if errs else "NO_TASKS"
            f.write(f"{ck:24s} {need:5d} {got:5d} {status:12s}\n")
            for err in errs[:3]:
                f.write(f"  {'':24s}  ERROR: {err[:120]}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF STAGE 6 REPORT\n")
        f.write("=" * 70 + "\n")

    logger.info(f"Report written to {report_path}")


def main():
    """Main entry point."""
    print("=" * 70)
    print("  STAGE 6: TARGETED GENERATION")
    print("=" * 70)

    # Initialize DeepSeek client
    try:
        client = DeepSeekClient()
        logger.info("DeepSeekClient initialized")
    except Exception as e:
        logger.error(f"Failed to initialize DeepSeekClient: {e}")
        sys.exit(1)

    # Load generation plan
    if not os.path.exists(PLAN_CSV):
        logger.error(f"Generation plan not found: {PLAN_CSV}")
        sys.exit(1)

    cells = load_generation_plan(PLAN_CSV)
    total_needed = sum(c["adjusted_needed"] for c in cells)
    logger.info(f"Need to generate {total_needed} tasks across {len(cells)} cells")

    # Load checkpoint
    checkpoint = load_checkpoint(CHECKPOINT_FILE)
    completed_set = set(checkpoint.get("completed_cells", []))
    generated_tasks = checkpoint.get("generated_tasks", [])
    errors_by_cell = {e["cell_key"]: e["errors"] for e in checkpoint.get("errors", [])}

    # Filter out already completed cells
    pending_cells = [c for c in cells if c["cell_key"] not in completed_set]
    already_done = len(cells) - len(pending_cells)
    logger.info(f"Checkpoint: {already_done} cells already completed, {len(pending_cells)} remaining")

    # Process each cell
    start_time = time.time()
    total_attempted = 0

    for idx, cell in enumerate(pending_cells):
        cell_key = cell["cell_key"]
        total_attempted += 1
        logger.info(f"\n[{total_attempted + already_done}/{len(cells)}] Processing {cell_key}...")

        tasks, error = generate_for_cell(client, cell)

        if tasks:
            generated_tasks.extend(tasks)
            logger.info(f"  -> Added {len(tasks)} tasks. Total: {len(generated_tasks)}")

        if error:
            errors_by_cell.setdefault(cell_key, []).append(error)

        # Save checkpoint
        completed_set.add(cell_key)
        checkpoint["completed_cells"] = list(completed_set)
        checkpoint["generated_tasks"] = generated_tasks
        checkpoint["errors"] = [{"cell_key": k, "errors": v} for k, v in errors_by_cell.items()]
        save_checkpoint(CHECKPOINT_FILE, checkpoint)

        # Save intermediate results every 5 cells
        if (total_attempted + already_done) % 5 == 0:
            tmp_output = OUTPUT_TASKS + ".tmp"
            with open(tmp_output, "w", encoding="utf-8") as f:
                json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
            logger.info(f"Intermediate save: {len(generated_tasks)} tasks to {tmp_output}")

        # Small delay between cells to avoid rate limiting
        if idx < len(pending_cells) - 1:
            time.sleep(3)

    # Final save
    with open(OUTPUT_TASKS, "w", encoding="utf-8") as f:
        json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
    logger.info(f"Final output saved: {len(generated_tasks)} tasks to {OUTPUT_TASKS}")

    # Write report
    elapsed = time.time() - start_time
    write_report(REPORT_FILE, cells, generated_tasks, errors_by_cell, elapsed)

    # Summary
    print("\n" + "=" * 70)
    print("  STAGE 6 COMPLETE")
    print("=" * 70)
    print(f"  Cells processed: {len(completed_set)}/{len(cells)}")
    print(f"  Tasks generated: {len(generated_tasks)}/{total_needed}")
    print(f"  Errors:          {sum(len(v) for v in errors_by_cell.values())}")
    print(f"  Duration:        {elapsed:.1f}s")
    print(f"  Output:          {OUTPUT_TASKS}")
    print(f"  Report:          {REPORT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
