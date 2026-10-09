#!/usr/bin/env python3
"""Phase 6: Analyze target cells and method definitions from verified main."""
import json, os

DOWNLOADS = "C:/Users/Victor/Downloads"
MAIN_PATH = f"{DOWNLOADS}/final_clean_dataset_5levels_verified.json"
RESERVE_PATH = f"{DOWNLOADS}/final_clean_dataset_5levels_verified_reserve.json"
FORMYLA_PATH = f"{DOWNLOADS}/formyla_dataset_slightly_fixed.json"
OLYMPIAD_DB_PATH = f"{DOWNLOADS}/olympiad_DB_final_fixed.jsonl"

TARGETS = [
    (5, "F3", 3, 4),
    (5, "G2", 3, 4),
    (6, "G1", 3, 1),
    (6, "G2", 3, 2),
    (10, "B2", 3, 1),
]

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_jsonl(path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data

def main():
    main_tasks = load_json(MAIN_PATH)
    reserve_tasks = load_json(RESERVE_PATH)
    
    print(f"Verified main: {len(main_tasks)} tasks")
    print(f"Verified reserve: {len(reserve_tasks)} tasks")
    print()
    
    # --- Analyze target cells in main ---
    print("=" * 70)
    print("TARGET CELLS - EXISTING TASKS IN MAIN")
    print("=" * 70)
    
    for grade, method, diff, need in TARGETS:
        cell = [t for t in main_tasks 
                if t.get("grade") == grade 
                and t.get("method_code") == method 
                and t.get("difficulty") == diff]
        print(f"\n--- Grade {grade} / Method {method} / Diff {diff} ---")
        print(f"  Found: {len(cell)} tasks (need {need} more)")
        for i, t in enumerate(cell, 1):
            tid = t.get("id", "?")
            theme = t.get("theme", "?")
            subtopic = t.get("subtopic", "?")
            text_preview = t.get("task_text", "")[:120].replace("\n", " ")
            print(f"  [{i}] {tid}")
            print(f"       theme={theme} subtopic={subtopic}")
            print(f"       text: {text_preview}...")
        
        if len(cell) == 0:
            print("  *** EMPTY CELL ***")
    
    # --- Analyze reserve candidates ---
    print("\n" + "=" * 70)
    print("RESERVE - CANDIDATES FOR TARGET CELLS")
    print("=" * 70)
    
    for grade, method, diff, need in TARGETS:
        candidates = [t for t in reserve_tasks
                      if t.get("grade") == grade
                      and t.get("method_code") == method
                      and t.get("difficulty") == diff]
        print(f"\n--- Grade {grade} / Method {method} / Diff {diff} ---")
        print(f"  Reserve candidates: {len(candidates)}")
        for i, t in enumerate(candidates, 1):
            tid = t.get("id", "?")
            text_preview = t.get("task_text", "")[:120].replace("\n", " ")
            has_solution = bool(t.get("solution"))
            has_answer = bool(t.get("correct_answer"))
            src = t.get("status", "?")
            print(f"  [{i}] {tid} src={src} sol={'Y' if has_solution else 'N'} ans={'Y' if has_answer else 'N'}")
            print(f"       text: {text_preview}...")
    
    # --- Analyze method definitions from existing tasks ---
    print("\n" + "=" * 70)
    print("METHOD DEFINITIONS - All F3/G1/G2/B2 tasks in main")
    print("=" * 70)
    
    for method_code in ["F3", "G1", "G2", "B2"]:
        all_m = [t for t in main_tasks if t.get("method_code") == method_code]
        print(f"\n--- Method {method_code} ---")
        print(f"  Total tasks: {len(all_m)}")
        
        # Group by grade
        by_grade = {}
        for t in all_m:
            g = t.get("grade", "?")
            by_grade.setdefault(g, []).append(t)
        
        for g in sorted(by_grade.keys(), key=lambda x: (isinstance(x, int), x)):
            tasks = by_grade[g]
            themes = set()
            subtopics = set()
            for t in tasks:
                themes.add(t.get("theme", "?"))
                subtopics.add(t.get("subtopic", "?"))
            print(f"  Grade {g}: {len(tasks)} tasks, themes={themes}")
            # Show first 3 task previews
            for i, t in enumerate(tasks[:5], 1):
                text = t.get("task_text", "")[:150].replace("\n", " ")
                print(f"    [{i}] {t.get('id','?')}: {text}...")

if __name__ == "__main__":
    main()
