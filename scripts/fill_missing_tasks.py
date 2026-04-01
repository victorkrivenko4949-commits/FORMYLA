# -*- coding: utf-8 -*-
"""
Автоматическое заполнение недостающих задач через DeepSeek API
Читает data/missing_tasks.json и генерирует задачи для каждой неполной ячейки
"""
import sys
import os
import json
import codecs
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Загружаем переменные окружения из .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv не установлен, используем системные переменные окружения")

try:
    from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
except ImportError:
    print("❌ Ошибка: не найден модуль ai.deepseek_client")
    print("Убедитесь, что файл ai/deepseek_client.py существует")
    sys.exit(1)

from problems import PROBLEMS_DB

# Настройки
TEST_MODE = False  # Если True, обрабатываем только первые 5 ячеек
DELAY_BETWEEN_REQUESTS = 2  # секунды между запросами
OUTPUT_FILE = "data/generated_missing_tasks.jsonl"

# Маппинг названий разделов и подтем на русский для промпта
SUBJECT_NAMES_RU = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Рыцари и лжецы"
}

SUBTOPIC_NAMES_RU = {
    "equations": "Уравнения и системы",
    "inequalities": "Неравенства и оценки",
    "text_problems": "Текстовые задачи",
    "basics": "Углы, отрезки и многоугольники",
    "triangles": "Треугольники",
    "circles": "Окружности",
    "dirichlet_and_graphs": "Графы и Принцип Дирихле",
    "games": "Игры и стратегии",
    "divisibility": "Делимость и остатки",
    "primes_and_equations": "Простые числа и диофантовы уравнения",
    "movement_all": "Все задачи на движение",
    "logic_all": "Рыцари, лжецы и логика"
}

def get_next_id():
    """Получить следующий свободный ID для задачи"""
    if not PROBLEMS_DB:
        return 1
    return max(p.get('id', 0) for p in PROBLEMS_DB) + 1

def generate_tasks_for_cell(client, cell_info, next_id):
    """
    Генерирует задачи для одной ячейки
    
    Args:
        client: DeepSeekClient instance
        cell_info: словарь с информацией о ячейке
        next_id: следующий свободный ID
        
    Returns:
        list: список сгенерированных задач
    """
    subject = cell_info['subject']
    subtopic = cell_info['subtopic']
    grade = cell_info['grade']
    level = cell_info['level']
    needed = cell_info['needed']
    
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)
    subtopic_ru = SUBTOPIC_NAMES_RU.get(subtopic, cell_info.get('subtopic_title', subtopic))
    
    system_prompt = f"""Ты — эксперт по составлению олимпиадных задач по математике для школьников.
Твоя задача — создать ровно {needed} уникальных, интересных задач.

Параметры:
- Раздел: {subject_ru}
- Тема: {subtopic_ru}
- Класс: {grade}
- Уровень сложности: {level} из 10

Требования:
1. Задачи должны быть олимпиадного уровня, не банальные школьные примеры
2. Каждая задача должна быть уникальной и интересной
3. Сложность должна соответствовать указанному уровню (1=легко, 10=очень сложно)
4. Решение должно быть подробным и понятным (не более 500 символов)

Верни ответ СТРОГО в виде валидного JSON-массива из {needed} элементов.
Каждый элемент должен иметь ключи:
- "title": краткое название задачи (2-5 слов)
- "text": полное условие задачи (не более 300 символов)
- "answer": краткий ответ (число, выражение или короткая фраза)
- "solution": подробное пошаговое решение (не более 500 символов)

НЕ добавляй markdown форматирование (```json), только чистый JSON-массив."""

    user_prompt = f"Сгенерируй {needed} задач по теме '{subtopic_ru}' для {grade} класса, уровень сложности {level}/10."
    
    try:
        print(f"  🤖 Запрос к DeepSeek API...", flush=True)
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.8,  # Больше креативности
            max_tokens=3000
        )
        
        # Очистка ответа от возможного markdown
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        # Парсинг JSON
        tasks_data = json.loads(response)
        
        if not isinstance(tasks_data, list):
            raise ValueError("Ответ API не является массивом")
        
        # Добавляем метаданные к каждой задаче
        generated_tasks = []
        for i, task in enumerate(tasks_data):
            task_obj = {
                "id": next_id + i,
                "subject": subject,
                "subtopic": subtopic,
                "grade": grade,
                "difficulty": level,
                "title": task.get("title", f"Задача {next_id + i}"),
                "text": task.get("text", ""),
                "answer": task.get("answer", ""),
                "solution": task.get("solution", ""),
                "source": "DeepSeek",
                "source_dataset": "generated",
                "generated_at": datetime.utcnow().isoformat()
            }
            generated_tasks.append(task_obj)
        
        print(f"  ✅ Сгенерировано {len(generated_tasks)} задач")
        return generated_tasks
        
    except json.JSONDecodeError as e:
        print(f"  ❌ Ошибка парсинга JSON: {e}")
        print(f"  Ответ API: {response[:200]}...")
        return []
    except DeepSeekAPIError as e:
        print(f"  ❌ Ошибка API: {e}")
        return []
    except Exception as e:
        print(f"  ❌ Неожиданная ошибка: {e}")
        return []

def main():
    print("="*70)
    print("Автоматическое заполнение недостающих задач")
    print("="*70)
    
    # Проверяем наличие файла с дефицитом
    if not os.path.exists("data/missing_tasks.json"):
        print("❌ Файл data/missing_tasks.json не найден!")
        print("Сначала запустите scripts/audit_database.py")
        sys.exit(1)
    
    # Читаем дефицит
    with open("data/missing_tasks.json", 'r', encoding='utf-8') as f:
        audit_data = json.load(f)
    
    missing_tasks = audit_data.get('missing_tasks', [])
    
    if not missing_tasks:
        print("✅ Все ячейки заполнены! Недостающих задач нет.")
        sys.exit(0)
    
    # Тестовый режим - только первые 5 ячеек
    if TEST_MODE:
        print(f"\n⚠️  ТЕСТОВЫЙ РЕЖИМ: обрабатываем только первые 5 ячеек")
        missing_tasks = missing_tasks[:5]
    
    print(f"\n📋 Всего ячеек к обработке: {len(missing_tasks)}")
    total_tasks_to_generate = sum(cell['needed'] for cell in missing_tasks)
    print(f"📝 Всего задач к генерации: {total_tasks_to_generate}")
    
    # Инициализируем клиент DeepSeek
    try:
        client = DeepSeekClient()
        print("✅ DeepSeek клиент инициализирован")
    except ValueError as e:
        print(f"❌ Ошибка инициализации: {e}")
        print("Убедитесь, что переменная окружения DEEPSEEK_API_KEY установлена")
        sys.exit(1)
    
    # Получаем следующий свободный ID
    next_id = get_next_id()
    print(f"🆔 Начальный ID для новых задач: {next_id}")
    
    # Создаем/открываем файл для записи
    os.makedirs("data", exist_ok=True)
    
    # Счетчики
    total_generated = 0
    total_failed = 0
    
    print("\n" + "="*70)
    print("Начинаем генерацию...")
    print("="*70)
    
    # Обрабатываем каждую ячейку
    for idx, cell in enumerate(missing_tasks, 1):
        print(f"\n[{idx}/{len(missing_tasks)}] {cell['subject_title']} → {cell['subtopic_title']}")
        print(f"  Класс: {cell['grade']}, Уровень: {cell['level']}")
        print(f"  Нужно: {cell['needed']} задач")
        
        # Генерируем задачи
        generated = generate_tasks_for_cell(client, cell, next_id)
        
        if generated:
            # Сохраняем в JSONL
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                for task in generated:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
            
            total_generated += len(generated)
            next_id += len(generated)
            print(f"  💾 Сохранено в {OUTPUT_FILE}")
        else:
            total_failed += cell['needed']
            print(f"  ⚠️  Не удалось сгенерировать задачи для этой ячейки")
        
        # Задержка между запросами
        if idx < len(missing_tasks):
            print(f"  ⏳ Ожидание {DELAY_BETWEEN_REQUESTS} сек...")
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    # Итоговая статистика
    print("\n" + "="*70)
    print("✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
    print("="*70)
    print(f"\n📊 Статистика:")
    print(f"  Обработано ячеек: {len(missing_tasks)}")
    print(f"  Успешно сгенерировано задач: {total_generated}")
    print(f"  Не удалось сгенерировать: {total_failed}")
    print(f"\n💾 Результаты сохранены в: {OUTPUT_FILE}")
    
    if TEST_MODE:
        print(f"\n⚠️  Это был тестовый прогон (5 ячеек)")
        print(f"Для полной генерации установите TEST_MODE = False в скрипте")
        print(f"Осталось обработать: {len(audit_data['missing_tasks']) - 5} ячеек")

if __name__ == "__main__":
    main()
