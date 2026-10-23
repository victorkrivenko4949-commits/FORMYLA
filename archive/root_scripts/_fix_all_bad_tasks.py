# -*- coding: utf-8 -*-
"""
Fix ALL bad/stub/placeholder problem texts in olympiads.py.

Strategy:
  1. Import olympiads module -> find ALL problems with bad/stub text fields
  2. Classify by fixability:
     - FIXABLE (Type C/E/some B): solution field contains recoverable condition -> AI extraction
     - UNFIXABLE (Type A/some B): solution is also missing -> report for manual review
  3. For fixable problems: extract problem text from solution via OpenRouter AI (5 threads)
  4. Apply targeted text replacements to olympiads.py
  5. Verify syntax and re-import

Key challenge: olympiads.py uses Python's implicit string concatenation for long texts:
    'text': 'fragment1... '
            'fragment2... '
            'fragment3...',
This script properly handles this by parsing the multi-fragment span and replacing it
with a single contiguous string literal.

Usage:
    python _fix_all_bad_tasks.py

Requires:
    OPENROUTER_API_KEY in .env or environment
"""

import ast
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ── paths ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("pipeline/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = OUTPUT_DIR / "bad_tasks_cache.json"
REPORT_PATH = OUTPUT_DIR / "bad_tasks_report.json"
BACKUP_SUFFIX = ".bak_all_bad_tasks"


# ── bad text patterns ──────────────────────────────────────────────────────

# Patterns that DEFINITELY indicate a bad/stub text
STUB_PATTERNS = [
    # Type A: "Решение не найдено"
    r'^Решение не найдено$',
    # Type B: very short non-descriptions
    r'^Домино\s*\([^)]*\)\.?\s*$',
    r'^См\.\s+задачу\s+\w+',
    r'^Задача\s+(про|о)\s+.+\([^)]+\)\.?\s*$',
    r'^Задача\s+\d+\s*\([^)]+\)\s*\.?\s*$',
    r'^Task\s+\d+\s*$',
    r'^Problem\s+\d+\s*$',
    r'^Условие\s+(задачи\s+)?\d*\s*$',
    r'^В разработке\s*$',
    r'^Нет данных\s*$',
    r'^\(нет\)\s*$',
    r'^Текст\s+(задачи\s+)?\d*\s*$',
    r'^\s*---\s*$',
    r'^\s*\.\.\.\s*$',
    r'^TBD\s*$',
    r'^TODO\s*$',
]

# Patterns for texts that are truncated/corrupted but NOT pure stubs
TRUNCATED_PATTERNS = [
    r'^(Задача|Текст|Условие)\s+\d+\s*(не\s+)?найдено',
    r'^Решение\s+не\s+найдено',
    r'^Не\s+удалось',
    r'(?i)не\s+восстановлено',
    r'^No\s+solution',
    r'^Missing\s+condition',
    r'^Incomplete',
]

SHORT_TEXT_MIN = 60  # below this is suspicious unless it contains math/numbers


def is_bad_text(text: str) -> tuple:
    """
    Classify a problem text as bad or not.

    Returns: (is_bad: bool, bad_type: str, reason: str)
      bad_type one of: 'A' (stub), 'B' (short/trivial),
                       'D' (placeholder/wildcard), 'E' (broken encoding),
                       'ok' (not bad)
    """
    if not text or not text.strip():
        return (True, 'A', 'Empty or whitespace-only text')

    stripped = text.strip()

    # Type A: known stub patterns
    for pat in STUB_PATTERNS:
        if re.match(pat, stripped):
            return (True, 'A', f'Stub pattern match: {pat}')

    # Type D: wildcard / placeholder patterns
    wildcard_patterns = [
        r'^[\s*\-\—\.\,\!\?]{0,10}$',
        r'^\d{1,3}\s*$',
        r'^[A-Za-zА-Яа-я]{1,5}\s*$',
    ]
    for pat in wildcard_patterns:
        if re.match(pat, stripped):
            return (True, 'D', f'Wildcard/placeholder match: {pat}')

    # Type E: broken encoding (common CJK / garbage bytes)
    broken_indicators = ['\u200b', '\ufeff', '\x00', '\x01', '\x02']
    for ch in broken_indicators:
        if ch in text:
            return (True, 'E', f'Broken encoding: contains {repr(ch)}')

    # Type B: very short texts
    if len(stripped) < SHORT_TEXT_MIN:
        # Allow if it contains substantial math content
        math_chars = len(re.findall(r'[$\\]', stripped))
        if math_chars < 3 and len(stripped.split()) < 5:
            return (True, 'B', f'Short text ({len(stripped)} chars, {len(stripped.split())} words)')

    # Truncated/corrupted
    for pat in TRUNCATED_PATTERNS:
        if re.search(pat, stripped):
            return (True, 'A', f'Truncated/corrupted pattern match: {pat}')

    return (False, 'ok', 'OK')


# ── detection ──────────────────────────────────────────────────────────────


def find_bad_tasks():
    """
    Import olympiads module and find all problems with bad text fields.

    OLYMPIADS_DB is a list of dicts, each with keys:
      id, olympiad, olympiad_title, year, grade, round, round_title,
      problems (list), source_url, source_name

    Returns: list of dicts:
      {
        'entry_id': int,        # the entry.id field (unique identifier)
        'set_key': str,         # the olympiad slug (e.g. 'euler')
        'num': int,             # problem number within the set
        'text': str,            # the old/bad text
        'solution': str,        # solution field (may be usable for AI extraction)
        'answer': str,
        'bad_type': str (A/B/D/E),
        'reason': str,
        'fixable': bool,
      }
    """
    # Import olympiads module dynamically
    import importlib.util
    spec = importlib.util.spec_from_file_location("olympiads", "olympiads.py")
    oly = importlib.util.module_from_spec(spec)
    # Suppress print output during import
    import io
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        spec.loader.exec_module(oly)
    finally:
        sys.stdout = old_stdout

    db = getattr(oly, 'OLYMPIADS_DB', None)
    if db is None:
        print("ERROR: olympiads module has no OLYMPIADS_DB attribute!")
        return []
    if not isinstance(db, list):
        print(f"ERROR: OLYMPIADS_DB is {type(db).__name__}, expected list!")
        return []

    bad_tasks = []
    type_counts = Counter()

    for entry in db:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get('id')
        set_key = entry.get('olympiad', 'unknown')
        problems = entry.get('problems', [])
        if not isinstance(problems, list):
            continue

        for prob in problems:
            if not isinstance(prob, dict):
                continue
            text = prob.get('text', '')
            is_bad, bad_type, reason = is_bad_text(text)
            if is_bad:
                solution = prob.get('solution', '') or ''
                type_counts[bad_type] += 1

                # Determine fixability
                # Type D/E are never fixable (no recoverable content)
                # Type A is fixable if solution has substantial content
                # Type B is fixable if solution has substantial content
                fixable = False
                if bad_type in ('A', 'B'):
                    sol_stripped = solution.strip()
                    if len(sol_stripped) > 50 and not is_bad_text(sol_stripped)[0]:
                        fixable = True

                bad_tasks.append({
                    'entry_id': entry_id,
                    'set_key': set_key,
                    'num': prob.get('num', 0),
                    'text': text,
                    'solution': solution,
                    'answer': prob.get('answer', ''),
                    'bad_type': bad_type,
                    'reason': reason,
                    'fixable': fixable,
                })

    print(f"\nFound {len(bad_tasks)} bad tasks by type: {dict(type_counts)}")
    fixable_count = sum(1 for t in bad_tasks if t['fixable'])
    print(f"Fixable: {fixable_count}, Unfixable: {len(bad_tasks) - fixable_count}")

    return bad_tasks


# ── AI extraction ──────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
AI_MODEL = 'deepseek/deepseek-chat'

EXTRACT_PROMPT = """Ты — эксперт по олимпиадной математике. Из предоставленного решения задачи восстанови точный и полный текст условия задачи на русском языке.

Требования к ответу:
1. Ответ должен содержать ТОЛЬКО текст условия задачи, без лишних комментариев.
2. Если в решении недостаточно информации для восстановления точного условия, напиши: "Не удалось восстановить условие задачи."
3. Используй LaTeX-разметку ($$...$$, $...$, \\[\\], \\(...\\)) где необходимо.
4. Сохрани все числовые данные, имена, геометрические обозначения из решения.
5. Не добавляй слова "Задача" или "Условие:" в начале."""


def _call_ai(prompt: str, max_retries: int = 3) -> str:
    """Call OpenRouter AI with the given prompt. Returns response text."""
    import requests

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': AI_MODEL,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 2048,
                    'temperature': 0.3,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content'].strip()
            return content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  AI call failed (attempt {attempt + 1}): {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  AI call FAILED after {max_retries} attempts: {e}")
                return ""

    return ""


def _extract_problem_text_from_solution(solution: str, answer: str = '') -> str:
    """Use AI to extract problem text from a solution."""
    prompt = EXTRACT_PROMPT + f"\n\nРешение:\n{solution}\n"
    if answer:
        prompt += f"\nОтвет: {answer}\n"
    result = _call_ai(prompt)
    return result.strip()


def extract_texts_parallel(tasks: list, max_workers: int = 5) -> dict:
    """
    Run AI extraction on fixable tasks in parallel.

    Returns: dict mapping 'set_key_num' (e.g., 'euler_5') -> new_text
    """
    results = {}
    completed = 0
    total = len(tasks)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for task in tasks:
            key = f"{task['set_key']}_{task['num']}"
            future = executor.submit(
                _extract_problem_text_from_solution,
                task['solution'],
                task.get('answer', ''),
            )
            future_map[future] = key

        for future in as_completed(future_map):
            key = future_map[future]
            completed += 1
            try:
                text = future.result()
                if text and 'Не удалось восстановить' not in text:
                    results[key] = text
                    print(f"  [{completed}/{total}] {key}: extracted ({len(text)} chars)")
                else:
                    print(f"  [{completed}/{total}] {key}: FAILED to extract")
            except Exception as e:
                print(f"  [{completed}/{total}] {key}: ERROR: {e}")

    return results


# ── file manipulation ──────────────────────────────────────────────────────


def _escape_py_string(text: str) -> str:
    """
    Convert a Python string value to its source code representation
    for use as a single-quoted string literal.

    This handles:
      - backslash: \\ -> \\\\
      - single quote: ' -> \\'
      - newlines: \\n -> \\\\n
      - other control chars
    """
    result = []
    for ch in text:
        if ch == '\\':
            result.append('\\\\')
        elif ch == "'":
            result.append("\\'")
        elif ch == '\n':
            result.append('\\n')
        elif ch == '\r':
            result.append('\\r')
        elif ch == '\t':
            result.append('\\t')
        elif ord(ch) < 32:
            result.append(f'\\x{ord(ch):02x}')
        else:
            result.append(ch)
    return ''.join(result)


def _unescape_py_fragment(fragment: str) -> str:
    """
    Unescape a Python string literal fragment to get the actual string value.
    Handles: \\', \\\\, \\n, \\t, \\r, \\xNN
    """
    result = []
    i = 0
    while i < len(fragment):
        if fragment[i] == '\\' and i + 1 < len(fragment):
            next_ch = fragment[i + 1]
            if next_ch == '\\':
                result.append('\\')
                i += 2
            elif next_ch == "'":
                result.append("'")
                i += 2
            elif next_ch == 'n':
                result.append('\n')
                i += 2
            elif next_ch == 't':
                result.append('\t')
                i += 2
            elif next_ch == 'r':
                result.append('\r')
                i += 2
            elif next_ch == 'x' and i + 3 < len(fragment):
                try:
                    result.append(chr(int(fragment[i + 2:i + 4], 16)))
                    i += 4
                except ValueError:
                    result.append(fragment[i])
                    i += 1
            else:
                result.append(fragment[i])
                i += 1
        else:
            result.append(fragment[i])
            i += 1
    return ''.join(result)


# (removed _find_text_span v1/v2 — replaced by _find_simple_text_span below)


def _find_simple_text_span(content: str, entry_id: int, problem_num: int) -> tuple:
    """
    Find the span (start, end) of the 'text' field value for problem
    `problem_num` in entry with id `entry_id`, handling implicit
    string concatenation.

    olympiads.py stores long string values as:
        'text': 'fragment1... '
                'fragment2... '
                'fragment3...',

    This function locates the opening quote of the first fragment and the
    closing quote of the last fragment, returning absolute byte positions.

    Returns: (span_start, span_end) or (-1, -1)
    """
    # Find the entry by 'id' field
    id_pattern = re.compile(
        r"'id'\s*:\s*" + re.escape(str(entry_id)) + r"\s*(?:[,}])"
    )
    id_match = id_pattern.search(content)
    if not id_match:
        return (-1, -1)

    # Scan backward from id_match to find the opening '{' of this dict
    dict_start = id_match.start()
    while dict_start > 0:
        if content[dict_start] == '{':
            break
        dict_start -= 1
    if content[dict_start] != '{':
        return (-1, -1)

    # Scope the dict (track brace depth for Python dict, NOT LaTeX)
    depth = 0
    dict_end = len(content)
    for i in range(dict_start, len(content)):
        c = content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                dict_end = i + 1
                break
    # NOTE: brace depth tracking for DICT SCOPING is safe because we're
    # scanning raw source code and Python dict braces are unambiguous.
    # This is different from tracking braces INSIDE a string value.

    scope = content[dict_start:dict_end]

    # Find 'num': problem_num within this scope
    num_pattern = re.compile(r"'num'\s*:\s*" + re.escape(str(problem_num)) + r"\s*(?:[,}])")
    num_match = num_pattern.search(scope)
    if not num_match:
        return (-1, -1)

    prob_start = num_match.start()

    # Find 'text': after 'num':
    text_key_match = re.search(r"'text'\s*:", scope[prob_start:])
    if not text_key_match:
        return (-1, -1)

    # Start of text value (after 'text': and whitespace)
    val_rel = prob_start + text_key_match.end()
    while val_rel < len(scope) and scope[val_rel] in ' \t\n\r':
        val_rel += 1

    if val_rel >= len(scope) or scope[val_rel] != "'":
        return (-1, -1)

    # Now find the end of the multi-fragment value.
    # We scan character by character within the string value,
    # tracking when we're inside a single-quoted fragment.
    #
    # IMPORTANT: Do NOT track brace depth here — the text value may
    # contain LaTeX with unbalanced braces like \begin{cases}...\end{cases}
    # or single braces. Brace tracking would break.

    pos = val_rel + 1  # skip opening quote of first fragment
    last_close = -1  # position of the closing quote of the last fragment found

    while pos < len(scope):
        ch = scope[pos]

        # Handle escape sequences: skip the escaped char after backslash
        if ch == '\\' and pos + 1 < len(scope):
            pos += 2
            continue

        if ch == "'":
            # Possible closing quote of a fragment
            # Check what follows: whitespace + another ' = continuation
            after = pos + 1
            while after < len(scope) and scope[after] in ' \t\n\r':
                after += 1

            if after < len(scope) and scope[after] == "'":
                # This is the end of a fragment, and there's another fragment
                last_close = pos
                pos = after + 1  # skip opening quote of next fragment
                continue
            else:
                # This is the FINAL closing quote of the last fragment
                last_close = pos
                break

        pos += 1

    if last_close == -1:
        return (-1, -1)

    span_start_abs = dict_start + val_rel
    span_end_abs = dict_start + last_close + 1  # +1 to include the closing quote

    return (span_start_abs, span_end_abs)


def apply_fixes_to_file(fixes: list, filepath: str = "olympiads.py") -> int:
    """
    Apply fixes to olympiads.py by replacing old text values with new ones.

    Each fix: {'set_key': str, 'num': int, 'old_text': str, 'new_text': str}

    This handles implicit string concatenation by finding the full span
    of the multi-fragment text value (from opening quote to closing quote
    of the last fragment) and replacing it with a single contiguous string.

    Returns: number of successfully applied fixes
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    applied = 0
    errors = []

    for idx, fix in enumerate(fixes):
        set_key = fix['set_key']
        problem_num = fix['num']
        old_text = fix['old_text']
        new_text = fix['new_text']

        escaped_new = _escape_py_string(new_text)

        # Find the span of the text value in the file
        span_start, span_end = _find_simple_text_span(content, fix.get('entry_id', 0), problem_num)

        if span_start == -1:
            errors.append(f"  Fix #{idx}: {set_key}#{problem_num} — could not find text field in file")
            continue

        # Verify: the text in the span should match old_text when parsed
        raw_span = content[span_start:span_end]
        # Remove surrounding quotes
        if raw_span.startswith("'") and raw_span.endswith("'"):
            inner = raw_span[1:-1]
            # Unescape
            actual_value = _unescape_py_fragment(inner)
            if actual_value != old_text:
                # The text may differ slightly (e.g., trailing whitespace differences)
                # Try normalizing both
                norm_actual = actual_value.strip()
                norm_old = old_text.strip()
                if norm_actual != norm_old:
                    errors.append(
                        f"  Fix #{idx}: {set_key}#{problem_num} — text mismatch! "
                        f"Found ({len(actual_value)} chars) != expected old_text ({len(old_text)} chars)"
                    )
                    continue
        else:
            errors.append(f"  Fix #{idx}: {set_key}#{problem_num} — span doesn't look like a quoted string: {raw_span[:50]}...")
            continue

        # Replace the span
        replacement = f"'{escaped_new}'"
        content = content[:span_start] + replacement + content[span_end:]
        applied += 1
        print(f"  Fixed #{idx}: {set_key}#{problem_num} ({len(old_text)}->{len(new_text)} chars)")

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(err)

    return applied


# ── verification ────────────────────────────────────────────────────────────


def verify_file(filepath: str = "olympiads.py") -> bool:
    """Verify that olympiads.py has valid Python syntax."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print("[OK] Syntax OK")
        return True
    except SyntaxError as e:
        print(f" SYNTAX ERROR: {e}")
        # Show context around error
        lines = source.split('\n')
        if e.lineno:
            start = max(0, e.lineno - 3)
            end = min(len(lines), e.lineno + 2)
            print(f"  Context (line {e.lineno}):")
            for ln in range(start, end):
                marker = " >>>" if ln == e.lineno - 1 else "    "
                print(f"  {marker} {ln + 1}: {lines[ln]}")
        return False


def reimport_olympiads(filepath: str = "olympiads.py") -> bool:
    """Try to re-import the olympiads module after fixes."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("olympiads_verify", filepath)
        module = importlib.util.module_from_spec(spec)
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            spec.loader.exec_module(module)
        finally:
            sys.stdout = old_stdout

        db = getattr(module, 'OLYMPIADS_DB', None)
        if db is None:
            print(" Re-import FAILED: no OLYMPIADS_DB attribute")
            return False

        entry_count = sum(
            1 for entry in db
            if isinstance(entry, dict) and isinstance(entry.get('problems', []), list)
            for _ in entry['problems']
        )
        set_count = len(db)
        print(f"[OK] Re-import OK: {set_count} sets, ~{entry_count} problems total")
        return True
    except Exception as e:
        print(f" Re-import FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ── backup ──────────────────────────────────────────────────────────────────


def backup_file(filepath: str = "olympiads.py"):
    """Create a backup of the file."""
    backup_path = filepath + BACKUP_SUFFIX
    if not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)
        print(f"Backup created: {backup_path}")
    else:
        print(f"Backup already exists: {backup_path} (not overwritten)")


# ─── cache helpers ──────────────────────────────────────────────────────────


def load_cache() -> dict:
    """Load cached AI extraction results."""
    if CACHE_PATH.exists():
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    """Save cache."""
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"Cache saved: {len(cache)} entries -> {CACHE_PATH}")


def save_report(bad_tasks: list):
    """Save full report of bad tasks."""
    report = {
        'total': len(bad_tasks),
        'by_type': dict(Counter(t['bad_type'] for t in bad_tasks)),
        'fixable_count': sum(1 for t in bad_tasks if t['fixable']),
        'unfixable_count': sum(1 for t in bad_tasks if not t['fixable']),
        'bad_tasks': bad_tasks,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"Report saved: {REPORT_PATH}")


# ── main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("FIX ALL BAD TASKS IN olympiads.py")
    print("=" * 60)

    # Step 1: Find bad tasks
    print("\n─── Step 1: Find bad tasks ───")
    bad_tasks = find_bad_tasks()
    if not bad_tasks:
        print("No bad tasks found. Exiting.")
        return

    save_report(bad_tasks)

    fixable = [t for t in bad_tasks if t['fixable']]
    unfixable = [t for t in bad_tasks if not t['fixable']]
    print(f"\nFixable: {len(fixable)}")
    print(f"Unfixable: {len(unfixable)}")
    if unfixable:
        print("  Unfixable tasks (need manual review):")
        for t in unfixable[:10]:
            print(f"    {t['set_key']}#{t['num']} (type {t['bad_type']}): {t['text'][:60]}...")
        if len(unfixable) > 10:
            print(f"    ... and {len(unfixable) - 10} more")

    if not fixable:
        print("No fixable tasks. Exiting.")
        return

    # Step 2: Load / clean cache
    print("\n─── Step 2: Load AI extraction cache ───")
    cache = load_cache()
    print(f"  Cache has {len(cache)} entries before cleaning")

    # Step 2b: Clean invalid cache entries
    cleaned = 0
    keys_to_delete = []
    for key, val in cache.items():
        if val is None or not val.strip():
            keys_to_delete.append(key)
        elif len(val) < 20:
            keys_to_delete.append(key)
        # Check if this cache entry refers to a task that still has old_text
        # (i.e., the cached text is the same as old_text — extraction failed)
        for task in fixable:
            task_key = f"{task['set_key']}_{task['num']}"
            if task_key == key and val.strip() == task['text'].strip():
                keys_to_delete.append(key)
                break

    for k in set(keys_to_delete):
        del cache[k]
        cleaned += 1

    if cleaned:
        print(f"  Cleaned {cleaned} invalid cache entries")
        save_cache(cache)
    else:
        print("  No invalid cache entries found")

    # Step 3: AI extraction for uncached tasks
    print("\n─── Step 3: AI extraction ───")
    if not OPENROUTER_API_KEY:
        print("  WARNING: No OPENROUTER_API_KEY set! Skipping AI extraction.")
        print("  Only cached tasks will be available.")
    else:
        tasks_to_extract = []
        for t in fixable:
            key = f"{t['set_key']}_{t['num']}"
            if key not in cache:
                tasks_to_extract.append(t)

        if tasks_to_extract:
            print(f"  Extracting {len(tasks_to_extract)} uncached tasks via AI...")
            new_results = extract_texts_parallel(tasks_to_extract, max_workers=5)
            cache.update(new_results)
            save_cache(cache)
        else:
            print("  All fixable tasks are already cached.")

    # Step 4: Build fixes list
    print("\n─── Step 4: Build fixes ───")
    fixes = []
    for t in fixable:
        key = f"{t['set_key']}_{t['num']}"
        new_text = cache.get(key, '')
        if new_text and len(new_text) > 20 and new_text != t['text']:
            fixes.append({
                'set_key': t['set_key'],
                'num': t['num'],
                'entry_id': t['entry_id'],
                'old_text': t['text'],
                'new_text': new_text,
            })

    print(f"  {len(fixes)} fixes to apply")

    if not fixes:
        print("No fixes to apply. Exiting.")
        return

    # Step 5: Apply fixes
    print("\n─── Step 5: Apply fixes ───")
    backup_file()

    applied = apply_fixes_to_file(fixes)
    print(f"\n  Applied {applied} / {len(fixes)} fixes")

    # Step 6: Verify
    print("\n─── Step 6: Verify ───")
    verify_file()
    reimport_olympiads()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total bad tasks found: {len(bad_tasks)}")
    print(f"  Fixable: {len(fixable)}")
    print(f"  Unfixable: {len(unfixable)}")
    print(f"  Fixes applied: {applied} / {len(fixes)}")
    print(f"  Report: {REPORT_PATH}")
    print(f"  Cache: {CACHE_PATH}")
    print(f"  Backup: olympiads.py{BACKUP_SUFFIX}")
    print()


if __name__ == '__main__':
    main()
