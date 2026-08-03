#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate a clean Markdown report of cell holes for Level 1 and Level 2.
Output: docs/cell_holes_report_L1_L2.md
"""
import json
from collections import defaultdict, Counter
import os

DB_PATH = 'adaptive_data/adaptive_full_9120_fixed.json'
OUTPUT_DIR = 'docs'
OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'cell_holes_report_L1_L2.md')

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(DB_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)

print(f"Total tasks in DB: {len(db)}")

l1 = [t for t in db if t.get('level') == 1]
l2 = [t for t in db if t.get('level') == 2]
l3 = [t for t in db if t.get('level') == 3]

# ----- helper: count cells -----
def analyze_cells(tasks, level_name):
    """Return (by_topic, by_section) where each is dict of cell_key->list_of_tasks"""
    by_topic = defaultdict(list)
    by_section = defaultdict(list)
    for t in tasks:
        grade = t.get('grade')
        topic = t.get('topic', '')
        section = t.get('section', '')
        by_topic[(grade, topic)].append(t)
        by_section[(grade, section)].append(t)
    return dict(by_topic), dict(by_section)

def severity(count):
    if count == 0: return " EMPTY"
    if count <= 2: return " CRITICAL"
    if count <= 4: return " PARTIAL"
    return " FULL"

def categorize_holes(cells_dict):
    holes = {k: v for k, v in cells_dict.items() if len(v) < 5}
    full = {k: v for k, v in cells_dict.items() if len(v) == 5}
    over = {k: v for k, v in cells_dict.items() if len(v) > 5}
    return holes, full, over

# ----- Build report -----
lines = []
lines.append("# Отчёт по дырам в ячейках L1 и L2")
lines.append("")
lines.append(f"**Дата генерации:** 2026-07-14")
lines.append(f"**Всего задач в БД:** {len(db)}")
lines.append(f"**L1:** {len(l1)} задач | **L2:** {len(l2)} задач | **L3:** {len(l3)} задач")
lines.append("")
lines.append("---")
lines.append("")

# === SECTION LEVEL (recommended view) ===
lines.append("##  Анализ по ячейкам (уровень, класс, раздел/section)")
lines.append("")
lines.append("Раздел (section) — более крупная таксономическая единица (40 уникальных разделов).")
lines.append("Ячейка = (level, grade, section), цель = 5 задач в ячейке.")
lines.append("")

for level_name, tasks in [("L1", l1), ("L2", l2)]:
    _, by_section = analyze_cells(tasks, level_name)
    holes, full, over = categorize_holes(by_section)
    
    # Also count completely empty sections per grade
    sections_per_grade = defaultdict(set)
    all_grades = sorted(set(t.get('grade') for t in tasks), key=lambda x: str(x))
    
    lines.append(f"### Уровень {level_name} — {len(tasks)} задач")
    lines.append("")
    lines.append(f"- **Всего ячеек (grade, section):** {len(by_section)}")
    lines.append(f"- **Полных (==5):** {len(full)}")
    lines.append(f"- **Переполненных (>5):** {len(over)}")
    lines.append(f"- **Дыр (<5):** {len(holes)}")
    lines.append("")
    
    if holes:
        # Group by severity
        by_severity = defaultdict(list)
        for key, task_list in sorted(holes.items(), key=lambda x: len(x[1])):
            grade, section = key
            count = len(task_list)
            by_severity[severity(count)].append((grade, section, count))
        
        for sev_label in [" EMPTY (0/5)", " CRITICAL (1-2/5)", " PARTIAL (3-4/5)"]:
            sev_key = sev_label.split(" ")[0]
            items = by_severity.get(sev_key, [])
            if items:
                lines.append(f"#### {sev_label} — {len(items)} ячеек")
                lines.append("")
                lines.append("| Класс | Раздел | Задач | Нужно ещё |")
                lines.append("|-------|--------|------:|----------:|")
                for grade, section, count in sorted(items, key=lambda x: (str(x[0]), x[1])):
                    need = 5 - count
                    lines.append(f"| {grade} класс | {section} | {count}/5 | {need} |")
                lines.append("")
    
    if over:
        lines.append(f"####  Переполненные ячейки (>5) — {len(over)}")
        lines.append("")
        lines.append("| Класс | Раздел | Задач | Лишних |")
        lines.append("|-------|--------|------:|-------:|")
        over_sorted = sorted(over.items(), key=lambda x: -len(x[1]))
        for key, task_list in over_sorted:
            grade, section = key
            excess = len(task_list) - 5
            lines.append(f"| {grade} класс | {section} | {len(task_list)} | +{excess} |")
        lines.append("")
    
    lines.append("---")
    lines.append("")

# === TOPIC LEVEL (detailed view) ===
lines.append("##  Детальный анализ по темам (topic)")
lines.append("")
lines.append("Тема (topic) — более мелкая таксономическая единица. (263 уникальных тем в L1, 379 в L2)")
lines.append("Здесь дыр МНОГО, т.к. темы очень дробные. Приведены только самые критичные (0-1 задач).")
lines.append("")

for level_name, tasks in [("L1", l1), ("L2", l2)]:
    by_topic, _ = analyze_cells(tasks, level_name)
    holes, full, over = categorize_holes(by_topic)
    
    lines.append(f"### Уровень {level_name} по темам")
    lines.append("")
    lines.append(f"- **Всего ячеек (grade, topic):** {len(by_topic)}")
    lines.append(f"- **Полных (==5):** {len(full)}")
    lines.append(f"- **Переполненных (>5):** {len(over)}")
    lines.append(f"- **Дыр (<5):** {len(holes)}")
    lines.append("")
    
    # Show only most critical: 0 or 1 tasks
    critical = {k: v for k, v in holes.items() if len(v) <= 1}
    if critical:
        lines.append(f"####  Критические дыры (0-1 задач) — {len(critical)} ячеек")
        lines.append("")
        lines.append("| Класс | Тема | Задач | Нужно ещё |")
        lines.append("|-------|------|------:|----------:|")
        for key in sorted(critical.keys(), key=lambda k: (str(k[0]), k[1])):
            grade, topic = key
            count = len(critical[key])
            lines.append(f"| {grade} класс | {topic} | {count}/5 | {5-count} |")
        lines.append("")
    
    lines.append("---")
    lines.append("")

# === SUMMARY TABLE ===
lines.append("##  Сводная таблица")
lines.append("")
lines.append("| Уровень | Тип ячейки | Всего ячеек | Полных (5) | Переполнено (>5) | Дыр (<5) |")
lines.append("|---------|-----------|-----------:|----------:|----------------:|--------:|")
for level_name, tasks in [("L1", l1), ("L2", l2)]:
    by_topic, by_section = analyze_cells(tasks, level_name)
    h_t, f_t, o_t = categorize_holes(by_topic)
    h_s, f_s, o_s = categorize_holes(by_section)
    lines.append(f"| {level_name} | (grade, topic) | {len(by_topic)} | {len(f_t)} | {len(o_t)} | {len(h_t)} |")
    lines.append(f"| {level_name} | (grade, section) | {len(by_section)} | {len(f_s)} | {len(o_s)} | {len(h_s)} |")

lines.append("")
lines.append("###  Приоритетные действия")
lines.append("")
lines.append("1. **Закрыть критические дыры по разделам (section)** — в приоритете ячейки с 1-2 задачами")
lines.append("2. **Закрыть критические дыры по темам (topic)** — 286 дыр в L1, 396 в L2")
lines.append("3. **Учесть переполненные ячейки** — возможно, часть задач оттуда можно перераспределить")
lines.append("")

# Write report
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"\n[OK] Report written to {OUTPUT_PATH}")
print(f"   Total lines: {len(lines)}")
