#!/usr/bin/env python
"""Diagnose why valid-looking JSON fails to parse in Stage 6.

Tests the FIXED sanitize/parse functions from _stage6_targeted_generation.py
against all raw and failed response files.
"""
import json, os, sys

# Import from the actual module (after fixes)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _stage6_targeted_generation import (
    sanitize_json_string, parse_json_response,
    _find_structural_end, _try_parse_json, _try_parse_with_completion
)

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
failed_dir = os.path.join(WORK_DIR, "stage6_failed_responses")

# Check raw files
raw_files = sorted([f for f in os.listdir(failed_dir) if f.startswith('raw_')])
print(f'=== Testing {len(raw_files)} raw response files with FIXED sanitize ===')
print(f'{"Filename":45s} | {"Size":>6s} | {"Status":40s}')
print('-' * 95)
for f in raw_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    
    size = len(text)
    ends_with_close = text.rstrip().endswith(']}') or text.rstrip().endswith('}]')
    
    # Try via parse_json_response (uses all strategies)
    try:
        result = parse_json_response(text, save_on_failure=False)
        n_tasks = len(result.get('tasks', result) if isinstance(result, dict) else result)
        status = f'OK ({n_tasks} tasks)'
    except ValueError as e:
        # Try just sanitize + parse
        try:
            sanitized = sanitize_json_string(text)
            json.loads(sanitized)
            status = 'SANITIZE_OK (parse_json_response still failed)'
        except json.JSONDecodeError as e2:
            # Show detailed error context
            sanitized = sanitize_json_string(text)
            try:
                json.loads(sanitized)
            except json.JSONDecodeError as e3:
                pos = e3.pos
                start = max(0, pos-60)
                end = min(len(sanitized), pos+60)
                ctx = sanitized[start:end]
                status = f'FAIL at {pos}: ...{ctx[:120]}...'
    
    print(f'{f:45s} | {size:6d} | {status:40s}')

# Check failed files  
print()
failed_files = sorted([f for f in os.listdir(failed_dir) if f.startswith('failed_')])
print(f'=== Testing {len(failed_files)} failed_ files with FIXED parse ===')
print(f'{"Filename":45s} | {"Size":>6s} | {"Status":40s}')
print('-' * 95)
for f in failed_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    
    size = len(text)
    
    try:
        result = parse_json_response(text, save_on_failure=False)
        n_tasks = len(result.get('tasks', result) if isinstance(result, dict) else result)
        status = f'OK ({n_tasks} tasks)'
    except ValueError as e:
        # Try direct sanitize
        try:
            sanitized = sanitize_json_string(text)
            json.loads(sanitized)
            status = 'SANITIZE_OK only'
        except json.JSONDecodeError as e2:
            pos = e2.pos
            start = max(0, pos-60)
            end = min(len(sanitized), pos+60)
            ctx = sanitized[start:end]
            status = f'FAIL at {pos}: ...{ctx[:120]}...'
    
    print(f'{f:45s} | {size:6d} | {status:40s}')

print()
print('=== Summary ===')
# Count successes
raw_ok = 0
for f in raw_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    try:
        parse_json_response(text, save_on_failure=False)
        raw_ok += 1
    except:
        pass

failed_ok = 0
for f in failed_files:
    path = os.path.join(failed_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    try:
        parse_json_response(text, save_on_failure=False)
        failed_ok += 1
    except:
        pass

print(f'raw files:    {raw_ok}/{len(raw_files)} parse OK')
print(f'failed files: {failed_ok}/{len(failed_files)} parse OK')
