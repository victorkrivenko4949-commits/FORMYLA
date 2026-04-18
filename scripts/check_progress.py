#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Progress Checker for Mass Generation
Reads generated_tasks_production.json and displays quality samples.
"""

import json
import random
import os
import sys
import io
import re

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def read_generated_tasks(filepath):
    """
    Reads JSON file with generated tasks (handles incomplete writes).
    
    Args:
        filepath: Path to JSON file
        
    Returns:
        List of task dictionaries
    """
    tasks = []
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return tasks
    
    try:
        # Read entire file
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Extract all complete JSON objects using regex
        # Pattern: { ... } followed by comma or end
        pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                task = json.loads(match)
                # Validate it's a task (has required fields)
                if 'text' in task and 'answer' in task:
                    tasks.append(task)
            except json.JSONDecodeError:
                continue
                            
    except Exception as e:
        print(f"⚠️  Error reading file: {e}")
        print("   (This is normal if generation is still in progress)")
    
    return tasks


def display_task(task, index):
    """
    Displays a single task in beautiful format.
    
    Args:
        task: Task dictionary
        index: Task index for display
    """
    print(f"\n{'='*80}")
    print(f"📝 ЗАДАЧА #{index}")
    print(f"{'='*80}")
    
    # Metadata
    print(f"🎓 Класс:      {task.get('grade', 'N/A')}")
    print(f"📚 Тема:       {task.get('topic', 'N/A')}")
    print(f"📖 Подтема:    {task.get('subtopic', 'N/A')}")
    print(f"⭐ Сложность:  {task.get('difficulty', 'N/A')}/7")
    print(f"🆔 ID:         {task.get('id', 'N/A')}")
    
    print(f"\n{'─'*80}")
    print("📋 УСЛОВИЕ:")
    print(f"{'─'*80}")
    print(task.get('text', 'N/A'))
    
    print(f"\n{'─'*80}")
    print("✅ ОТВЕТ:")
    print(f"{'─'*80}")
    answer = task.get('answer', task.get('correct_answer', 'N/A'))
    print(answer)
    
    # Check answer format
    answer_str = str(answer).strip()
    if len(answer_str) > 50:
        print("⚠️  WARNING: Answer is too long (should be short/numeric)")
    
    print(f"\n{'─'*80}")
    print("💡 РЕШЕНИЕ:")
    print(f"{'─'*80}")
    solution = task.get('solution', 'N/A')
    # Truncate solution if too long
    if len(solution) > 500:
        print(solution[:500] + "...")
        print(f"\n[... решение обрезано, полная длина: {len(solution)} символов]")
    else:
        print(solution)
    
    print(f"\n{'='*80}\n")


def analyze_tasks(tasks):
    """
    Analyzes task distribution and quality.
    
    Args:
        tasks: List of task dictionaries
    """
    if not tasks:
        print("❌ No tasks to analyze")
        return
    
    print(f"\n{'='*80}")
    print("📊 СТАТИСТИКА ГЕНЕРАЦИИ")
    print(f"{'='*80}")
    
    print(f"\n✅ Всего задач сгенерировано: {len(tasks)}")
    print(f"📈 Прогресс: {len(tasks)}/504 ({len(tasks)*100//504}%)")
    
    # Count by difficulty
    difficulty_counts = {}
    for task in tasks:
        diff = task.get('difficulty', 'Unknown')
        difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1
    
    print(f"\n📊 Распределение по сложности:")
    for diff in sorted(difficulty_counts.keys()):
        count = difficulty_counts[diff]
        bar = '█' * (count // 2)
        print(f"   Уровень {diff}: {count:3d} задач {bar}")
    
    # Count by topic
    topic_counts = {}
    for task in tasks:
        topic = task.get('topic', 'Unknown')
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    print(f"\n📚 Распределение по темам:")
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        bar = '█' * (count // 5)
        print(f"   {topic:25s}: {count:3d} задач {bar}")
    
    # Check answer formats
    print(f"\n🔍 Проверка формата ответов:")
    long_answers = 0
    for task in tasks:
        answer = str(task.get('answer', task.get('correct_answer', ''))).strip()
        if len(answer) > 50:
            long_answers += 1
    
    if long_answers > 0:
        print(f"   ⚠️  Найдено {long_answers} задач с длинными ответами (>50 символов)")
    else:
        print(f"   ✅ Все ответы имеют корректный формат")
    
    print(f"\n{'='*80}\n")


def main():
    """Main entry point."""
    filepath = 'generated_tasks_production.json'
    
    print("="*80)
    print(" " * 20 + "PROGRESS CHECKER")
    print("="*80)
    print(f"\n📁 Читаем файл: {filepath}")
    print("   (read-only режим, не мешаем основному процессу)\n")
    
    # Read tasks
    tasks = read_generated_tasks(filepath)
    
    if not tasks:
        print("\n⚠️  Пока нет сгенерированных задач или файл еще не создан.")
        print("   Подождите несколько минут и запустите скрипт снова.")
        return
    
    # Analyze distribution
    analyze_tasks(tasks)
    
    # Display random samples
    print("="*80)
    print(" " * 25 + "СЛУЧАЙНЫЕ ОБРАЗЦЫ")
    print("="*80)
    
    num_samples = min(3, len(tasks))
    samples = random.sample(tasks, num_samples)
    
    for i, task in enumerate(samples, 1):
        display_task(task, i)
    
    print("="*80)
    print("✅ Проверка завершена!")
    print("="*80)


if __name__ == '__main__':
    main()
