#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для генерации базы адаптивных задач через DeepSeek API
Генерирует 175 задач (25 тем × 7 уровней сложности) для 7 класса
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Матрица тем для 7 класса (25 тем)
TEST_MATRIX_7_CLASS = {
    1: "Вычисления с дробями и десятичными числами",
    2: "Свойства степеней",
    3: "Линейные уравнения",
    4: "Алгебраические тождества",
    5: "Задачи на движение",
    6: "Совместная работа",
    7: "Проценты и смеси",
    8: "Сюжетные задачи на составление уравнений",
    9: "Признаки делимости",
    10: "Деление с остатком",
    11: "НОД и НОК",
    12: "Последняя цифра степени",
    13: "Диофантовы уравнения",
    14: "Рыцари и лжецы",
    15: "Взвешивания и переливания",
    16: "Игры из двух лиц",
    17: "Принцип Дирихле",
    18: "Правила умножения и сложения",
    19: "Перестановки и размещения",
    20: "Графы (основы)",
    21: "Раскраски",
    22: "Углы и параллельные прямые",
    23: "Разрезания и замощения",
    24: "Периметры и площади",
    25: "Признаки равенства треугольников"
}

# Настройки API
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
USE_OPENROUTER = os.environ.get('USE_OPENROUTER', 'false').lower() in ['true', '1', 't', 'yes']

if USE_OPENROUTER:
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "deepseek/deepseek-chat"
else:
    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

# Путь к файлу с данными
DATA_DIR = Path(__file__).parent.parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = DATA_DIR / 'adaptive_7.json'


def load_existing_tasks():
    """Загружает существующие задачи из файла"""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Ошибка при загрузке существующих задач: {e}")
            return {}
    return {}


def save_tasks(tasks):
    """Сохраняет задачи в файл"""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    print(f"💾 Сохранено в {OUTPUT_FILE}")


def generate_task(step, level, topic):
    """Генерирует одну задачу через DeepSeek API"""
    
    # Описание уровней сложности
    difficulty_desc = {
        1: "чуть сложнее обычной школьной программы",
        2: "школьная олимпиада",
        3: "муниципальная олимпиада",
        4: "региональная олимпиада (начальный уровень)",
        5: "региональная олимпиада",
        6: "заключительный этап ВсОШ (начальный уровень)",
        7: "финал ВсОШ"
    }
    
    prompt = f"""Сгенерируй ОРИГИНАЛЬНУЮ математическую задачу для 7 класса.

Тема: {topic}
Уровень сложности: {level} ({difficulty_desc.get(level, 'средний')})

СТРОГИЕ ТРЕБОВАНИЯ:
1. Ответ должен быть СТРОГИМ ЧИСЛОМ (без единиц измерения, например: '42' или '-5.5' или '0.75')
2. Математика строго в формате LaTeX: \\( ... \\) для строчных формул и \\[ ... \\] для блочных
3. Задача должна быть ОРИГИНАЛЬНОЙ, не копируй известные задачи
4. Условие должно быть четким и понятным школьнику 7 класса
5. Решение должно быть подробным, с пояснениями каждого шага

ФОРМАТ ОТВЕТА - строго валидный JSON (БЕЗ markdown маркеров ```json):
{{
  "text": "условие задачи с LaTeX формулами",
  "answer": "число",
  "solution": "подробное решение с LaTeX формулами"
}}

ВАЖНО: НЕ оборачивай JSON в markdown блоки!"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,  # Выше для разнообразия задач
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        
        data = response.json()
        content = data['choices'][0]['message']['content'].strip()
        
        # Очищаем от markdown маркеров
        import re
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)
        content = content.strip()
        
        # Парсим JSON
        task_data = json.loads(content)
        
        # Проверяем наличие обязательных полей
        if not all(key in task_data for key in ['text', 'answer', 'solution']):
            raise ValueError("Отсутствуют обязательные поля в ответе API")
        
        return {
            "step": step,
            "level": level,
            "topic": topic,
            "text": task_data['text'],
            "answer": task_data['answer'],
            "solution": task_data['solution']
        }
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка API запроса: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"   Ответ API: {content[:200]}...")
        return None
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return None


def main():
    """Основная функция генерации"""
    
    if not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден в переменных окружения!")
        print("   Создайте файл .env и добавьте: DEEPSEEK_API_KEY=your_key_here")
        return
    
    print("="*60)
    print("🚀 Генератор адаптивных задач для 7 класса")
    print("="*60)
    print(f"📊 Всего будет сгенерировано: 25 тем × 7 уровней = 175 задач")
    print(f"🔑 API: {'OpenRouter' if USE_OPENROUTER else 'DeepSeek'}")
    print(f"💾 Файл: {OUTPUT_FILE}")
    print("="*60)
    
    # Загружаем существующие задачи
    tasks = load_existing_tasks()
    print(f"📂 Загружено существующих задач: {len(tasks)}")
    
    total_tasks = 25 * 7
    generated = 0
    skipped = 0
    failed = 0
    
    # Генерируем задачи
    for step in range(1, 26):  # 25 тем
        topic = TEST_MATRIX_7_CLASS[step]
        print(f"\n📚 Тема {step}/25: {topic}")
        
        for level in range(1, 8):  # 7 уровней
            task_key = f"step_{step}_level_{level}"
            
            # Проверяем, есть ли уже задача
            if task_key in tasks:
                print(f"   ⏭️  Уровень {level}/7: пропущено (уже есть)")
                skipped += 1
                continue
            
            print(f"   🔄 Уровень {level}/7: генерация...", end=' ')
            
            # Генерируем задачу
            task = generate_task(step, level, topic)
            
            if task:
                tasks[task_key] = task
                generated += 1
                print("✅")
                
                # Сохраняем после каждой успешной генерации
                save_tasks(tasks)
            else:
                failed += 1
                print("❌")
            
            # Задержка между запросами
            time.sleep(2)
    
    # Итоговая статистика
    print("\n" + "="*60)
    print("📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"   ✅ Сгенерировано: {generated}")
    print(f"   ⏭️  Пропущено (уже были): {skipped}")
    print(f"   ❌ Ошибок: {failed}")
    print(f"   📦 Всего в базе: {len(tasks)}/{total_tasks}")
    print("="*60)
    
    if len(tasks) == total_tasks:
        print("🎉 ВСЕ ЗАДАЧИ СГЕНЕРИРОВАНЫ!")
    else:
        print(f"⚠️  Осталось сгенерировать: {total_tasks - len(tasks)} задач")
        print("   Запустите скрипт еще раз для повторной попытки")


if __name__ == "__main__":
    main()
