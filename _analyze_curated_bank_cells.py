#!/usr/bin/env python
"""Analyze curated_bank_L1_L5_fixed.json cell structure.

Curated bank has NO 'subtopic' or 'subject' fields.
Uses 'topic' field (e.g., "Алгебра. Делимость и её свойства").
'level' is integer (1-5).
'grade' is integer (5-11).
"""
import json
from collections import defaultdict

SRC = "curated_bank_L1_L5_fixed.json"
OUT = "_curated_cell_analysis.txt"

with open(SRC, "r", encoding="utf-8") as f:
    tasks = json.load(f)

print(f"Total tasks: {len(tasks)}")
print(f"Type: {type(tasks).__name__}")

# --- Strategy 1: group by grade + level + topic (since topic = subject.subtopic) ---
cells_by_grade_level_topic = defaultdict(list)
# --- Strategy 2: group by grade + level only (original approach) ---
cells_by_grade_level = defaultdict(list)
# --- Strategy 3: group by level only ---
cells_by_level = defaultdict(list)

# Track unique values
unique_grades = set()
unique_levels = set()
unique_topics = set()
grade_level_combos = set()

for t in tasks:
    grade = t.get("grade", "")
    level = t.get("level", "")
    topic = t.get("topic", "")
    
    if grade != "": unique_grades.add(int(grade) if isinstance(grade, (int, float)) else grade)
    if level != "": unique_levels.add(int(level) if isinstance(level, (int, float)) else level)
    if topic != "": unique_topics.add(topic)
    
    g = str(grade) if grade != "" else ""
    l = str(level) if level != "" else ""
    
    # By grade + level + topic
    key1 = f"G{g}_L{l}_T<{topic}>"
    cells_by_grade_level_topic[key1].append(t)
    
    # By grade + level only
    key2 = f"G{g}_L{l}"
    cells_by_grade_level[key2].append(t)
    
    # By level only
    key3 = f"L{l}"
    cells_by_level[key3].append(t)
    
    if g and l:
        grade_level_combos.add((g, l))

def cell_key_sort(key):
    """Sort cell keys: G<grade>_L<level>_T<topic>"""
    try:
        parts = key.split("_")
        grade_part = parts[0]  # G<grade>
        level_part = parts[1]  # L<level>
        grade = int(grade_part[1:]) if grade_part[1:] else -1
        level = int(level_part[1:]) if level_part[1:] else -1
        return (grade, level, key)
    except:
        return (-1, -1, key)

def report_cells(cells_dict, strategy_name, out_lines):
    out_lines.append(f"\n{'='*70}")
    out_lines.append(f"STRATEGY: {strategy_name}")
    out_lines.append(f"Total cells: {len(cells_dict)}")
    
    sorted_keys = sorted(cells_dict.keys(), key=cell_key_sort)
    
    ok_count = 0
    over_count = 0
    under_count = 0
    empty_topic_count = 0
    
    for idx, key in enumerate(sorted_keys, 1):
        cell_tasks = cells_dict[key]
        count = len(cell_tasks)
        
        status = ""
        if count == 5:
            status = "[OK]"
            ok_count += 1
        elif count > 5:
            status = f"[OVER by {count-5}]"
            over_count += 1
        else:
            status = f"[UNDER by {5-count}]"
            under_count += 1
        
        # Check if topic is empty
        if "<>" in key:
            empty_topic_count += 1
        
        # Show grade/level/topic breakdown for first task
        t0 = cell_tasks[0]
        grade_val = t0.get("grade", "?")
        level_val = t0.get("level", "?")
        topic_val = t0.get("topic", "(empty)")
        topic_preview = topic_val[:60] if topic_val and topic_val != "(empty)" else "(empty)"
        
        out_lines.append(f"  #{idx:3d} | {key:60s} | {count:3d} tasks {status:20s}")
        out_lines.append(f"       sample: grade={grade_val}, level={level_val}, topic=\"{topic_preview}\"")
    
    out_lines.append(f"\nSummary:")
    out_lines.append(f"  Total cells: {len(cells_dict)}")
    out_lines.append(f"  OK (exactly 5): {ok_count}")
    out_lines.append(f"  Overfilled:     {over_count}")
    out_lines.append(f"  Underfilled:    {under_count}")
    if empty_topic_count:
        out_lines.append(f"  With empty topic: {empty_topic_count}")

out_lines = []
out_lines.append(f"CURATED BANK CELL ANALYSIS")
out_lines.append(f"Source: {SRC}")
out_lines.append(f"Total tasks: {len(tasks)}")
out_lines.append(f"")

# Report unique values
out_lines.append(f"=== UNIQUE VALUES ===")
out_lines.append(f"Grades: {sorted(unique_grades)}")
out_lines.append(f"Levels: {sorted(unique_levels)}")
out_lines.append(f"Unique topics: {len(unique_topics)}")
out_lines.append(f"Grade-Level combos: {sorted(grade_level_combos)}")

# Show all unique topics
out_lines.append(f"\n=== ALL UNIQUE TOPICS ({len(unique_topics)}) ===")
for i, t in enumerate(sorted(unique_topics), 1):
    out_lines.append(f"  #{i:3d}: \"{t}\"")

# Task distribution by level
out_lines.append(f"\n=== TASKS BY LEVEL ===")
for lvl in sorted(unique_levels):
    level_tasks = [t for t in tasks if t.get("level") == lvl]
    out_lines.append(f"  Level {lvl}: {len(level_tasks)} tasks")

# Task distribution by grade
out_lines.append(f"\n=== TASKS BY GRADE ===")
for gr in sorted(unique_grades):
    grade_tasks = [t for t in tasks if t.get("grade") == gr]
    out_lines.append(f"  Grade {gr}: {len(grade_tasks)} tasks")

# Task distribution by grade+level
out_lines.append(f"\n=== TASKS BY GRADE+LEVEL ===")
for gr in sorted(unique_grades):
    for lvl in sorted(unique_levels):
        gl_tasks = [t for t in tasks if t.get("grade") == gr and t.get("level") == lvl]
        if gl_tasks:
            out_lines.append(f"  G{gr}_L{lvl}: {len(gl_tasks)} tasks")

# Report by grade+level+topic (most granular)
report_cells(cells_by_grade_level_topic, "Grade + Level + Topic (most granular)", out_lines)

# Report by grade+level
report_cells(cells_by_grade_level, "Grade + Level only", out_lines)

# Report by level only
report_cells(cells_by_level, "Level only", out_lines)

# --- FIND CELL #103 (by grade+level+topic) ---
out_lines.append(f"\n{'='*70}")
out_lines.append(f"FINDING CELL #103")
sorted_by_g_l_t = sorted(cells_by_grade_level_topic.keys(), key=cell_key_sort)
if len(sorted_by_g_l_t) >= 103:
    cell103_key = sorted_by_g_l_t[102]  # 0-indexed
    cell103_tasks = cells_by_grade_level_topic[cell103_key]
    count103 = len(cell103_tasks)
    out_lines.append(f"Cell #103 (by grade+level+topic): {cell103_key}")
    out_lines.append(f"  Tasks: {count103}")
    if count103 == 5:
        out_lines.append(f"  STATUS: PERFECT ✓ (exactly 5 tasks)")
    elif count103 > 5:
        out_lines.append(f"  STATUS: OVERFILLED (need to remove {count103-5})")
    else:
        out_lines.append(f"  STATUS: UNDERFILLED (need to add {5-count103})")
    
    # Show task details
    for i, t in enumerate(cell103_tasks, 1):
        topic_short = t.get("topic", "")[:50]
        text_short = t.get("task_text", t.get("statement", ""))[:80]
        out_lines.append(f"  Task {i}: grade={t.get('grade')}, level={t.get('level')}, topic=\"{topic_short}\"")
        out_lines.append(f"    text: \"{text_short}\"")
else:
    out_lines.append(f"Only {len(sorted_by_g_l_t)} cells by grade+level+topic, cannot find #103")

# Also find cell #103 by grade+level
sorted_by_g_l = sorted(cells_by_grade_level.keys(), key=cell_key_sort)
if len(sorted_by_g_l) >= 103:
    cell103b_key = sorted_by_g_l[102]
    cell103b_tasks = cells_by_grade_level[cell103b_key]
    count103b = len(cell103b_tasks)
    out_lines.append(f"\nCell #103 (by grade+level): {cell103b_key}")
    out_lines.append(f"  Tasks: {count103b}")
    if count103b == 5:
        out_lines.append(f"  STATUS: PERFECT ✓")
    elif count103b > 5:
        out_lines.append(f"  STATUS: OVERFILLED")
    else:
        out_lines.append(f"  STATUS: UNDERFILLED")

# Tasks with empty grade or level
no_grade = [t for t in tasks if not t.get("grade") and t.get("grade") != 0]
no_level = [t for t in tasks if not t.get("level") and t.get("level") != 0]
no_topic = [t for t in tasks if not t.get("topic")]
out_lines.append(f"\n{'='*70}")
out_lines.append(f"EMPTY FIELD ANALYSIS")
out_lines.append(f"Tasks with empty grade: {len(no_grade)}")
out_lines.append(f"Tasks with empty level: {len(no_level)}")
out_lines.append(f"Tasks with empty topic: {len(no_topic)}")

if no_grade:
    out_lines.append(f"\nSample tasks with empty grade:")
    for t in no_grade[:5]:
        out_lines.append(f"  id={t.get('original_id','?')}, level={t.get('level')}, topic=\"{t.get('topic','')[:40]}\"")

# Write to UTF-8 file
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print(f"\nReport written to {OUT}")
print(f"Total cells by grade+level+topic: {len(cells_by_grade_level_topic)}")
print(f"Total cells by grade+level: {len(cells_by_grade_level)}")
print(f"Total cells by level: {len(cells_by_level)}")
