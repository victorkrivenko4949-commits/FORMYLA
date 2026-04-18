"""
Скрипт для импорта сгенерированных задач в таблицу adaptive_tasks
"""

import os
import json
from app import app
from models import db, AdaptiveTask


def import_tasks_from_json(json_file):
    """Импортирует задачи из JSON файла в базу данных"""
    
    if not os.path.exists(json_file):
        print(f"❌ Файл {json_file} не найден!")
        return
    
    with open(json_file, 'r', encoding='utf-8') as f:
        tasks_data = json.load(f)
    
    print(f"📂 Загружено {len(tasks_data)} задач из {json_file}")
    print()
    
    with app.app_context():
        # Создаем таблицу если её нет
        db.create_all()
        
        imported_count = 0
        skipped_count = 0
        
        for idx, task_data in enumerate(tasks_data, 1):
            try:
                # Проверяем, есть ли уже такая задача (по тексту условия)
                existing = AdaptiveTask.query.filter_by(
                    task_text=task_data['task_text']
                ).first()
                
                if existing:
                    print(f"⏭️  Задача {idx}: уже существует (ID {existing.id}), пропускаем")
                    skipped_count += 1
                    continue
                
                # Создаем новую задачу
                task = AdaptiveTask(
                    class_level=task_data['class_level'],
                    difficulty_level=task_data['difficulty_level'],
                    topic=task_data['topic'],
                    task_text=task_data['task_text'],
                    solution=task_data['solution'],
                    criteria_1_point=task_data['criteria_1_point'],
                    criteria_2_points=task_data['criteria_2_points']
                )
                
                db.session.add(task)
                imported_count += 1
                
                print(f"✅ Задача {idx}: импортирована (Класс {task.class_level}, Уровень {task.difficulty_level}, Тема: {task.topic[:40]}...)")
                
                # Коммитим каждые 10 задач
                if imported_count % 10 == 0:
                    db.session.commit()
                    print(f"💾 Сохранено {imported_count} задач...")
            
            except Exception as e:
                print(f"❌ Ошибка при импорте задачи {idx}: {e}")
                db.session.rollback()
        
        # Финальный коммит
        try:
            db.session.commit()
            print()
            print("=" * 80)
            print(f"✅ ИМПОРТ ЗАВЕРШЕН!")
            print(f"📊 Импортировано: {imported_count} задач")
            print(f"⏭️  Пропущено (дубликаты): {skipped_count} задач")
            print(f"📈 Всего в базе: {AdaptiveTask.query.count()} задач")
            print("=" * 80)
        except Exception as e:
            print(f"❌ Ошибка при финальном сохранении: {e}")
            db.session.rollback()


def show_stats():
    """Показать статистику по задачам в базе"""
    
    with app.app_context():
        total = AdaptiveTask.query.count()
        
        if total == 0:
            print("📊 База данных adaptive_tasks пуста")
            return
        
        print("=" * 80)
        print(f"📊 СТАТИСТИКА БАЗЫ ADAPTIVE_TASKS")
        print("=" * 80)
        print(f"Всего задач: {total}")
        print()
        
        # Статистика по классам
        print("По классам:")
        for class_level in sorted(set(task.class_level for task in AdaptiveTask.query.all())):
            count = AdaptiveTask.query.filter_by(class_level=class_level).count()
            print(f"  Класс {class_level}: {count} задач")
        print()
        
        # Статистика по уровням сложности
        print("По уровням сложности:")
        for difficulty in range(1, 8):
            count = AdaptiveTask.query.filter_by(difficulty_level=difficulty).count()
            print(f"  Уровень {difficulty}: {count} задач")
        print()
        
        # Статистика по темам
        print("По темам (топ-10):")
        topics = {}
        for task in AdaptiveTask.query.all():
            topics[task.topic] = topics.get(task.topic, 0) + 1
        
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {topic[:60]}: {count} задач")
        
        print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Импорт из указанного файла
        json_file = sys.argv[1]
        import_tasks_from_json(json_file)
    else:
        # Показать статистику
        print("Использование:")
        print("  python import_adaptive_tasks.py <json_file>  - импортировать задачи")
        print("  python import_adaptive_tasks.py              - показать статистику")
        print()
        show_stats()
