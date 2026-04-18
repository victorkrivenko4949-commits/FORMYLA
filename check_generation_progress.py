"""
Скрипт для проверки прогресса генерации задач
"""

import os
import json

def check_progress():
    """Проверяет прогресс генерации"""
    
    output_file = "adaptive_tasks_full.json"
    
    if not os.path.exists(output_file):
        print("⏳ Файл adaptive_tasks_full.json еще не создан")
        print("💡 Генерация все еще идет...")
        return
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        
        total = len(tasks)
        target = 300
        progress = (total / target) * 100
        
        print("=" * 80)
        print(f"📊 ПРОГРЕСС ГЕНЕРАЦИИ")
        print("=" * 80)
        print(f"Сгенерировано: {total}/{target} задач ({progress:.1f}%)")
        print(f"Осталось: {target - total} задач")
        print()
        
        # Статистика по темам
        topics = {}
        for task in tasks:
            topic = task.get('topic', 'Unknown')
            topics[topic] = topics.get(topic, 0) + 1
        
        print(f"Уникальных тем: {len(topics)}/25")
        print()
        
        if total == target:
            print("✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
            print()
            print("Следующий шаг:")
            print("  python import_adaptive_tasks.py adaptive_tasks_full.json")
        else:
            print("⏳ Генерация продолжается...")
        
        print("=" * 80)
        
    except json.JSONDecodeError:
        print("⚠️ Файл еще записывается, подождите...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    check_progress()
