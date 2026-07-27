#!/usr/bin/env python
"""Diagnose raw responses from failed cells to understand JSON parsing failures."""
import os, json, sys

failed_dir = os.path.join(os.path.dirname(__file__), "stage6_failed_responses")

# The 8 failed cells and their details
failed_cells = {
    "G5|L5|T004|S2": 5,  # Множества и комбинаторика / Комбинаторные конфигурации
    "G5|L5|T005|S1": 5,  # Логика и алгоритмы / Метод инвариантов
    "G5|L5|T008|S1": 5,  # Текстовые задачи / Задачи на движение
    "G6|L5|T016|S1": 5,  # Делимость и остатки / Признаки делимости
    "G6|L5|T018|S2": 5,  # Алгебраические выражения / Разложение на множители
    "G6|L5|T033|S2": 5,  # Комбинаторика и теория игр / Игры с числами
    "G5|L5|T004|S0": 4,  # Множества и комбинаторика / Комбинаторные конфигурации
    "G6|L5|T018|S1": 4,  # Алгебраические выражения / Разложение на множители
}

print("=" * 70)
print("DIAGNOSING FAILED RAW RESPONSES")
print("=" * 70)

for cell_key, needed in failed_cells.items():
    # Build filename - replace | with _
    fname = cell_key.replace("|", "_")
    raw_path = os.path.join(failed_dir, f"raw_{fname}.txt")
    
    if not os.path.exists(raw_path):
        print(f"\n[SKIP] {cell_key}: raw file not found at {raw_path}")
        continue
    
    with open(raw_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    print(f"\n{'='*70}")
    print(f"CELL: {cell_key} (needed={needed})")
    print(f"Size: {len(text)} bytes")
    print(f"Starts with: {repr(text[:80])}")
    print(f"Ends with: {repr(text[-120:])}")
    
    # Try direct JSON parse
    try:
        data = json.loads(text)
        tasks = data.get("tasks", [])
        print(f"[DIRECT PARSE] OK - {len(tasks)} tasks found")
        continue
    except json.JSONDecodeError as e:
        print(f"[DIRECT PARSE] FAILED at pos {e.pos}: {e.msg}")
        
        # Show context around error
        start = max(0, e.pos - 150)
        end = min(len(text), e.pos + 150)
        ctx = text[start:end]
        print(f"--- Context around error position ---")
        # Find exact byte position in context
        rel_pos = e.pos - start
        print(f"Context ({rel_pos} chars before error):")
        before = ctx[:rel_pos]
        after = ctx[rel_pos:]
        print(repr(before))
        print(f"^^^ {len(before)} chars ^^^")
        print(f"vvv ERROR AT THIS POINT vvv")
        print(repr(after[:200]))
        print("--- End context ---")
    
    # Try sanitized parse
    from _stage6_targeted_generation import sanitize_json_string
    sanitized = sanitize_json_string(text)
    try:
        data = json.loads(sanitized)
        tasks = data.get("tasks", [])
        print(f"[SANITIZED PARSE] OK - {len(tasks)} tasks found")
    except json.JSONDecodeError as e:
        print(f"[SANITIZED PARSE] Also FAILED at pos {e.pos}: {e.msg}")
        start2 = max(0, e.pos - 80)
        end2 = min(len(sanitized), e.pos + 80)
        print(f"  Sanitized context: {repr(sanitized[start2:end2])}")
    
    print()

print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)
