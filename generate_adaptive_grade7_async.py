"""
ТУРБО-ГЕНЕРАТОР для 7 класса (Асинхронный + Двойная проверка)
Генерирует 150 задач на основе 25 якорных задач 3-го уровня
"""

import asyncio
import aiohttp
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Матрица из 25 тем для 7 класса
GRADE7_TOPICS = [
    "Вычисления (рациональные числа)",
    "Движение (вдогонку и навстречу)",
    "Совместная работа",
    "Проценты",
    "Делимость (признаки)",
    "НОД и НОК",
    "Простые и составные числа",
    "Уравнения (текстовые)",
    "Линейные диофантовы уравнения",
    "Логика (Рыцари и лжецы)",
    "Принцип Дирихле",
    "Метод от противного",
    "Инварианты (четность)",
    "Инварианты (раскраски)",
    "Игры (симметрия)",
    "Игры (анализ с конца)",
    "Графы (степени вершин)",
    "Графы (связность)",
    "Геометрия (смежные и вертикальные углы)",
    "Геометрия (равнобедренный треугольник)",
    "Комбинаторика (правило умножения)",
    "Комбинаторика (перестановки)",
    "Текстовые задачи на возраст",
    "Взвешивания",
    "Закономерности"
]

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Семафор для ограничения параллельных запросов
SEMAPHORE = asyncio.Semaphore(30)

# Счетчики
success_count = 0
error_count = 0


def create_generator_prompt(topic: str, level: int, anchor_task: dict) -> str:
    """Создает промпт для Генератора на основе якорной задачи"""
    
    anchor_text = anchor_task.get('task_text', '')
    anchor_solution = anchor_task.get('solution', '')
    
    level_desc = {
        1: "базовая математика 7 класса",
        2: "простая задача, 1-2 шага",
        3: "средний уровень (якорь)",
        4: "выше среднего, несколько шагов",
        5: "региональная олимпиада",
        6: "сложная региональная олимпиада",
        7: "финал Всероссийской олимпиады"
    }
    
    return f"""Перед тобой якорная задача 3-го уровня на тему "{topic}" для 7 класса:

ЯКОРЬ (Уровень 3):
Условие: {anchor_text}
Решение: {anchor_solution}

Сгенерируй НОВУЮ задачу на эту же тему для уровня {level} ({level_desc[level]}).

ПРАВИЛА:
1. Сюжет и числа ДОЛЖНЫ отличаться от якоря!
2. Если {level} < 3: упрости логику (меньше шагов, проще числа).
3. Если {level} > 3: усложни логику (больше параметров, сложнее вычисления).
4. ЗАПРЕЩЕНЫ графические ответы.
5. LaTeX: \\\\( ... \\\\) или \\\\[ ... \\\\]. В JSON удваивай слеши!
6. РЕШИ задачу в уме перед генерацией - проверь логику!

ВЕРНИ ТОЛЬКО JSON (без комментариев):
{{
  "class_level": 7,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Новое условие",
  "solution": "Новое решение",
  "criteria_1_point": "За что 1 балл",
  "criteria_2_points": "За что 2 балла"
}}"""


def create_critic_prompt(task_json: str) -> str:
    """Создает промпт для Критика"""
    
    return f"""Ты — строгое жюри олимпиады. Перед тобой сгенерированная задача:

{task_json}

ПРОВЕРЬ:
1. Математическая корректность решения (нет логических дыр).
2. LaTeX правильно экранирован (\\\\( ... \\\\) в JSON).
3. Все обратные слеши удвоены.
4. Если есть ошибки — ИСПРАВЬ их.

ВЕРНИ ТОЛЬКО ИСПРАВЛЕННЫЙ JSON:"""


async def call_deepseek_api(session: aiohttp.ClientSession, prompt: str, system_prompt: str = None) -> str:
    """Асинхронный вызов DeepSeek API"""
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt or "Ты — генератор олимпиадных задач."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85,
        "max_tokens": 2500
    }
    
    for attempt in range(3):
        try:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, 
                                   timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                elif response.status in [429, 500, 502, 503]:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise Exception(f"API error {response.status}")
        except asyncio.TimeoutError:
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise
    
    raise Exception("Max retries exceeded")


def clean_json_response(text: str) -> str:
    """Очищает ответ от markdown оберток"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def generate_task_with_critic(session: aiohttp.ClientSession, topic: str, level: int, 
                                    anchor_task: dict, task_index: int, total: int) -> dict:
    """Генерирует задачу с двойной проверкой (Генератор + Критик)"""
    
    global success_count, error_count
    
    async with SEMAPHORE:
        try:
            # Шаг 1: Генератор создает задачу
            generator_prompt = create_generator_prompt(topic, level, anchor_task)
            generator_response = await call_deepseek_api(session, generator_prompt)
            generator_json = clean_json_response(generator_response)
            
            # Шаг 2: Критик проверяет и исправляет
            critic_prompt = create_critic_prompt(generator_json)
            critic_response = await call_deepseek_api(
                session, 
                critic_prompt,
                system_prompt="Ты — строгий критик. Проверяй математику и LaTeX. Возвращай только JSON."
            )
            final_json = clean_json_response(critic_response)
            
            # Парсим финальный JSON
            task_data = json.loads(final_json)
            
            success_count += 1
            print(f"[{task_index}/{total}] [{topic} | Level {level}] SUCCESS!")
            return task_data
            
        except json.JSONDecodeError as e:
            error_count += 1
            print(f"[{task_index}/{total}] [{topic} | Level {level}] ERROR: JSON - {str(e)[:50]}")
            return None
        except Exception as e:
            error_count += 1
            print(f"[{task_index}/{total}] [{topic} | Level {level}] ERROR: {str(e)[:50]}")
            return None


async def generate_all_tasks():
    """Главная функция: генерирует 150 задач для 7 класса"""
    
    print("=" * 80)
    print("TURBO-GENERATOR FOR GRADE 7 (Async + Critic)")
    print("=" * 80)
    print(f"Plan: Generate 150 tasks (levels 1,2,4,5,6,7) based on 25 anchors")
    print(f"Parallelism: 30 requests simultaneously")
    print("=" * 80)
    print()
    
    # Загружаем якорные задачи
    try:
        with open('adaptive_anchor_25_tasks_grade7_level3.json', 'r', encoding='utf-8') as f:
            anchor_tasks = json.load(f)
    except FileNotFoundError:
        print("ERROR: File adaptive_anchor_25_tasks_grade7_level3.json not found!")
        return
    
    print(f"Loaded {len(anchor_tasks)} anchor tasks (level 3)")
    print()
    
    # Создаем словарь якорей по темам
    anchors_by_topic = {task['topic']: task for task in anchor_tasks}
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        
        # Генерируем 150 задач (6 уровней × 25 тем)
        print("Generating 150 tasks...")
        print("-" * 80)
        
        tasks = []
        coroutines = []
        target_levels = [1, 2, 4, 5, 6, 7]
        
        task_index = 0
        for topic in GRADE7_TOPICS:
            anchor = anchors_by_topic.get(topic)
            if not anchor:
                print(f"WARNING: No anchor for topic: {topic}")
                continue
            
            for level in target_levels:
                task_index += 1
                coro = generate_task_with_critic(session, topic, level, anchor, task_index, 150)
                coroutines.append(coro)
        
        # Запускаем все 150 задач параллельно (с семафором на 30)
        results = await asyncio.gather(*coroutines)
        
        for task in results:
            if task:
                tasks.append(task)
        
        # Сохраняем результат
        with open('adaptive_150_tasks_grade7.json', 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        
        elapsed_time = time.time() - start_time
        
        print()
        print("=" * 80)
        print("GENERATION COMPLETED!")
        print("=" * 80)
        print(f"SUCCESS: {success_count}/150")
        print(f"ERRORS: {error_count}")
        print(f"TIME: {elapsed_time:.1f} seconds")
        print(f"SAVED: adaptive_150_tasks_grade7.json")
        print("=" * 80)
        
        # Статистика по уровням
        levels_stat = {}
        for task in tasks:
            level = task['difficulty_level']
            levels_stat[level] = levels_stat.get(level, 0) + 1
        
        print()
        print("Distribution by level:")
        for level in sorted(levels_stat.keys()):
            print(f"  Level {level}: {levels_stat[level]} tasks")


if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not found in .env!")
    else:
        asyncio.run(generate_all_tasks())
