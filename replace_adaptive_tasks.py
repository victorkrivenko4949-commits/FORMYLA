# Замена старых задач адаптивного теста на новые из adaptive_full_db.json

import json
from models import db, AdaptiveTask
from app import app

def replace_adaptive_tasks():
    """Удаляет старые задачи и загружает новые из adaptive_full_db.json"""
    
    # Загружаем новые задачи
    print("Загрузка новых задач из data/adaptive_full_db.json...")
    with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
        new_tasks = json.load(f)
    
    print(f"Загружено {len(new_tasks)} новых задач")
    
    with app.app_context():
        # Удаляем все старые задачи
        print("Удаление старых задач из базы данных...")
        deleted_count = AdaptiveTask.query.delete()
        print(f"Удалено {deleted_count} старых задач")
        
        # Добавляем новые задачи
        print("Добавление новых задач в базу данных...")
        added_count = 0
        
        for task_data in new_tasks:
            task = AdaptiveTask(
                class_level=task_data['grade'],
                topic=task_data['topic'],
                difficulty_level=task_data['level'],
                task_text=task_data['question'],
                solution=task_data['explanation'],
                criteria_1_point=f"Частичное решение. Ответ: {task_data['answer']}",
                criteria_2_points=f"Полное решение. Ответ: {task_data['answer']}"
            )
            db.session.add(task)
            added_count += 1
            
            # Коммитим каждые 100 задач
            if added_count % 100 == 0:
                db.session.commit()
                print(f"Добавлено {added_count} задач...")
        
        # Финальный коммит
        db.session.commit()
        print(f"\n✅ Успешно добавлено {added_count} новых задач")
        
        # Проверка
        total_in_db = AdaptiveTask.query.count()
        print(f"✅ Всего задач в базе данных: {total_in_db}")

if __name__ == '__main__':
    replace_adaptive_tasks()
