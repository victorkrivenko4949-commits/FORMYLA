"""
Точечное удаление только задач с реальными проблемами в тексте.
"""

from app import app
from models import db, AdaptiveTask
from sqlalchemy import or_

def clean_only_broken_tasks():
    """Удаление только задач с явными проблемами в тексте."""
    with app.app_context():
        print("\n" + "="*70)
        print("ТОЧЕЧНОЕ УДАЛЕНИЕ ЗАДАЧ С ПРОБЛЕМАМИ")
        print("="*70)
        
        # Критерии удаления - только явные проблемы
        broken_patterns = [
            '%нет решений%',
            '%не имеет решения%',
            '%невозможно решить%',
            '%противоречие в условии%',
            '%ошибка в условии%',
            '%не существует решения%',
            '%бесконечно много решений%'
        ]
        
        # Находим задачи с проблемами в solution или correct_answer
        broken_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 5
        ).filter(
            or_(
                *[AdaptiveTask.solution.ilike(pattern) for pattern in broken_patterns],
                *[AdaptiveTask.correct_answer.ilike(pattern) for pattern in broken_patterns]
            )
        ).all()
        
        print(f"\nНайдено задач с проблемными фразами: {len(broken_tasks)}")
        
        if broken_tasks:
            print("\nПримеры удаляемых задач:")
            for i, task in enumerate(broken_tasks[:10], 1):
                print(f"\n{i}. ID={task.id}, Тема: {task.topic}, Уровень: {task.difficulty_level}")
                print(f"   Ответ: {task.correct_answer[:80] if task.correct_answer else 'ПУСТО'}")
                print(f"   Условие: {task.task_text[:100]}...")
                if any(pattern.strip('%').lower() in task.solution.lower() for pattern in broken_patterns):
                    print(f"   Решение содержит проблемную фразу!")
            
            # Удаляем
            for task in broken_tasks:
                db.session.delete(task)
            
            db.session.commit()
            print(f"\n✅ Удалено {len(broken_tasks)} проблемных задач из БД")
        else:
            print("\n✅ Проблемных задач не найдено!")
        
        # Проверяем результат
        remaining = AdaptiveTask.query.filter_by(class_level=5).count()
        print(f"\nОсталось задач 5 класса в БД: {remaining}")
        
        # Проверяем, что у всех задач есть ответы
        tasks_without_answer = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 5,
            or_(
                AdaptiveTask.correct_answer == None,
                AdaptiveTask.correct_answer == ''
            )
        ).count()
        
        print(f"Задач без ответа: {tasks_without_answer}")
        
        # Показываем пример задачи с ответом
        sample_task = AdaptiveTask.query.filter_by(class_level=5).first()
        if sample_task:
            print(f"\n✅ ПРОВЕРКА: Задача ID={sample_task.id}")
            print(f"   Тема: {sample_task.topic}")
            print(f"   Уровень: {sample_task.difficulty_level}")
            print(f"   Ответ: {sample_task.correct_answer}")
            print(f"   Условие: {sample_task.task_text[:150]}...")
        
        return len(broken_tasks), remaining


if __name__ == "__main__":
    print("\n🔧 ЗАПУСК ТОЧЕЧНОЙ ОЧИСТКИ БАЗЫ ДАННЫХ (5 КЛАСС)")
    
    deleted, remaining = clean_only_broken_tasks()
    
    print("\n" + "="*70)
    print("✅ ОЧИСТКА ЗАВЕРШЕНА")
    print("="*70)
    print(f"Удалено проблемных задач: {deleted}")
    print(f"Осталось качественных задач: {remaining}")
    print("\nБаза данных готова к использованию!")
