#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fill the G2|L1 cell (grade=2, level=1) from 1 task to 5 tasks.
Generates 4 simple grade-2 level-1 math problems.
"""
import json
from copy import deepcopy

SRC = 'curated_bank_L1_L5_fixed.json'
DST = 'curated_bank_L1_L5_fixed.json'

bank = json.load(open(SRC, 'r', encoding='utf-8'))

# Find the existing G2|L1 task as template
g2l1 = [t for t in bank if t.get('level')==1 and str(t.get('grade',''))=='2']
assert len(g2l1) == 1, f"Expected 1 G2|L1 task, found {len(g2l1)}"
template = g2l1[0]
print(f"Template: {template['original_id']} topic={template['topic']}")

# Current max rank in G2|L1
max_rank = max(t.get('rank_in_cell', 0) for t in g2l1)
print(f"Current max rank: {max_rank}")

# Find max source_index and original_id number
max_src_idx = max(t.get('source_index', 0) for t in bank)
max_id_num = 0
for t in bank:
    oid = t.get('original_id', '')
    if oid.startswith('SEL1080-'):
        try:
            n = int(oid.split('-')[1])
            if n > max_id_num:
                max_id_num = n
        except:
            pass

print(f"Max source_index: {max_src_idx}")
print(f"Max original_id num: SEL1080-{max_id_num:04d}")

# 4 new grade-2 level-1 tasks
# Grade 2 = 2nd class students (~8 years old), Level 1 = easiest difficulty
new_tasks_data = [
    {
        "topic": "Сложение и вычитание",
        "statement": "В вазе лежало 15 яблок. Мама добавила ещё 8 яблок. Сколько яблок стало в вазе?",
        "answer": "23 яблока",
        "solution": "15 + 8 = 23 (яб.)",
        "task_text": "В вазе лежало 15 яблок. Мама добавила ещё 8 яблок. Сколько яблок стало в вазе?"
    },
    {
        "topic": "Умножение",
        "statement": "На каждой тарелке лежит по 5 пирожков. Сколько пирожков на 4 тарелках?",
        "answer": "20 пирожков",
        "solution": "5 * 4 = 20 (п.)",
        "task_text": "На каждой тарелке лежит по 5 пирожков. Сколько пирожков на 4 тарелках?"
    },
    {
        "topic": "Периметр",
        "statement": "Длина прямоугольника 6 см, а ширина 3 см. Найди периметр прямоугольника.",
        "answer": "18 см",
        "solution": "P = (6 + 3) * 2 = 9 * 2 = 18 (см)",
        "task_text": "Длина прямоугольника 6 см, а ширина 3 см. Найди периметр прямоугольника."
    },
    {
        "topic": "Задачи на стоимость",
        "statement": "Одна ручка стоит 7 рублей. Сколько рублей нужно заплатить за 3 такие ручки?",
        "answer": "21 рубль",
        "solution": "7 * 3 = 21 (р.)",
        "task_text": "Одна ручка стоит 7 рублей. Сколько рублей нужно заплатить за 3 такие ручки?"
    }
]

# Build new task objects
new_tasks = []
for i, td in enumerate(new_tasks_data):
    max_id_num += 1
    max_src_idx += 1
    rank = max_rank + 1 + i
    task = {
        "original_id": f"SEL1080-{max_id_num:04d}",
        "source_index": max_src_idx,
        "class_level": None,
        "original_difficulty": None,
        "target_level": "L1",
        "task_text": td["task_text"],
        "image": None,
        "topic": td["topic"],
        "audit_mode": None,
        "evidence_source": "ai_fill_g2_l1",
        "decision_status": None,
        "final_court_status": None,
        "confidence": None,
        "feature_score": None,
        "mechanical_mapping": None,
        "quality_score": 90,
        "rank_in_cell": rank,
        "total_in_cell_pool": 5,
        "issues": None,
        "in_duplicate_cluster": False,
        "duplicate_clusters": None,
        "validation_warnings": None,
        "selection_notes": None,
        "statement": td["statement"],
        "answer": td["answer"],
        "solution": td["solution"],
        "level": 1,
        "grade": 2,
        "fixed_by_ai": True,
        "fix_timestamp": "2026-07-17T21:55:00+03:00",
        "changes_made": ["cell_fill: Generated for G2|L1 hole (4 new tasks)"],
        "pending_live_audit": True
    }
    new_tasks.append(task)

# Append to bank
for t in new_tasks:
    # Verify all keys from template are present
    for k in template.keys():
        if k not in t:
            t[k] = deepcopy(template[k])
    bank.append(t)

print(f"\nAdded {len(new_tasks)} new tasks")
print(f"Bank size: {len(bank)}")

# Verify
g2l1_after = [t for t in bank if t.get('level')==1 and str(t.get('grade',''))=='2']
print(f"G2|L1 count after: {len(g2l1_after)}")
for t in g2l1_after:
    print(f"  rank={t.get('rank_in_cell')} id={t.get('original_id')} topic={t.get('topic')}")

# Save
json.dump(bank, open(DST, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\nSaved to {DST}")

# Also create a backup
import shutil
shutil.copy(SRC, SRC.replace('.json', '_before_fill_g2_l1.json'))
print(f"Backup created")
