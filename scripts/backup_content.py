#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт бэкапа контента FORMYLA в JSON файлы.
Запускается вручную или автоматически через APScheduler.

Бэкапит:
- OlympiadSecret (статьи "Секреты")
- AdaptiveTask (задачи для адаптивных тестов)
"""

import json
import os
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from models import db, OlympiadSecret, AdaptiveTask

BACKUP_DIR = "backups"
MAX_BACKUPS = 14  # Хранить последние 14 бэкапов


def backup_secrets(backup_dir: str) -> int:
    """Бэкап статей OlympiadSecret."""
    secrets = OlympiadSecret.query.all()
    data = [{
        'topic': s.topic,
        'title': s.title,
        'content': s.content,
        'difficulty_level': s.difficulty_level,
    } for s in secrets]
    
    path = os.path.join(backup_dir, 'secrets.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Также обновляем основной файл secrets_dump.json
    with open('secrets_dump.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return len(data)


def backup_adaptive_tasks(backup_dir: str) -> int:
    """Бэкап задач AdaptiveTask."""
    tasks = AdaptiveTask.query.all()
    data = [{
        'class_level': t.class_level,
        'difficulty_level': t.difficulty_level,
        'topic': t.topic,
        'subtopic': t.subtopic,
        'task_text': t.task_text,
        'solution': t.solution,
        'correct_answer': t.correct_answer,
        'criteria_1_point': t.criteria_1_point,
        'criteria_2_points': t.criteria_2_points,
    } for t in tasks]
    
    path = os.path.join(backup_dir, 'adaptive_tasks.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return len(data)


def rotate_backups():
    """Удаляет старые бэкапы, оставляя только MAX_BACKUPS последних."""
    if not os.path.exists(BACKUP_DIR):
        return
    
    backups = sorted([
        d for d in os.listdir(BACKUP_DIR)
        if os.path.isdir(os.path.join(BACKUP_DIR, d))
    ])
    
    for old in backups[:-MAX_BACKUPS]:
        old_path = os.path.join(BACKUP_DIR, old)
        shutil.rmtree(old_path)
        print(f"[BACKUP] Removed old backup: {old}")


def run_backup():
    """Основная функция бэкапа."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(BACKUP_DIR, timestamp)
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"\n[BACKUP] Starting backup at {timestamp}")
    
    with app.app_context():
        # Бэкап статей
        secrets_count = backup_secrets(backup_dir)
        print(f"[BACKUP] Secrets: {secrets_count} articles")
        
        # Бэкап задач
        tasks_count = backup_adaptive_tasks(backup_dir)
        print(f"[BACKUP] Adaptive tasks: {tasks_count} tasks")
    
    # Ротация старых бэкапов
    rotate_backups()
    
    print(f"[BACKUP] Done! Saved to {backup_dir}")
    return {
        'timestamp': timestamp,
        'secrets': secrets_count,
        'tasks': tasks_count,
        'backup_dir': backup_dir
    }


if __name__ == "__main__":
    result = run_backup()
    print(f"\n[BACKUP] Summary:")
    print(f"  - Secrets: {result['secrets']}")
    print(f"  - Tasks: {result['tasks']}")
    print(f"  - Location: {result['backup_dir']}")
