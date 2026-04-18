"""
Догенератор недостающих задач для 6 класса (асинхронный)
"""

import asyncio
import aiohttp
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
SEMAPHORE = asyncio.Semaphore(10)  # Меньше параллельности для стабильности

success_count = 0
error_count = 0


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
        return f"""Сгенерируй олимпиадную задачу для 6 класса на тему: "{topic}"
Уровень сложности: {level} ({level_desc[level]})

ПРАВИЛА:
1. ЗАПРЕЩЕНЫ графические ответы.
2. LaTeX: \\\\( ... \\\\) или \\\\[ ... \\\\]. В JSON удваивай слеши!
3. Реши задачу в уме перед генерацией!

ВЕРНИ ТОЛЬКО JSON:
{{
  "class_level": 6,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Условие",
  "solution": "Решение",
  "criteria_1_point": "За что 1 балл",
  "criteria_2_points": "За что 2 балла"
}}"""
    else:
        return f"""Якорная задача на тему "{topic}":
Условие: {anchor_text}
Решение: {anchor_solution}

Сгенерируй НОВУЮ задачу для уровня {level} ({level_desc[level]}).

ПРАВИЛА:
1. Сюжет и числа ДОЛЖНЫ отличаться!
2. Если {level} < 3: упрости. Если {level} > 3: усложни.
3. LaTeX: \\\\( ... \\\\). В JSON удваивай слеши!

ВЕРНИ ТОЛЬКО JSON:
{{
  "class_level": 6,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Условие",
  "solution": "Решение",
  "criteria_1_point": "1 балл",
  "criteria_2_points": "2 балла"
}}"""


async def call_deepseek_api(session: aiohttp.ClientSession, prompt: str) -> str:
    """Асинхронный вызов API"""
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Ты — генератор олимпиадных задач. Возвращай только валидный JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85,
        "max_tokens": 2500
    }
    
    for attempt in range(3):
        try:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    await asyncio.sleep(2 ** attempt)
        except:
            if attempt < 2:
                await asyncio.sleep(2)
            else:
                raise
    
    raise Exception("Max retries exceeded")


def clean_json(text: str) -> str:
    """Очищает JSON от markdown"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def generate_task(session: aiohttp.ClientSession, topic: str, level: int, anchor: dict = None) -> dict:
    """Генерирует одну задачу"""
    
    global success_count, error_count
    
    async with SEMAPHORE:
        try:
            anchor_text = anchor.get('task_text', '') if anchor else None
            anchor_solution = anchor.get('solution', '') if anchor else None
            
            prompt = create_generator_prompt(topic, level, anchor_text, anchor_solution)
            response = await call_deepseek_api(session, prompt)
            json_text = clean_json(response)
            
            task_data = json.loads(json_text)
            success_count += 1
            return task_data
            
        except Exception as e:
            error_count += 1
            print(f"ERROR: {topic} (level {level}): {str(e)[:100]}")
            return None


async def generate_missing():
    """Генерирует недостающие задачи"""
    
    with open('missing_tasks_grade6.json', 'r', encoding='utf-8') as f:
        missing_list = json.load(f)
    
    print("=" * 80)
    print(f"GENERATING MISSING TASKS: {len(missing_list)} tasks")
    print("=" * 80)
    print()
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        coroutines = []
        
        for item in missing_list:
            coro = generate_task(session, item['topic'], item['level'], item.get('anchor'))
            coroutines.append(coro)
        
        results = await asyncio.gather(*coroutines)
        
        tasks = [t for t in results if t]
        
        # Сохраняем
        with open('missing_grade6_generated.json', 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        
        elapsed = time.time() - start_time
        
        print()
        print("=" * 80)
        print("COMPLETED!")
        print(f"SUCCESS: {success_count}/{len(missing_list)}")
        print(f"ERRORS: {error_count}")
        print(f"TIME: {elapsed:.1f} seconds")
        print(f"SAVED: missing_grade6_generated.json")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(generate_missing())
