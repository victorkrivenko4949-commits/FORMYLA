"""
ФИНАЛЬНЫЙ генератор олимпиадных задач для 5 класса
С retry logic и гарантией генерации всех 1050 задач
"""

import asyncio
import aiohttp
import json
import os
import re
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден в .env файле!")

# Олимпиадный syllabus для 5 класса
TOPICS_5 = [
    "Логика (рыцари и лжецы, логические таблицы)",
    "Принцип Дирихле",
    "Числовые ребусы и крипторифмы",
    "Делимость, остатки и последняя цифра",
    "Инварианты, четность и чередование",
    "Графы (знакомства, турниры, маршруты)",
    "Комбинаторика (правилы суммы/произведения, деревья)",
    "Геометрия на клетчатой бумаге и разрезания",
    "Взвешивания, переливания и алгоритмы",
    "Текстовые задачи (совместная работа, обратный ход)"
]

LEVELS = list(range(1, 8))
TASKS_PER_LEVEL = 15  # ПОЛНАЯ ГЕНЕРАЦИЯ

# Настройки API
API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_RETRIES = 5  # Увеличено до 5 попыток
TIMEOUT = 60
MAX_CONCURRENT = 10  # Снижено до 10 для стабильности

OUTPUT_FILE = "grade5_full.jsonl"


def get_system_prompt(topic: str, level: int) -> str:
    """Системный промпт для генерации олимпиадной задачи"""
    return f"""Ты — составитель задач для Всероссийской олимпиады школьников. 
Создай ОДНУ задачу для 5 класса. Тема: {topic}. Сложность: {level} из 7.

Уровни сложности:
- 1-2: Школьная программа с подвохом
- 3-4: Школьный этап ВсОШ
- 5: Муниципальный этап ВсОШ (оценка+пример, инварианты)
- 6-7: Региональный/Заключительный этап (сложные раскраски, графы, многоходовые доказательства)

Требования:
1. Строго русский язык.
2. Формулы и числа строго в LaTeX (например, $x^2$, $\\\\frac{{1}}{{2}}$).
3. "answer" — только краткий ответ (число/слово).
4. "explanation" — безупречное, подробное доказательство с обоснованием каждого шага.
5. ВАЖНО: В JSON все обратные слеши в LaTeX должны быть удвоены!

Верни ТОЛЬКО валидный JSON без дополнительного текста:
{{"question": "...", "answer": "...", "explanation": "..."}}"""


def fix_json_escaping(content: str) -> str:
    """
    Исправляет экранирование обратных слешей в JSON
    Заменяет одинарные \ на \\, кроме уже экранированных
    """
    # Заменяем все одинарные обратные слеши на двойные
    # Но не трогаем уже экранированные последовательности
    fixed = re.sub(r'\\(?![\\nrt"\'/bfnrtu])', r'\\\\', content)
    return fixed


async def generate_task_with_retry(
    session: aiohttp.ClientSession,
    topic: str,
    level: int,
    step: int,
    semaphore: asyncio.Semaphore,
    topic_idx: int,
    total_topics: int
) -> Optional[Dict]:
    """
    Генерирует одну задачу с retry logic
    Гарантирует получение валидного результата или None после всех попыток
    """
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                system_prompt = get_system_prompt(topic, level)
                
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Сгенерируй задачу."}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2000
                }
                
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                async with session.post(
                    API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] API error {response.status} | {topic[:30]} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"].strip()
                    
                    # Очистка от markdown блоков
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                    
                    # КРИТИЧНО: Исправление экранирования для LaTeX
                    content = fix_json_escaping(content)
                    
                    # Парсинг JSON
                    try:
                        ai_response = json.loads(content)
                    except json.JSONDecodeError as e:
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] JSON error | {topic[:30]} L{level} S{step}: {str(e)[:50]}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    # Проверка обязательных полей
                    if not all(key in ai_response for key in ["question", "answer", "explanation"]):
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Missing fields | {topic[:30]} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    # КРИТИЧНО: topic берется из цикла, а не из ответа ИИ!
                    task_data = {
                        "grade": 5,
                        "topic": topic,
                        "level": level,
                        "step": step,
                        "question": ai_response["question"],
                        "answer": ai_response["answer"],
                        "explanation": ai_response["explanation"],
                        "generated_at": datetime.utcnow().isoformat()
                    }
                    
                    # Прогресс с указанием темы
                    progress = f"[{topic_idx+1}/{total_topics}] {topic[:30]:30} | L{level} S{step:2}/{TASKS_PER_LEVEL}"
                    print(f"[OK] {progress}")
                    return task_data
                    
            except asyncio.TimeoutError:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Timeout | {topic[:30]} L{level} S{step}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
                
            except Exception as e:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Error | {topic[:30]} L{level} S{step}: {str(e)[:50]}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
        
        print(f"[FAIL] Не удалось сгенерировать после {MAX_RETRIES} попыток | {topic[:30]} L{level} S{step}")
        return None


async def save_task(task_data: Dict, output_file: str):
    """Сохраняет задачу в JSONL файл"""
    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"[ERROR] Ошибка сохранения: {e}")


async def generate_all_tasks():
    """Главная функция: генерирует все задачи"""
    print("="*70)
    print("ГЕНЕРАЦИЯ ОЛИМПИАДНЫХ ЗАДАЧ ДЛЯ 5 КЛАССА")
    print("="*70)
    print(f"Темы: {len(TOPICS_5)}")
    print(f"Уровни: {len(LEVELS)}")
    print(f"Задач на уровень: {TASKS_PER_LEVEL}")
    print(f"ВСЕГО задач: {len(TOPICS_5) * len(LEVELS) * TASKS_PER_LEVEL}")
    print(f"Одновременных запросов: {MAX_CONCURRENT}")
    print(f"Файл: {OUTPUT_FILE}")
    print("="*70)
    
    # Очистка старого файла
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"[INFO] Удален старый файл {OUTPUT_FILE}\n")
    
    # Создаем список всех задач
    tasks_to_generate = []
    for topic_idx, topic in enumerate(TOPICS_5):
        for level in LEVELS:
            for step in range(1, TASKS_PER_LEVEL + 1):
                tasks_to_generate.append((topic, level, step, topic_idx))
    
    print(f"[INFO] Подготовлено {len(tasks_to_generate)} задач\n")
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async with aiohttp.ClientSession() as session:
        coroutines = []
        for topic, level, step, topic_idx in tasks_to_generate:
            coro = generate_task_with_retry(
                session, topic, level, step, semaphore, topic_idx, len(TOPICS_5)
            )
            coroutines.append(coro)
        
        results = await asyncio.gather(*coroutines)
        
        successful = 0
        failed = 0
        
        for task_data in results:
            if task_data is not None:
                await save_task(task_data, OUTPUT_FILE)
                successful += 1
            else:
                failed += 1
        
        print("\n" + "="*70)
        print(f"[SUCCESS] Успешно: {successful}/{len(tasks_to_generate)}")
        print(f"[FAILED] Ошибок: {failed}")
        print(f"[SAVED] Файл: {OUTPUT_FILE}")
        print("="*70)


async def main():
    """Точка входа"""
    start_time = datetime.now()
    await generate_all_tasks()
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"\n[TIME] Время выполнения: {duration:.2f} секунд ({duration/60:.1f} минут)")


if __name__ == "__main__":
    asyncio.run(main())
