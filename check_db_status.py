# Проверка состояния базы данных

from models import db, AdaptiveTask, MockExam
from app import app

with app.app_context():
    # Проверяем адаптивные задачи
    adaptive_count = AdaptiveTask.query.count()
    print(f"✅ Адаптивных задач (AdaptiveTask): {adaptive_count}")
    
    # Проверяем пробники
    mock_count = MockExam.query.count()
    print(f"✅ Пробников (MockExam): {mock_count}")
    
    # Примеры адаптивных задач
    print("\n📝 Примеры адаптивных задач:")
    sample_tasks = AdaptiveTask.query.limit(3).all()
    for task in sample_tasks:
        print(f"  - Класс {task.class_level}, Уровень {task.difficulty_level}, Тема: {task.topic[:50]}")
