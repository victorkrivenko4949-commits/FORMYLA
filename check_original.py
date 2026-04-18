#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Проверка восстановленного оригинала
"""

import sys
import codecs

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB
from collections import defaultdict

print("="*80)
print("✅ ПРОВЕРКА ВОССТАНОВЛЕННОГО ОРИГИНАЛА")
print("="*80)

print(f"\n📊 Общее количество задач: {len(PROBLEMS_DB)}")

# Собираем темы
topics = defaultdict(int)
for task in PROBLEMS_DB:
    subject = task.get('subject', 'unknown')
    subtopic = task.get('subtopic', 'unknown')
    topic_key = f"{subject}_{subtopic}"
    topics[topic_key] += 1

print(f"📚 Уникальных тем: {len(topics)}\n")

print("="*80)
print("ПЕРВЫЕ 3 ТЕМЫ И ПРИМЕРЫ ЗАДАЧ:")
print("="*80)

for i, (topic_key, count) in enumerate(sorted(topics.items())[:3], 1):
    print(f"\n[ТЕМА {i}] {topic_key}")
    print(f"Количество задач: {count}")
    
    # Находим задачи этой темы
    subject, subtopic = topic_key.split('_', 1)
    matching = [p for p in PROBLEMS_DB 
                if p.get('subject') == subject 
                and p.get('subtopic') == subtopic]
    
    print(f"\nПримеры задач:")
    print("-"*80)
    for j, task in enumerate(matching[:2], 1):
        text = task.get('text', '')[:120]
        print(f"{j}. {text}...")
    print("-"*80)

print(f"\n{'='*80}")
print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
print("="*80)
