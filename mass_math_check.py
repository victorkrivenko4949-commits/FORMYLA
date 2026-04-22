"""
Массовая асинхронная проверка математической корректности задач через AI.
Использует DeepSeek API для проверки всех задач 5 класса.
"""

import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from app import app
from models import db, AdaptiveTask

load_dotenv()

# Настройки
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
MAX_CONCURRENT_REQUESTS = 10  # Максимум параллельных запросов
BATCH_SIZE = 50  # Сохранять результаты каждые 50 задач


async def check_task_validity(session, task_data):
    """
    Проверяет математическую корректность одной задачи через DeepSeek API.
    
    Args:
        session: aiohttp ClientSession
        task_data: dict с полями id, question, answer, topic, level
    
    Returns:
        dict: {id, is_valid, reason, task_data}
    """
    import aiohttp
    
    system_prompt = """Ты — строгий математический рецензент олимпиадных задач.

Проверь эту задачу для 5 класса на корректность.

АЛГОРИТМ ПРОВЕРКИ:
1. Внимательно прочитай условие. Есть ли логические противоречия?
   - Невыполнимые условия в числовых ребусах (разные буквы = одинаковые цифры)
   - Нехватка данных для однозначного решения
   - Противоречивые условия (например, "A > B > C, но A < C")
   
2. Реши задачу сам, шаг за шагом.

3. Сравни свой ответ с предложенным.

ВАЖНО: Верни ТОЛЬКО валидный JSON без markdown:
{
  "is_valid": true/false,
  "reason": "если false, кратко объясни почему (на русском)"
}

Если задача корректна и ответ правильный, верни:
{
  "is_valid": true,
  "reason": ""
}"""

    user_prompt = f"""ЗАДАЧА:
{task_data['question']}

ПРЕДЛАГАЕМЫЙ ОТВЕТ:
{task_data['answer']}

Проверь корректность задачи и верни JSON."""

    try:
        async with session.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.2,
                'max_tokens': 1000
            },
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"[ERROR] API error for task {task_data['id']}: {response.status} - {error_text[:200]}")
                return {
                    'id': task_data['id'],
                    'is_valid': True,  # В случае ошибки API не удаляем задачу
                    'reason': f'API Error: {response.status}',
                    'task_data': task_data
                }
            
            result = await response.json()
            ai_response = result['choices'][0]['message']['content']
            
            # Очистка от markdown
            import re
            cleaned = ai_response.strip()
            cleaned = re.sub(r'```json\s*', '', cleaned)
            cleaned = re.sub(r'```\s*$', '', cleaned)
            cleaned = cleaned.strip()
            
            # Парсинг JSON
            validation = json.loads(cleaned)
            
            return {
                'id': task_data['id'],
                'is_valid': validation.get('is_valid', True),
                'reason': validation.get('reason', ''),
                'task_data': task_data
            }
            
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] Task {task_data['id']} timed out")
        return {
            'id': task_data['id'],
            'is_valid': True,  # Не удаляем при таймауте
            'reason': 'Timeout',
            'task_data': task_data
        }
    except Exception as e:
        print(f"[ERROR] Task {task_data['id']}: {str(e)[:100]}")
        return {
            'id': task_data['id'],
            'is_valid': True,  # Не удаляем при ошибке
            'reason': f'Error: {str(e)[:100]}',
            'task_data': task_data
        }


async def check_all_tasks():
    """Асинхронная проверка всех задач."""
    import aiohttp
    
    print("\n" + "="*70)
    print("МАССОВАЯ ПРОВЕРКА МАТЕМАТИЧЕСКОЙ КОРРЕКТНОСТИ ЗАДАЧ")
    print("="*70)
    print(f"Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Получаем все задачи из БД
    with app.app_context():
        tasks = AdaptiveTask.query.filter_by(class_level=5).all()
        
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                'id': task.id,
                'question': task.task_text,
                'answer': task.correct_answer,
                'topic': task.topic,
                'level': task.difficulty_level
            })
    
    print(f"\nВсего задач для проверки: {len(tasks_data)}")
    print(f"Максимум параллельных запросов: {MAX_CONCURRENT_REQUESTS}")
    print(f"Примерное время: {len(tasks_data) / MAX_CONCURRENT_REQUESTS / 60:.1f} минут\n")
    
    # Создаем семафор для ограничения параллельности
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def check_with_semaphore(session, task_data):
        async with semaphore:
            return await check_task_validity(session, task_data)
    
    # Запускаем проверку
    invalid_tasks = []
    valid_count = 0
    error_count = 0
    
    async with aiohttp.ClientSession() as session:
        # Создаем задачи для всех проверок
        check_tasks = [
            check_with_semaphore(session, task_data)
            for task_data in tasks_data
        ]
        
        # Выполняем с прогресс-баром
        for i, coro in enumerate(asyncio.as_completed(check_tasks), 1):
            result = await coro
            
            if result['is_valid']:
                valid_count += 1
            else:
                invalid_tasks.append(result)
                print(f"\n[INVALID] ID={result['id']}, Тема: {result['task_data']['topic']}")
                print(f"  Причина: {result['reason']}")
                print(f"  Ответ: {result['task_data']['answer']}")
            
            # Прогресс
            if i % 10 == 0:
                print(f"[PROGRESS] Проверено: {i}/{len(tasks_data)} ({i/len(tasks_data)*100:.1f}%)")
    
    # Сохраняем результаты
    print("\n" + "="*70)
    print("РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    print("="*70)
    print(f"Всего проверено: {len(tasks_data)}")
    print(f"Корректных задач: {valid_count}")
    print(f"Некорректных задач: {len(invalid_tasks)}")
    print(f"Ошибок проверки: {error_count}")
    
    # Сохраняем некорректные задачи в файл
    if invalid_tasks:
        with open('bad_tasks_report.json', 'w', encoding='utf-8') as f:
            json.dump(invalid_tasks, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Отчет сохранен в bad_tasks_report.json")
        
        # Удаляем некорректные задачи из БД
        print(f"\nУдаление {len(invalid_tasks)} некорректных задач из БД...")
        with app.app_context():
            for invalid in invalid_tasks:
                task = AdaptiveTask.query.get(invalid['id'])
                if task:
                    db.session.delete(task)
            db.session.commit()
        print("✅ Некорректные задачи удалены из БД")
        
        # Показываем примеры
        print("\nПримеры некорректных задач:")
        for i, invalid in enumerate(invalid_tasks[:5], 1):
            print(f"\n{i}. ID={invalid['id']}")
            print(f"   Тема: {invalid['task_data']['topic']}")
            print(f"   Причина: {invalid['reason']}")
            print(f"   Условие: {invalid['task_data']['question'][:100]}...")
    
    print(f"\nЗавершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)


if __name__ == "__main__":
    print("\n🚀 ЗАПУСК МАССОВОЙ ПРОВЕРКИ ЗАДАЧ")
    print("Это может занять 10-30 минут в зависимости от количества задач...")
    
    asyncio.run(check_all_tasks())
    
    print("\n✅ Проверка завершена! База данных очищена от некорректных задач.")
