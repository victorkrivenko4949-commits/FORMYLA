#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Search source DB for class 8, L3-relevant tasks"""

import json

source_path = r"../../Downloads/FORMYLA_olympiad_DB_no_holes_with_images (1).jsonl"

# Count all class 8 tasks
class8_total = 0
class8_diff4 = []  # Difficulty 4 -> mechanical L3
class8_diff3 = []  # Difficulty 3 -> could be bumped to L3
class8_diff5 = []  # Difficulty 5 -> could be lowered to L3

with open(source_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
    cl = t.get('class_level')
    if cl == 8:
        class8_total += 1
        diff = t.get('difficulty_level')
        oid = t.get('original_id', t.get('id', 'N/A'))
        text = t.get('task_text', '')[:120]
        
        if diff == 4:
            class8_diff4.append({'id': oid, 'diff': diff, 'text': text})
        elif diff == 3:
            class8_diff3.append({'id': oid, 'diff': diff, 'text': text})
        elif diff == 5:
            class8_diff5.append({'id': oid, 'diff': diff, 'text': text})

print(f"Class 8 total in source DB: {class8_total}")
print(f"  Difficulty 4 (L3 mechanical): {len(class8_diff4)}")
print(f"  Difficulty 3 (potential L3): {len(class8_diff3)}")
print(f"  Difficulty 5 (potential L3): {len(class8_diff5)}")

print("\n--- Difficulty 4 tasks (mechanical L3) ---")
for t in class8_diff4:
    print(f"  {t['id']}: {t['text']}")

print("\n--- Difficulty 3 tasks (could be bumped to L3) ---")
for t in class8_diff3:
    print(f"  {t['id']}: {t['text']}")

print("\n--- Difficulty 5 tasks (could be lowered to L3) ---")
for t in class8_diff5[:10]:  # Just first 10
    print(f"  {t['id']}: {t['text']}")
if len(class8_diff5) > 10:
    print(f"  ... and {len(class8_diff5) - 10} more")
