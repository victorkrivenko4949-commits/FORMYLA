#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Аудит распределения задач по темам и уровням сложности
"""

import sys
import codecs
from collections import defaultdict

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB

def audit_distribution():
    """
    Строит таблицу распределения задач по темам и уровням
    """
    print("="*80)
    print("📊 АУДИТ РАСПРЕДЕЛЕНИЯ ЗАДАЧ ПО ТЕМАМ И УРОВНЯМ")
    print("="*80)
    
    # Собираем статистику
    distribution = defaultdict(lambda: defaultdict(int))
    topics_set = set()
    
    for task in PROBLEMS_DB:
        subject = task.get('subject', 'unknown')
        subtopic = task.get('subtopic', 'unknown')
        difficulty = task.get('difficulty', 0)
        
        # Комбинируем subject и subtopic как "тему"
        topic_key = f"{subject}_{subtopic}"
        topics_set.add(topic_key)
        
        distribution[topic_key][difficulty] += 1
    
    # Сортируем темы
    topics = sorted(topics_set)
    
    print(f"\n📈 Всего задач в базе: {len(PROBLEMS_DB)}")
    print(f"📚 Уникальных тем: {len(topics)}")
    print(f"🎯 Уровней сложности: 1-7\n")
    
    # Строим таблицу
    print("="*80)
    print("ТАБЛИЦА РАСПРЕДЕЛЕНИЯ (Тема × Уровень):")
    print("="*80)
    
    # Заголовок
    header = "Тема".ljust(30) + " | " + " | ".join([f"Ур.{i}".center(5) for i in range(1, 8)]) + " | Всего"
    print(header)
    print("-"*80)
    
    total_by_level = defaultdict(int)
    empty_cells = []
    partial_cells = []
    full_cells = []
    
    for topic in topics:
        row = topic.ljust(30) + " | "
        topic_total = 0
        
        for level in range(1, 8):
            count = distribution[topic][level]
            topic_total += count
            total_by_level[level] += count
            
            # Форматируем ячейку
            if count == 0:
                cell = "❌ 0".center(5)
                empty_cells.append((topic, level))
            elif count < 5:
                cell = f"⚠️ {count}".center(5)
                partial_cells.append((topic, level, count))
            else:
                cell = f"✅{count}".center(5)
                full_cells.append((topic, level, count))
            
            row += cell + " | "
        
        row += str(topic_total).rjust(5)
        print(row)
    
    # Итоги по уровням
    print("-"*80)
    footer = "ИТОГО".ljust(30) + " | "
    for level in range(1, 8):
        footer += str(total_by_level[level]).center(5) + " | "
    footer += str(len(PROBLEMS_DB)).rjust(5)
    print(footer)
    print("="*80)
    
    # Статистика
    print(f"\n📊 СТАТИСТИКА ЯЧЕЕК:")
    print(f"✅ Полных (≥5 задач): {len(full_cells)}")
    print(f"⚠️  Частичных (1-4 задачи): {len(partial_cells)}")
    print(f"❌ Пустых (0 задач): {len(empty_cells)}")
    print(f"\n📐 Всего ячеек: {len(topics) * 7}")
    print("="*80)
    
    # Детали по проблемным ячейкам
    if empty_cells:
        print(f"\n❌ ПУСТЫЕ ЯЧЕЙКИ ({len(empty_cells)}):")
        for topic, level in empty_cells[:10]:  # Показываем первые 10
            print(f"   • {topic}, уровень {level}")
        if len(empty_cells) > 10:
            print(f"   ... и ещё {len(empty_cells) - 10} ячеек")
    
    if partial_cells:
        print(f"\n⚠️  НЕПОЛНЫЕ ЯЧЕЙКИ ({len(partial_cells)}):")
        for topic, level, count in partial_cells[:10]:
            print(f"   • {topic}, уровень {level}: {count} задач (нужно {5-count})")
        if len(partial_cells) > 10:
            print(f"   ... и ещё {len(partial_cells) - 10} ячеек")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    audit_distribution()
