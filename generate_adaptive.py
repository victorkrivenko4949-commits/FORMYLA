"""
Генератор задач для Адаптивного теста FORMYLA
Создает 300 уникальных задач (25 тем × 12 задач разной сложности)
"""

import os
import sys
import json
import time
from dotenv import load_dotenv

# Добавляем путь к модулю ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai.deepseek_client import DeepSeekClient

load_dotenv()

# Матрица из 25 тем для Адаптивного теста (5 класс)
ADAPTIVE_TOPICS = [
    # Блок 1: Арифметика и Текстовые задачи
    "Вычисления (вынос за скобки, группировка)",
    "Движение (навстречу, вдогонку)",
    "Совместная работа (трубы, покраска)",
    "Возраст (отец старше сына...)",
    "Метод обратного хода (раскрутить с конца)",
    
    # Блок 2: Логика и Алгоритмы
    "Рыцари и Лжецы (кто сказал правду)",
    "Переправы (волк, коза, капуста)",
    "Переливания (получить объем двумя кувшинами)",
    "Взвешивания на чашечных весах (найти фальшивую монету)",
    "Календарь и время (дни недели, сдвиги)",
    
    # Блок 3: Теория чисел
    "Четность / Нечетность (инварианты)",
    "Признаки делимости (на 3, 5, 9, 4)",
    "Деление с остатком (периодичность)",
    "Последняя цифра большой степени",
    "Числовые ребусы (восстановить цифры)",
    
    # Блок 4: Аналитическая Геометрия
    "Периметры составных фигур",
    "Площади (аналитическое вычисление)",
    "Замощения (покрыть доминошками)",
    "Углы на циферблате часов",
    "Кубики (видимые грани, развертки)",
    
    # Блок 5: Комбинаторика
    "Правило умножения (дерево вариантов)",
    "Перестановки и расстановки",
    "Рукопожатия и турниры (подсчет партий)",
    "Принцип Дирихле (кролики и клетки)",
    "Теория Игр (выигрышные стратегии)"
]

# Системный промпт для LLM
SYSTEM_PROMPT = """Ты — генератор задач для умного Адаптивного теста (5 класс). 

ОГРАНИЧЕНИЯ ДЛЯ АДАПТИВНОГО ТЕСТА:
1. ЗАПРЕЩЕНЫ задачи, требующие рисунка в ответе. Только число, текст или логическое уравнение.
2. МАТЕМАТИКА (LaTeX): ВЕСЬ математический текст строго внутри \\( ... \\) (инлайн) или \\[ ... \\] (блоки). 
   - Дроби только \\frac{}{}, корни \\sqrt{}, нижние индексы _{} внутри фигурных скобок.
   - Символы ^ и / без LaTeX запрещены!
3. Имена героев и предметы должны меняться между задачами, чтобы они не были клонами.
4. Уровень сложности от 1 до 7:
   - 1-2: школьная база, простые вычисления
   - 3-4: средний уровень, требует рассуждений
   - 5-6: олимпиадный уровень, нестандартные подходы
   - 7: финал олимпиады, сложная логика

ВЕРНИ ТОЛЬКО ВАЛИДНЫЙ JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА:
{
  "class_level": 5,
  "difficulty_level": <уровень>,
  "topic": "<тема>",
  "task_text": "Условие в идеальном LaTeX",
  "solution": "Полное пошаговое авторское решение",
  "criteria_1_point": "Критерий на 1 балл (частичное решение или только голый ответ)",
  "criteria_2_points": "Критерий на 2 балла (полное обоснованное решение)"
}"""


def generate_task_with_deepseek(topic: str, difficulty: int, client: DeepSeekClient) -> dict:
    """Генерирует одну задачу через DeepSeek API"""
    
    user_prompt = f"""Сгенерируй задачу на тему: "{topic}"
Уровень сложности: {difficulty} (1 - школьная база, 7 - финал олимпиады)

Верни ТОЛЬКО валидный JSON без дополнительного текста."""
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response_text = client.generate(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.8,
                max_tokens=2000
            )
            
            response_text = response_text.strip()
            
            # Убираем возможные markdown обертки
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Исправляем проблемы с экранированием LaTeX в JSON
            # Заменяем одинарные обратные слеши на двойные для корректного JSON
            response_text = response_text.replace('\\(', '\\\\(').replace('\\)', '\\\\)')
            response_text = response_text.replace('\\[', '\\\\[').replace('\\]', '\\\\]')
            response_text = response_text.replace('\\frac', '\\\\frac')
            response_text = response_text.replace('\\sqrt', '\\\\sqrt')
            
            task_data = json.loads(response_text)
            return task_data
            
        except json.JSONDecodeError as e:
            if attempt < max_attempts - 1:
                print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Ошибка JSON, повторяю...")
                time.sleep(1)
            else:
                print(f"❌ Ошибка при генерации задачи после {max_attempts} попыток: {e}")
                return None
        except Exception as e:
            print(f"❌ Ошибка при генерации задачи: {e}")
            return None
    
    return None


def test_topic_9():
    """Тестовый запуск для Темы №9 (Взвешивания) - 3 задачи разной сложности"""
    
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"❌ ОШИБКА: {e}")
        print("💡 Убедитесь, что DEEPSEEK_API_KEY указан в .env файле!")
        return
    
    topic = ADAPTIVE_TOPICS[8]  # Тема №9 (индекс 8)
    difficulty_levels = [1, 4, 7]
    
    print("=" * 80)
    print(f"🧪 ТЕСТОВЫЙ ЗАПУСК: Генерация задач для темы №9")
    print(f"📚 Тема: {topic}")
    print(f"🎯 Уровни сложности: {difficulty_levels}")
    print("=" * 80)
    print()
    
    generated_tasks = []
    
    for level in difficulty_levels:
        print(f"⏳ Генерирую задачу уровня {level}...")
        
        task = generate_task_with_deepseek(topic, level, client)
        
        if task:
            generated_tasks.append(task)
            print(f"✅ Задача уровня {level} сгенерирована!")
            print()
            print("─" * 80)
            print(f"📝 ЗАДАЧА (Уровень {level}):")
            print("─" * 80)
            print(f"Условие:\n{task['task_text']}")
            print()
            print(f"Решение:\n{task['solution']}")
            print()
            print(f"Критерий 1 балл:\n{task['criteria_1_point']}")
            print()
            print(f"Критерий 2 балла:\n{task['criteria_2_points']}")
            print("─" * 80)
            print()
            
            # Пауза между запросами
            time.sleep(2)
        else:
            print(f"❌ Не удалось сгенерировать задачу уровня {level}")
    
    # Сохраняем результат в JSON для проверки
    output_file = "test_adaptive_topic9.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print(f"✅ ТЕСТ ЗАВЕРШЕН!")
    print(f"📊 Сгенерировано задач: {len(generated_tasks)}/3")
    print(f"💾 Результат сохранен в: {output_file}")
    print("=" * 80)


def generate_all_tasks():
    """Генерирует все 300 задач для базы Адаптивного теста"""
    
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"❌ ОШИБКА: {e}")
        print("💡 Убедитесь, что DEEPSEEK_API_KEY указан в .env файле!")
        return
    
    print("=" * 80)
    print("🚀 ПОЛНАЯ ГЕНЕРАЦИЯ: 300 задач для Адаптивного теста")
    print("=" * 80)
    print()
    
    all_tasks = []
    total_tasks = 0
    
    # Для каждой из 25 тем генерируем 12 задач разной сложности
    for topic_idx, topic in enumerate(ADAPTIVE_TOPICS, 1):
        print(f"\n📚 Тема {topic_idx}/25: {topic}")
        print("─" * 80)
        
        # Генерируем задачи разных уровней сложности (1-7)
        # Распределение: по 2 задачи на уровни 1,2,3,4,5,6 = 12 задач
        difficulty_distribution = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
        
        for task_num, difficulty in enumerate(difficulty_distribution, 1):
            print(f"  ⏳ Задача {task_num}/12 (уровень {difficulty})...", end=" ")
            
            task = generate_task_with_deepseek(topic, difficulty, client)
            
            if task:
                all_tasks.append(task)
                total_tasks += 1
                print(f"✅")
            else:
                print(f"❌")
            
            # Пауза между запросами (чтобы не превысить rate limit)
            time.sleep(1)
    
    # Сохраняем все задачи
    output_file = "adaptive_tasks_full.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print(f"✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"📊 Сгенерировано задач: {total_tasks}/300")
    print(f"💾 Результат сохранен в: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    # Запускаем тестовый режим для Темы №9
    # test_topic_9()
    
    # Полная генерация всех 300 задач
    generate_all_tasks()
