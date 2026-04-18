"""
ТУРБО-ГЕНЕРАТОР для 6 класса (Асинхронный + Двойная проверка)
Генерирует 175 задач: 25 якорных (уровень 3) + 150 остальных (уровни 1,2,4,5,6,7)
"""

import asyncio
import aiohttp
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Матрица из 25 тем для 6 класса
GRADE6_TOPICS = [
    "Дроби (сложение, вычитание, умножение, деление)",
    "Делимость чисел (НОД и НОК)",
    "Проценты и их применение",
    "Пропорции и отношения",
    "Модуль числа и координатная прямая",
    "Рыцари и Лжецы (сложные конструкции)",
    "Метод от противного",
    "Логические таблицы",
    "Принцип Дирихле",
    "Игры и стратегии",
    "Движение (по реке, навстречу, вдогонку)",
    "Совместная работа (производительность)",
    "Смеси и сплавы",
    "Метод обратного хода",
    "Переправы и взвешивания",
    "Правило суммы и произведения",
    "Перестановки",
    "Размещения и сочетания",
    "Подсчет вариантов (дерево)",
    "Графы (степени вершин)",
    "Площади и периметры сложных фигур",
    "Разрезания и замощения",
    "Углы и многоугольники",
    "Куб и его развертки",
    "Координатная плоскость"
]

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Семафор для ограничения параллельных запросов
SEMAPHORE = asyncio.Semaphore(30)

# Счетчики
success_count = 0
error_count = 0
total_tasks = 0


def create_generator_prompt(topic: str, level: int, anchor_text: str = None, anchor_solution: str = None) -> str:
    """Создает промпт для Генератора"""
    
    level_desc = {
        1: "базовая математика 6 класса",
        2: "простая задача, 1-2 шага",
        3: "средний уровень (якорная задача)",
        4: "выше среднего, несколько шагов",
        5: "региональная олимпиада",
        6: "сложная региональная олимпиада",
        7: "финал Всероссийской олимпиады"
    }
    
    if level == 3 or not anchor_text:
        # Генерация якорной задачи (без эталона)
        return f"""Сгенерируй олимпиадную задачу для 6 класса на тему: "{topic}"
Уровень сложности: {level} ({level_desc[level]})

ПРАВИЛА:
1. ЗАПРЕЩЕНЫ графические ответы. Только число или текст.
2. МАТЕМАТИКА (LaTeX): ВЕСЬ математический текст строго внутри \\\\( ... \\\\) или \\\\[ ... \\\\].
3. В JSON все обратные слеши УДВАИВАЙ: \\\\( вместо \\(, \\\\frac вместо \\frac.
4. Перед генерацией РЕШИ задачу в уме, проверь логику!

ВЕРНИ ТОЛЬКО JSON:
{{
  "class_level": 6,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Условие с правильным LaTeX",
  "solution": "Полное решение",
  "criteria_1_point": "За что 1 балл",
  "criteria_2_points": "За что 2 балла"
}}"""
    else:
        # Генерация на основе якоря
        return f"""Перед тобой якорная задача 3-го уровня на тему "{topic}":

ЯКОРЬ:
Условие: {anchor_text}
Решение: {anchor_solution}

Сгенерируй НОВУЮ задачу на эту же тему для уровня {level} ({level_desc[level]}).

ПРАВИЛА:
1. Сюжет и числа ДОЛЖНЫ отличаться от якоря!
2. Если {level} < 3: упрости логику. Если {level} > 3: усложни.
3. ЗАПРЕЩЕНЫ графические ответы.
4. LaTeX: \\\\( ... \\\\) и \\\\[ ... \\\\]. В JSON удваивай слеши!
5. РЕШИ задачу в уме перед генерацией!

ВЕРНИ ТОЛЬКО JSON:
{{
  "class_level": 6,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Новое условие",
  "solution": "Новое решение",
  "criteria_1_point": "За что 1 балл",
  "criteria_2_points": "За что 2 балла"
}}"""


def create_critic_prompt(task_json: str) -> str:
    """Создает промпт для Критика"""
    
    return f"""Ты — строгое жюри олимпиады. Перед тобой сгенерированная задача в JSON:

{task_json}

ТВОЯ ЗАДАЧА:
1. Проверь математическую корректность решения (нет ли логических дыр).
2. Проверь LaTeX (все формулы в \\\\( ... \\\\) или \\\\[ ... \\\\]).
3. Проверь JSON (все обратные слеши удвоены).
4. Если есть ошибки — ИСПРАВЬ их.
5. Верни ИДЕАЛЬНЫЙ JSON.

ВЕРНИ ТОЛЬКО ИСПРАВЛЕННЫЙ JSON (без комментариев):"""


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
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                elif response.status in [429, 500, 502, 503]:
                    # Rate limit или server error - ждем и повторяем
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text}")
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
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
                                    anchor_text: str = None, anchor_solution: str = None) -> dict:
    """Генерирует задачу с двойной проверкой (Генератор + Критик)"""
    
    global success_count, error_count
    
    async with SEMAPHORE:
        try:
            # Шаг 1: Генератор создает задачу
            generator_prompt = create_generator_prompt(topic, level, anchor_text, anchor_solution)
            generator_response = await call_deepseek_api(session, generator_prompt)
            generator_json = clean_json_response(generator_response)
            
            # Шаг 2: Критик проверяет и исправляет
            critic_prompt = create_critic_prompt(generator_json)
            critic_response = await call_deepseek_api(
                session, 
                critic_prompt,
                system_prompt="Ты — строгий критик. Проверяй математику и LaTeX. Возвращай только исправленный JSON."
            )
            final_json = clean_json_response(critic_response)
            
            # Парсим финальный JSON
            task_data = json.loads(final_json)
            
            success_count += 1
            return task_data
            
        except json.JSONDecodeError as e:
            error_count += 1
            print(f"ERROR: JSON error for {topic} (level {level}): {e}")
            return None
        except Exception as e:
            error_count += 1
            print(f"ERROR: {topic} (level {level}): {e}")
            return None


async def generate_all_tasks():
    """Главная функция: генерирует все 175 задач"""
    
    global total_tasks
    
    print("=" * 80)
    print("TURBO-GENERATOR DLYA 6 KLASSA (Asynchronous + Critic)")
    print("=" * 80)
    print(f"Plan: 25 anchor tasks (level 3) + 150 others = 175 tasks")
    print(f"Parallelism: 30 requests simultaneously")
    print("=" * 80)
    print()
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        
        # ============================================================
        # STAGE 1: Generate 25 ANCHOR tasks (level 3)
        # ============================================================
        print("STAGE 1: Generating 25 anchor tasks (level 3)...")
        print("-" * 80)
        
        anchor_tasks = []
        anchor_coroutines = []
        
        for topic in GRADE6_TOPICS:
            coro = generate_task_with_critic(session, topic, 3)
            anchor_coroutines.append(coro)
        
        # Запускаем все 25 якорных задач параллельно
        anchor_results = await asyncio.gather(*anchor_coroutines)
        
        for task in anchor_results:
            if task:
                anchor_tasks.append(task)
        
        total_tasks += len(anchor_tasks)
        
        print()
        print(f"SUCCESS: Anchor tasks: {len(anchor_tasks)}/25")
        print()
        
        # Сохраняем якорные задачи
        with open('adaptive_anchor_25_tasks_grade6_level3.json', 'w', encoding='utf-8') as f:
            json.dump(anchor_tasks, f, ensure_ascii=False, indent=2)
        print(f"SAVED: adaptive_anchor_25_tasks_grade6_level3.json")
        print()
        
        # ============================================================
        # STAGE 2: Generate 150 remaining tasks (levels 1,2,4,5,6,7)
        # ============================================================
        print("STAGE 2: Generating 150 remaining tasks (levels 1,2,4,5,6,7)...")
        print("-" * 80)
        
        # Создаем словарь якорей по темам
        anchors_by_topic = {task['topic']: task for task in anchor_tasks}
        
        remaining_tasks = []
        remaining_coroutines = []
        
        target_levels = [1, 2, 4, 5, 6, 7]
        
        for topic in GRADE6_TOPICS:
            anchor = anchors_by_topic.get(topic)
            if not anchor:
                print(f"WARNING: No anchor for topic: {topic}")
                continue
            
            anchor_text = anchor.get('task_text', '')
            anchor_solution = anchor.get('solution', '')
            
            for level in target_levels:
                coro = generate_task_with_critic(session, topic, level, anchor_text, anchor_solution)
                remaining_coroutines.append(coro)
        
        # Запускаем все 150 задач параллельно (с семафором на 30)
        remaining_results = await asyncio.gather(*remaining_coroutines)
        
        for task in remaining_results:
            if task:
                remaining_tasks.append(task)
        
        total_tasks += len(remaining_tasks)
        
        print()
        print(f"SUCCESS: Remaining tasks: {len(remaining_tasks)}/150")
        print()
        
        # Сохраняем остальные задачи
        with open('adaptive_150_tasks_grade6.json', 'w', encoding='utf-8') as f:
            json.dump(remaining_tasks, f, ensure_ascii=False, indent=2)
        print(f"SAVED: adaptive_150_tasks_grade6.json")
        print()
        
        # ============================================================
        # FINAL: Combine all tasks
        # ============================================================
        all_tasks = anchor_tasks + remaining_tasks
        
        with open('adaptive_175_grade6_COMPLETE.json', 'w', encoding='utf-8') as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
        
        elapsed_time = time.time() - start_time
        
        print("=" * 80)
        print("GENERATION COMPLETED!")
        print("=" * 80)
        print(f"SUCCESS: {success_count}/{total_tasks + error_count}")
        print(f"ERRORS: {error_count}")
        print(f"TIME: {elapsed_time:.1f} seconds")
        print(f"FINAL FILE: adaptive_175_grade6_COMPLETE.json")
        print("=" * 80)
        
        # Статистика по уровням
        levels_stat = {}
        for task in all_tasks:
            level = task['difficulty_level']
            levels_stat[level] = levels_stat.get(level, 0) + 1
        
        print()
        print("Распределение по уровням:")
        for level in sorted(levels_stat.keys()):
            print(f"  Уровень {level}: {levels_stat[level]} задач")


if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден в .env файле!")
    else:
        asyncio.run(generate_all_tasks())
