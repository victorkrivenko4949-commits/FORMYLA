"""
Массовый асинхронный генератор адаптивных задач для 8-11 классов
Генерирует 600 задач (150 × 4 класса) с двухэтапной валидацией Generator + Critic
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

# Конфигурация
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SEMAPHORE = asyncio.Semaphore(30)  # 30 параллельных запросов

# Маппинг файлов якорных задач
ANCHOR_FILES = {
    8: "anchor_grade8.json",
    9: "anchor_grade9.json",
    10: "grade10_anchor.json",
    11: "grade11_anchor.json"
}

# Уровни сложности для генерации (пропускаем 3 - это якорный уровень)
DIFFICULTY_LEVELS = [1, 2, 4, 5, 6, 7]

# Глобальные счетчики
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
                    print(f"  [RETRY] Status {response.status}, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"  [ERROR] API returned status {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"  [TIMEOUT] Attempt {attempt + 1}/{max_retries}")
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {str(e)}")
            await asyncio.sleep(2 ** attempt)
    
    return None


async def generate_task(
    session: aiohttp.ClientSession,
    grade: int,
    topic: str,
    difficulty: int,
    anchor_task: dict
) -> Optional[dict]:
    """
    Генерация одной задачи с двухэтапной валидацией:
    1. Generator - создает задачу
    2. Critic - проверяет и исправляет
    """
    
    async with SEMAPHORE:
        stats[grade]["total"] += 1
        
        # Формируем JSON якорной задачи для примера
        anchor_json = json.dumps(anchor_task, ensure_ascii=False, indent=2)
        
        # ШАГ 1: GENERATOR
        generator_prompt = f"""Ты — составитель олимпиадных задач по математике. Сгенерируй задачу для {grade} класса по теме "{topic}", уровень сложности {difficulty} из 7.

Вот эталонная задача уровня 3 для этой же темы (используй её как образец формата, стиля и экранирования LaTeX):

{anchor_json}

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Уровень 1 = элементарная задача для начинающих
2. Уровень 7 = олимпиада всероссийского/международного уровня
3. Твой уровень {difficulty} должен пропорционально отличаться от эталонного уровня 3
4. Задача должна быть математически корректной с правильным решением
5. Весь LaTeX экранируй ДВОЙНЫМИ обратными слешами: \\\\( ... \\\\) и \\\\[ ... \\\\]
6. Перед генерацией JSON реши задачу в уме, чтобы убедиться в корректности

Верни ТОЛЬКО валидный JSON (без маркдауна, без ```json```) со следующими полями:
- question_number: {stats[grade]["total"]}
- topic: "{topic}"
- class_level: {grade}
- difficulty_level: {difficulty}
- task_text: текст задачи с правильно экранированным LaTeX
- solution: подробное решение с правильно экранированным LaTeX
- criteria_1_point: критерий оценки на 1 балл
- criteria_2_points: критерий оценки на 2 балла"""

        generator_response = await call_deepseek_api(session, generator_prompt)
        
        if not generator_response:
            print(f"[Класс {grade} | {topic} | Уровень {difficulty}] FAILED - Generator timeout")
            stats[grade]["failed"] += 1
            return None
        
        # Очистка от markdown
        generated_json = generator_response.strip()
        if generated_json.startswith("```json"):
            generated_json = generated_json[7:]
        if generated_json.startswith("```"):
            generated_json = generated_json[3:]
        if generated_json.endswith("```"):
            generated_json = generated_json[:-3]
        generated_json = generated_json.strip()
        
        # ШАГ 2: CRITIC
        critic_prompt = f"""Ты — эксперт-методист и жюри математических олимпиад. Проверь эту задачу для {grade} класса по теме "{topic}":

{generated_json}

ПРОВЕРЬ:
1. Математическая корректность: решение должно быть правильным, ответ должен следовать из решения
2. Соответствие уровню сложности {difficulty} для {grade} класса (1=легко, 7=очень сложно)
3. Двойное экранирование LaTeX: должно быть \\\\( и \\\\), НЕ \\( и \\)
4. Полнота решения: все шаги должны быть объяснены
5. Критерии оценки должны быть адекватными

Если найдешь ошибки - ИСПРАВЬ их.
Верни ТОЛЬКО исправленный валидный JSON без маркдауна."""

        critic_response = await call_deepseek_api(session, critic_prompt)
        
        if not critic_response:
            print(f"[Класс {grade} | {topic} | Уровень {difficulty}] FAILED - Critic timeout")
            stats[grade]["failed"] += 1
            return None
        
        # Очистка от markdown
        final_json = critic_response.strip()
        if final_json.startswith("```json"):
            final_json = final_json[7:]
        if final_json.startswith("```"):
            final_json = final_json[3:]
        if final_json.endswith("```"):
            final_json = final_json[:-3]
        final_json = final_json.strip()
        
        # Парсинг финального JSON
        try:
            task = json.loads(final_json)
            
            # Валидация обязательных полей
            required_fields = ["question_number", "topic", "class_level", "difficulty_level", 
                             "task_text", "solution", "criteria_1_point", "criteria_2_points"]
            
            if all(field in task for field in required_fields):
                stats[grade]["success"] += 1
                print(f"[Класс {grade} | {topic} | Уровень {difficulty}] SUCCESS")
                return task
            else:
                missing = [f for f in required_fields if f not in task]
                print(f"[Класс {grade} | {topic} | Уровень {difficulty}] FAILED - Missing fields: {missing}")
                stats[grade]["failed"] += 1
                return None
                
        except json.JSONDecodeError as e:
            print(f"[Класс {grade} | {topic} | Уровень {difficulty}] FAILED - JSON parse error: {str(e)[:100]}")
            stats[grade]["failed"] += 1
            return None


async def generate_for_grade(session: aiohttp.ClientSession, grade: int) -> List[dict]:
    """Генерация всех 150 задач для одного класса"""
    
    print(f"\n{'='*80}")
    print(f"НАЧАЛО ГЕНЕРАЦИИ ДЛЯ {grade} КЛАССА")
    print(f"{'='*80}\n")
    
    # Загрузка якорных задач
    anchor_file = ANCHOR_FILES[grade]
    try:
        with open(anchor_file, 'r', encoding='utf-8') as f:
            anchor_tasks = json.load(f)
    except Exception as e:
        print(f"ERROR: Не удалось загрузить {anchor_file}: {e}")
        return []
    
    print(f"Загружено {len(anchor_tasks)} якорных задач из {anchor_file}")
    
    # Извлекаем темы из якорных задач
    topics = [task["topic"] for task in anchor_tasks]
    print(f"Темы ({len(topics)}): {', '.join(topics[:3])}...")
    
    # Создаем маппинг тема -> якорная задача
    topic_to_anchor = {task["topic"]: task for task in anchor_tasks}
    
    # Генерируем задачи
    tasks_to_generate = []
    for topic in topics:
        anchor_task = topic_to_anchor[topic]
        for difficulty in DIFFICULTY_LEVELS:
            tasks_to_generate.append((grade, topic, difficulty, anchor_task))
    
    print(f"\nВсего задач к генерации: {len(tasks_to_generate)} ({len(topics)} тем x {len(DIFFICULTY_LEVELS)} уровней)")
    print(f"Начало генерации...\n")
    
    # Асинхронная генерация всех задач
    coroutines = [
        generate_task(session, grade, topic, difficulty, anchor)
        for grade, topic, difficulty, anchor in tasks_to_generate
    ]
    
    results = await asyncio.gather(*coroutines)
    
    # Фильтруем успешные результаты
    generated_tasks = [task for task in results if task is not None]
    
    print(f"\n{'='*80}")
    print(f"ЗАВЕРШЕНО ДЛЯ {grade} КЛАССА")
    print(f"Успешно: {stats[grade]['success']}/{stats[grade]['total']}")
    print(f"Провалено: {stats[grade]['failed']}/{stats[grade]['total']}")
    print(f"Процент успеха: {stats[grade]['success']/stats[grade]['total']*100:.1f}%")
    print(f"{'='*80}\n")
    
    return generated_tasks


async def main():
    """Главная функция - генерация для всех классов"""
    
    start_time = datetime.now()
    print(f"\n{'#'*80}")
    print(f"# МАССОВАЯ ГЕНЕРАЦИЯ АДАПТИВНЫХ ЗАДАЧ ДЛЯ 8-11 КЛАССОВ")
    print(f"# Начало: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}\n")
    
    async with aiohttp.ClientSession() as session:
        # Генерируем для всех классов параллельно
        results = await asyncio.gather(
            generate_for_grade(session, 8),
            generate_for_grade(session, 9),
            generate_for_grade(session, 10),
            generate_for_grade(session, 11)
        )
        
        # Сохраняем результаты
        for grade, tasks in zip([8, 9, 10, 11], results):
            if tasks:
                filename = f"adaptive_150_tasks_grade{grade}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(tasks, f, ensure_ascii=False, indent=2)
                print(f"Сохранено {len(tasks)} задач в {filename}")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Итоговая статистика
    print(f"\n{'#'*80}")
    print(f"# ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'#'*80}")
    print(f"\nВремя выполнения: {duration:.1f} секунд ({duration/60:.1f} минут)")
    print(f"\nПо классам:")
    
    total_success = 0
    total_failed = 0
    total_all = 0
    
    for grade in [8, 9, 10, 11]:
        success = stats[grade]["success"]
        failed = stats[grade]["failed"]
        total = stats[grade]["total"]
        percent = (success / total * 100) if total > 0 else 0
        
        total_success += success
        total_failed += failed
        total_all += total
        
        print(f"  Класс {grade}: {success}/{total} ({percent:.1f}%) | Провалено: {failed}")
    
    overall_percent = (total_success / total_all * 100) if total_all > 0 else 0
    print(f"\nОБЩИЙ ИТОГ: {total_success}/{total_all} ({overall_percent:.1f}%)")
    print(f"Провалено: {total_failed}")
    print(f"\n{'#'*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
