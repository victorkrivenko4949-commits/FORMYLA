#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор олимпиадных задач для 6 класса (STRICT MODE)
Создает 1050 задач: 10 тем × 7 уровней × 15 задач
Выходной файл: grade6_olympiad_RAW.jsonl
"""

import json
import os
import sys
import time
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

def get_system_prompt(topic: Dict[str, Any], level: int) -> str:
    """
    Формирует СТРОГИЙ системный промпт для генерации олимпиадной задачи
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
- Уровень 2: Школьный этап ВсОШ. Требует понимания олимпиадного метода (например, принцип Дирихле).
- Уровень 3: Муниципальный этап ВсОШ. Комбинация базовых идей или построение модели.
- Уровень 4: Сложный муниципальный этап. Требует нескольких шагов рассуждений.
- Уровень 5: Математический праздник (МГУ). Метод "Оценка + Пример" или сложные раскраски.
- Уровень 6: Региональный этап олимпиады Эйлера. Глубокая логика, неочевидные инварианты.
- Уровень 7: Заключительный этап ВсОШ. Гениальные идеи. Многоходовые доказательства. Вызов для преподавателей.

КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:

1. **ЯЗЫК**: Пиши СТРОГО на русском языке.

2. **LATEX FORMATTING (СТРОГИЙ РЕЖИМ)**:
   - Используй ТОЛЬКО \\( ... \\) для inline-формул
   - Используй ТОЛЬКО \\[ ... \\] для display-формул
   - ЗАПРЕЩЕНО использовать одинарные $ или двойные $$
   - Примеры ПРАВИЛЬНОГО форматирования:
     * "Найдите \\( x \\), если \\( x^2 = 16 \\)"
     * "Дробь \\( \\frac{{1}}{{2}} \\) равна половине"
     * "Формула: \\[ S = \\pi r^2 \\]"
   - ВСЕ числа, переменные, формулы, дроби ОБЯЗАТЕЛЬНО в LaTeX!

3. **ПОЛЕ "answer" (СТРОГИЙ ФОРМАТ)**:
   - Содержит ТОЛЬКО краткий ответ
   - БЕЗ слова "Ответ:", БЕЗ пояснений
   - Примеры ПРАВИЛЬНЫХ ответов:
     * "42"
     * "\\( \\frac{{3}}{{4}} \\)"
     * "невозможно"
     * "да"
     * "нет"
   - Примеры НЕПРАВИЛЬНЫХ ответов:
     * "Ответ: 42" ❌
     * "Правильный ответ — 42" ❌
     * "Получается 42" ❌

4. **ЛОГИЧЕСКАЯ КОРРЕКТНОСТЬ**:
   - В числовых ребусах: разные буквы = разные цифры
   - В задачах на рыцарей/лжецов: НЕТ логических противоречий
   - Условие должно быть ДОСТАТОЧНЫМ для однозначного решения
   - Проверь решение дважды перед отправкой!

5. **ПОЛЕ "explanation"**:
   - Безупречное пошаговое математическое доказательство
   - Каждый шаг обоснован
   - Используй LaTeX для всех формул

ФОРМАТ ВЫВОДА:
Верни результат СТРОГО в формате JSON (без markdown-оберток, только чистый JSON):
{{
  "question": "Текст задачи с формулами в \\\\( ... \\\\) или \\\\[ ... \\\\]",
  "answer": "Краткий ответ БЕЗ слова 'Ответ:'",
  "explanation": "Пошаговое решение с формулами в LaTeX"
}}

ВАЖНО: Задача должна быть ОРИГИНАЛЬНОЙ, не копией известных олимпиадных задач!"""

def call_llm(system_prompt: str, max_retries: int = 3) -> Dict[str, str]:
    """
    Вызывает LLM API для генерации задачи с повторными попытками
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
        "temperature": 0.95,  # Высокая креативность для олимпиадных задач
        "max_tokens": 2500
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            
            # Убираем markdown обертки если есть
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Парсим JSON с поддержкой LaTeX (strict=False позволяет неэкранированные символы)
            # Но сначала попробуем стандартный парсинг
            try:
                task_json = json.loads(content)
            except json.JSONDecodeError as e:
                # Если не получилось, пробуем исправить распространенные проблемы с LaTeX
                # Заменяем одинарные обратные слеши на двойные (кроме уже экранированных)
                import re
                # Это сложная эвристика, но для LaTeX в JSON она работает
                content_fixed = content.replace('\\(', '\\\\(').replace('\\)', '\\\\)')
                content_fixed = content_fixed.replace('\\[', '\\\\[').replace('\\]', '\\\\]')
                content_fixed = content_fixed.replace('\\frac', '\\\\frac')
                content_fixed = content_fixed.replace('\\cdot', '\\\\cdot')
                content_fixed = content_fixed.replace('\\times', '\\\\times')
                content_fixed = content_fixed.replace('\\div', '\\\\div')
                content_fixed = content_fixed.replace('\\equiv', '\\\\equiv')
                content_fixed = content_fixed.replace('\\pmod', '\\\\pmod')
                content_fixed = content_fixed.replace('\\text', '\\\\text')
                content_fixed = content_fixed.replace('\\ldots', '\\\\ldots')
                content_fixed = content_fixed.replace('\\dots', '\\\\dots')
                task_json = json.loads(content_fixed)
            
            # Валидация обязательных полей
            if not all(key in task_json for key in ["question", "answer", "explanation"]):
                raise ValueError("Отсутствуют обязательные поля в ответе LLM")
            
            # Проверка на пустые значения
            if not task_json["question"] or not task_json["answer"] or not task_json["explanation"]:
                raise ValueError("Одно из полей пустое")
            
            # STRICT MODE: Проверка на запрещенные паттерны
            answer = task_json["answer"]
            if answer.lower().startswith("ответ:") or answer.lower().startswith("ответ —"):
                # Автоматически чистим ответ
                task_json["answer"] = answer.split(":", 1)[-1].strip() if ":" in answer else answer.split("—", 1)[-1].strip()
            
            return task_json
            
        except Exception as e:
            print(f"  ⚠️  Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)  # Пауза перед повторной попыткой
            else:
                raise Exception(f"Не удалось сгенерировать задачу после {max_retries} попыток: {e}")

def generate_task(topic: Dict[str, Any], level: int, task_num: int) -> Dict[str, Any]:
    """
    Генерирует одну олимпиадную задачу
    """
    topic_name = topic['name']
    print(f"  [>] Генерация: Тема='{topic_name}', Уровень={level}, Задача={task_num}")
    
    # Получаем промпт
    system_prompt = get_system_prompt(topic, level)
    
    # Вызываем LLM
    ai_response = call_llm(system_prompt)
    
    # Формируем структуру задачи
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
    
    print(f"  [OK] Задача сгенерирована успешно")
    return task_data

def save_task_to_jsonl(task: Dict[str, Any], filename: str):
    """
    Добавляет задачу в JSONL файл (каждая задача на новой строке)
    """
    with open(filename, "a", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False)
        f.write("\n")

def generate_all_tasks():
    """
    Генерирует все 1050 задач для 6 класса
    10 тем × 7 уровней × 15 задач = 1050 задач
    """
    total_tasks = len(GRADE_6_TOPICS) * len(DIFFICULTY_LEVELS) * TASKS_PER_CELL
    current_task = 0
    
    print(f"\n{'='*80}")
    print(f">>> НАЧАЛО ГЕНЕРАЦИИ ОЛИМПИАДНЫХ ЗАДАЧ ДЛЯ 6 КЛАССА (STRICT MODE)")
    print(f"{'='*80}")
    print(f"[*] Всего задач к генерации: {total_tasks}")
    print(f"[*] Тем: {len(GRADE_6_TOPICS)}")
    print(f"[*] Уровней сложности: {len(DIFFICULTY_LEVELS)}")
    print(f"[*] Задач на ячейку (тема × уровень): {TASKS_PER_CELL}")
    print(f"[*] Выходной файл: {OUTPUT_FILE}")
    print(f"{'='*80}\n")
    
    # Очищаем выходной файл если он существует
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
                          f"ETA: {eta/60:.1f} мин | Успешно: {successful_tasks}")
                    
                    # Пауза между запросами (чтобы не перегрузить API)
                    time.sleep(1.5)
                    
                except Exception as e:
                    failed_tasks += 1
                    print(f"  [ERROR] ОШИБКА при генерации задачи: {e}")
                    print(f"          Тема: {topic['name']}, Уровень: {level}, Задача: {task_num}")
                    # Продолжаем генерацию несмотря на ошибку
                    continue
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*80}")
    print(f">>> ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"[OK] Успешно сгенерировано задач: {successful_tasks}/{total_tasks}")
    print(f"[FAIL] Ошибок генерации: {failed_tasks}")
    print(f"[TIME] Общее время: {total_time/60:.1f} минут")
    print(f"[SPEED] Средняя скорость: {total_time/successful_tasks:.1f} сек/задача")
    print(f"[FILE] Файл сохранен: {OUTPUT_FILE}")
    print(f"{'='*80}\n")

def show_sample_tasks():
    """
    Показывает примеры сгенерированных задач разных уровней
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
    
    # Показываем по одной задаче каждого уровня
    for level in [1, 3, 5, 7]:
        level_tasks = [t for t in tasks if t["level"] == level]
        if level_tasks:
            sample = level_tasks[0]
            print(f"{'-'*80}")
            print(f"[УРОВЕНЬ {level}/7] Тема: {sample['topic']}")
            print(f"{'-'*80}")
            print(f"[?] ВОПРОС:\n{sample['question']}\n")
            print(f"[!] ОТВЕТ: {sample['answer']}\n")
            print(f"[i] РЕШЕНИЕ:\n{sample['explanation'][:300]}...\n")

def main():
    """
    Главная функция запуска генерации
    """
    # Проверка API ключа
    if not API_KEY:
        print("[ERROR] ОШИБКА: Не найден DEEPSEEK_API_KEY в .env файле!")
        print("Создайте файл .env и добавьте строку:")
        print("DEEPSEEK_API_KEY=your_api_key_here")
        return
    
    try:
        # Генерируем все задачи
        generate_all_tasks()
        
        # Показываем примеры
        show_sample_tasks()
        
        print("\n>>> ВСЕ ГОТОВО! Олимпиадная база для 6 класса создана!")
        print(f"[NEXT] Следующий шаг: запустите mass_math_check.py для валидации задач")
        
    except KeyboardInterrupt:
        print("\n\n[STOP] Генерация прервана пользователем")
        print(f"[SAVE] Частичные результаты сохранены в {OUTPUT_FILE}")
    except Exception as e:
        print(f"\n[CRITICAL] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
