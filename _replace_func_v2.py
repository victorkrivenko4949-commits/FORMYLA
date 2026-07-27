# -*- coding: utf-8 -*-
"""Replace _find_simple_text_span in _fix_all_bad_tasks.py using external file."""
import re
import ast

TARGET = '_fix_all_bad_tasks.py'
NEW_FUNC_FILE = '_new_func_simple_text_span.py'

# Read the target file
with open(TARGET, 'r', encoding='utf-8') as f:
    content = f.read()

# Read and parse the new function file using AST to get exact source
with open(NEW_FUNC_FILE, 'r', encoding='utf-8') as f:
    new_func_source = f.read()

# Find the start of the old function
start_marker = 'def _find_simple_text_span(content: str, set_key: str, problem_num: int) -> tuple:'
idx_start = content.find(start_marker)
if idx_start == -1:
    print("ERROR: could not find old function start")
    exit(1)

# Find the end: next 'def ' at file level (before apply_fixes_to_file)
end_marker = '\n\ndef apply_fixes_to_file'
idx_end = content.find(end_marker, idx_start)
if idx_end == -1:
    print("ERROR: could not find function end (apply_fixes_to_file)")
    exit(1)

old_func = content[idx_start:idx_end]
print(f"Old function: {len(old_func)} chars (lines {content[:idx_start].count(chr(10))+2}-{content[:idx_end].count(chr(10))+1})")
print(f"New function: {len(new_func_source)} chars")

# Verify old function
assert old_func.startswith('def _find_simple_text_span'), "Doesn't start with function def!"
assert 're.escape(set_key)' in old_func, "Old func uses set_key"

# Verify new function is valid Python
try:
    tree = ast.parse(new_func_source)
    func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert len(func_defs) == 1, f"Expected 1 function def, got {len(func_defs)}"
    assert func_defs[0].name == '_find_simple_text_span'
    print("New function is valid Python!")
except SyntaxError as e:
    print(f"SYNTAX ERROR in new function file: {e}")
    exit(1)

# Replace
new_content = content[:idx_start] + new_func_source + content[idx_end:]

# Verify overall syntax
try:
    compile(new_content, TARGET, 'exec')
    print("Overall syntax OK!")
except SyntaxError as e:
    print(f"SYNTAX ERROR after replacement: {e}")
    # Show context around error
    lines = new_content.split('\n')
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        for ln in range(start, end):
            marker = " >>>" if ln == e.lineno - 1 else "    "
            print(f"  {marker} {ln+1}: {lines[ln]}")
    exit(1)

# Write
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(new_content)

# Verify old function is gone
if new_func_source in new_content:
    print("New function written successfully!")
else:
    print("ERROR: new function not found in written content!")
    exit(1)

if old_func in new_content:
    print("ERROR: old function still present!")
    exit(1)

print(f"Done! Replaced {len(old_func)}-char old function with {len(new_func_source)}-char new function")
