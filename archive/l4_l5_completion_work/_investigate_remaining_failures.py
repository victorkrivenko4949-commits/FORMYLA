#!/usr/bin/env python
"""Investigate why 4 cells still fail even with the fix."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _stage6_targeted_generation import sanitize_json_string, _extract_tasks_known_structure, _extract_fields_from_task_obj

FAILED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage6_failed_responses")

cases = [
    ("G5|L5|T004|S2", "raw_G5_L5_T004_S2.txt", 2242),
    ("G6|L5|T016|S1", "raw_G6_L5_T016_S1.txt", 59),
    ("G6|L5|T018|S2", "raw_G6_L5_T018_S2.txt", 56),
    ("G6|L5|T018|S1", "raw_G6_L5_T018_S1.txt", 333),
]

for cell_key, raw_file, error_pos in cases:
    raw_path = os.path.join(FAILED_DIR, raw_file)
    with open(raw_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    print(f"\n{'='*80}")
    print(f"[{cell_key}] ({raw_file}) — {len(text)} bytes")
    print(f"{'='*80}")
    
    # Show context around error position
    start = max(0, error_pos - 100)
    end = min(len(text), error_pos + 100)
    context = text[start:end]
    
    # Try to find the raw bytes around error_pos
    print(f"\nContext around error position {error_pos}:")
    print(f"  {repr(context[:50])}")
    print(f"  >>>{repr(context[50:-50])}<<<")
    print(f"  {repr(context[-50:])}")
    
    # Show characters at error position
    print(f"\n  Char at pos {error_pos}: {repr(text[error_pos] if error_pos < len(text) else 'EOF')}")
    if error_pos + 1 < len(text):
        print(f"  Next char: {repr(text[error_pos + 1])}")
    if error_pos + 2 < len(text):
        print(f"  Next+1 char: {repr(text[error_pos + 2])}")
    
    # Show the specific line
    lines = text[:error_pos+200].split('\n')
    line_num = 0
    char_count = 0
    for i, line in enumerate(lines):
        if char_count + len(line) + 1 > error_pos:
            line_num = i + 1
            col = error_pos - char_count
            print(f"\n  Line {line_num}, col {col}:")
            print(f"    {line}")
            print(f"    {' ' * col}^")
            break
        char_count += len(line) + 1
    
    # Show the sanitized text at the same position
    sanitized = sanitize_json_string(text)
    if len(sanitized) > error_pos:
        print(f"\n  Sanitized char at pos {error_pos}: {repr(sanitized[error_pos] if error_pos < len(sanitized) else 'EOF')}")
        san_start = max(0, error_pos - 50)
        san_end = min(len(sanitized), error_pos + 50)
        print(f"  Sanitized context: ...{repr(sanitized[san_start:san_end])}...")
    
    # Check Strategy 6 more carefully
    print(f"\n  Strategy 6 analysis:")
    
    # Does the text contain "tasks"?
    tasks_idx = text.find('"tasks"')
    print(f"    'tasks' key found at: {tasks_idx}")
    
    if tasks_idx >= 0:
        bracket_idx = text.find('[', tasks_idx)
        print(f"    '[' after tasks at: {bracket_idx}")
        
        if bracket_idx >= 0:
            # Try to count task objects
            after_bracket = text[bracket_idx+1:]
            obj_count = 0
            i = 0
            depth = 0
            in_str = False
            escaped = False
            while i < len(after_bracket):
                c = after_bracket[i]
                if escaped:
                    escaped = False
                    i += 1
                    continue
                if c == '\\' and in_str:
                    escaped = True
                    i += 1
                    continue
                if c == '"':
                    in_str = not in_str
                    i += 1
                    continue
                if not in_str:
                    if c == '{':
                        depth += 1
                        if depth == 1:
                            obj_count += 1
                    elif c == '}':
                        depth -= 1
                    elif c == ']':
                        break
                i += 1
            print(f"    Estimated task objects: {obj_count}")
    else:
        print(f"    'tasks' key NOT found!")
    
    # Check if the text has a known structure problem
    print(f"\n  Looking for 'statement' pattern:")
    import re
    for m in re.finditer(r'"statement"\s*:\s*"', text):
        print(f"    Found at {m.start()}: ...{text[m.start():m.start()+80]}...")

print(f"\n{'='*80}")
print("DONE")
