# -*- coding: utf-8 -*-
"""ШАГ 1: Найти битую задачу с 'x - 2 = x + 10' и похожие"""
import json, glob, re, sys

print("=== ШАГ 1: Поиск в adaptive_data/*.json ===")

# Паттерны для поиска
search_texts = ['x - 2 = x + 10', '(x - 2 = x + 10)', 'x-2=x+10']
suspicious_patterns = [
    r'\([^)]*=[^)]*=',           # два = в одних скобках
    r'=\s*\)',                    # = перед закрывающей скобкой
    r'\(\s*\w\s*[-+]\s*\d+\s*=', # (x - N = внутри скобок
    r'\xb7\s*\(\s*\w\s*[-+].*=', # · (x ... = в скобках
    r'cdot\s*\([^)]*=',          # \cdot( ... =
]

found_exact = []
found_suspicious = []

for filepath in glob.glob('adaptive_data/*.json'):
    try:
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
        tasks = data if isinstance(data, list) else data.get('tasks', [])
        for t in tasks:
            text = t.get('task_text', '') or t.get('statement', '') or t.get('problem', '')
            tid = t.get('id', '?')
            
            # Точный поиск
            for s in search_texts:
                if s in text:
                    found_exact.append({'file': filepath, 'id': tid, 'text': text[:300]})
                    break
            
            # Подозрительные паттерны
            for pat in suspicious_patterns:
                if re.search(pat, text):
                    found_suspicious.append({'file': filepath, 'id': tid, 'text': text[:200], 'pat': pat})
                    break
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

print(f"\n--- Точные совпадения: {len(found_exact)} ---")
for item in found_exact:
    print(f"  File: {item['file']}, ID: {item['id']}")
    print(f"  Text: {item['text']}")

print(f"\n--- Подозрительные паттерны: {len(found_suspicious)} ---")
for item in found_suspicious[:20]:
    print(f"  File: {item['file']}, ID: {item['id']}, Pat: {item['pat']}")
    print(f"  Text: {item['text']}")

# Также ищем в БД
print("\n=== Поиск в БД (AdaptiveTask) ===")
try:
    import os
    os.environ.setdefault('FLASK_ENV', 'development')
    from app import app
    from models import db, AdaptiveTask
    with app.app_context():
        for s in search_texts:
            tasks = AdaptiveTask.query.filter(AdaptiveTask.task_text.like(f'%{s}%')).all()
            if tasks:
                print(f"  Found {len(tasks)} tasks with '{s}':")
                for t in tasks:
                    print(f"    ID {t.id} [cl{t.class_level} L{t.difficulty_level}]: {t.task_text[:200]}")
                    print(f"    answer: {t.correct_answer}")
        
        # Подозрительные в БД
        print("\n  Checking suspicious patterns in DB...")
        count = 0
        for t in AdaptiveTask.query.all():
            text = t.task_text or ''
            for pat in suspicious_patterns:
                if re.search(pat, text):
                    print(f"    ID {t.id} [cl{t.class_level} L{t.difficulty_level}]: {text[:150]}")
                    count += 1
                    break
        print(f"  Total suspicious in DB: {count}")
except Exception as e:
    print(f"  DB search error: {e}")

print("\nDone.")
