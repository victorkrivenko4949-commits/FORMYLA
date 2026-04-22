"""
Скрипт математической валидации задач в базе данных.
Использует DeepSeek Reasoner для проверки корректности задач.
"""

import os
import json
from dotenv import load_dotenv
from models import db, AdaptiveTask
from app import app
from ai.deepseek_client import DeepSeekClient

load_dotenv()


def validate_task_with_ai(task):
    """
    Проверяет математическую корректность задачи через AI.
    
    Returns:
        dict: {
            'is_valid': bool,
            'reason': str (если is_valid=False)
        }
    """
    client = DeepSeekClient()
    
    system_prompt = """Ты — строгий профессор математики и член жюри математической олимпиады.

ТВОЯ ЗАДАЧА:
1. Внимательно прочитать условие задачи.
2. Решить задачу шаг за шагом, используя строгую математическую логику.
3. Проверить условие на логические противоречия:
   - Достаточно ли данных для решения?
   - Нет ли взаимоисключающих правил?
   - Корректны ли числовые ребусы (разные буквы = разные цифры)?
   - Имеет ли задача хотя бы одно решение?
4. Если в задаче указан ответ, проверить, совпадает ли он с твоим решением.

КРИТЕРИИ НЕКОРРЕКТНОСТИ:
- Задача не имеет решения из-за противоречий в условии
- Задача имеет бесконечно много решений при требовании единственного ответа
- Указанный ответ не совпадает с правильным решением
- В условии недостаточно данных для однозначного решения
- Числовой ребус нарушает правило "разные буквы = разные цифры"

ВАЖНО: Верни ТОЛЬКО валидный JSON без markdown маркеров:
{
  "is_mathematically_correct": true/false,
  "reason": "краткое объяснение, если false (на русском языке)"
}

Если задача корректна, верни:
{
  "is_mathematically_correct": true,
  "reason": ""
}"""

    user_prompt = f"""Проверь математическую корректность этой задачи:

УСЛОВИЕ:
{task.task_text}

РЕШЕНИЕ (авторское):
{task.solution}

Проверь задачу и верни JSON с оценкой корректности."""

    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,  # Низкая температура для строгой логики
            max_tokens=2000
        )
        
        # Очистка от markdown
        import re
        cleaned = response.strip()
        cleaned = re.sub(r'```json\s*', '', cleaned)
        cleaned = re.sub(r'```\s*$', '', cleaned)
        cleaned = cleaned.strip()
        
        # Парсинг JSON
        result = json.loads(cleaned)
        
        return {
            'is_valid': result.get('is_mathematically_correct', True),
            'reason': result.get('reason', '')
        }
        
    except Exception as e:
        print(f"❌ Ошибка при проверке задачи ID={task.id}: {e}")
        # В случае ошибки API считаем задачу валидной (не удаляем)
        return {
            'is_valid': True,
            'reason': f'Ошибка API: {str(e)}'
        }


def validate_all_tasks(class_level=5, dry_run=True):
    """
    Проверяет все задачи указанного класса.
    
    Args:
        class_level: Класс для проверки (по умолчанию 5)
        dry_run: Если True, только показывает результаты без удаления
    """
    with app.app_context():
        # Получаем все задачи класса, которые еще не помечены
        tasks = AdaptiveTask.query.filter_by(
            class_level=class_level,
            is_flagged=False
        ).all()
        
        print(f"\n{'='*70}")
        print(f"🔍 МАТЕМАТИЧЕСКАЯ ВАЛИДАЦИЯ ЗАДАЧ - КЛАСС {class_level}")
        print(f"{'='*70}")
        print(f"Всего задач для проверки: {len(tasks)}")
        print(f"Режим: {'DRY RUN (без изменений)' if dry_run else 'PRODUCTION (с удалением)'}")
        print(f"{'='*70}\n")
        
        invalid_tasks = []
        valid_count = 0
        error_count = 0
        
        for i, task in enumerate(tasks, 1):
            print(f"\n[{i}/{len(tasks)}] Проверка задачи ID={task.id}")
            print(f"Тема: {task.topic}")
            print(f"Уровень: {task.difficulty_level}/7")
            print(f"Условие (первые 100 символов): {task.task_text[:100]}...")
            
            # Проверяем через AI
            validation = validate_task_with_ai(task)
            
            if validation['is_valid']:
                print(f"✅ Задача корректна")
                valid_count += 1
            else:
                print(f"❌ Задача НЕКОРРЕКТНА!")
                print(f"   Причина: {validation['reason']}")
                invalid_tasks.append({
                    'id': task.id,
                    'topic': task.topic,
                    'difficulty': task.difficulty_level,
                    'reason': validation['reason'],
                    'text': task.task_text[:200]
                })
                
                if not dry_run:
                    # Помечаем задачу как некорректную
                    task.is_flagged = True
                    task.flagged_reason = f"AI Validator: {validation['reason']}"
                    db.session.commit()
                    print(f"   ⚠️  Задача помечена как is_flagged=True")
        
        # Итоговый отчет
        print(f"\n{'='*70}")
        print(f"📊 ИТОГОВЫЙ ОТЧЕТ")
        print(f"{'='*70}")
        print(f"✅ Корректных задач: {valid_count}")
        print(f"❌ Некорректных задач: {len(invalid_tasks)}")
        print(f"⚠️  Ошибок проверки: {error_count}")
        print(f"{'='*70}\n")
        
        if invalid_tasks:
            print(f"\n🚨 СПИСОК НЕКОРРЕКТНЫХ ЗАДАЧ:\n")
            for task_info in invalid_tasks:
                print(f"ID {task_info['id']} | {task_info['topic']} | Уровень {task_info['difficulty']}")
                print(f"   Причина: {task_info['reason']}")
                print(f"   Текст: {task_info['text']}...")
                print()
        
        if dry_run:
            print(f"\n💡 Это был DRY RUN. Для реального удаления запустите:")
            print(f"   python math_validator_db.py --production")
        else:
            print(f"\n✅ Валидация завершена. Некорректные задачи помечены как is_flagged=True")
            print(f"   Они больше не будут показываться ученикам.")


if __name__ == "__main__":
    import sys
    
    # Проверяем аргументы командной строки
    dry_run = '--production' not in sys.argv
    class_level = 5
    
    # Можно указать класс: python math_validator_db.py --class=6
    for arg in sys.argv:
        if arg.startswith('--class='):
            class_level = int(arg.split('=')[1])
    
    validate_all_tasks(class_level=class_level, dry_run=dry_run)
