"""
Импорт олимпиадных задач 5 класса в базу данных FORMYLA
"""

import json
import hashlib
from models import db, AdaptiveTask
from app import app

INPUT_FILE = "grade5_olympiad_PERFECT.jsonl"


def get_task_hash(question: str) -> str:
    """Создает хеш задачи для проверки дубликатов"""
    return hashlib.md5(question.encode('utf-8')).hexdigest()


def import_tasks():
    """Импортирует задачи в базу данных"""
    print("="*70)
    print("ИМПОРТ ОЛИМПИАДНЫХ ЗАДАЧ 5 КЛАССА В БД")
    print("="*70)
    
    # Читаем задачи из файла
    tasks_data = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            tasks_data.append(json.loads(line))
    
    print(f"Загружено из файла: {len(tasks_data)} задач\n")
    
    with app.app_context():
        # Получаем существующие хеши задач
        existing_tasks = AdaptiveTask.query.filter_by(class_level=5).all()
        existing_hashes = {get_task_hash(t.task_text) for t in existing_tasks}
        
        print(f"Существующих задач 5 класса в БД: {len(existing_tasks)}")
        
        imported = 0
        skipped = 0
        errors = 0
        
        for idx, task_data in enumerate(tasks_data, 1):
            try:
                # Проверка на дубликат
                task_hash = get_task_hash(task_data['question'])
                if task_hash in existing_hashes:
                    skipped += 1
                    continue
                
                # Маппинг полей JSON -> БД
                new_task = AdaptiveTask(
                    class_level=task_data['grade'],  # 5
                    difficulty_level=task_data['level'],  # 1-7
                    topic=task_data['topic'],
                    task_text=task_data['question'],
                    solution=task_data['explanation'],
                    correct_answer=str(task_data['answer']),  # КРИТИЧНО: Заполняем ответ!
                    # criteria_1_point и criteria_2_points оставляем пустыми
                    # они используются для оценивания, но у нас есть answer
                    criteria_1_point=f"Краткий ответ: {task_data['answer']}",
                    criteria_2_points=task_data['explanation'][:500]  # Первые 500 символов решения
                )
                
                db.session.add(new_task)
                existing_hashes.add(task_hash)
                imported += 1
                
                # Коммитим каждые 50 задач
                if imported % 50 == 0:
                    db.session.commit()
                    print(f"[PROGRESS] Импортировано: {imported}/{len(tasks_data)}")
                
            except Exception as e:
                errors += 1
                print(f"[ERROR] Ошибка при импорте задачи {idx}: {str(e)[:100]}")
                db.session.rollback()
        
        # Финальный коммит
        try:
            db.session.commit()
        except Exception as e:
            print(f"[ERROR] Ошибка финального коммита: {e}")
            db.session.rollback()
        
        print("\n" + "="*70)
        print("ИМПОРТ ЗАВЕРШЕН!")
        print("="*70)
        print(f"Импортировано новых задач: {imported}")
        print(f"Пропущено (дубликаты): {skipped}")
        print(f"Ошибок: {errors}")
        print(f"Всего задач 5 класса в БД: {AdaptiveTask.query.filter_by(class_level=5).count()}")
        print("="*70)


if __name__ == "__main__":
    import_tasks()
