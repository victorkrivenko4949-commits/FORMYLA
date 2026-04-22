"""
Скрипт очистки и аудита базы данных для 5 класса.
ШАГ 1: Удаление "битых" задач
ШАГ 2: Подсчет дефицита задач
"""

from app import app
from models import db, AdaptiveTask
from sqlalchemy import or_

def clean_broken_tasks():
    """ШАГ 1: Удаление задач с противоречиями и ошибками."""
    with app.app_context():
        print("\n" + "="*70)
        print("ШАГ 1: АГРЕССИВНОЕ УДАЛЕНИЕ БРАКА ИЗ БД")
        print("="*70)
        
        # Критерии удаления
        broken_patterns = [
            '%нет решений%',
            '%не имеет решения%',
            '%невозможно%',
            '%противоречие%',
            '%ошибка в условии%',
            '%не существует%',
            '%бесконечно много%'
        ]
        
        # Находим задачи с проблемами в solution или task_text
        broken_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 5
        ).filter(
            or_(
                *[AdaptiveTask.solution.ilike(pattern) for pattern in broken_patterns],
                *[AdaptiveTask.task_text.ilike(pattern) for pattern in broken_patterns]
            )
        ).all()
        
        print(f"\nНайдено задач с подозрительными фразами: {len(broken_tasks)}")
        
        # Удаляем задачи с пустым или слишком длинным ответом
        empty_answer_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 5,
            or_(
                AdaptiveTask.correct_answer == None,
                AdaptiveTask.correct_answer == '',
                db.func.length(AdaptiveTask.correct_answer) > 30
            )
        ).all()
        
        print(f"Найдено задач с пустым/длинным ответом: {len(empty_answer_tasks)}")
        
        # Объединяем списки (убираем дубликаты)
        all_broken = {task.id: task for task in (broken_tasks + empty_answer_tasks)}
        
        print(f"\nВсего уникальных задач для удаления: {len(all_broken)}")
        
        if all_broken:
            print("\nПримеры удаляемых задач:")
            for i, (task_id, task) in enumerate(list(all_broken.items())[:5], 1):
                print(f"\n{i}. ID={task_id}, Тема: {task.topic}, Уровень: {task.difficulty_level}")
                print(f"   Ответ: {task.correct_answer[:50] if task.correct_answer else 'ПУСТО'}")
                print(f"   Условие: {task.task_text[:100]}...")
            
            # Удаляем
            for task in all_broken.values():
                db.session.delete(task)
            
            db.session.commit()
            print(f"\n✅ Удалено {len(all_broken)} задач из БД")
        else:
            print("\n✅ Битых задач не найдено!")
        
        return len(all_broken)


def audit_missing_tasks():
    """ШАГ 2: Подсчет дефицита задач по темам и уровням."""
    with app.app_context():
        print("\n" + "="*70)
        print("ШАГ 2: АУДИТ ДЕФИЦИТА ЗАДАЧ")
        print("="*70)
        
        # Получаем все задачи 5 класса
        all_tasks = AdaptiveTask.query.filter_by(class_level=5).all()
        
        print(f"\nВсего задач в БД для 5 класса: {len(all_tasks)}")
        
        # Группируем по темам и уровням
        distribution = {}
        for task in all_tasks:
            key = (task.topic, task.difficulty_level)
            if key not in distribution:
                distribution[key] = 0
            distribution[key] += 1
        
        # Получаем уникальные темы
        topics = sorted(set(task.topic for task in all_tasks))
        
        print(f"\nНайдено уникальных тем: {len(topics)}")
        print("Темы:", topics[:10])  # Показываем первые 10
        
        # Эталон: 15 задач на каждую связку "Тема + Уровень"
        TARGET_PER_CELL = 15
        
        # Подсчитываем дефицит
        deficit_report = []
        total_deficit = 0
        
        print("\n" + "="*70)
        print("ТАБЛИЦА ДЕФИЦИТА (показаны только ячейки с нехваткой)")
        print("="*70)
        print(f"{'Тема':<40} | {'Уровень':<8} | {'Есть':<6} | {'Нужно':<6} | {'Дефицит':<8}")
        print("-"*70)
        
        for topic in topics:
            for level in range(1, 8):  # Уровни 1-7
                current_count = distribution.get((topic, level), 0)
                deficit = max(0, TARGET_PER_CELL - current_count)
                
                if deficit > 0:
                    deficit_report.append({
                        'topic': topic,
                        'level': level,
                        'current': current_count,
                        'target': TARGET_PER_CELL,
                        'deficit': deficit
                    })
                    total_deficit += deficit
                    
                    # Выводим только ячейки с дефицитом
                    topic_short = topic[:38] if len(topic) > 38 else topic
                    print(f"{topic_short:<40} | {level:<8} | {current_count:<6} | {TARGET_PER_CELL:<6} | {deficit:<8}")
        
        print("="*70)
        print(f"\nИТОГО:")
        print(f"  Всего задач в БД: {len(all_tasks)}")
        print(f"  Целевое количество: {len(topics) * 7 * TARGET_PER_CELL}")
        print(f"  ДЕФИЦИТ: {total_deficit} задач")
        print(f"  Ячеек с нехваткой: {len(deficit_report)}")
        
        # Сохраняем отчет в JSON для генератора
        import json
        with open('grade5_deficit_report.json', 'w', encoding='utf-8') as f:
            json.dump({
                'total_tasks': len(all_tasks),
                'total_deficit': total_deficit,
                'deficit_cells': deficit_report,
                'topics': topics
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Отчет сохранен в grade5_deficit_report.json")
        
        return deficit_report


if __name__ == "__main__":
    print("\n🔧 ЗАПУСК ОЧИСТКИ И АУДИТА БАЗЫ ДАННЫХ (5 КЛАСС)")
    
    # ШАГ 1: Удаление брака
    deleted_count = clean_broken_tasks()
    
    # ШАГ 2: Аудит дефицита
    deficit_report = audit_missing_tasks()
    
    print("\n" + "="*70)
    print("✅ ОЧИСТКА И АУДИТ ЗАВЕРШЕНЫ")
    print("="*70)
    print(f"Удалено битых задач: {deleted_count}")
    print(f"Обнаружено ячеек с дефицитом: {len(deficit_report)}")
    print("\nГотово к генерации недостающих задач!")
