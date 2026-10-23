#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grade 11 vsosh 2020 regional - FINAL fix v8.
Uses existing DeepSeek responses (NO new API calls).

Key improvement: Instead of brace matching (which breaks on unescaped quotes),
anchors on "num": N patterns and extracts fields per-problem using
quote-aware extract_field_value().
"""
import ast
import json
import os
import sys
import shutil
import re

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
os.environ['PYTHONIOENCODING'] = 'utf-8'

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

GRADE_11_INDEX = 1046


def fix_json_escapes(text):
    """Fix invalid backslash escapes."""
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c); result.append(nextc); i += 2
            else:
                result.append('\\\\'); result.append(nextc); i += 2
        else:
            result.append(c); i += 1
    return ''.join(result)


def extract_field_value(text, key, start_pos=0):
    """
    Extract value of JSON key starting from start_pos.
    Handles unescaped quotes inside string values.
    Returns (value, end_position) or (None, start_pos).
    """
    pattern = rf'"{re.escape(key)}"\s*:\s*'
    m = re.search(pattern, text[start_pos:])
    if not m:
        return None, start_pos
    key_end = start_pos + m.end()
    
    if key_end >= len(text):
        return None, key_end
    
    if text[key_end] == '"':
        # String value
        result_chars = []
        i = key_end + 1
        while i < len(text):
            c = text[i]
            if c == '\\':
                result_chars.append(c); i += 1
                if i < len(text):
                    result_chars.append(text[i]); i += 1
            elif c == '"':
                # Look ahead to check if this is real closing quote
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',}]':
                    return ''.join(result_chars), j
                else:
                    # Unescaped quote inside value
                    result_chars.append(c); i += 1
            else:
                result_chars.append(c); i += 1
        return ''.join(result_chars), len(text)
    else:
        # Number value
        j = key_end
        while j < len(text) and text[j] not in ',}\n\r]':
            j += 1
        raw = text[key_end:j].strip()
        try:
            return int(raw), j
        except ValueError:
            return raw, j


def extract_problems_anchor(text, expected_nums=(8, 9, 10)):
    """
    Extract problems by anchoring on "num": N patterns.
    For each expected num, finds the pattern, walks backward to the opening {,
    then extracts all fields using quote-aware extract_field_value().
    
    This avoids brace matching entirely - the only brace we need is the opening
    { which we find by walking backward from "num": N.
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
    
    # Strategy 1: Try direct json.loads (quick win if no unescaped quotes)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"  Direct JSON parse succeeded: {len(data)} problems", flush=True)
            return data
        elif isinstance(data, dict):
            for key in ['problems', 'tasks', 'day2', 'data']:
                if key in data and isinstance(data[key], list):
                    print(f"  Direct JSON parse (wrapped in '{key}'): {len(data[key])} problems", flush=True)
                    return data[key]
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Anchor-based extraction
    print(f"  Using anchor-based extraction for nums {expected_nums}...", flush=True)
    problems = []
    
    for num in expected_nums:
        # Find "num": NUM (not followed by another digit)
        pattern = rf'"num"\s*:\s*{num}(?:\s*[,}}\s]|\s*\n)'
        m = re.search(pattern, text)
        if not m:
            print(f"  WARNING: 'num': {num} not found!", flush=True)
            continue
        
        match_end = m.end()
        
        # Walk backward from the match to find the opening '{'
        obj_start = -1
        brace_depth = 0
        for pos in range(match_end - 1, -1, -1):
            c = text[pos]
            if c == '}':
                brace_depth += 1
            elif c == '{':
                if brace_depth == 0:
                    obj_start = pos
                    break
                brace_depth -= 1
        
        if obj_start < 0:
            print(f"  WARNING: Could not find opening '{{' for num={num}!", flush=True)
            continue
        
        # Now extract all fields from obj_start using extract_field_value
        obj = {}
        pos = obj_start
        
        # Extract num
        val, pos = extract_field_value(text, 'num', pos)
        if val is not None:
            obj['num'] = val
        
        # Extract text
        val, pos = extract_field_value(text, 'text', pos)
        if val is not None:
            obj['text'] = val
        
        # Extract answer
        val, pos = extract_field_value(text, 'answer', pos)
        if val is not None:
            obj['answer'] = val
        
        # Extract solution
        val, pos = extract_field_value(text, 'solution', pos)
        if val is not None:
            obj['solution'] = val
        
        if 'num' in obj or 'text' in obj:
            problems.append(obj)
            txt_preview = (str(obj.get('text', '')) or '')[:80]
            print(f"  Extracted problem {obj.get('num', '?')}: {txt_preview}", flush=True)
        else:
            print(f"  WARNING: No useful fields extracted for num={num}!", flush=True)
    
    print(f"  Anchor extraction: {len(problems)} problems", flush=True)
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
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11_v8.py')
        print("  Backup: olympiads_backup_grade11_v8.py", flush=True)
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
    
    for i, p in enumerate(valid):
        if expected_nums:
            p['num'] = expected_nums[i] if i < len(expected_nums) else expected_nums[-1] + (i - len(expected_nums) + 1)
        else:
            p['num'] = 6 + i
    
    return valid


def main():
    print("=" * 60, flush=True)
    print("Grade 11 VSOSH 2020 Regional - Day 2 Fix (v8 - anchor)", flush=True)
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
    # LOAD EXISTING RESPONSES
    # ================================================================
    all_day2 = []
    
    # ---- Call 1: problems 6-7 ----
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
    
    probs1 = extract_problems_anchor(resp1, expected_nums=(6, 7))
    valid1 = validate_problems(probs1, expected_nums=[6, 7])
    print(f"  Valid: {len(valid1)} problems", flush=True)
    for p in valid1:
        print(f"    Problem {p.get('num')}: {(str(p.get('text','')) or '')[:80]}", flush=True)
    
    if not valid1:
        print("  ERROR: No valid problems from Call 1!", flush=True)
        sys.exit(1)
    
    all_day2.extend(valid1)
    
    # ---- Call 2: problems 8-10 ----
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
    
    probs2 = extract_problems_anchor(resp2, expected_nums=(8, 9, 10))
    valid2 = validate_problems(probs2, expected_nums=[8, 9, 10])
    print(f"  Valid: {len(valid2)} problems", flush=True)
    for p in valid2:
        txt = (str(p.get('text', '')) or '')[:80]
        print(f"    Problem {p.get('num')}: {txt}", flush=True)
    
    if not valid2:
        print("  ERROR: No valid problems from Call 2!", flush=True)
        sys.exit(1)
    
    all_day2.extend(valid2)
    
    # ================================================================
    # APPLY
    # ================================================================
    print(f"\n{'='*60}")
    print(f"Total: {len(all_day2)} problems from both calls")
    print(f"{'='*60}")
    
    for i, p in enumerate(all_day2):
        p['num'] = 6 + i
    
    print(f"  Using {len(all_day2)} problems for Day 2:")
    for p in all_day2:
        txt = (str(p.get('text', '')) or '')[:80]
        print(f"    Problem {p['num']}: {txt}", flush=True)
    
    if len(all_day2) < 3:
        print(f"  ERROR: Too few problems ({len(all_day2)}). Aborting.", flush=True)
        sys.exit(1)
    
    # Add day fields
    for p in all_day2:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
    
    for p in existing_problems:
        p['day'] = 1
    
    existing_problems.extend(all_day2)
    
    print(f"\n  Total problems now: {len(existing_problems)}")
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")
    
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
        shutil.copy2(db_py_path, db_py_path + '.bak8')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
    
    print("\n" + "=" * 60)
    print("[OK] Grade 11 Day 2 problems applied successfully!", flush=True)
    print("=" * 60)


if __name__ == '__main__':
    main()
