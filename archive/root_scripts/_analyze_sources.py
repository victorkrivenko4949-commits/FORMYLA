# -*- coding: utf-8 -*-
"""Analyze VICTOR2.0 and candidate file structures."""
import json, sys

# 1. Analyze curated_bank
print("=" * 60)
print("ANALYZING curated_bank_L1_L5_fixed.json")
print("=" * 60)
try:
    with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Total tasks: {len(data)}")
    
    levels = {}
    for t in data:
        l = t.get('level', t.get('target_level', t.get('original_difficulty', '?')))
        levels[str(l)] = levels.get(str(l), 0) + 1
    for k, v in sorted(levels.items(), key=lambda x: str(x[0])):
        print(f"  Level {k}: {v} tasks")
    
    # Check for topic field
    has_topic = sum(1 for t in data if t.get('topic'))
    has_subtopic = sum(1 for t in data if t.get('subtopic'))
    has_class = sum(1 for t in data if t.get('class_level'))
    has_grade = sum(1 for t in data if t.get('grade'))
    print(f"\nHas topic: {has_topic}")
    print(f"Has subtopic: {has_subtopic}")
    print(f"Has class_level: {has_class}")
    print(f"Has grade: {has_grade}")
    
    # Sample first task keys
    if data:
        print(f"\nFirst task keys: {list(data[0].keys())}")
        print(f"First task topic: {data[0].get('topic', 'N/A')}")
        print(f"First task level: {data[0].get('level', 'N/A')}")
        print(f"First task grade/class: {data[0].get('grade', data[0].get('class_level', 'N/A'))}")
except Exception as e:
    print(f"Error: {e}")

# 2. Analyze candidate file
print("\n" + "=" * 60)
print("ANALYZING candidate file")
print("=" * 60)
try:
    cand_path = r'C:\Users\Victor\Downloads\СКАЧАТЬ_FORMYLA_3302_задачи_уровни_4_5.jsonl'
    total_lines = 0
    total_problems = 0
    level_counts = {}
    with open(cand_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_lines += 1
            obj = json.loads(line)
            problems = obj.get('problems', [])
            for p in problems:
                total_problems += 1
                lvl = p.get('level', '?')
                level_counts[str(lvl)] = level_counts.get(str(lvl), 0) + 1
    
    print(f"Total lines (olympiads): {total_lines}")
    print(f"Total problems: {total_problems}")
    for k, v in sorted(level_counts.items()):
        print(f"  Level {k}: {v} problems")
    
    # Show first problem keys
    with open(cand_path, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
        first_obj = json.loads(first_line)
        first_problems = first_obj.get('problems', [])
        if first_problems:
            print(f"\nFirst problem keys: {list(first_problems[0].keys())}")
            print(f"First problem level: {first_problems[0].get('level')}")
            print(f"Has text: {'text' in first_problems[0]}")
            print(f"Has answer: {'answer' in first_problems[0]}")
            print(f"Has solution: {'solution' in first_problems[0]}")
except Exception as e:
    print(f"Error: {e}")

print("\nDone.")
