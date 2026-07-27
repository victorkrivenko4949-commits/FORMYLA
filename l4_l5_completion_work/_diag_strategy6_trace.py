#!/usr/bin/env python
"""Trace _extract_tasks_known_structure on the 4 failing files."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _stage6_targeted_generation import _extract_tasks_known_structure, sanitize_json_string, parse_json_response

basedir = 'l4_l5_completion_work/stage6_failed_responses'
files = ['raw_G5_L5_T004_S2.txt', 'raw_G6_L5_T016_S1.txt', 'raw_G6_L5_T018_S2.txt', 'raw_G6_L5_T018_S1.txt']

out_path = os.path.join('l4_l5_completion_work', '_diag_strategy6_trace_output.txt')
with open(out_path, 'w', encoding='utf-8') as out:
    for f in files:
        path = os.path.join(basedir, f)
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        out.write(f'=== {f} === len={len(text)}\n')
        
        # Test Strategy 6 on RAW text
        result = _extract_tasks_known_structure(text)
        out.write(f'  Strategy 6 (raw): {"OK: " + str(len(result.get("tasks", []))) + " tasks" if result else "FAILED"}\n')
        if result:
            for i, t in enumerate(result.get("tasks", [])):
                out.write(f'    Task {i}: statement_len={len(t.get("statement",""))}, answer_len={len(t.get("answer",""))}, solution_len={len(t.get("solution",""))}\n')
        
        # Test Strategy 6 on SANITIZED text
        sanitized = sanitize_json_string(text)
        result2 = _extract_tasks_known_structure(sanitized)
        out.write(f'  Strategy 6 (sanitized): {"OK: " + str(len(result2.get("tasks", []))) + " tasks" if result2 else "FAILED"}\n')
        if result2:
            for i, t in enumerate(result2.get("tasks", [])):
                out.write(f'    Task {i}: statement_len={len(t.get("statement",""))}, answer_len={len(t.get("answer",""))}, solution_len={len(t.get("solution",""))}\n')
        
        # Test full parse_json_response
        try:
            result3 = parse_json_response(text, save_on_failure=False)
            out.write(f'  parse_json_response: OK ({len(result3.get("tasks", []))} tasks)\n')
        except ValueError as e:
            err_msg = str(e)
            out.write(f'  parse_json_response: FAILED - {err_msg[:150]}\n')
        
        out.write('\n')

print(f"Diagnostic written to {out_path}")
