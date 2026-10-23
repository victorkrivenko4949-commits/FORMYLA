#!/usr/bin/env python
"""Test the regex fix for LaTeX backslashes in JSON."""

import re

def fix_escaped_backslashes_old(text):
    """Original regex - character class matches \ as well."""
    result = re.sub(r'(?<!\\)\\(?=[\(\[\]])', r'\\\\', text)
    return result

def fix_escaped_backslashes_new(text):
    """Fixed regex - character class only matches (, [, ]."""
    # Using simpler approach: character-by-character
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text) and text[i+1] in '([]':
            # Check if already escaped (preceded by an odd number of backslashes)
            if i > 0 and text[i-1] == '\\':
                # Already escaped - keep as is
                result.append(text[i])
            else:
                # Need to escape - add another backslash
                result.append('\\\\')
            result.append(text[i+1])
            i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)

# Test cases
test_cases = [
    # (input, description)
    (r'\(G\)', "Simple LaTeX parens"),
    (r'\[G:H\]', "Simple LaTeX brackets"),
    (r'\\(G\\)', "Already escaped LaTeX parens"),
    (r'\\[G:H\\]', "Already escaped LaTeX brackets"),
    (r'\\\\(G\\)', "Double-escaped (4 backslashes)"),
    (r'"statement": "Пусть \(G\)"', "In JSON string"),
    (r'"answer": "Доказано, что \(G = HK\)."', "Answer with LaTeX"),
    (r'{"x": "\\[test\\]"}', "Already escaped in JSON"),
    (r'{"x": "\(test\)"}', "Unescaped LaTeX in JSON"),
    (r'\\', "Single backslash alone"),
    (r'\\\\', "Double backslash alone"),
]

print("Testing regex fixes:\n")
for input_text, desc in test_cases:
    old_result = fix_escaped_backslashes_old(input_text)
    new_result = fix_escaped_backslashes_new(input_text)
    
    old_ok = True
    new_ok = True
    try:
        # Only test on proper JSON wrappers
        json_str = '{"data": "' + input_text + '"}'
        import json
        json.loads(json_str)
    except json.JSONDecodeError:
        pass  # Not expected to parse
    
    old_status = "OK" if input_text == old_result else "CHANGED"
    new_status = "OK" if input_text == new_result else "CHANGED"
    
    print(f"[{desc}]")
    print(f"  Input:    {repr(input_text)}")
    print(f"  Old reg:  {repr(old_result)}  [{old_status}]")
    print(f"  New loop: {repr(new_result)}  [{new_status}]")
    
    # Check if NEW fix breaks already-escaped
    if '\\\\' in input_text or r'\\' in input_text.replace(r'\\\\', ''):
        # This is an already-escaped case
        if new_result != input_text:
            print(f"  *** NEW fix BROKE already-escaped! ***")
    
    print()

# Now test actual JSON parsing
print("=" * 60)
print("Testing JSON parsing after fix:\n")

json_input = '''{
  "tasks": [
    {
      "statement": "Пусть \\(G\\) — конечная группа.",
      "answer": "Доказано.",
      "solution": "Рассмотрим \\(H \\cap K\\)."
    }
  ]
}'''

import json

print("Original JSON:")
try:
    json.loads(json_input)
    print("  PARSED OK")
except json.JSONDecodeError as e:
    print(f"  FAILED: {e}")

print("\nAfter OLD regex fix:")
old_fixed = fix_escaped_backslashes_old(json_input)
try:
    json.loads(old_fixed)
    print("  PARSED OK")
except json.JSONDecodeError as e:
    print(f"  FAILED: {e}")
    # Show the problematic area
    print(f"  First diff at: ...{repr(old_fixed[max(0, e.pos-20):e.pos+20])}...")

print("\nAfter NEW loop fix:")
new_fixed = fix_escaped_backslashes_new(json_input)
try:
    json.loads(new_fixed)
    print("  PARSED OK")
except json.JSONDecodeError as e:
    print(f"  FAILED: {e}")
    print(f"  First diff at: ...{repr(new_fixed[max(0, e.pos-20):e.pos+20])}...")
