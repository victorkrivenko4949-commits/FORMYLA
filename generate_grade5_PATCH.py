"""
ДОГЕНЕРАЦИЯ недостающих задач для 5 класса
С увеличенным max_tokens=8192 для длинных решений
"""

import asyncio
import aiohttp
import json
import os
import re
import ast
from datetime import datetime
from typing import Dict, Optional, Set, Tuple
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден в .env файле!")

# Олимпиадный syllabus
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
TASKS_PER_LEVEL = 15

# Настройки API
API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_RETRIES = 5
TIMEOUT = 90  # Увеличен таймаут для длинных ответов
MAX_CONCURRENT = 10

INPUT_FILE = "grade5_olympiad_FINAL.jsonl"
OUTPUT_FILE = "grade5_olympiad_PATCH.jsonl"


def get_system_prompt(topic: str, level: int) -> str:
    """Системный промпт с увеличенным вниманием к структуре"""
    base_prompt = f"""Ты — составитель задач для Всероссийской олимпиады школьников. 
Создай ОДНУ задачу для 5 класса. Тема: {topic}. Сложность: {level} из 7.

Уровни сложности:
- 1-2: Школьная программа с подвохом
- 3-4: Школьный этап ВсОШ
- 5: Муниципальный этап ВсОШ (оценка+пример, инварианты)
- 6-7: Региональный/Заключительный этап (сложные раскраски, графы, многоходовые доказательства)

МАТЕМАТИЧЕСКОЕ ФОРМАТИРОВАНИЕ (LATEX STRICT MODE):
Абсолютно все числа, переменные, дроби, степени, скобки и формулы ДОЛЖНЫ быть обернуты в $...$ (inline LaTeX) или $$...$$ (block LaTeX).
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
1. Использовать юникод-символы для математики (например, ², ³, ⌈, ⌉, ½, °, ×, ÷).
2. Писать дроби через слэш вне LaTeX (например, 25/4). Используй ТОЛЬКО $\\\\frac{{25}}{{4}}$.
3. Округлять или писать спецсимволы текстом. Вместо ⌈25/4⌉ = 7 пиши $\\\\lceil \\\\frac{{25}}{{4}} \\\\rceil = 7$.
Все обратные слеши в JSON должны быть двойными (например, \\\\frac, \\\\lceil, \\\\rceil).

КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ КАВЫЧЕК:
Никогда не используй двойные кавычки (") внутри значений текстовых полей JSON!
Если тебе нужны кавычки в тексте задачи или решения, ИСПОЛЬЗУЙ ТОЛЬКО ОДИНАРНЫЕ КАВЫЧКИ ('') или ЁЛОЧКИ («»).

ВАЖНОЕ ПРАВИЛО JSON:
Внутри JSON все обратные слеши для LaTeX должны быть экранированы двумя слешами!
ПЛОХО: "text": "Найти \\frac{{1}}{{2}}"
ХОРОШО: "text": "Найти \\\\frac{{1}}{{2}}"
"""
    
    # Дополнительные правила для проблемных тем
    if "Взвешивания" in topic or "Логика" in topic:
        base_prompt += """
СПЕЦИАЛЬНОЕ ПРАВИЛО ДЛЯ ДЛИННЫХ РЕШЕНИЙ:
Решения должны быть ИСЧЕРПЫВАЮЩИМИ, но СТРУКТУРИРОВАННЫМИ.
Используй нумерованные шаги (1., 2., 3.) или подпункты (а), б), в)).
Не пиши лишних слов. Главное — ОБЯЗАТЕЛЬНО доведи JSON до конца и закрой все скобки!
Если решение получается очень длинным, разбей его на четкие этапы с краткими выводами.
"""
    
    base_prompt += """
Верни ТОЛЬКО валидный JSON без дополнительного текста:
{{"question": "...", "answer": "...", "explanation": "..."}}"""
    
    return base_prompt


def robust_json_parse(text: str) -> Optional[Dict]:
    """ПУЛЕНЕПРОБИВАЕМЫЙ парсинг JSON"""
    try:
        if not text or not text.strip():
            print("[ERROR] API вернул пустую строку!")
            return None
        
        # Умный поиск JSON
        start_dict = text.find('{')
        end_dict = text.rfind('}')
        
        if start_dict != -1 and end_dict != -1 and end_dict > start_dict:
            text_to_parse = text[start_dict:end_dict+1]
        else:
            print("[ERROR] Не найдено JSON-подобного блока!")
            return None
        
        # Экранирование слешей для LaTeX
        text_to_parse = text_to_parse.replace('\\\\', '@@DOUBLE_SLASH@@')
        text_to_parse = text_to_parse.replace('\\"', '@@ESCAPED_QUOTE@@')
        text_to_parse = text_to_parse.replace('\\', '\\\\')
        text_to_parse = text_to_parse.replace('@@DOUBLE_SLASH@@', '\\\\')
        text_to_parse = text_to_parse.replace('@@ESCAPED_QUOTE@@', '\\"')
        
        return json.loads(text_to_parse)
        
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON error: {str(e)[:80]}")
        try:
            text_for_ast = text_to_parse.replace('null', 'None').replace('true', 'True').replace('false', 'False')
            return ast.literal_eval(text_for_ast)
        except:
            return None
    except:
        return None


def find_missing_tasks(input_file: str) -> list:
    """Находит недостающие задачи"""
    existing = set()
    
    if os.path.exists(input_file):
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                task = json.loads(line)
                key = (task['topic'], task['level'], task['step'])
                existing.add(key)
    
    missing = []
    for topic in TOPICS_5:
        for level in LEVELS:
            for step in range(1, TASKS_PER_LEVEL + 1):
                key = (topic, level, step)
                if key not in existing:
                    missing.append(key)
    
    return missing


async def generate_task_with_retry(
    session: aiohttp.ClientSession,
    topic: str,
    level: int,
    step: int,
    semaphore: asyncio.Semaphore,
    task_idx: int,
    total_tasks: int
) -> Optional[Dict]:
    """Генерирует одну задачу с retry logic"""
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
                    "max_tokens": 8192  # УВЕЛИЧЕН ЛИМИТ!
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
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] API error {response.status} | {topic[:25]} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"].strip()
                    
                    ai_response = robust_json_parse(content)
                    
                    if not ai_response:
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Parse fail | {topic[:25]} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    if not all(key in ai_response for key in ["question", "answer", "explanation"]):
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Missing fields | {topic[:25]} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
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
                    
                    print(f"[OK] [{task_idx+1}/{total_tasks}] {topic[:25]:25} | L{level} S{step:2}")
                    return task_data
                    
            except asyncio.TimeoutError:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Timeout | {topic[:25]} L{level} S{step}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
                
            except Exception as e:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Error | {topic[:25]} L{level} S{step}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
        
        return None


def save_task(task_data: Dict, output_file: str):
    """Сохраняет задачу в JSONL файл"""
    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"[ERROR] Ошибка сохранения: {e}")


async def generate_missing_tasks():
    """Догенерация недостающих задач"""
    print("="*70)
    print("ДОГЕНЕРАЦИЯ НЕДОСТАЮЩИХ ЗАДАЧ ДЛЯ 5 КЛАССА")
    print("="*70)
    
    missing = find_missing_tasks(INPUT_FILE)
    
    if not missing:
        print("Все задачи уже сгенерированы!")
        return
    
    print(f"Недостающих задач: {len(missing)}")
    print(f"Файл: {OUTPUT_FILE}")
    print(f"max_tokens: 8192 (увеличен для длинных решений)")
    print("="*70)
    
    # Группировка по темам для статистики
    by_topic = defaultdict(int)
    for topic, level, step in missing:
        by_topic[topic] += 1
    
    print("\nНедостающие задачи по темам:")
    for topic in TOPICS_5:
        count = by_topic[topic]
        if count > 0:
            print(f"  {topic}: {count} задач")
    print()
    
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async with aiohttp.ClientSession() as session:
        coroutines = []
        for idx, (topic, level, step) in enumerate(missing):
            coro = generate_task_with_retry(
                session, topic, level, step, semaphore, idx, len(missing)
            )
            coroutines.append(coro)
        
        results = await asyncio.gather(*coroutines)
        
        successful = 0
        failed = 0
        
        for task_data in results:
            if task_data is not None:
                save_task(task_data, OUTPUT_FILE)
                successful += 1
            else:
                failed += 1
        
        print("\n" + "="*70)
        print(f"[SUCCESS] Успешно: {successful}/{len(missing)}")
        print(f"[FAILED] Ошибок: {failed}")
        print(f"[SAVED] Файл: {OUTPUT_FILE}")
        print("="*70)


async def main():
    start_time = datetime.now()
    await generate_missing_tasks()
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"\n[TIME] Время: {duration:.2f} сек ({duration/60:.1f} мин)")


if __name__ == "__main__":
    asyncio.run(main())
