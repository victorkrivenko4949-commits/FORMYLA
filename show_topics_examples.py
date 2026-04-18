#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ШАГ 1: Показать список тем и примеры задач
"""

import sys
import codecs
from collections import defaultdict

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB

def show_topics_and_examples():
    """
    Показывает список тем и примеры задач из каждой
    """
    print("="*80)
    print("📚 ШАГ 1: АНАЛИЗ ТЕМ И ПРИМЕРЫ ЗАДАЧ")
    print("="*80)
    
    # Собираем уникальные темы
    topics = defaultdict(list)
    
    for task in PROBLEMS_DB:
        subject = task.get('subject', 'unknown')
        subtopic = task.get('subtopic', 'unknown')
        topic_key = f"{subject}_{subtopic}"
        topics[topic_key].append(task)
    
    print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")
    print(f"📚 Уникальных тем: {len(topics)}\n")
    
    print("="*80)
    print("СПИСОК ВСЕХ ТЕМ И ПРИМЕРЫ ЗАДАЧ:")
    print("="*80)
    
    for i, (topic_key, tasks) in enumerate(sorted(topics.items()), 1):
        print(f"\n[ТЕМА {i}] {topic_key}")
        print(f"Количество задач: {len(tasks)}")
        print(f"\nПримеры задач:")
        print("-"*80)
        
        # Показываем первые 2 задачи
        for j, task in enumerate(tasks[:2], 1):
            text = task.get('text', '')[:150]
            print(f"{j}. {text}...")
        
        print("-"*80)
    
    print(f"\n{'='*80}")

if __name__ == '__main__':
    show_topics_and_examples()
