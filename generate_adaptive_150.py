"""
Генератор 150 недостающих задач для Адаптивного теста (5 класс)
Использует Few-Shot Prompting на основе 25 эталонных задач 3-го уровня
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

# Уровни сложности, которые нужно сгенерировать (3-й уровень уже есть в эталонах)
TARGET_LEVELS = [1, 2, 4, 5, 6, 7]


def load_anchor_tasks(filepath: str) -> list:
    """Загружает 25 эталонных задач 3-го уровня из JSON"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ ОШИБКА: Файл {filepath} не найден!")
        print("💡 Убедитесь, что файл с эталонами находится в текущей директории.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ ОШИБКА: Некорректный JSON в файле {filepath}: {e}")
        sys.exit(1)


def create_few_shot_prompt(anchor_task: dict, target_level: int) -> str:
    """Создает промпт для LLM с использованием эталонной задачи (Few-Shot)"""
    
    topic = anchor_task.get('topic', 'Неизвестная тема')
    anchor_text = anchor_task.get('task_text', '')
    anchor_solution = anchor_task.get('solution', '')
    
    level_descriptions = {
        1: "базовая математика 5 класса, простые вычисления",
        2: "простая задача, требует 1-2 шага рассуждений",
        3: "средний уровень (эталон)",
        4: "выше среднего, требует нескольких шагов логики",
        5: "региональная олимпиада, нестандартный подход",
        6: "сложная региональная олимпиада, многошаговое решение",
        7: "финал Всероссийской олимпиады, максимальная сложность"
    }
    
    prompt = f"""Перед тобой эталонная олимпиадная задача 3-го уровня сложности на тему '{topic}':

ЭТАЛОН (Уровень 3):
Условие: {anchor_text}

Решение: {anchor_solution}

═══════════════════════════════════════════════════════════════

Твоя задача: сгенерировать НОВУЮ, похожую по смыслу задачу на эту же тему, но для **Уровня сложности {target_level}** ({level_descriptions[target_level]}).

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Сюжет, имена персонажей и числа ДОЛЖНЫ отличаться от эталона! (Не клонируй текст слепо).
2. Если {target_level} < 3, сделай логику и вычисления ЗНАЧИТЕЛЬНО ПРОЩЕ эталона (меньше шагов, проще числа).
3. Если {target_level} > 3, УСЛОЖНИ логику (добавь параметры, увеличь количество шагов алгоритма, добавь дополнительные условия).
4. ЗАПРЕЩЕНЫ графические ответы (никаких рисунков). Только число или короткий текст.
5. МАТЕМАТИКА (LaTeX): ВЕСЬ математический текст строго внутри \\( ... \\) (инлайн) или \\[ ... \\] (блоки).
   - Дроби только \\frac{{}}{{}}, корни \\sqrt{{}}, нижние индексы _{{}}.
   - Символы ^ и / без LaTeX запрещены!

**КРИТИЧЕСКИ ВАЖНО (МАТЕМАТИЧЕСКАЯ ТОЧНОСТЬ):**
Перед тем как писать JSON, ты ОБЯЗАН решить свою собственную задачу в уме и убедиться, что решение математически строгое и не содержит логических дыр.
Например:
- За 1 взвешивание можно найти фальшивую монету только из 3 монет (не из 4!).
- За 2 взвешивания — из 9 монет.
- За 3 взвешивания — из 27 монет.
Если твоя задача содержит математическую ошибку, ПЕРЕДЕЛАЙ её до корректной!

ВЕРНИ СТРОГО JSON (без лишних слов до и после):
{{
  "class_level": 5,
  "difficulty_level": {target_level},
  "topic": "{topic}",
  "task_text": "Новое математически КОРРЕКТНОЕ условие",
  "solution": "Новое решение БЕЗ ЛОГИЧЕСКИХ ОШИБОК",
  "criteria_1_point": "За что дать 1 балл (арифметическая ошибка или только ответ без обоснования)",
  "criteria_2_points": "За что дать 2 балла (полное обоснованное решение)"
}}"""
    
    return prompt


def generate_task_from_anchor(anchor_task: dict, target_level: int, client: DeepSeekClient) -> dict:
    """Генерирует одну задачу на основе эталона через DeepSeek API"""
    
    user_prompt = create_few_shot_prompt(anchor_task, target_level)
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response_text = client.generate(
                prompt=user_prompt,
                system_prompt="Ты — генератор олимпиадных задач для 5 класса. Строго следуй инструкциям и возвращай только валидный JSON.",
                temperature=0.85,  # Повышенная креативность для разнообразия
                max_tokens=2500
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
            response_text = response_text.replace('\\(', '\\\\(').replace('\\)', '\\\\)')
            response_text = response_text.replace('\\[', '\\\\[').replace('\\]', '\\\\]')
            response_text = response_text.replace('\\frac', '\\\\frac')
            response_text = response_text.replace('\\sqrt', '\\\\sqrt')
            response_text = response_text.replace('\\cdot', '\\\\cdot')
            response_text = response_text.replace('\\times', '\\\\times')
            
            task_data = json.loads(response_text)
            return task_data
            
        except json.JSONDecodeError as e:
            if attempt < max_attempts - 1:
                print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Ошибка JSON, повторяю...")
                time.sleep(2)
            else:
                print(f"❌ Ошибка при генерации задачи после {max_attempts} попыток: {e}")
                print(f"Ответ LLM: {response_text[:200]}...")
                return None
        except Exception as e:
            print(f"❌ Ошибка при генерации задачи: {e}")
            return None
    
    return None


def test_topic_9_generation(anchor_file: str):
    """Тестовый запуск: генерация задач 1-го и 7-го уровня для Темы №9 (Взвешивания)"""
    
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"❌ ОШИБКА: {e}")
        print("💡 Убедитесь, что DEEPSEEK_API_KEY указан в .env файле!")
        return
    
    # Загружаем эталоны
    anchor_tasks = load_anchor_tasks(anchor_file)
    
    # Находим Тему №9 (индекс 8, так как нумерация с 0)
    if len(anchor_tasks) < 9:
        print(f"❌ ОШИБКА: В файле эталонов меньше 9 задач!")
        return
    
    anchor_task = anchor_tasks[8]  # Тема №9 (Взвешивания)
    
    print("=" * 80)
    print(f"🧪 ТЕСТОВЫЙ ЗАПУСК: Генерация задач для Темы №9")
    print(f"📚 Тема: {anchor_task.get('topic', 'Неизвестная тема')}")
    print(f"🎯 Целевые уровни: 1 (базовый) и 7 (финал)")
    print("=" * 80)
    print()
    
    print("📖 ЭТАЛОННАЯ ЗАДАЧА (Уровень 3):")
    print("─" * 80)
    print(f"Условие:\n{anchor_task.get('task_text', 'Нет текста')}")
    print()
    print(f"Решение:\n{anchor_task.get('solution', 'Нет решения')}")
    print("─" * 80)
    print()
    
    generated_tasks = []
    test_levels = [1, 7]
    
    for level in test_levels:
        print(f"⏳ Генерирую задачу уровня {level}...")
        
        task = generate_task_from_anchor(anchor_task, level, client)
        
        if task:
            generated_tasks.append(task)
            print(f"✅ Задача уровня {level} сгенерирована!")
            print()
            print("═" * 80)
            print(f"📝 НОВАЯ ЗАДАЧА (Уровень {level}):")
            print("═" * 80)
            print(f"Условие:\n{task['task_text']}")
            print()
            print(f"Решение:\n{task['solution']}")
            print()
            print(f"Критерий 1 балл:\n{task['criteria_1_point']}")
            print()
            print(f"Критерий 2 балла:\n{task['criteria_2_points']}")
            print("═" * 80)
            print()
            
            # Пауза между запросами
            time.sleep(3)
        else:
            print(f"❌ Не удалось сгенерировать задачу уровня {level}")
    
    # Сохраняем результат
    output_file = "test_topic9_levels_1_7.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print(f"✅ ТЕСТ ЗАВЕРШЕН!")
    print(f"📊 Сгенерировано задач: {len(generated_tasks)}/2")
    print(f"💾 Результат сохранен в: {output_file}")
    print("=" * 80)


def generate_all_150_tasks(anchor_file: str):
    """Генерирует все 150 недостающих задач (6 уровней × 25 тем)"""
    
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"❌ ОШИБКА: {e}")
        print("💡 Убедитесь, что DEEPSEEK_API_KEY указан в .env файле!")
        return
    
    # Загружаем эталоны
    anchor_tasks = load_anchor_tasks(anchor_file)
    
    if len(anchor_tasks) != 25:
        print(f"⚠️ ВНИМАНИЕ: Ожидалось 25 эталонов, найдено {len(anchor_tasks)}")
    
    print("=" * 80)
    print("🚀 ПОЛНАЯ ГЕНЕРАЦИЯ: 150 задач для Адаптивного теста")
    print(f"📚 Тем: {len(anchor_tasks)}")
    print(f"🎯 Уровни на тему: {TARGET_LEVELS}")
    print(f"📊 Всего задач: {len(anchor_tasks) * len(TARGET_LEVELS)}")
    print("=" * 80)
    print()
    
    all_generated_tasks = []
    total_success = 0
    total_failed = 0
    
    for topic_idx, anchor_task in enumerate(anchor_tasks, 1):
        topic_name = anchor_task.get('topic', f'Тема {topic_idx}')
        print(f"\n📚 Тема {topic_idx}/{len(anchor_tasks)}: {topic_name}")
        print("─" * 80)
        
        for level in TARGET_LEVELS:
            print(f"  ⏳ Уровень {level}...", end=" ", flush=True)
            
            task = generate_task_from_anchor(anchor_task, level, client)
            
            if task:
                all_generated_tasks.append(task)
                total_success += 1
                print(f"✅")
            else:
                total_failed += 1
                print(f"❌")
            
            # Пауза между запросами (чтобы не превысить rate limit)
            time.sleep(2)
        
        # Промежуточное сохранение после каждой темы
        if topic_idx % 5 == 0:
            temp_file = f"adaptive_150_progress_{topic_idx}_topics.json"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(all_generated_tasks, f, ensure_ascii=False, indent=2)
            print(f"💾 Промежуточное сохранение: {temp_file}")
    
    # Финальное сохранение
    output_file = "adaptive_150_tasks_generated.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_generated_tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print(f"✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"📊 Успешно: {total_success}/{len(anchor_tasks) * len(TARGET_LEVELS)}")
    print(f"❌ Ошибок: {total_failed}")
    print(f"💾 Результат сохранен в: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Генератор задач для Адаптивного теста')
    parser.add_argument('--anchor', type=str, default='adaptive_anchor_25_tasks_grade5_level3.json',
                        help='Путь к файлу с эталонными задачами')
    parser.add_argument('--test', action='store_true',
                        help='Тестовый режим: генерация только для Темы №9 (уровни 1 и 7)')
    parser.add_argument('--full', action='store_true',
                        help='Полная генерация всех 150 задач')
    
    args = parser.parse_args()
    
    if args.test:
        test_topic_9_generation(args.anchor)
    elif args.full:
        generate_all_150_tasks(args.anchor)
    else:
        print("Используйте --test для тестового запуска или --full для полной генерации")
        print("Пример: python generate_adaptive_150.py --test")
