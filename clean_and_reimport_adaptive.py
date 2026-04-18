"""
Полная очистка таблицы AdaptiveTask и переимпорт всех задач для классов 5-11
"""

from app import app, db
from models import AdaptiveTask
import json

# Список файлов для импорта
FILES_TO_IMPORT = [
    "adaptive_175_grade5_FINAL.json",
    "adaptive_175_grade6_FINAL.json", 
    "adaptive_175_grade7_FINAL.json",
    "adaptive_175_tasks_grade8_COMPLETE.json",
    "adaptive_175_tasks_grade9_COMPLETE.json",
    "adaptive_175_tasks_grade10_COMPLETE.json",
    "adaptive_175_tasks_grade11_COMPLETE.json"
]

with app.app_context():
    print("\n" + "="*80)
    print("ШАГ 1: ПОЛНАЯ ОЧИСТКА ТАБЛИЦЫ AdaptiveTask")
    print("="*80)
    
    # Удаляем ВСЕ задачи из таблицы
    deleted_count = AdaptiveTask.query.delete()
    db.session.commit()
    
    print(f"Удалено {deleted_count} старых задач из базы данных")
    
    print("\n" + "="*80)
    print("ШАГ 2: ИМПОРТ СВЕЖИХ ЗАДАЧ")
    print("="*80)
    
    total_imported = 0
    total_skipped = 0
    
    for filename in FILES_TO_IMPORT:
        print(f"\nИмпорт из {filename}...")
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
        except FileNotFoundError:
            print(f"  ОШИБКА: Файл {filename} не найден!")
            continue
        
        imported = 0
        skipped = 0
        
        for task in tasks:
            # Проверяем обязательные поля
            required_fields = ['topic', 'class_level', 'difficulty_level', 'task_text', 'solution']
            if not all(field in task for field in required_fields):
                skipped += 1
                continue
            
            # Проверяем, нет ли уже такой задачи (по тексту задачи)
            existing = AdaptiveTask.query.filter_by(
                task_text=task['task_text']
            ).first()
            
            if existing:
                skipped += 1
                continue
            
            # Создаем новую задачу
            new_task = AdaptiveTask(
                topic=task['topic'],
                class_level=task['class_level'],
                difficulty_level=task['difficulty_level'],
                task_text=task['task_text'],
                solution=task['solution'],
                criteria_1_point=task.get('criteria_1_point', ''),
                criteria_2_points=task.get('criteria_2_points', '')
            )
            
            db.session.add(new_task)
            imported += 1
            
            # Коммитим каждые 50 задач
            if imported % 50 == 0:
                db.session.commit()
        
        # Финальный коммит для файла
        db.session.commit()
        
        print(f"  Импортировано: {imported}")
        print(f"  Пропущено (дубликаты): {skipped}")
        
        total_imported += imported
        total_skipped += skipped
    
    print("\n" + "="*80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    print(f"Всего импортировано: {total_imported} задач")
    print(f"Пропущено (дубликаты): {total_skipped} задач")
    
    # Проверяем финальное состояние базы
    print("\nСостояние базы данных:")
    for grade in [5, 6, 7, 8, 9, 10, 11]:
        count = AdaptiveTask.query.filter_by(class_level=grade).count()
        print(f"  Класс {grade}: {count} задач")
    
    total = AdaptiveTask.query.count()
    print(f"\nВСЕГО В БАЗЕ: {total} задач")
    print("="*80 + "\n")
