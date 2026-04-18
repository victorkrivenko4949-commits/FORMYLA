"""
Валидация и замена мусорных задач в адаптивном тесте через DeepSeek AI
"""

import asyncio
import aiohttp
import json
import os
from app import app, db
from models import AdaptiveTask

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SEMAPHORE = asyncio.Semaphore(10)  # Ограничение для валидации

stats = {
    "total": 0,
    "validated": 0,
    "trash": 0,
    "replaced": 0,
    "failed": 0
}


async def call_deepseek_api(session: aiohttp.ClientSession, prompt: str) -> str:
    """Вызов DeepSeek API"""
    try:
        async with session.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000
            },
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                return None
    except Exception as e:
        print(f"  [ERROR] API call failed: {e}")
        return None


async def validate_task(session: aiohttp.ClientSession, task: AdaptiveTask) -> dict:
    """Валидация одной задачи через AI"""
    
    async with SEMAPHORE:
        stats["total"] += 1
        
        prompt = f"""Оцени эту задачу по математике. Она заявлена как задача для {task.class_level} класса, уровень сложности {task.difficulty_level}/7.

Задача: {task.task_text}

Ответь строго в формате JSON:
{{"real_class": число от 1 до 11, "real_difficulty": число от 1 до 7, "is_olympiad_worthy": true/false, "reason": "краткое пояснение"}}

Критерии оценки is_olympiad_worthy:
- true: задача нестандартная, требует смекалки, подходит для олимпиадного тренажёра
- false: задача тривиальная, из обычного учебника, решается за 5 секунд без раздумий

Критерии real_class:
- 5 класс: натуральные числа, дроби, проценты. НЕТ уравнений с x!
- 6 класс: отрицательные числа, простые уравнения, пропорции
- 7 класс: линейные уравнения, формулы сокращённого умножения
- 8 класс: квадратные уравнения, неравенства, корни
- 9 класс: системы уравнений, прогрессии, функции
- 10 класс: тригонометрия, логарифмы, производные
- 11 класс: интегралы, комплексные числа, параметры"""

        response = await call_deepseek_api(session, prompt)
        
        if not response:
            stats["failed"] += 1
            return None
        
        # Парсим JSON
        try:
            # Очистка от markdown
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            validation = json.loads(clean_response)
            stats["validated"] += 1
            
            # Проверяем, мусор ли это
            class_diff = abs(validation["real_class"] - task.class_level)
            is_trash = (
                class_diff > 2 or
                (not validation["is_olympiad_worthy"] and task.difficulty_level >= 3)
            )
            
            if is_trash:
                stats["trash"] += 1
                print(f"[TRASH] Task {task.id} (Class {task.class_level}, Level {task.difficulty_level})")
                print(f"  Real: Class {validation['real_class']}, Olympiad: {validation['is_olympiad_worthy']}")
                print(f"  Reason: {validation['reason']}")
                print(f"  Text: {task.task_text[:60]}...")
            
            return {
                "task_id": task.id,
                "is_trash": is_trash,
                "validation": validation
            }
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Task {task.id}: JSON parse error")
            stats["failed"] += 1
            return None


async def replace_trash_task(session: aiohttp.ClientSession, task: AdaptiveTask) -> bool:
    """Замена мусорной задачи на новую"""
    
    prompt = f"""Сгенерируй 1 ОЛИМПИАДНУЮ задачу по математике.
Класс: {task.class_level} (российская школа).
Уровень сложности: {task.difficulty_level}/7.
Тема: {task.topic}

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
- Задача должна быть НЕСТАНДАРТНОЙ, с подвохом или хитрым приёмом
- НЕ генерируй примитивные вычисления типа '20*5-0' или '2+3'
- Для 10-11 класса используй: тригонометрию, логарифмы, производные, параметры
- Для 5-6 класса: задачи на логику, делимость, принцип Дирихле, нестандартные задачи на дроби
- Все формулы в LaTeX: \\\\( ... \\\\)

Формат ответа - ТОЛЬКО JSON:
{{"task_text": "текст с LaTeX", "solution": "подробное решение", "criteria_1_point": "критерий на 1 балл", "criteria_2_points": "критерий на 2 балла"}}"""

    response = await call_deepseek_api(session, prompt)
    
    if not response:
        return False
    
    try:
        # Очистка от markdown
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        new_data = json.loads(clean_response)
        
        # Обновляем задачу в базе
        with app.app_context():
            task_to_update = AdaptiveTask.query.get(task.id)
            if task_to_update:
                task_to_update.task_text = new_data["task_text"]
                task_to_update.solution = new_data["solution"]
                task_to_update.criteria_1_point = new_data.get("criteria_1_point", "")
                task_to_update.criteria_2_points = new_data.get("criteria_2_points", "")
                db.session.commit()
                
                stats["replaced"] += 1
                print(f"[REPLACED] Task {task.id}: {new_data['task_text'][:60]}...")
                return True
        
        return False
        
    except Exception as e:
        print(f"[ERROR] Failed to replace task {task.id}: {e}")
        return False


async def main():
    """Главная функция"""
    
    print("\n" + "="*80)
    print("ВАЛИДАЦИЯ И ЗАМЕНА МУСОРНЫХ ЗАДАЧ")
    print("="*80 + "\n")
    
    # Загружаем все задачи из базы
    with app.app_context():
        all_tasks = AdaptiveTask.query.all()
        print(f"Загружено {len(all_tasks)} задач из базы данных\n")
    
    # ШАГ 1: ВАЛИДАЦИЯ
    print("="*80)
    print("ШАГ 1: ВАЛИДАЦИЯ ЗАДАЧ")
    print("="*80 + "\n")
    
    async with aiohttp.ClientSession() as session:
        # Валидируем все задачи
        validation_tasks = [validate_task(session, task) for task in all_tasks]
        validation_results = await asyncio.gather(*validation_tasks)
        
        # Фильтруем мусорные задачи
        trash_tasks = []
        for result in validation_results:
            if result and result["is_trash"]:
                task = next(t for t in all_tasks if t.id == result["task_id"])
                trash_tasks.append(task)
        
        print(f"\n{'='*80}")
        print(f"РЕЗУЛЬТАТЫ ВАЛИДАЦИИ")
        print(f"{'='*80}")
        print(f"Всего задач: {stats['total']}")
        print(f"Провалидировано: {stats['validated']}")
        print(f"Мусорных задач: {stats['trash']}")
        print(f"Ошибок валидации: {stats['failed']}")
        print(f"{'='*80}\n")
        
        if not trash_tasks:
            print("✅ Мусорных задач не найдено! Все задачи качественные.")
            return
        
        # ШАГ 2: ЗАМЕНА
        print("="*80)
        print(f"ШАГ 2: ЗАМЕНА {len(trash_tasks)} МУСОРНЫХ ЗАДАЧ")
        print("="*80 + "\n")
        
        # Заменяем мусорные задачи
        replacement_tasks = [replace_trash_task(session, task) for task in trash_tasks]
        await asyncio.gather(*replacement_tasks)
        
        print(f"\n{'='*80}")
        print(f"ИТОГОВАЯ СТАТИСТИКА")
        print(f"{'='*80}")
        print(f"Мусорных задач найдено: {stats['trash']}")
        print(f"Успешно заменено: {stats['replaced']}")
        print(f"Не удалось заменить: {stats['trash'] - stats['replaced']}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
