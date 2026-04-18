"""
Догенерация недостающих задач для 8-11 классов
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Optional

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SEMAPHORE = asyncio.Semaphore(30)

stats = {
    8: {"success": 0, "failed": 0, "total": 0},
    9: {"success": 0, "failed": 0, "total": 0},
    10: {"success": 0, "failed": 0, "total": 0},
    11: {"success": 0, "failed": 0, "total": 0}
}


async def call_deepseek_api(session: aiohttp.ClientSession, prompt: str, max_retries: int = 3) -> Optional[str]:
    """Вызов DeepSeek API с retry логикой"""
    
    for attempt in range(max_retries):
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
                    "temperature": 0.7,
                    "max_tokens": 2000
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif response.status in [429, 500, 502, 503]:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    return None
                    
        except asyncio.TimeoutError:
            await asyncio.sleep(2 ** attempt)
        except Exception:
            await asyncio.sleep(2 ** attempt)
    
    return None


async def generate_task(
    session: aiohttp.ClientSession,
    grade: int,
    topic: str,
    difficulty: int,
    anchor_task: dict,
    task_number: int
) -> Optional[dict]:
    """Генерация одной задачи с двухэтапной валидацией"""
    
    async with SEMAPHORE:
        stats[grade]["total"] += 1
        
        anchor_json = json.dumps(anchor_task, ensure_ascii=False, indent=2)
        
        # GENERATOR
        generator_prompt = f"""Ты — составитель олимпиадных задач по математике. Сгенерируй задачу для {grade} класса по теме "{topic}", уровень сложности {difficulty} из 7.

Вот эталонная задача уровня 3 для этой же темы:

{anchor_json}

ТРЕБОВАНИЯ:
1. Уровень {difficulty} должен пропорционально отличаться от эталонного уровня 3
2. Задача должна быть математически корректной
3. Весь LaTeX экранируй ДВОЙНЫМИ обратными слешами: \\\\( ... \\\\) и \\\\[ ... \\\\]
4. Реши задачу в уме перед генерацией JSON

Верни ТОЛЬКО валидный JSON (без маркдауна) с полями: question_number, topic, class_level, difficulty_level, task_text, solution, criteria_1_point, criteria_2_points."""

        generator_response = await call_deepseek_api(session, generator_prompt)
        
        if not generator_response:
            stats[grade]["failed"] += 1
            return None
        
        generated_json = generator_response.strip()
        if generated_json.startswith("```json"):
            generated_json = generated_json[7:]
        if generated_json.startswith("```"):
            generated_json = generated_json[3:]
        if generated_json.endswith("```"):
            generated_json = generated_json[:-3]
        generated_json = generated_json.strip()
        
        # CRITIC
        critic_prompt = f"""Ты — эксперт-методист. Проверь эту задачу для {grade} класса:

{generated_json}

ПРОВЕРЬ:
1. Математическая корректность
2. Соответствие уровню {difficulty}
3. Двойное экранирование LaTeX (\\\\( и \\\\))
4. Полнота решения

Исправь ошибки и верни ТОЛЬКО исправленный JSON без маркдауна."""

        critic_response = await call_deepseek_api(session, critic_prompt)
        
        if not critic_response:
            stats[grade]["failed"] += 1
            return None
        
        final_json = critic_response.strip()
        if final_json.startswith("```json"):
            final_json = final_json[7:]
        if final_json.startswith("```"):
            final_json = final_json[3:]
        if final_json.endswith("```"):
            final_json = final_json[:-3]
        final_json = final_json.strip()
        
        try:
            task = json.loads(final_json)
            
            required_fields = ["question_number", "topic", "class_level", "difficulty_level", 
                             "task_text", "solution", "criteria_1_point", "criteria_2_points"]
            
            if all(field in task for field in required_fields):
                task["question_number"] = task_number
                stats[grade]["success"] += 1
                print(f"[Класс {grade} | {topic} | Уровень {difficulty}] SUCCESS")
                return task
            else:
                stats[grade]["failed"] += 1
                return None
                
        except json.JSONDecodeError:
            stats[grade]["failed"] += 1
            return None


async def generate_missing_for_grade(session: aiohttp.ClientSession, grade: int) -> list:
    """Догенерация недостающих задач для одного класса"""
    
    print(f"\n{'='*80}")
    print(f"ДОГЕНЕРАЦИЯ ДЛЯ {grade} КЛАССА")
    print(f"{'='*80}\n")
    
    # Загружаем список недостающих
    missing_file = f"missing_tasks_grade{grade}.json"
    try:
        with open(missing_file, 'r', encoding='utf-8') as f:
            missing_data = json.load(f)
    except FileNotFoundError:
        print(f"Файл {missing_file} не найден!")
        return []
    
    print(f"Недостающих задач: {len(missing_data)}")
    
    # Загружаем уже сгенерированные задачи для определения номеров
    generated_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}_COMPLETE.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}.json"
    
    try:
        with open(generated_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        start_number = len(existing) + 1
    except FileNotFoundError:
        start_number = 1
    
    # Генерируем недостающие задачи
    coroutines = []
    for i, item in enumerate(missing_data):
        task_number = start_number + i
        coroutines.append(
            generate_task(
                session,
                item["grade"],
                item["topic"],
                item["level"],
                item["anchor"],
                task_number
            )
        )
    
    results = await asyncio.gather(*coroutines)
    generated_tasks = [task for task in results if task is not None]
    
    print(f"\n{'='*80}")
    print(f"ЗАВЕРШЕНО ДЛЯ {grade} КЛАССА")
    print(f"Успешно: {stats[grade]['success']}/{stats[grade]['total']}")
    print(f"Провалено: {stats[grade]['failed']}/{stats[grade]['total']}")
    print(f"{'='*80}\n")
    
    return generated_tasks


async def main():
    """Главная функция"""
    
    start_time = datetime.now()
    print(f"\n{'#'*80}")
    print(f"# ДОГЕНЕРАЦИЯ НЕДОСТАЮЩИХ ЗАДАЧ ДЛЯ 8-11 КЛАССОВ")
    print(f"# Начало: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}\n")
    
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            generate_missing_for_grade(session, 8),
            generate_missing_for_grade(session, 9),
            generate_missing_for_grade(session, 10),
            generate_missing_for_grade(session, 11)
        )
        
        # Объединяем с существующими и сохраняем
        for grade, new_tasks in zip([8, 9, 10, 11], results):
            if new_tasks:
                # Загружаем существующие
                existing_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
                if not os.path.exists(existing_file):
                    existing_file = f"adaptive_150_tasks_grade{grade}_COMPLETE.json"
                if not os.path.exists(existing_file):
                    existing_file = f"adaptive_150_tasks_grade{grade}.json"
                
                try:
                    with open(existing_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                except FileNotFoundError:
                    existing = []
                
                # Объединяем
                combined = existing + new_tasks
                
                # Сохраняем
                output_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(combined, f, ensure_ascii=False, indent=2)
                
                print(f"Класс {grade}: {len(existing)} + {len(new_tasks)} = {len(combined)} задач")
                print(f"Сохранено в {output_file}")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n{'#'*80}")
    print(f"# ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'#'*80}")
    print(f"\nВремя: {duration:.1f} сек ({duration/60:.1f} мин)")
    
    total_success = sum(stats[g]["success"] for g in [8, 9, 10, 11])
    total_all = sum(stats[g]["total"] for g in [8, 9, 10, 11])
    
    for grade in [8, 9, 10, 11]:
        s = stats[grade]["success"]
        t = stats[grade]["total"]
        p = (s/t*100) if t > 0 else 0
        print(f"  Класс {grade}: {s}/{t} ({p:.1f}%)")
    
    overall = (total_success/total_all*100) if total_all > 0 else 0
    print(f"\nОБЩИЙ ИТОГ: {total_success}/{total_all} ({overall:.1f}%)")
    print(f"{'#'*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
