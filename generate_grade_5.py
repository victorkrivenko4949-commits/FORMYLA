#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор олимпиадных задач для 5 класса
Создает базу данных адаптивного тестирования с идеальным контролем качества
"""

import json
import os
import time
from typing import Dict, List, Any
from dotenv import load_dotenv
import requests

# Загружаем переменные окружения
load_dotenv()

# Олимпиадный syllabus для 5 класса
TOPICS_5 = [
    "Логика (рыцари и лжецы, логические таблицы)",
    "Принцип Дирихле",
    "Числовые ребусы и крипторифмы",
    "Делимость, остатки и последняя цифра",
    "Инварианты, четность и чередование",
    "Графы (знакомства, турниры, маршруты)",
    "Комбинаторика (правила суммы/произведения, деревья)",
    "Геометрия на клетчатой бумаге и разрезания",
    "Взвешивания, переливания и алгоритмы",
    "Текстовые задачи (движение, совместная работа, обратный ход)"
]

# Количество задач на каждый уровень сложности
TASKS_PER_LEVEL = 2
LEVELS = list(range(1, 8))  # Уровни от 1 до 7

# API конфигурация
API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"

def get_system_prompt(topic: str, level: int) -> str:
    """
    Формирует идеальный системный промпт для генерации задачи
    """
    return f"""Ты — выдающийся составитель задач для Всероссийской олимпиады школьников по математике.
Твоя задача: придумать ОДНУ оригинальную задачу для 5 класса.
Тема задачи: {topic}.
Сложность: {level} из 7.

ШКАЛА СЛОЖНОСТИ СТРОГО ТАКОВА:
- Уровень 1: Школьная программа с небольшим логическим подвохом. Решается в 1-2 действия.
- Уровень 2: Школьный этап ВсОШ. Требует знания базовых олимпиадных идей.
- Уровень 3: Муниципальный этап ВсОШ. Требует построения математической модели или графа.
- Уровень 4: Сложный Муниципальный этап. Комбинация двух олимпиадных идей (например, четность + графы).
- Уровень 5: Математический праздник (МГУ). Задачи, требующие метода "Оценка + Пример" или сложных раскрасок.
- Уровень 6: Региональный этап олимпиады Эйлера. Глубокая логика, неочевидные инварианты.
- Уровень 7: Заключительный этап ВсОШ. Гениальные, нестандартные идеи. Многоходовые доказательства. Вызов даже для преподавателей.

ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ:
1. Пиши СТРОГО на русском языке.
2. ВСЕ числа, формулы, переменные, дроби должны быть в формате LaTeX (например, $x^2$, $\\frac{{1}}{{2}}$, $5$).
3. Поле "answer" должно содержать ТОЛЬКО краткий ответ (одно число, слово или формулу, без текста "Ответ:").
4. В "explanation" дай безупречное, пошаговое математическое доказательство.

Выведи результат строго в формате JSON (без маркдаун-оберток, только сам JSON):
{{
  "question": "Текст задачи...",
  "answer": "Ответ",
  "explanation": "Пошаговое решение..."
}}"""

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
            {"role": "user", "content": "Сгенерируй задачу согласно требованиям."}
        ],
        "temperature": 0.9,
        "max_tokens": 2000
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
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
            
            # Парсим JSON
            task_json = json.loads(content)
            
            # Валидация обязательных полей
            if not all(key in task_json for key in ["question", "answer", "explanation"]):
                raise ValueError("Отсутствуют обязательные поля в ответе LLM")
            
            # Проверка на пустые значения
            if not task_json["question"] or not task_json["answer"] or not task_json["explanation"]:
                raise ValueError("Одно из полей пустое")
            
            return task_json
            
        except Exception as e:
            print(f"  ⚠️  Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Пауза перед повторной попыткой
            else:
                raise Exception(f"Не удалось сгенерировать задачу после {max_retries} попыток")

def generate_task(topic: str, level: int, step: int) -> Dict[str, Any]:
    """
    Генерирует одну задачу с жестким контролем параметров
    """
    print(f"  🔄 Генерация: Тема='{topic}', Уровень={level}, Шаг={step}")
    
    # Получаем промпт
    system_prompt = get_system_prompt(topic, level)
    
    # Вызываем LLM
    ai_response = call_llm(system_prompt)
    
    # КРИТИЧНО: Python-скрипт сам определяет grade, topic, level, step
    # ИИ НЕ ДОЛЖЕН их угадывать!
    task_data = {
        "grade": 5,
        "topic": topic,  # СТРОГО из цикла Python
        "level": level,
        "step": step,
        "question": ai_response["question"],
        "answer": ai_response["answer"],
        "explanation": ai_response["explanation"]
    }
    
    print(f"  ✅ Задача сгенерирована успешно")
    return task_data

def generate_all_tasks() -> List[Dict[str, Any]]:
    """
    Генерирует все задачи для 5 класса
    10 тем × 7 уровней × 2 задачи = 140 задач
    """
    all_tasks = []
    total_tasks = len(TOPICS_5) * len(LEVELS) * TASKS_PER_LEVEL
    current_task = 0
    
    print(f"\n{'='*80}")
    print(f"🚀 НАЧАЛО ГЕНЕРАЦИИ БАЗЫ ДАННЫХ ДЛЯ 5 КЛАССА")
    print(f"{'='*80}")
    print(f"📊 Всего задач к генерации: {total_tasks}")
    print(f"📚 Тем: {len(TOPICS_5)}")
    print(f"📈 Уровней сложности: {len(LEVELS)}")
    print(f"🔢 Задач на уровень: {TASKS_PER_LEVEL}")
    print(f"{'='*80}\n")
    
    for topic_idx, topic in enumerate(TOPICS_5, 1):
        print(f"\n{'─'*80}")
        print(f"📖 ТЕМА {topic_idx}/{len(TOPICS_5)}: {topic}")
        print(f"{'─'*80}")
        
        for level in LEVELS:
            print(f"\n  📊 Уровень {level}/7:")
            
            for step in range(1, TASKS_PER_LEVEL + 1):
                current_task += 1
                try:
                    task = generate_task(topic, level, step)
                    all_tasks.append(task)
                    
                    progress = (current_task / total_tasks) * 100
                    print(f"  ✨ Прогресс: {current_task}/{total_tasks} ({progress:.1f}%)")
                    
                    # Небольшая пауза между запросами
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"  ❌ ОШИБКА при генерации задачи: {e}")
                    print(f"     Тема: {topic}, Уровень: {level}, Шаг: {step}")
                    # Продолжаем генерацию несмотря на ошибку
                    continue
    
    print(f"\n{'='*80}")
    print(f"🎉 ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"✅ Успешно сгенерировано задач: {len(all_tasks)}/{total_tasks}")
    print(f"{'='*80}\n")
    
    return all_tasks

def save_database(tasks: List[Dict[str, Any]], filename: str = "adaptive_grade_5.json"):
    """
    Сохраняет базу данных с правильной кодировкой UTF-8
    """
    print(f"💾 Сохранение базы данных в файл: {filename}")
    
    # КРИТИЧНО: ensure_ascii=False для сохранения русского языка!
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=4)
    
    print(f"✅ База данных успешно сохранена!")
    print(f"📁 Файл: {filename}")
    print(f"📊 Задач в базе: {len(tasks)}")

def show_sample_task(tasks: List[Dict[str, Any]]):
    """
    Показывает случайную задачу 7-го уровня для проверки качества
    """
    import random
    
    # Фильтруем задачи 7-го уровня
    level_7_tasks = [t for t in tasks if t["level"] == 7]
    
    if not level_7_tasks:
        print("⚠️  Задачи 7-го уровня не найдены")
        return
    
    # Выбираем случайную задачу
    sample = random.choice(level_7_tasks)
    
    print(f"\n{'='*80}")
    print(f"🎯 ПРИМЕР ЗАДАЧИ 7-ГО УРОВНЯ (МАКСИМАЛЬНАЯ СЛОЖНОСТЬ)")
    print(f"{'='*80}")
    print(f"📚 Тема: {sample['topic']}")
    print(f"📊 Уровень: {sample['level']}")
    print(f"🔢 Шаг: {sample['step']}")
    print(f"\n❓ ВОПРОС:")
    print(f"{sample['question']}")
    print(f"\n✅ ОТВЕТ:")
    print(f"{sample['answer']}")
    print(f"\n📝 ОБЪЯСНЕНИЕ:")
    print(f"{sample['explanation']}")
    print(f"{'='*80}\n")

def main():
    """
    Главная функция запуска генерации
    """
    # Проверка API ключа
    if not API_KEY:
        print("❌ ОШИБКА: Не найден DEEPSEEK_API_KEY в .env файле!")
        print("Создайте файл .env и добавьте строку:")
        print("DEEPSEEK_API_KEY=your_api_key_here")
        return
    
    try:
        # Генерируем все задачи
        tasks = generate_all_tasks()
        
        if not tasks:
            print("❌ Не удалось сгенерировать ни одной задачи!")
            return
        
        # Сохраняем базу данных
        save_database(tasks)
        
        # Показываем пример задачи 7-го уровня
        show_sample_task(tasks)
        
        print("\n🎊 ВСЕ ГОТОВО! База данных для 5 класса создана успешно!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Генерация прервана пользователем")
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
