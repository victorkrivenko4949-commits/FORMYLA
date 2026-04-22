"""
ПОЛНАЯ ЗАЧИСТКА БАЗЫ ДАННЫХ
Удаляет ВСЕ задачи кроме новых олимпиадных для 5 класса
"""

from models import db, AdaptiveTask
from app import app
from datetime import datetime

def clean_all_old_tasks():
    """Удаляет все старые задачи, оставляет только новые для 5 класса"""
    
    with app.app_context():
        print("="*70)
        print("ПОЛНАЯ ЗАЧИСТКА БАЗЫ ДАННЫХ")
        print("="*70)
        
        # Статистика ДО
        print("\nСтатистика ДО очистки:")
        total_before = AdaptiveTask.query.count()
        print(f"Всего задач в БД: {total_before}")
        
        for grade in range(5, 12):
            count = AdaptiveTask.query.filter_by(class_level=grade).count()
            print(f"  Класс {grade}: {count} задач")
        
        # Находим наши новые задачи 5 класса
        today = datetime(2026, 4, 22)
        perfect_tasks = AdaptiveTask.query.filter_by(class_level=5).filter(
            AdaptiveTask.created_at >= today
        ).all()
        
        perfect_ids = [t.id for t in perfect_tasks]
        
        print(f"\nНаших новых задач 5 класса: {len(perfect_ids)}")
        print(f"Будет удалено: {total_before - len(perfect_ids)} задач")
        
        # КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ
        print("\n" + "!"*70)
        print("ВНИМАНИЕ! Это удалит ВСЕ задачи 6-11 классов!")
        print("Останутся только новые олимпиадные задачи для 5 класса.")
        print("!"*70)
        
        confirm = input("\nПродолжить? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Отменено пользователем.")
            return
        
        # УДАЛЕНИЕ
        print("\nУдаление старых задач...")
        deleted = AdaptiveTask.query.filter(
            ~AdaptiveTask.id.in_(perfect_ids)
        ).delete(synchronize_session='fetch')
        
        db.session.commit()
        
        # Статистика ПОСЛЕ
        print("\n" + "="*70)
        print("ОЧИСТКА ЗАВЕРШЕНА!")
        print("="*70)
        
        total_after = AdaptiveTask.query.count()
        print(f"\nУдалено задач: {deleted}")
        print(f"Осталось в БД: {total_after}")
        
        print("\nСтатистика ПОСЛЕ очистки:")
        for grade in range(5, 12):
            count = AdaptiveTask.query.filter_by(class_level=grade).count()
            status = "[OK]" if (grade == 5 and count == 1007) or (grade != 5 and count == 0) else "[WARN]"
            print(f"  Класс {grade}: {count} задач {status}")
        
        # Проверка тем
        grade5_tasks = AdaptiveTask.query.filter_by(class_level=5).all()
        topics = set(t.topic for t in grade5_tasks)
        print(f"\nТем в 5 классе: {len(topics)}")
        
        print("\n" + "="*70)
        print("[SUCCESS] База очищена! Готова к генерации задач для 6-11 классов.")
        print("="*70)


if __name__ == "__main__":
    clean_all_old_tasks()
