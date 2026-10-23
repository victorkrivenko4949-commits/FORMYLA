#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test gen_solutions.py internal logic: matching, LaTeX conversion, JSON sanitizer."""
import sys, os, json

# Ensure we can import gen_solutions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_solutions import load_db, find_problem, _make_key, _convert_latex
from gen_solutions import _escape_control_chars_in_strings, _sanitize_json_content

# ── Test 1: Load DB ──
db = load_db()
print(f"DB loaded: {len(db)} olympiads")

# ── Test 2: Matching ──
with open(r"C:\Users\Victor\Downloads\tasks_solutions_out.json", "r", encoding="utf-8") as f:
    out = json.load(f)
first = out[0]
print(f"\nTesting matching for: {first['key']}")
oi, pi = find_problem(db, first)
assert oi is not None, f"Matching FAILED for {first['key']}"
print(f"  Found: olympiad index {oi}, problem index {pi}")
print(f"  Olympiad: {db[oi]['olympiad']}")
print(f"  Problem num: {db[oi]['problems'][pi]['num']}")
print(f"  Current solution_status: '{db[oi]['problems'][pi].get('solution_status', 'MISSING')}'")

# Verify ALL 60 match
for rec in out:
    oi, pi = find_problem(db, rec)
    if oi is None:
        print(f"  MISMATCH: {rec['key']}")
if all(find_problem(db, rec)[0] is not None for rec in out):
    print(f"  All {len(out)} tasks match correctly!")

# ── Test 3: LaTeX conversion ──
print(f"\nTesting LaTeX conversion:")
test = r"Решение: \(x^2 + y^2 = 1\) и \[\sum_{k=1}^{n} k\]"
converted = _convert_latex(test)
print(f"  Before: {test}")
print(f"  After:  {converted}")
assert "\\(" not in converted, "Should not contain unescaped \\("
assert "\\[" not in converted, "Should not contain unescaped \\["
assert "$" in converted, "Should contain $"
assert "$$" in converted, "Should contain $$"
print(f"  PASS")

# ── Test 4: JSON sanitizer ──
print(f"\nTesting JSON sanitizer:")
valid = '{"solution": "test", "answer": "42"}'
result = _sanitize_json_content(valid)
print(f"  Valid JSON: {result}")
assert result is not None

with_ctrl = '{"solution": "line1\nline2", "answer": "42"}'
result = _sanitize_json_content(with_ctrl)
print(f"  With control chars: {result}")
assert result is not None

with_latex = '{"solution": "\\\\(x^2\\\\)", "answer": "42"}'
result = _sanitize_json_content(with_latex)
print(f"  With LaTeX escapes: {result}")
assert result is not None

# ── Test 5: done_keys ──
done_keys = set()
for o in db:
    for p in o.get("problems", []):
        if p.get("solution_status") == "generated" and p.get("solution", "").strip():
            k = _make_key(o, p.get("num", ""))
            done_keys.add(k)
print(f"\nDone keys in DB: {len(done_keys)}")

first_key = first["key"]
task_key = _make_key(first)
print(f"  First task key from _make_key: {task_key}")
print(f"  First task in done_keys: {task_key in done_keys}")

# ── Test 6: Count remaining tasks ──
with open(r"C:\Users\Victor\Downloads\tasks_need_solutions.json", "r", encoding="utf-8") as f:
    tasks = json.load(f)
need_keys = set(_make_key(t) for t in tasks)
remaining = need_keys - done_keys
print(f"\nTasks need solutions: {len(need_keys)}")
print(f"Already in DB (generated): {len(done_keys)}")
print(f"Remaining to process: {len(remaining)}")

print("\n=== ALL CHECKS PASSED ===")
