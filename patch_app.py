#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Патч для добавления subtopic_breakdown в роут free_mock_submit"""

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Ищем строку с очисткой сессии
marker = "    session.pop('free_mock_tasks', None)\n    session.pop('free_mock_grade', None)\n    session.pop('free_mock_level', None)"

if marker not in content:
    print("[ERROR] Маркер не найден!")
    idx = content.find("free_mock_tasks")
    print(f"[INFO] free_mock_tasks найдено на позиции: {idx}")
    exit(1)

# Новый код для вставки перед очисткой сессии
new_code = """    # Формируем breakdown по подтемам для UI chips
    from services.topic_taxonomy import SUBTOPIC_NAMES_RU, TOPIC_NAMES_RU, get_subtopics_for_topic
    subtopic_breakdown = []
    for i, result in enumerate(results):
        task_topic = result.get('topic', '')
        task_subtopics = get_subtopics_for_topic(task_topic)
        if task_subtopics:
            subtopic_idx = i % len(task_subtopics)
            subtopic_key = task_subtopics[subtopic_idx]
            subtopic_breakdown.append({
                'topic': TOPIC_NAMES_RU.get(task_topic, task_topic),
                'subtopic_key': subtopic_key,
                '{
