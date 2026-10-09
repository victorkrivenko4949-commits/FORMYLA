#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grade 11 vsosh 2020 regional - Final fix.
Uses existing (already collected) DeepSeek responses:
  - Call 1: _last_11_call1_v6.txt (problems 6-7, already valid)
  - Call 2: _last_response_11_v4_call2.txt (problems 8-10, needs quote-aware parsing)

Avoids any new API calls. Uses manual field-by-field extraction
that handles unescaped quotes inside JSON string values.
"""
import ast
import json
import os
import sys
import shutil
import re

# Fix terminal encoding for Cyrillic output
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
os.environ['PYTHONIOENCODING'] = 'utf-8'

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

GRADE_11_INDEX = 1046


def fix_json_escapes(text):
    """Fix invalid backslash escapes in JSON string content."""
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c)
                result.append(nextc)
                i += 2
            else:
                result.append('\\\\')
                result.append(nextc)
                i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def extract_field_value(text, key, start_pos=0):
    """
    Extract the value of a JSON key from text, handling unescaped quotes.
    
    Strategy: after finding `"key":`, for string values, scan character by
    character. When we see a `"`, look ahead to check if it's the real closing
    quote (next non-whitespace char is `,`, `}`, or `]`).
    
    Returns (value_string_or_int, end_position) or (None, start_pos) if not found.
    """
    pattern = rf'"{re.escape(key)}"\s*:\s*'
    m = re.search(pattern, text[start_pos:])
    if not m:
        return None, start_pos
    key_end = start_pos + m.end()
    
    if key_end >= len(text):
        return None, key_end
    
    if text[key_end] == '"':
        # String value — handle unescaped quotes
        result_chars = []
        i = key_end + 1
        while i < len(text):
            c = text[i]
            if c == '\\':
                # Next char is escaped
                result_chars.append(c)
                i += 1
                if i < len(text):
                    result_chars.append(text[i])
                    i += 1
            elif c == '"':
                # Check if this is the end of the value
                # Look ahead for , or } or ] (skipping whitespace)
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',}]':
                    # This is the real closing quote
                    return ''.join(result_chars), j
                else:
                    # This is an unescaped quote inside the value
                    result_chars.append(c)
                    i += 1
            else:
                result_chars.append(c)
                i += 1
        # Hit end of text without finding closing quote
        return ''.join(result_chars), len(text)
    else:
        # Number or other value
        j = key_end
        while j < len(text) and text[j] not in ',}\n\r]':
            j += 1
        raw = text[key_end:j].strip()
        try:
            return int(raw), j
        except ValueError:
            return raw, j


def extract_problems_manual(text):
    """
    Extract problems from JSON-like text using field-by-field extraction.
    Handles unescaped quotes inside string values.
    
    Returns list of dicts with num, text, answer, solution.
    """
    # Strip markdown fences
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    
    text = text.strip()
    
    # Fix backslash escapes first
    text = fix_json_escapes(text)
    
    # Strategy 1: try direct json.loads (might work if there are no unescaped quotes)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"  Direct JSON parse succeeded: {len(data)} problems", flush=True)
            return data
    except json.JSONDecodeError as e:
        print(f"  Direct JSON parse failed: {e}", flush=True)
    
    # Strategy 2: find array bounds and extract problems one by one
    start = text.find('[')
    end = text.rfind(']')
    if start < 0 or end <= start:
        print("  ERROR: No array brackets found!", flush=True)
        return []
    
    array_text = text[start:end+1]
    
    # Find each '{...}' object with quote-aware brace matching
    problems = []
    i = 1  # skip '['
    while i < len(array_text):
        brace_start = array_text.find('{', i)
        if brace_start < 0 or brace_start >= len(array_text):
            break
        
        # Find matching '}' with quote awareness
        depth = 0
        brace_end = -1
        j = brace_start
        in_str = False
        while j < len(array_text):
            c = array_text[j]
            if c == '\\':
                j += 2
                continue
            if c == '"':
                in_str = not in_str
            if not in_str:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = j
                        break
            j += 1
        
        if brace_end <= brace_start:
            i = brace_start + 1
            continue
        
        obj_text = array_text[brace_start:brace_end + 1]
        
        # Extract fields using quote-aware extraction
        obj = {}
        pos = 0
        
        # Extract num
        val, pos = extract_field_value(obj_text, 'num', pos)
        if val is not None:
            obj['num'] = val
        
        # Extract text
        val, pos = extract_field_value(obj_text, 'text', pos)
        if val is not None:
            obj['text'] = val
        
        # Extract answer
        val, pos = extract_field_value(obj_text, 'answer', pos)
        if val is not None:
            obj['answer'] = val
        
        # Extract solution
        val, pos = extract_field_value(obj_text, 'solution', pos)
        if val is not None:
            obj['solution'] = val
        
        if 'num' in obj or 'text' in obj:
            problems.append(obj)
            print(f"  Extracted problem {obj.get('num', '?')}: "
                  f"text={str(obj.get('text',''))[:60]}...", flush=True)
        
        i = brace_end + 1
    
    print(f"  Manual extraction: {len(problems)} problems", flush=True)
    return problems


# ============================================================
def load_olympiads_db():
    with open('olympiads.py', 'r', encoding='utf-8') as f:
        content = f.read()
    tree = ast.parse(content)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
        ):
            entries = node.value.elts
            print(f"  Found OLYMPIADS_DB with {len(entries)} entries", flush=True)
            return content, entries
    print("ERROR: Could not find OLYMPIADS_DB!", flush=True)
    sys.exit(1)


def ast_to_dict(ast_node):
    if isinstance(ast_node, ast.Dict):
        result = {}
        for k, v in zip(ast_node.keys, ast_node.values):
            key = ast_to_dict(k)
            result[key] = ast_to_dict(v)
        return result
    elif isinstance(ast_node, ast.List):
        return [ast_to_dict(elem) for elem in ast_node.elts]
    elif isinstance(ast_node, ast.Constant):
        return ast_node.value
    elif isinstance(ast_node, ast.Str):
        return ast_node.s
    elif isinstance(ast_node, ast.Num):
        return ast_node.n
    elif isinstance(ast_node, ast.NameConstant):
        return ast_node.value
    elif isinstance(ast_node, ast.UnaryOp) and isinstance(ast_node.op, ast.USub):
        return -ast_to_dict(ast_node.operand)
    else:
        return None


def save_olympiads_db(db_list):
    print("Saving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11_v7.py')
        print("  Backup: olympiads_backup_grade11_v7.py", flush=True)
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes to olympiads.py", flush=True)


def validate_problems(problems, expected_nums=None):
    """Validate and renumber problems."""
    valid = []
    for p in problems:
        if not isinstance(p, dict):
            continue
        if not p.get('text', '').strip():
            continue
        num = p.get('num', 0)
        if isinstance(num, str) and num.isdigit():
            num = int(num)
        if not isinstance(num, int):
            num = 0
        if expected_nums and num in expected_nums:
            valid.append(p)
        elif not expected_nums:
            valid.append(p)
    
    # Renumber
    for i, p in enumerate(valid):
        if expected_nums:
            p['num'] = expected_nums[i] if i < len(expected_nums) else expected_nums[-1] + (i - len(expected_nums) + 1)
        else:
            p['num'] = 6 + i
    
    return valid


def main():
    print("=" * 60, flush=True)
    print("Grade 11 VSOSH 2020 Regional - Day 2 Fix (v7)", flush=True)
    print("=" * 60, flush=True)
    
    # Load olympiads.py
    content, ast_entries = load_olympiads_db()
    
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = ast_to_dict(entry)
        all_entries.append(d)
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    idx = GRADE_11_INDEX
    entry = all_entries[idx]
    existing_problems = entry.get('problems', [])
    
    print(f"\nEntry index {idx}: grade={entry.get('grade','?')}, id={entry.get('id','')}")
    print(f"  Existing problems: {len(existing_problems)}")
    
    has_day = any('day' in p for p in existing_problems)
    print(f"  Has 'day' field: {has_day}")
    
    if has_day:
        day2_count = sum(1 for p in existing_problems if p.get('day') == 2)
        if day2_count >= 5:
            print(f"  Already has {day2_count} Day 2 problems. Nothing to do.")
            return
    
    # ================================================================
    # LOAD EXISTING RESPONSES (NO NEW API CALLS)
    # ================================================================
    
    all_day2 = []
    
    # ---- Call 1: problems 6-7 from _last_11_call1_v6.txt ----
    call1_path = '_last_11_call1_v6.txt'
    if not os.path.exists(call1_path):
        print(f"ERROR: {call1_path} not found!", flush=True)
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Loading Call 1 (problems 6-7) from {call1_path}")
    print(f"{'='*60}")
    
    with open(call1_path, 'r', encoding='utf-8') as f:
        resp1 = f.read()
    print(f"  Loaded {len(resp1)} chars", flush=True)
    
    probs1 = extract_problems_manual(resp1)
    valid1 = validate_problems(probs1, expected_nums=[6, 7])
    print(f"  Valid: {len(valid1)} problems", flush=True)
    for p in valid1:
        txt = (p.get('text', '') or '')[:80]
        print(f"    Problem {p.get('num')}: {txt}", flush=True)
    
    if not valid1:
        print("  ERROR: No valid problems from Call 1!", flush=True)
        sys.exit(1)
    
    all_day2.extend(valid1)
    
    # ---- Call 2: problems 8-10 from _last_response_11_v4_call2.txt ----
    call2_path = '_last_response_11_v4_call2.txt'
    if not os.path.exists(call2_path):
        print(f"ERROR: {call2_path} not found!", flush=True)
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Loading Call 2 (problems 8-10) from {call2_path}")
    print(f"{'='*60}")
    
    with open(call2_path, 'r', encoding='utf-8') as f:
        resp2 = f.read()
    print(f"  Loaded {len(resp2)} chars", flush=True)
    
    probs2 = extract_problems_manual(resp2)
    valid2 = validate_problems(probs2, expected_nums=[8, 9, 10])
    print(f"  Valid: {len(valid2)} problems", flush=True)
    for p in valid2:
        txt = (p.get('text', '') or '')[:80]
        print(f"    Problem {p.get('num')}: {txt}", flush=True)
    
    if not valid2:
        print("  ERROR: No valid problems from Call 2!", flush=True)
        sys.exit(1)
    
    all_day2.extend(valid2)
    
    # ================================================================
    # APPLY TO ENTRY
    # ================================================================
    print(f"\n{'='*60}")
    print(f"Total: {len(all_day2)} problems from both calls")
    print(f"{'='*60}")
    
    # Renumber sequentially starting from 6
    for i, p in enumerate(all_day2):
        p['num'] = 6 + i
    
    print(f"  Using {len(all_day2)} problems for Day 2:")
    for p in all_day2:
        txt = (p.get('text', '') or '')[:80]
        print(f"    Problem {p['num']}: {txt}", flush=True)
    
    if len(all_day2) < 5:
        print(f"  WARNING: Only {len(all_day2)} Day 2 problems (expected 5).", flush=True)
        print(f"  Will still apply what we have.", flush=True)
    
    # Add day=2 to new problems
    for p in all_day2:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
    
    # Add day=1 to existing problems
    for p in existing_problems:
        p['day'] = 1
    
    # Append Day 2 problems
    existing_problems.extend(all_day2)
    
    print(f"\n  Total problems now: {len(existing_problems)}")
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")
    
    # Save olympiads.py
    save_olympiads_db(all_entries)
    
    # Update data/olympiads_db.py
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
        db_content += '\n'
        shutil.copy2(db_py_path, db_py_path + '.bak7')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
    
    print("\n" + "=" * 60)
    print("[OK] Grade 11 Day 2 problems applied successfully!", flush=True)
    print("=" * 60)


if __name__ == '__main__':
    main()
