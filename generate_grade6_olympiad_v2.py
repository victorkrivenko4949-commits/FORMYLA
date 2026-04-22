#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор олимпиадных задач для 6 класса (STRICT MODE v2)
Создает 1050 задач: 10 тем × 7 уровней × 15 задач
Выходной файл: grade6_olympiad_RAW.jsonl

ИСПРАВЛЕНИЯ v2:
- Robust LaTeX-in-JSON parsing с fallback логикой
- Использование $ $ и $$ $$ вместо \( \) для избежания проблем с экранированием
- Автоматическая конвертация $ → \( и $$ → \[ после парсинга
- Счетчик fallback_count для статистики
"""

import json
import os
import sys
import time
import re
from typing import Dict, List, Any
from dotenv import load_dotenv
import requests
from topics_grade6 import GRADE_6_TOPICS, DIFFICULTY_LEVELS, TASKS_PER_CELL

# Настройка кодировки для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Загружаем переменные окружения
load_dotenv()

# API конфигурация
API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"

# Выходной файл
OUTPUT_FILE = "grade6_olympiad_RAW.jsonl"

# Статистика
fallback_count = 0
total_generated = 0


def extract_json(raw_response: str) -> Dict[str, Any]:
    """
    Извлекает и парсит JSON из ответа AI с fallback логикой.
    
    Пробует несколько стратегий:
    1. Прямой json.loads после снятия markdown
    2. Regex-фикс невалидных LaTeX слешей
    3. Поиск JSON блока в тексте
    
    Returns:
        dict: Распарсенный JSON
    
    Raises:
        Exception: Если все стратегии не сработали
    """
    global fallback_count
    
    # Стратегия 1: Снятие markdown обертки
    cleaned = raw_response.strip()
    cleaned = re.sub(r'```json\s*', '', cleaned)
    cleaned = re.sub(r'```\s*$', '', cleaned)
    cleaned = cleaned.strip()
    
    # Попытка 1: Прямой парсинг
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Попытка 2: Фикс LaTeX слешей ($ вместо \)
    # Заменяем одинарные обратные слеши перед спецсимволами на двойные
    try:
        fixed = re.sub(r'(?<!\\)\\([()[\]{}])', r'\\\\\1', cleaned)
        result = json.loads(fixed)
        fallback_count += 1
        return result
    except json.JSONDecodeError:
        pass
    
    # Попытка 3: Поиск JSON блока
    try:
        json_match = re.search(r'\{[^{}]*"question"[^{}]*"answer"[^{}]*"explanation"[^{}]*\}', cleaned, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            fallback_count += 1
            return result
    except:
        pass
    
    # Все стратегии провалились
    raise Exception(f"Failed to parse JSON. Raw response (first 200 chars): {raw_response[:200]}")


def convert_dollar_to_latex(text: str) -> str:
    """
    Конвертирует $ $ и $$ $$ в \( \) и \[ \].
    
    Args:
        text: Текст с формулами в $ $
    
    Returns:
        str: Текст с формулами в \( \) и \[ \]
    """
    # Сначала конвертируем display формулы $$ ... $$
    text = re.sub(r'\$\$(.+?)\$\$', r'\\[ \1 \\]', text, flags=re.DOTALL)
    
    # Затем inline формулы $ ... $
    text = re.sub(r'\$(.+?)\$', r'\\( \1 \\)', text)
    
    return text


def get_system_prompt(topic: Dict[str, Any], level: int) -> str:
    """
    Формирует СТРОГИЙ системный промпт для генерации олимпиадной задачи.
    ИЗМЕНЕНИЕ v2: Просим использовать $ $ вместо \( \) для избежания проблем с JSON.
    """
    topic_name = topic['name']
    topic_desc = topic['description']
    keywords = ', '.join(topic['keywords'])
    
    return f"""Ты — выдающийся составитель задач для Всероссийской олимпиады школьников по математике.
Твоя задача: придумать ОДНУ оригинальную олимпиадную задачу для 6 класса.

ТЕМА ЗАДАЧИ: {topic_name}
ОПИСАНИЕ: {topic_desc}
КЛЮЧЕВЫЕ СЛОВА: {keywords}
СЛОЖНОСТЬ: {level} из 7

ШКАЛА СЛОЖНОСТИ (СТРОГО):
- Уровень 1: Базовая олимпиадная задача. Прямое применение одной идеи. Решается в 2-3 действия.
- Уровень 2: Школьный этап ВсОШ. Требует понимания олимпиадного метода.
- Уровень 3: Муниципальный этап ВсОШ. Комбинация базовых идей или построение модели.
- Уровень 4: Сложный муниципальный этап. Требует нескольких шагов рассуждений.
- Уровень 5: Математический праздник (МГУ). Метод "Оценка + Пример" или сложные раскраски.
- Уровень 6: Региональный этап олимпиады Эйлера. Глубокая логика, неочевидные инварианты.
- Уровень 7: Заключительный этап ВсОШ. Гениальные идеи. Многоходовые доказательства.

КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:

1. **ЯЗЫК**: Пиши СТРОГО на русском языке.

2. **LATEX FORMATTING (УПРОЩЕННЫЙ ДЛЯ JSON)**:
   - Используй ОДИНАРНЫЕ доллары $ ... $ для inline-формул
   - Используй ДВОЙНЫЕ доллары $$ ... $$ для display-формул
   - НЕ используй обратные слеши \( \) \[ \] - они ломают JSON!
   - Примеры ПРАВИЛЬНОГО форматирования:
     * "Найдите $x$, если $x^2 = 16$"
     * "Дробь $\\frac{{1}}{{2}}$ равна половине"
     * "Формула: $$ S = \\pi r^2 $$"
   - ВСЕ числа, переменные, формулы, дроби ОБЯЗАТЕЛЬНО в LaTeX с $!

3. **ПОЛЕ "answer" (СТРОГИЙ ФОРМАТ)**:
   - Содержит ТОЛЬКО краткий ответ
   - БЕЗ слова "Ответ:", БЕЗ пояснений
   - Примеры: "42", "$\\frac{{3}}{{4}}$", "невозможно"

4. **ЛОГИЧЕСКАЯ КОРРЕКТНОСТЬ**:
   - В числовых ребусах: разные буквы = разные цифры
   - В задачах на рыцарей/лжецов: НЕТ логических противоречий
   - Условие должно быть ДОСТАТОЧНЫМ для однозначного решения

5. **ПОЛЕ "explanation"**:
   - Безупречное пошаговое математическое доказательство
   - Каждый шаг обоснован
   - Используй $ $ для всех формул

ФОРМАТ ВЫВОДА:
Верни результат СТРОГО в формате JSON (без markdown-оберток):
{{
  "question": "Текст задачи с формулами в $ ... $ или $$ ... $$",
  "answer": "Краткий ответ БЕЗ слова 'Ответ:'",
  "explanation": "Пошаговое решение с формулами в $ $"
}}

ВАЖНО: Задача должна быть ОРИГИНАЛЬНОЙ!"""


def call_llm(system_prompt: str, max_retries: int = 3) -> Dict[str, str]:
    """
    Вызывает LLM API для генерации задачи с повторными попытками.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Сгенерируй олимпиадную задачу согласно всем требованиям. Верни только JSON."}
        ],
        "temperature": 0.95,
        "max_tokens": 2500
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            
            # Используем улучшенный парсер JSON
            task_json = extract_json(content)
            
            # Валидация обязательных полей
            if not all(key in task_json for key in ["question", "answer", "explanation"]):
                raise ValueError("Отсутствуют обязательные поля в ответе LLM")
            
            # Проверка на пустые значения
            if not task_json["question"] or not task_json["answer"] or not task_json["explanation"]:
                raise ValueError("Одно из полей пустое")
            
            # Конвертируем $ $ в \( \) и $$ $$ в \[ \]
            task_json["question"] = convert_dollar_to_latex(task_json["question"])
            task_json["answer"] = convert_dollar_to_latex(task_json["answer"])
            task_json["explanation"] = convert_dollar_to_latex(task_json["explanation"])
            
            # STRICT MODE: Проверка на запрещенные паттерны в ответе
            answer = task_json["answer"]
            if answer.lower().startswith("ответ:") or answer.lower().startswith("ответ —"):
                task_json["answer"] = answer.split(":", 1)[-1].strip() if ":" in answer else answer.split("—", 1)[-1].strip()
            
            return task_json
            
        except Exception as e:
            print(f"  [WARN] Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                raise Exception(f"Не удалось сгенерировать задачу после {max_retries} попыток: {e}")


def generate_task(topic: Dict[str, Any], level: int, task_num: int) -> Dict[str, Any]:
    """
    Генерирует одну олимпиадную задачу.
    """
    global total_generated
    
    topic_name = topic['name']
    print(f"  [>] Генерация: Тема='{topic_name}', Уровень={level}, Задача={task_num}")
    
    system_prompt = get_system_prompt(topic, level)
    ai_response = call_llm(system_prompt)
    
    task_data = {
        "grade": 6,
        "topic": topic_name,
        "level": level,
        "task_number": task_num,
        "question": ai_response["question"],
        "answer": ai_response["answer"],
        "explanation": ai_response["explanation"],
        "keywords": topic['keywords']
    }
    
    total_generated += 1
    print(f"  [OK] Задача сгенерирована успешно")
    return task_data


def save_task_to_jsonl(task: Dict[str, Any], filename: str):
    """
    Добавляет задачу в JSONL файл.
    """
    with open(filename, "a", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False)
        f.write("\n")


def generate_all_tasks():
    """
    Генерирует все 1050 задач для 6 класса.
    """
    global fallback_count, total_generated
    
    total_tasks = len(GRADE_6_TOPICS) * len(DIFFICULTY_LEVELS) * TASKS_PER_CELL
    current_task = 0
    
    print(f"\n{'='*80}")
    print(f">>> НАЧАЛО ГЕНЕРАЦИИ ОЛИМПИАДНЫХ ЗАДАЧ ДЛЯ 6 КЛАССА (STRICT MODE v2)")
    print(f"{'='*80}")
    print(f"[*] Всего задач к генерации: {total_tasks}")
    print(f"[*] Тем: {len(GRADE_6_TOPICS)}")
    print(f"[*] Уровней сложности: {len(DIFFICULTY_LEVELS)}")
    print(f"[*] Задач на ячейку: {TASKS_PER_CELL}")
    print(f"[*] Выходной файл: {OUTPUT_FILE}")
    print(f"[*] НОВОЕ: Robust JSON parsing + $ $ LaTeX")
    print(f"{'='*80}\n")
    
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"[DEL] Старый файл {OUTPUT_FILE} удален\n")
    
    start_time = time.time()
    successful_tasks = 0
    failed_tasks = 0
    
    for topic_idx, topic in enumerate(GRADE_6_TOPICS, 1):
        print(f"\n{'-'*80}")
        print(f"[ТЕМА {topic_idx}/{len(GRADE_6_TOPICS)}] {topic['name']}")
        print(f"{'-'*80}")
        
        for level in DIFFICULTY_LEVELS:
            print(f"\n  [Уровень {level}/7]:")
            
            for task_num in range(1, TASKS_PER_CELL + 1):
                current_task += 1
                try:
                    task = generate_task(topic, level, task_num)
                    save_task_to_jsonl(task, OUTPUT_FILE)
                    successful_tasks += 1
                    
                    progress = (current_task / total_tasks) * 100
                    elapsed = time.time() - start_time
                    avg_time = elapsed / current_task
                    eta = avg_time * (total_tasks - current_task)
                    
                    print(f"  [ПРОГРЕСС] {current_task}/{total_tasks} ({progress:.1f}%) | "
                          f"ETA: {eta/60:.1f} мин | Успешно: {successful_tasks} | Fallback: {fallback_count}")
                    
                    time.sleep(1.5)
                    
                except Exception as e:
                    failed_tasks += 1
                    print(f"  [ERROR] ОШИБКА при генерации задачи: {e}")
                    print(f"          Тема: {topic['name']}, Уровень: {level}, Задача: {task_num}")
                    continue
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*80}")
    print(f">>> ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"[OK] Успешно сгенерировано задач: {successful_tasks}/{total_tasks}")
    print(f"[FAIL] Ошибок генерации: {failed_tasks}")
    print(f"[FALLBACK] Задач с regex-фиксом: {fallback_count}/{successful_tasks} ({fallback_count/max(successful_tasks,1)*100:.1f}%)")
    print(f"[TIME] Общее время: {total_time/60:.1f} минут")
    print(f"[SPEED] Средняя скорость: {total_time/successful_tasks:.1f} сек/задача")
    print(f"[FILE] Файл сохранен: {OUTPUT_FILE}")
    print(f"{'='*80}\n")


def show_sample_tasks():
    """
    Показывает примеры сгенерированных задач.
    """
    if not os.path.exists(OUTPUT_FILE):
        print("[WARN] Файл с задачами не найден")
        return
    
    print(f"\n{'='*80}")
    print(f">>> ПРИМЕРЫ СГЕНЕРИРОВАННЫХ ЗАДАЧ")
    print(f"{'='*80}\n")
    
    tasks = []
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            tasks.append(json.loads(line))
    
    for level in [1, 3, 5, 7]:
        level_tasks = [t for t in tasks if t["level"] == level]
        if level_tasks:
            sample = level_tasks[0]
            print(f"{'-'*80}")
            print(f"[УРОВЕНЬ {level}/7] Тема: {sample['topic']}")
            print(f"{'-'*80}")
            print(f"[?] ВОПРОС:\n{sample['question'][:200]}...\n")
            print(f"[!] ОТВЕТ: {sample['answer']}\n")


def main():
    """
    Главная функция запуска генерации.
    """
    if not API_KEY:
        print("[ERROR] ОШИБКА: Не найден DEEPSEEK_API_KEY в .env файле!")
        return
    
    try:
        generate_all_tasks()
        show_sample_tasks()
        
        print("\n>>> ВСЕ ГОТОВО! Олимпиадная база для 6 класса создана!")
        print(f"[NEXT] Следующий шаг: запустите clean_grade6.py для очистки")
        
    except KeyboardInterrupt:
        print("\n\n[STOP] Генерация прервана пользователем")
        print(f"[SAVE] Частичные результаты сохранены в {OUTPUT_FILE}")
        print(f"[STATS] Сгенерировано: {total_generated}, Fallback: {fallback_count}")
    except Exception as e:
        print(f"\n[CRITICAL] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
