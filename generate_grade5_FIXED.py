"""
ИСПРАВЛЕННЫЙ генератор олимпиадных задач для 5 класса
С ПУЛЕНЕПРОБИВАЕМЫМ парсингом JSON для LaTeX
"""

import asyncio
import aiohttp
import json
import os
import re
import ast
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

LEVELS = list(range(1, 8))  # ВСЕ 7 уровней
TASKS_PER_LEVEL = 15  # ПОЛНАЯ ГЕНЕРАЦИЯ: 15 задач на уровень

# Настройки API
API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_RETRIES = 5
TIMEOUT = 60
MAX_CONCURRENT = 10

OUTPUT_FILE = "grade5_olympiad_FINAL.jsonl"


def get_system_prompt(topic: str, level: int) -> str:
    """Системный промпт для генерации олимпиадной задачи"""
    return f"""Ты — составитель задач для Всероссийской олимпиады школьников.
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

Верни ТОЛЬКО валидный JSON без дополнительного текста:
{{"question": "...", "answer": "...", "explanation": "..."}}"""


def robust_json_parse(text: str) -> Optional[Dict]:
    """
    ПУЛЕНЕПРОБИВАЕМЫЙ парсинг JSON с LaTeX формулами
    Использует агрессивное экранирование слешей и умный поиск JSON
    """
    try:
        if not text or not text.strip():
            print("[ERROR] API вернул пустую строку!")
            return None
        
        # 1. УМНЫЙ ПОИСК JSON - находим фигурные скобки даже если есть мусор
        text_to_parse = None
        
        # Сначала пробуем найти в markdown блоке
        json_match = re.search(r'```(?:json)?\s*(\{.*\}|\[.*\])\s*```', text, re.DOTALL)
        if json_match:
            text_to_parse = json_match.group(1)
        else:
            # Ищем от первой { до последней }
            start_dict = text.find('{')
            end_dict = text.rfind('}')
            
            if start_dict != -1 and end_dict != -1 and end_dict > start_dict:
                text_to_parse = text[start_dict:end_dict+1]
            else:
                print("[ERROR] Не найдено JSON-подобного блока в тексте!")
                return None
        
        # 2. КРИТИЧЕСКИЙ ФИКС ДЛЯ LATEX:
        # Сначала временно прячем уже экранированные слеши и кавычки
        text_to_parse = text_to_parse.replace('\\\\', '@@DOUBLE_SLASH@@')
        text_to_parse = text_to_parse.replace('\\"', '@@ESCAPED_QUOTE@@')
        
        # Теперь все оставшиеся \ превращаем в \\
        text_to_parse = text_to_parse.replace('\\', '\\\\')
        
        # Возвращаем спрятанное
        text_to_parse = text_to_parse.replace('@@DOUBLE_SLASH@@', '\\\\')
        text_to_parse = text_to_parse.replace('@@ESCAPED_QUOTE@@', '\\"')
        
        # 3. Парсим
        return json.loads(text_to_parse)
        
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON error после очистки: {str(e)[:100]}")
        # Если всё равно упало, используем ast.literal_eval как последний шанс
        try:
            # Превращаем null/true/false в None/True/False для python
            text_for_ast = text_to_parse.replace('null', 'None').replace('true', 'True').replace('false', 'False')
            return ast.literal_eval(text_for_ast)
        except Exception as ast_e:
            print(f"[ERROR] ast.literal_eval тоже не справился: {str(ast_e)[:100]}")
            return None
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка парсинга: {str(e)[:100]}")
        return None


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
                    
                    # ИСПОЛЬЗУЕМ ПУЛЕНЕПРОБИВАЕМЫЙ ПАРСИНГ
                    ai_response = robust_json_parse(content)
                    
                    if not ai_response:
                        print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Не удалось распарсить JSON | {topic[:30]} L{level} S{step}")
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
                    
                    # КРИТИЧНО: topic берется из цикла!
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
        
        print(f"[FAIL] Не удалось после {MAX_RETRIES} попыток | {topic[:30]} L{level} S{step}")
        return None


def save_task(task_data: Dict, output_file: str):
    """Сохраняет задачу в JSONL файл (СИНХРОННАЯ версия)"""
    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"[ERROR] Ошибка сохранения: {e}")


async def generate_all_tasks():
    """Главная функция"""
    print("="*70)
    print("ТЕСТОВАЯ ГЕНЕРАЦИЯ С ИСПРАВЛЕННЫМ ПАРСИНГОМ")
    print("="*70)
    print(f"Темы: {len(TOPICS_5)}")
    print(f"Уровни: {len(LEVELS)}")
    print(f"Задач на уровень: {TASKS_PER_LEVEL}")
    print(f"ВСЕГО задач: {len(TOPICS_5) * len(LEVELS) * TASKS_PER_LEVEL}")
    print(f"Файл: {OUTPUT_FILE}")
    print("="*70)
    
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"[INFO] Удален старый файл\n")
    
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
                save_task(task_data, OUTPUT_FILE)  # Убрали await!
                successful += 1
            else:
                failed += 1
        
        print("\n" + "="*70)
        print(f"[SUCCESS] Успешно: {successful}/{len(tasks_to_generate)}")
        print(f"[FAILED] Ошибок: {failed}")
        print(f"[SAVED] Файл: {OUTPUT_FILE}")
        print("="*70)


async def main():
    start_time = datetime.now()
    await generate_all_tasks()
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"\n[TIME] Время: {duration:.2f} сек ({duration/60:.1f} мин)")


if __name__ == "__main__":
    asyncio.run(main())
