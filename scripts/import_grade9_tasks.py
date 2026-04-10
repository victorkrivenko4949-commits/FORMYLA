#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для импорта 480 новых задач для 9 класса в problems.py
"""
import json
import os

# Пути к JSON файлам в Downloads
DOWNLOADS_PATH = "C:/Users/Victor/Downloads"
JSON_FILES = [
    "algebra_base_90001_90040.json",
    "algebra_adv_90041_90080.json",
    "geometry_90101_90180.json",
    "number_theory_90201_90280.json",
    "combinatorics_90301_90380.json",
    "kl_movement_full_90401_90560.json"
]

def load_tasks_from_json(filepath):
    """Загрузить задачи из JSON файла"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'problems' in data:
                return data['problems']
            else:
                print(f"⚠️  Неизвестный формат в {filepath}")
                return []
    except Exception as e:
        print(f"❌ Ошибка чтения {filepath}: {e}")
        return []

def main():
    """Импорт всех задач"""
    all_tasks = []
    
    print("="*60)
    print("IMPORT TASKS FOR GRADE 9")
    print("="*60)
    
    for filename in JSON_FILES:
        filepath = os.path.join(DOWNLOADS_PATH, filename)
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            continue
        
        tasks = load_tasks_from_json(filepath)
        print(f"[+] {filename}: {len(tasks)} tasks")
        all_tasks.extend(tasks)
    
    print("="*60)
    print(f"TOTAL LOADED: {len(all_tasks)} tasks")
    print("="*60)
    
    # Читаем текущий problems.py
    problems_path = "problems.py"
    
    try:
        with open(problems_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим PROBLEMS_DB
        if 'PROBLEMS_DB = [' in content:
            # Извлекаем существующие задачи
            start = content.find('PROBLEMS_DB = [')
            end = content.find('\n]', start) + 2
            
            if end > start:
                # Формируем новый список
                new_content = content[:start] + 'PROBLEMS_DB = [\n'
                
                # Добавляем новые задачи
                for task in all_tasks:
                    new_content += '    ' + json.dumps(task, ensure_ascii=False) + ',\n'
                
                new_content += ']\n' + content[end:]
                
                # Сохраняем
                with open(problems_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print(f"[OK] Tasks added to {problems_path}")
                print(f"[INFO] New PROBLEMS_DB size: {len(all_tasks)} tasks")
            else:
                print("[ERROR] Could not find end of PROBLEMS_DB")
        else:
            print("[ERROR] PROBLEMS_DB not found in problems.py")
    
    except Exception as e:
        print(f"[ERROR] Failed to update problems.py: {e}")

if __name__ == '__main__':
    main()
