"""
Асинхронный генератор олимпиадных задач для 5 класса
Генерирует задачи уровня ВсОШ с промежуточным сохранением
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

# Загрузка API ключа
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

# Уровни сложности (1-7)
LEVELS = list(range(1, 8))

# ТЕСТОВЫЙ РЕЖИМ: 1 задача на уровень (всего 70 задач)
# Для полной генерации замените на 15
TASKS_PER_LEVEL = 1

# Настройки API
API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_RETRIES = 3
TIMEOUT = 60
MAX_CONCURRENT = 30  # Количество одновременных запросов

# Файл для сохранения
OUTPUT_FILE = "grade5_olympiad_tasks.jsonl"


def robust_json_parse(text: str) -> Optional[Dict]:
    """
    Пуленепробиваемый парсинг JSON с LaTeX.
    Обрабатывает кривые слеши, markdown блоки и другие проблемы.
    """
    import re
    
    # 1. Вытаскиваем только JSON из блока ```json ... ``` или фигурных скобок
    json_match = re.search(r'```(?:json)?\s*(\{.*\}|\[.*\])\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        # Если нет маркдауна, ищем от первой { до последней }
        json_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
    
    # 2. КРИТИЧЕСКИЙ ФИКС ДЛЯ LATEX:
    # Временно прячем уже экранированные слеши и кавычки
    text = text.replace('\\\\', '@@DOUBLE_SLASH@@')
    text = text.replace('\\"', '@@ESCAPED_QUOTE@@')
    
    # Теперь все оставшиеся \ превращаем в \\
    text = text.replace('\\', '\\\\')
    
    # Возвращаем спрятанное
    text = text.replace('@@DOUBLE_SLASH@@', '\\\\')
    text = text.replace('@@ESCAPED_QUOTE@@', '\\"')
    
    # 3. Парсим
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга даже после жесткой очистки: {e}")
        print(f"Проблемный JSON (первые 300 символов):\n{text[:300]}")
        return None


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

КРИТИЧЕСКОЕ ПРАВИЛО JSON:
Внутри JSON все обратные слеши для LaTeX должны быть экранированы ДВУМЯ слешами!
ПЛОХО: "text": "Найти \\frac{{1}}{{2}}"
ХОРОШО: "text": "Найти \\\\frac{{1}}{{2}}"
Это критически важно, иначе парсер сломается!

Верни ТОЛЬКО валидный JSON без дополнительного текста:
{{"question": "...", "answer": "...", "explanation": "..."}}"""


async def generate_task(
    session: aiohttp.ClientSession,
    topic: str,
    level: int,
    step: int,
    semaphore: asyncio.Semaphore
) -> Optional[Dict]:
    """
    Генерирует одну задачу через DeepSeek API
    
    Args:
        session: aiohttp сессия
        topic: Тема задачи
        level: Уровень сложности (1-7)
        step: Номер задачи в рамках темы и уровня
        semaphore: Семафор для ограничения одновременных запросов
    
    Returns:
        Словарь с данными задачи или None при ошибке
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
                        print(f"[ERROR] API ошибка {response.status} для {topic} L{level} S{step}: {error_text}")
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
                    
                    # Парсинг JSON с пуленепробиваемой функцией
                    ai_response = robust_json_parse(content)
                    
                    if not ai_response:
                        print(f"[WARN] Не удалось распарсить JSON для {topic} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    # Проверка обязательных полей
                    if not all(key in ai_response for key in ["question", "answer", "explanation"]):
                        print(f"[WARN] Отсутствуют обязательные поля для {topic} L{level} S{step}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    # КРИТИЧНО: topic берется из цикла, а не из ответа ИИ!
                    task_data = {
                        "grade": 5,
                        "topic": topic,  # <-- Жестко из списка TOPICS_5
                        "level": level,
                        "step": step,
                        "question": ai_response["question"],
                        "answer": ai_response["answer"],
                        "explanation": ai_response["explanation"],
                        "generated_at": datetime.utcnow().isoformat()
                    }
                    
                    print(f"[OK] Сгенерирована: {topic} | L{level} | S{step}")
                    return task_data
                    
            except asyncio.TimeoutError:
                print(f"[TIMEOUT] Таймаут для {topic} L{level} S{step} (попытка {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
                
            except Exception as e:
                print(f"[ERROR] Ошибка для {topic} L{level} S{step}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
        
        return None


async def save_task(task_data: Dict, output_file: str):
    """
    Сохраняет задачу в JSONL файл (промежуточное сохранение)
    
    Args:
        task_data: Данные задачи
        output_file: Путь к файлу
    """
    try:
        # Открываем в режиме append, сохраняем с ensure_ascii=False для русского языка
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"[ERROR] Ошибка сохранения задачи: {e}")


async def generate_all_tasks():
    """
    Главная функция: генерирует все задачи асинхронно
    """
    print(f">> Запуск генерации олимпиадных задач для 5 класса")
    print(f">> Темы: {len(TOPICS_5)}")
    print(f">> Уровни: {len(LEVELS)}")
    print(f">> Задач на уровень: {TASKS_PER_LEVEL}")
    print(f">> ВСЕГО задач: {len(TOPICS_5) * len(LEVELS) * TASKS_PER_LEVEL}")
    print(f">> Одновременных запросов: {MAX_CONCURRENT}")
    print(f">> Файл сохранения: {OUTPUT_FILE}")
    print("-" * 60)
    
    # Очистка файла если он существует
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f">> Удален старый файл {OUTPUT_FILE}")
    
    # Создаем список всех задач для генерации
    tasks_to_generate = []
    for topic in TOPICS_5:
        for level in LEVELS:
            for step in range(1, TASKS_PER_LEVEL + 1):
                tasks_to_generate.append((topic, level, step))
    
    print(f">> Подготовлено {len(tasks_to_generate)} задач к генерации\n")
    
    # Семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    # Создаем aiohttp сессию
    async with aiohttp.ClientSession() as session:
        # Создаем корутины для всех задач
        coroutines = []
        for topic, level, step in tasks_to_generate:
            coro = generate_task(session, topic, level, step, semaphore)
            coroutines.append(coro)
        
        # Запускаем все корутины и собираем результаты
        results = await asyncio.gather(*coroutines)
        
        # Сохраняем успешные результаты
        successful = 0
        failed = 0
        
        for task_data in results:
            if task_data is not None:
                await save_task(task_data, OUTPUT_FILE)
                successful += 1
            else:
                failed += 1
        
        print("\n" + "=" * 60)
        print(f"[SUCCESS] Успешно сгенерировано: {successful}")
        print(f"[FAILED] Ошибок: {failed}")
        print(f"[SAVED] Результаты сохранены в: {OUTPUT_FILE}")
        print("=" * 60)


def show_sample_task():
    """
    Показывает пример задачи 7-го уровня из сгенерированного файла
    """
    if not os.path.exists(OUTPUT_FILE):
        print(f"[ERROR] Файл {OUTPUT_FILE} не найден!")
        return
    
    print("\n" + "=" * 60)
    print(">> ПРИМЕР ЗАДАЧИ 7-ГО УРОВНЯ:")
    print("=" * 60)
    
    level_7_tasks = []
    
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            task = json.loads(line)
            if task.get("level") == 7:
                level_7_tasks.append(task)
    
    if not level_7_tasks:
        print("[ERROR] Задачи 7-го уровня не найдены!")
        return
    
    # Показываем первую задачу 7-го уровня
    task = level_7_tasks[0]
    
    print(f"\n>> Тема: {task['topic']}")
    print(f">> Уровень: {task['level']}")
    print(f">> Шаг: {task['step']}")
    print(f"\n>> ВОПРОС:\n{task['question']}")
    print(f"\n>> ОТВЕТ:\n{task['answer']}")
    print(f"\n>> ОБЪЯСНЕНИЕ:\n{task['explanation']}")
    print("\n" + "=" * 60)
    
    # Статистика по темам
    print("\n>> СТАТИСТИКА ПО ТЕМАМ:")
    topic_counts = {}
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            task = json.loads(line)
            topic = task.get('topic', 'Unknown')
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    for topic, count in sorted(topic_counts.items()):
        print(f"  - {topic}: {count} задач")
    
    print("=" * 60)


async def main():
    """Точка входа"""
    start_time = datetime.now()
    
    await generate_all_tasks()
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n>> Время выполнения: {duration:.2f} секунд")
    
    # Показываем пример задачи
    show_sample_task()


if __name__ == "__main__":
    asyncio.run(main())
