#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix the DeepSeek response for grade 11 and apply it to olympiads.py.
The JSON has invalid LaTeX escapes like \alpha, \angle, etc.
Strategy: escape any backslash that precedes a non-valid-JSON-escape char.
"""
import ast
import json
import os
import sys
import re
import shutil

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

# Valid JSON escape sequences
VALID_ESCAPES = set('"\\/bfnrtu')

def fix_json_escapes(text):
    # Fix invalid backslash escapes in JSON string content.
    # In JSON, only \", \\, \/, \b, \f, \n, \r, \t, \uXXXX are valid.
    # LaTeX commands like \alpha, \angle, \beta etc. are NOT valid.
    # Need to double-escape those: \a -> \\a, etc.
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                # Valid escape sequence - pass through
                result.append(c)
                result.append(nextc)
                i += 2
            else:
                # Invalid escape - double the backslash
                result.append('\\\\')
                result.append(nextc)
                i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def extract_and_fix_json(raw_response):
    """Extract JSON from response, fix escapes, parse it."""
    # Strip markdown fences
    text = raw_response
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    text = text.strip()

    # CRITICAL: Fix LaTeX escapes BEFORE any JSON parsing.
    # DeepSeek returns \alpha, \angle, \gcd, \mid etc.
    # These are INVALID in JSON (only \", \\, \/, \b, \f, \n, \r, \t, \u are valid).
    # Must double-escape: \alpha -> \\alpha, etc.
    text = fix_json_escapes(text)

    # Now try direct parse (should work after escape fixing)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"  JSON parsed directly ({len(data)} items)!", flush=True)
            return data
        elif isinstance(data, dict):
            print(f"  JSON parsed as dict with keys: {list(data.keys())}", flush=True)
            return data
    except json.JSONDecodeError:
        pass

    print("  Direct parse failed after escape fix, trying fallback...", flush=True)

    # Find the JSON array bounds
    start = text.find('[')
    if start < 0:
        print("  ERROR: No '[' found!", flush=True)
        return None

    # Find matching closing bracket
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == '[':
            depth += 1
        elif text[i] == ']':
            depth -= 1
            if depth == 0:
                end = i
                break

    if end < 0:
        print("  ERROR: No matching closing bracket found!", flush=True)
        return None

    json_text = text[start:end+1]

    # Try to parse the extracted bracket-delimited text
    try:
        data = json.loads(json_text)
        print(f"  JSON bracket-parse succeeded ({len(data) if isinstance(data, list) else 'dict'} items)!", flush=True)
        return data
    except json.JSONDecodeError as e:
        print(f"  Still failing: {e}", flush=True)
        print(f"  Around pos {e.pos}: {repr(json_text[max(0,e.pos-100):e.pos+100])}", flush=True)
        return None


def load_olympiads_db():
    """Load OLYMPIADS_DB from olympiads.py."""
    print("Loading olympiads.py via AST...", flush=True)
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
    """Convert AST node to Python dict/list/primitive."""
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
    """Save back to olympiads.py."""
    print("Saving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'

    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11.py')
        print("  Backup: olympiads_backup_grade11.py", flush=True)

    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes", flush=True)


def main():
    # Load the raw response
    print("Loading DeepSeek response...", flush=True)
    with open('_last_response_11_v2.txt', 'r', encoding='utf-8') as f:
        raw = f.read()

    print(f"  Raw response: {len(raw)} chars", flush=True)

    # Extract and fix JSON
    day2_problems = extract_and_fix_json(raw)

    if day2_problems is None:
        print("FAILED to parse JSON!")
        sys.exit(1)

    if isinstance(day2_problems, dict):
        for key in ['problems', 'tasks', 'day2', 'data']:
            if key in day2_problems:
                day2_problems = day2_problems[key]
                break

    if not isinstance(day2_problems, list):
        print(f"Unexpected type: {type(day2_problems).__name__}")
        sys.exit(1)

    print(f"\nExtracted {len(day2_problems)} problems:")
    for p in day2_problems:
        print(f"  num={p.get('num')}: {p.get('text','')[:80]}...")

    # Load olympiads.py
    content, ast_entries = load_olympiads_db()

    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = ast_to_dict(entry)
        all_entries.append(d)

    idx = 1046
    entry = all_entries[idx]
    existing_problems = entry.get('problems', [])

    print(f"\nEntry index {idx}: grade={entry.get('grade','?')}, id={entry.get('id','')}")
    print(f"  Existing problems: {len(existing_problems)}")

    # Validate day2_problems - get nums 6-10
    valid = []
    for p in day2_problems:
        if not isinstance(p, dict):
            continue
        num = p.get('num', 0) or p.get('number', 0)
        if isinstance(num, str) and num.isdigit():
            num = int(num)
        if not isinstance(num, int):
            num = 0
        if 6 <= num <= 10:
            valid.append(p)

    if len(valid) < 5:
        print(f"  WARNING: Only {len(valid)} valid problems with nums 6-10", flush=True)
        # Accept all with text, renumber
        valid = []
        for p in day2_problems:
            if isinstance(p, dict) and p.get('text'):
                valid.append(p)
        for i, p in enumerate(valid):
            p['num'] = 6 + i

    if len(valid) < 3:
        print(f"  ERROR: Too few problems ({len(valid)})")
        sys.exit(1)

    print(f"  Using {len(valid)} problems")

    # Add day=2 to new problems
    for p in valid:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
        p.setdefault('text', '')

    # Add day=1 to existing problems
    for p in existing_problems:
        p['day'] = 1

    # Append Day 2
    existing_problems.extend(valid)

    print(f"\n  Total problems now: {len(existing_problems)}")
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")

    # Save
    save_olympiads_db(all_entries)

    # Also update data/olympiads_db.py
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
        db_content += '\n'

        shutil.copy2(db_py_path, db_py_path + '.bak2')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)

    print("\n✅ Grade 11 Day 2 problems added successfully!")


if __name__ == '__main__':
    main()
