"""
Удаление старых задач 5 класса, сохранение новых олимпиадных
ВНИМАНИЕ: Не трогает задачи 6-11 классов!
"""

from models import db, AdaptiveTask
from app import app
from datetime import datetime

def cleanup_old_tasks():
    """Удаляет старые задачи 5 класса, оставляет только новые"""
    
    with app.app_context():
        print("="*70)
        print("ОЧИСТКА СТАРЫХ ЗАДАЧ 5 КЛАССА")
        print("="*70)
        
        # Статистика ДО удаления
        print("\nСтатистика ДО удаления:")
        for grade in range(5, 12):
            count = AdaptiveTask.query.filter_by(class_level=grade).count()
            print(f"  Класс {grade}: {count} задач")
        
        total_grade5 = AdaptiveTask.query.filter_by(class_level=5).count()
        print(f"\nВсего задач 5 класса: {total_grade5}")
        
        # Определяем новые задачи (импортированные сегодня)
        today = datetime(2026, 4, 22)
        new_tasks = AdaptiveTask.query.filter_by(class_level=5).filter(
            AdaptiveTask.created_at >= today
        ).all()
        
        print(f"Новых задач (с 22.04.2026): {len(new_tasks)}")
        print(f"Старых задач (до 22.04.2026): {total_grade5 - len(new_tasks)}")
        
        # Проверка: есть ли у новых задач LaTeX
        new_with_latex = sum(1 for t in new_tasks if '$' in (t.task_text or ''))
        print(f"Новых задач с LaTeX: {new_with_latex}/{len(new_tasks)} ({new_with_latex/len(new_tasks)*100:.1f}%)")
        
        # Проверка тем новых задач
        new_topics = set(t.topic for t in new_tasks)
        print(f"\nТемы новых задач ({len(new_topics)} уникальных):")
        for topic in sorted(new_topics):
            count = sum(1 for t in new_tasks if t.topic == topic)
            print(f"  - {topic}: {count} задач")
        
        # БЕЗОПАСНОЕ УДАЛЕНИЕ
        print("\n" + "="*70)
        confirm = input("Удалить старые задачи 5 класса? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Отменено пользователем.")
            return
        
        print("\nУдаление старых задач...")
        deleted = AdaptiveTask.query.filter_by(class_level=5).filter(
            AdaptiveTask.created_at < today
        ).delete()
        
        db.session.commit()
        print(f"Удалено: {deleted} старых задач")
        
        # Статистика ПОСЛЕ удаления
        print("\n" + "="*70)
        print("Статистика ПОСЛЕ удаления:")
        print("="*70)
        
        for grade in range(5, 12):
            count = AdaptiveTask.query.filter_by(class_level=grade).count()
            print(f"  Класс {grade}: {count} задач")
        
        remaining_grade5 = AdaptiveTask.query.filter_by(class_level=5).count()
        print(f"\nОсталось задач 5 класса: {remaining_grade5}")
        
        # Проверка тем после удаления
        all_grade5 = AdaptiveTask.query.filter_by(class_level=5).all()
        topics_after = set(t.topic for t in all_grade5)
        print(f"Уникальных тем: {len(topics_after)}")
        
        print("\n" + "="*70)
        print("[OK] ОЧИСТКА ЗАВЕРШЕНА!")
        print("="*70)


if __name__ == "__main__":
    cleanup_old_tasks()
