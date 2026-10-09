#!/usr/bin/env python
"""Test that iterative _fix_invalid_escapes handles doubled backslashes."""
import json
import re

# Simulate the raw string from the API (with double backslashes before LaTeX)
# In Python source: \\\\ = two literal backslashes
raw = '{\n  "statement": "$$\\\\frac{x^2 - 5x + 6}{x^2 - 4x + 3} \\\\leq 0$$",\n  "answer": "$$x \\\\in [2, 3) \\\\cup (3, +\\\\infty)$$"\n}'

print("=== RAW (repr) ===")
print(repr(raw))

# Show the actual characters at key positions
idx = raw.find("\\\\frac")
if idx >= 0:
    print(f"\n'frac' at pos {idx}: chars={[hex(ord(c)) for c in raw[idx:idx+6]]}")

idx = raw.find("leq")
if idx >= 0:
    print(f"'leq' at pos {idx}: chars={[hex(ord(c)) for c in raw[idx-2:idx+4]]}")


def fix_escapes_once(text):
    replacements = {
        '(': '(', ')': ')', '[': '[', ']': ']',
        '{': '{', '}': '}', '<': '<', '>': '>',
        '|': '|', '`': '`', '_': '_', '*': '*',
    }
    # Reconstruct with proper escaping
    replacements2 = {
        '\\(': '(',
        '\\)': ')',
        '\\[': '[',
        '\\]': ']',
        '\\{': '{',
        '\\}': '}',
        '\\<': '<',
        '\\>': '>',
        '\\|': '|',
        '\\`': '`',
        '\\_': '_',
        '\\*': '*',
    }
    for old, new in replacements2.items():
        text = text.replace(old, new)
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)
    return text


def fix_escapes_iterative(text):
    prev = None
    while prev != text:
        prev = text
        text = fix_escapes_once(text)
    return text


# Test single pass
single = fix_escapes_once(raw)
print("\n=== SINGLE PASS (repr) ===")
print(repr(single[:250]))

# Test iterative
iterative = fix_escapes_iterative(raw)
print("\n=== ITERATIVE (repr) ===")
print(repr(iterative[:250]))

# Test json.loads
print("\n=== JSON PARSE SINGLE PASS ===")
try:
    r = json.loads(single)
    print(f"SUCCESS: {r['statement'][:60]}")
except json.JSONDecodeError as e:
    pos = e.pos
    print(f"FAIL at pos {pos}: {e}")
    start = max(0, pos - 30)
    end = min(len(single), pos + 30)
    print(f"  Context: {repr(single[start:end])}")

print("\n=== JSON PARSE ITERATIVE ===")
try:
    r = json.loads(iterative)
    print(f"SUCCESS!")
    print(f"  statement: {r['statement'][:80]}")
    print(f"  answer: {r['answer'][:80]}")
except json.JSONDecodeError as e:
    pos = e.pos
    print(f"FAIL at pos {pos}: {e}")
    start = max(0, pos - 30)
    end = min(len(iterative), pos + 30)
    print(f"  Context: {repr(iterative[start:end])}")
