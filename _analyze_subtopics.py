#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyse all possible interpretations of 'подтема' (subtopic) in the data."""

import json
import sys

with open('adaptive_data/adaptive_full_9120_fixed.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

out = sys.stdout

out.write('=== Анализ подтем ===\n\n')
out.write(f'Всего задач: {len(data)}\n\n')

# 1) unique section values
sections = set(t.get('section', '') for t in data)
out.write(f'1. Уникальных section: {len(sections)}\n')

# 2) unique topic values
topics = set(t.get('topic', '') for t in data)
out.write(f'2. Уникальных topic: {len(topics)}\n')

# 3) unique (grade, section)
grade_sections = set((t.get('grade'), t.get('section', '')) for t in data)
out.write(f'3. Уникальных (grade, section): {len(grade_sections)}\n')

# 4) unique (grade, topic)
grade_topics = set((t.get('grade'), t.get('topic', '')) for t in data)
out.write(f'4. Уникальных (grade, topic): {len(grade_topics)}\n')

# 5) unique (level, grade, topic) — i.e. cells as used in _fill_l3_holes.py
cells = set((t.get('level'), t.get('grade'), t.get('topic', '')) for t in data)
out.write(f'5. Уникальных (level, grade, topic) — ячеек: {len(cells)}\n')

# 6) unique (level, grade, section)
level_grade_sections = set((t.get('level'), t.get('grade'), t.get('section', '')) for t in data)
out.write(f'6. Уникальных (level, grade, section): {len(level_grade_sections)}\n')

# 7) Print grades
grades = sorted(set(t.get('grade') for t in data), key=lambda x: str(x))
out.write(f'\nКлассы: {grades}\n')
levels = sorted(set(t.get('level') for t in data), key=lambda x: str(x))
out.write(f'Уровни: {levels}\n\n')

# 8) Per level analysis
out.write('=== По уровням ===\n')
for level in levels:
    ldata = [t for t in data if t.get('level') == level]
    s = set(t.get('section', '') for t in ldata)
    tp = set(t.get('topic', '') for t in ldata)
    gs = set((t.get('grade'), t.get('section', '')) for t in ldata)
    gt = set((t.get('grade'), t.get('topic', '')) for t in ldata)
    out.write(f'  level={level}: задач={len(ldata)}, sections={len(s)}, topics={len(tp)}, (grade,section)={len(gs)}, (grade,topic)={len(gt)}\n')

# 9) Per grade analysis
out.write('\n=== По классам ===\n')
for g in grades:
    gdata = [t for t in data if t.get('grade') == g]
    s = set(t.get('section', '') for t in gdata)
    tp = set(t.get('topic', '') for t in gdata)
    out.write(f'  grade={g}: задач={len(gdata)}, sections={len(s)}, topics={len(tp)}\n')

# 10) Per (grade, level) analysis
out.write('\n=== Section по (класс, уровень) ===\n')
for g in grades:
    for level in levels:
        secs = set(t.get('section', '') for t in data if t.get('grade') == g and t.get('level') == level)
        if secs:
            out.write(f'  grade={g}, level={level}: sections={len(secs)}\n')

out.write('\n=== Topic по (класс, уровень) ===\n')
for g in grades:
    for level in levels:
        tops = set(t.get('topic', '') for t in data if t.get('grade') == g and t.get('level') == level)
        if tops:
            out.write(f'  grade={g}, level={level}: topics={len(tops)}\n')

# 11) Sum of topics across all (grade, level) — cumulative
out.write('\n=== Сумма всех topic по (grade, level) ===\n')
total_topic_gl = 0
for g in grades:
    for level in levels:
        tops = set(t.get('topic', '') for t in data if t.get('grade') == g and t.get('level') == level)
        if tops:
            total_topic_gl += len(tops)
out.write(f'  Сумма всех topic по (grade, level): {total_topic_gl}\n')

total_section_gl = 0
for g in grades:
    for level in levels:
        secs = set(t.get('section', '') for t in data if t.get('grade') == g and t.get('level') == level)
        if secs:
            total_section_gl += len(secs)
out.write(f'  Сумма всех section по (grade, level): {total_section_gl}\n')

# 12) Also check: (grade, level, section) — unique combos
gls = set((t.get('grade'), t.get('level'), t.get('section', '')) for t in data)
out.write(f'\n7. Уникальных (grade, level, section): {len(gls)}\n')

glt = set((t.get('grade'), t.get('level'), t.get('topic', '')) for t in data)
out.write(f'8. Уникальных (grade, level, topic): {len(glt)}\n')

out.write('\n=== ПРОВЕРКА НА 135 ===\n')
out.write(f'  section = {len(sections)} (не 135)\n')
out.write(f'  topic = {len(topics)} (не 135)\n')
out.write(f'  (grade, section) = {len(grade_sections)} (не 135)\n')
out.write(f'  (grade, topic) = {len(grade_topics)} (не 135)\n')
out.write(f'  (level, grade, topic) = {len(cells)} (не 135)\n')
out.write(f'  (grade, level, section) = {len(gls)} (не 135)\n')
out.write(f'  сумма topic по (grade, level) = {total_topic_gl} (не 135)\n')
out.write(f'  сумма section по (grade, level) = {total_section_gl} (не 135)\n')

out.write('\nГотово.\n')
