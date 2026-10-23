#!/usr/bin/env python
"""Debug specific raw files to verify f/b removal didn't cause regression."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _stage6_targeted_generation import sanitize_json_string, parse_json_response, _VALID_JSON_ESCAPES

print('_VALID_JSON_ESCAPES:', _VALID_JSON_ESCAPES)
print()

failed_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage6_failed_responses")

# First, run the full diagnostic
print("=" * 70)
print("RUNNING FULL DIAGNOSTIC...")
print("=" * 70)

raw_files = sorted([f for f in os.listdir(failed_dir) if f.startswith('raw_')])
raw_ok = 0
for f in raw_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    try:
        result = parse_json_response(text, save_on_failure=False)
        raw_ok += 1
    except ValueError:
        pass

failed_files = sorted([f for f in os.listdir(failed_dir) if f.startswith('failed_')])
failed_ok = 0
for f in failed_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    try:
        result = parse_json_response(text, save_on_failure=False)
        failed_ok += 1
    except ValueError:
        pass

print(f'raw files:    {raw_ok}/{len(raw_files)} parse OK')
print(f'failed files: {failed_ok}/{len(failed_files)} parse OK')
print()

# Deep debug the 4 suspicious files
print("=" * 70)
print("DEEP DEBUG OF 4 SUSPICIOUS FILES")
print("=" * 70)

for fname in ['raw_G11_L5_T043_S1.txt', 'raw_G5_L4_T004_S2.txt', 'raw_G5_L4_T005_S0.txt', 'raw_G6_L5_T007_S1.txt']:
    path = os.path.join(failed_dir, fname)
    if not os.path.exists(path):
        print(f'{fname}: FILE NOT FOUND')
        continue
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f'=== {fname} ({len(text)} bytes) ===')
    try:
        result = parse_json_response(text, save_on_failure=False)
        tasks = result.get('tasks', result) if isinstance(result, dict) else result
        print(f'  parse_json_response: OK ({len(tasks)} tasks)')
    except ValueError as e:
        print(f'  parse_json_response: FAILED')
        print(f'  Error: {str(e)[:300]}')
        
        try:
            sanitized = sanitize_json_string(text)
            parsed = json.loads(sanitized)
            tasks = parsed.get('tasks', []) if isinstance(parsed, dict) else parsed
            print(f'  sanitize+json.loads: OK ({len(tasks)} tasks)')
            print(f'  -> So the failure is in parse_json_response logic (strategies)')
        except json.JSONDecodeError as e2:
            pos = e2.pos
            start = max(0, pos-100)
            end = min(len(sanitized), pos+100)
            ctx = sanitized[start:end]
            print(f'  sanitize+json.loads: FAIL at pos={pos}')
            before = sanitized[max(0,pos-30):pos]
            after = sanitized[pos:pos+30]
            print(f'  Before pos: {repr(before)}')
            print(f'  After pos:  {repr(after)}')
    print()

# Now deeper investigation of raw_G6_L5_T007_S1.txt
print("=" * 70)
print("DEEPER INVESTIGATION: raw_G6_L5_T007_S1.txt")
print("=" * 70)

fname = 'raw_G6_L5_T007_S1.txt'
path = os.path.join(failed_dir, fname)
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

sanitized = sanitize_json_string(text)

# Find what's at position 12167 (the failure point)
pos = 12167
start = max(0, pos-200)
end = min(len(sanitized), pos+200)
ctx = sanitized[start:end]
print(f'Context around pos={pos} (sanitized):')
print(repr(ctx))
print()

# Check if it ends with proper JSON closing
end_text = sanitized[-300:]
print(f'Last 300 chars of sanitized:')
print(repr(end_text))
print()

# Try JSON parsing to see the exact error
try:
    json.loads(sanitized)
    print('json.loads OK!')
except json.JSONDecodeError as e:
    print(f'json.loads error at pos={e.pos}: {e.msg}')
    ctx_fail = sanitized[max(0,e.pos-100):e.pos+100]
    print(f'Context: {repr(ctx_fail)}')

print()
print("=" * 70)
print("DEEPER INVESTIGATION: raw_G11_L5_T043_S1.txt")
print("=" * 70)

fname = 'raw_G11_L5_T043_S1.txt'
path = os.path.join(failed_dir, fname)
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

sanitized = sanitize_json_string(text)

pos = 7186
start = max(0, pos-200)
end = min(len(sanitized), pos+200)
ctx = sanitized[start:end]
print(f'Context around pos={pos} (sanitized):')
print(repr(ctx))
print()

try:
    json.loads(sanitized)
    print('json.loads OK!')
except json.JSONDecodeError as e:
    print(f'json.loads error at pos={e.pos}: {e.msg}')
    ctx_fail = sanitized[max(0,e.pos-100):e.pos+100]
    print(f'Context: {repr(ctx_fail)}')
