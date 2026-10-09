"""
Analyze olympiads.py to find ALL bad/stub/placeholder problem texts.
"""
import re
import json
import ast
import sys

FILE = 'olympiads.py'
OUTPUT = 'c:/Users/Victor/Desktop/bad_tasks_report.json'

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Use a more robust approach: parse the file with ast and walk the tree
# First verify it's valid
try:
    tree = ast.parse(content)
    print(f"[OK] {FILE} is valid Python ({len(content)} bytes)")
except SyntaxError as e:
    print(f"[ERROR] {FILE} has syntax error: {e}")
    sys.exit(1)

# Find all text fields using regex (most reliable for 250K line file)
# Pattern: 'text': '...'
text_pattern = re.compile(r"'text':\s*'(.*?)'(?=[,}])", re.DOTALL)
matches = list(text_pattern.finditer(content))
print(f"Total 'text' fields found via regex: {len(matches)}")

# Analyze short/placeholder texts
stub_patterns = [
    (r"Задача \d+ \(вариант \d+\)\.?", "stub_zadacha_variant"),
    (r"^\s*Задача\s+\d+\s*$", "stub_zadacha_only"),
    (r"^\s*Task\s+\d+\s*$", "stub_task_only"),
    (r"^\s*Problem\s+\d+\s*$", "stub_problem_only"),
    (r"^\s*Условие\s+задачи\s+\d+\s*$", "stub_uslovie"),
    (r"^\s*Условие\s*$", "stub_uslovie_short"),
    (r"^\s*В разработке\s*$", "stub_wip"),
    (r"^\s*Решение\s*$", "stub_solution_only"),
    (r"^\s*Ответ\s*$", "stub_answer_only"),
    (r"^\s*Нет данных\s*$", "stub_no_data"),
    (r"^\s*\(нет\)\s*$", "stub_none"),
    (r"^\s*---\s*$", "stub_dashes"),
    (r"^\s*\.\.\.\s*$", "stub_dots"),
    (r"^\s*TBD\s*$", "stub_tbd"),
    (r"^\s*TODO\s*$", "stub_todo"),
]

bad_tasks = []

for idx, m in enumerate(matches):
    text_val = m.group(1)
    text_stripped = text_val.strip()
    
    # Skip empty
    if not text_stripped:
        continue
    
    # Get line number
    line_no = content[:m.start()].count('\n') + 1
    
    reasons = []
    
    # Check length
    if len(text_stripped) < 40:
        reasons.append(f"very_short({len(text_stripped)} chars)")
    
    # Check against known stub patterns
    for pattern, pname in stub_patterns:
        if re.search(pattern, text_stripped):
            reasons.append(pname)
    
    if reasons:
        bad_tasks.append({
            'idx': idx,
            'line': line_no,
            'reasons': reasons,
            'text': text_stripped[:120]
        })

print(f"\n=== BAD/STUB TASKS FOUND: {len(bad_tasks)} ===")

# Group by reason
from collections import Counter
reason_counts = Counter()
for bt in bad_tasks:
    for r in bt['reasons']:
        reason_counts[r] += 1

print("\nBreakdown by reason:")
for reason, count in reason_counts.most_common():
    print(f"  {reason}: {count}")

print("\nFirst 50 bad tasks:")
for bt in bad_tasks[:50]:
    print(f"  line {bt['line']:>6} | {', '.join(bt['reasons']):30s} | {bt['text'][:80]}")

# Save full report
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump({
        'total_text_fields': len(matches),
        'total_bad': len(bad_tasks),
        'by_reason': dict(reason_counts.most_common()),
        'bad_tasks': bad_tasks
    }, f, ensure_ascii=False, indent=2)

print(f"\nFull report saved to: {OUTPUT}")
