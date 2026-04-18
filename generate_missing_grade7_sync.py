"""
Синхронный догенератор недостающих задач для 7 класса
(используем синхронный подход для большей стабильности)
"""

import json
import time
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai.deepseek_client import DeepSeekClient

load_dotenv()


def create_prompt(topic: str, level: int, anchor: dict) -> str:
    """Создает промпт для генерации"""
    
    if not anchor:
        return f"""Сгенерируй задачу для 7 класса на тему "{topic}", уровень {level}.

ПРАВИЛА:
1. LaTeX: \\\\( ... \\\\). В JSON удваивай слеши!
2. Реши задачу в уме перед генерацией!

ВЕРНИ JSON:
{{
  "class_level": 7,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Условие",
  "solution": "Решение",
  "criteria_1_point": "1 балл",
  "criteria_2_points": "2 балла"
}}"""
    
    anchor_text = anchor.get('task_text', '')
    anchor_solution = anchor.get('solution', '')
    
    return f"""Якорь (уровень 3) на тему "{topic}":
Условие: {anchor_text}
Решение: {anchor_solution}

Сгенерируй НОВУЮ задачу для уровня {level}.

ПРАВИЛА:
1. Сюжет ДОЛЖЕН отличаться!
2. Если {level} < 3: упрости. Если {level} > 3: усложни.
3. LaTeX: \\\\( ... \\\\). В JSON удваивай слеши!

ВЕРНИ JSON:
{{
  "class_level": 7,
  "difficulty_level": {level},
  "topic": "{topic}",
  "task_text": "Условие",
  "solution": "Решение",
  "criteria_1_point": "1 балл",
  "criteria_2_points": "2 балла"
}}"""


def generate_task(client: DeepSeekClient, topic: str, level: int, anchor: dict) -> dict:
    """Генерирует одну задачу"""
    
    prompt = create_prompt(topic, level, anchor)
    
    for attempt in range(3):
        try:
            response = client.generate(
                prompt=prompt,
                system_prompt="Ты — генератор задач. Возвращай только валидный JSON.",
                temperature=0.85,
                max_tokens=2500
            )
            
            # Очистка
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            task_data = json.loads(response)
            return task_data
            
        except json.JSONDecodeError as e:
            if attempt < 2:
                print(f"  Retry {attempt + 1}/3...")
                time.sleep(2)
            else:
                print(f"  ERROR: JSON error after 3 attempts")
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  ERROR: {str(e)[:100]}")
                return None
    
    return None


def main():
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"ERROR: {e}")
        return
    
    with open('missing_tasks_grade7.json', 'r', encoding='utf-8') as f:
        missing_list = json.load(f)
    
    print("=" * 80)
    print(f"GENERATING MISSING TASKS FOR GRADE 7: {len(missing_list)} tasks")
    print("=" * 80)
    print()
    
    tasks = []
    success = 0
    errors = 0
    
    for idx, item in enumerate(missing_list, 1):
        topic = item['topic']
        level = item['level']
        anchor = item.get('anchor')
        
        print(f"[{idx}/{len(missing_list)}] {topic} (level {level})...", end=" ")
        
        task = generate_task(client, topic, level, anchor)
        
        if task:
            tasks.append(task)
            success += 1
            print("SUCCESS")
        else:
            errors += 1
            print("FAILED")
        
        time.sleep(2)
    
    with open('missing_grade7_generated.json', 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print("COMPLETED!")
    print(f"SUCCESS: {success}/{len(missing_list)}")
    print(f"ERRORS: {errors}")
    print(f"SAVED: missing_grade7_generated.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
