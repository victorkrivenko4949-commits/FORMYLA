"""
Генератор недостающих 53 задач с улучшенной обработкой LaTeX
"""

import os
import sys
import json
import time
import re
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai.deepseek_client import DeepSeekClient

load_dotenv()


def aggressive_latex_escape(text):
    """Агрессивное экранирование LaTeX для JSON"""
    if not isinstance(text, str):
        return text
    
    # Заменяем все обратные слеши на двойные
    text = text.replace('\\', '\\\\')
    
    return text


def create_few_shot_prompt(anchor_task: dict, target_level: int) -> str:
    """Создает промпт для LLM с использованием эталонной задачи"""
    
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
1. Сюжет, имена персонажей и числа ДОЛЖНЫ отличаться от эталона!
2. Если {target_level} < 3, сделай логику и вычисления ЗНАЧИТЕЛЬНО ПРОЩЕ эталона (меньше шагов, проще числа).
3. Если {target_level} > 3, УСЛОЖНИ логику (добавь параметры, увеличь количество шагов алгоритма).
4. ЗАПРЕЩЕНЫ графические ответы. Только число или короткий текст.
5. МАТЕМАТИКА (LaTeX): ВЕСЬ математический текст строго внутри \\( ... \\) (инлайн) или \\[ ... \\] (блоки). 
   - Дроби только \\frac{{}}{{}}, корни \\sqrt{{}}, нижние индексы _{{}}.
   - Символы ^ и / без LaTeX запрещены!

**КРИТИЧЕСКИ ВАЖНО (МАТЕМАТИЧЕСКАЯ ТОЧНОСТЬ):**
Перед тем как писать JSON, ты ОБЯЗАН решить свою собственную задачу в уме и убедиться, что решение математически строгое и не содержит логических дыр.
Например:
- За 1 взвешивание можно найти фальшивую монету только из 3 монет (не из 4!).
- За 2 взвешивания — из 9 монет.
- За 3 взвешивания — из 27 монет.

**ВАЖНО ДЛЯ JSON:**
В JSON все обратные слеши должны быть удвоены. Например:
- Пиши \\\\( вместо \\(
- Пиши \\\\) вместо \\)
- Пиши \\\\frac вместо \\frac

ВЕРНИ СТРОГО JSON (без лишних слов до и после):
{{
  "class_level": 5,
  "difficulty_level": {target_level},
  "topic": "{topic}",
  "task_text": "Новое математически КОРРЕКТНОЕ условие",
  "solution": "Новое решение БЕЗ ЛОГИЧЕСКИХ ОШИБОК",
  "criteria_1_point": "За что дать 1 балл",
  "criteria_2_points": "За что дать 2 балла"
}}"""
    
    return prompt


def generate_task_from_anchor(anchor_task: dict, target_level: int, client: DeepSeekClient) -> dict:
    """Генерирует одну задачу на основе эталона"""
    
    user_prompt = create_few_shot_prompt(anchor_task, target_level)
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response_text = client.generate(
                prompt=user_prompt,
                system_prompt="Ты — генератор олимпиадных задач для 5 класса. Строго следуй инструкциям и возвращай только валидный JSON с правильно экранированным LaTeX.",
                temperature=0.85,
                max_tokens=2500
            )
            
            response_text = response_text.strip()
            
            # Убираем markdown обертки
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # НЕ делаем дополнительное экранирование, так как LLM должен вернуть уже правильно экранированный JSON
            
            task_data = json.loads(response_text)
            return task_data
            
        except json.JSONDecodeError as e:
            if attempt < max_attempts - 1:
                print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Ошибка JSON, повторяю...")
                time.sleep(2)
            else:
                print(f"❌ Ошибка JSON после {max_attempts} попыток: {e}")
                print(f"Ответ LLM (первые 300 символов): {response_text[:300]}...")
                return None
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None
    
    return None


def generate_missing_tasks():
    """Генерирует недостающие 53 задачи"""
    
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"❌ ОШИБКА: {e}")
        print("💡 Убедитесь, что DEEPSEEK_API_KEY указан в .env файле!")
        return
    
    # Загружаем список недостающих задач
    try:
        with open('missing_tasks_list.json', 'r', encoding='utf-8') as f:
            missing_tasks = json.load(f)
    except FileNotFoundError:
        print("❌ Файл missing_tasks_list.json не найден!")
        print("Сначала запустите: python analyze_missing_tasks.py")
        return
    
    print("=" * 80)
    print("🚀 ГЕНЕРАЦИЯ НЕДОСТАЮЩИХ ЗАДАЧ")
    print(f"📊 Всего задач к генерации: {len(missing_tasks)}")
    print("=" * 80)
    print()
    
    generated_tasks = []
    total_success = 0
    total_failed = 0
    
    for idx, item in enumerate(missing_tasks, 1):
        topic = item['topic']
        level = item['level']
        anchor = item['anchor']
        
        print(f"[{idx}/{len(missing_tasks)}] {topic} (уровень {level})...", end=" ", flush=True)
        
        task = generate_task_from_anchor(anchor, level, client)
        
        if task:
            generated_tasks.append(task)
            total_success += 1
            print("✅")
        else:
            total_failed += 1
            print("❌")
        
        # Пауза между запросами
        time.sleep(2)
        
        # Промежуточное сохранение каждые 10 задач
        if idx % 10 == 0:
            temp_file = f"missing_progress_{idx}_tasks.json"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
            print(f"💾 Промежуточное сохранение: {temp_file}")
    
    # Финальное сохранение
    output_file = "missing_53_tasks_generated.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(generated_tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print("✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"📊 Успешно: {total_success}/{len(missing_tasks)}")
    print(f"❌ Ошибок: {total_failed}")
    print(f"💾 Результат сохранен в: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    generate_missing_tasks()
