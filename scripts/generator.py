#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Task Generator for FORMYLA Platform
Generates 8400 unique math problems using DeepSeek API according to Russian FGOS standards.
"""

import os
import sys
import json
import time
import random
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.deepseek_client import DeepSeekClient, CheckpointManager, DeepSeekAPIError

# Configuration
TEST_MODE = True  # Set to False for full generation
TEST_LIMIT = 3    # Number of tasks to generate in test mode

OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "generated_problems.jsonl")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "generator_checkpoint.json")

# Subjects and their subtopics
SUBJECTS = {
    "algebra": {
        "title": "Алгебра",
        "subtopics": {
            "equations": "Уравнения",
            "inequalities": "Неравенства",
            "sequences": "Последовательности",
            "functions": "Функции",
            "systems": "Системы уравнений"
        }
    },
    "geometry": {
        "title": "Геометрия",
        "subtopics": {
            "triangles": "Треугольники",
            "circles": "Окружности",
            "areas": "Площади",
            "quadrilaterals": "Четырёхугольники",
            "coordinate": "Координатная геометрия"
        }
    },
    "combinatorics": {
        "title": "Комбинаторика",
        "subtopics": {
            "counting": "Подсчёт и перебор",
            "pigeonhole": "Принцип Дирихле",
            "graphs": "Графы и раскраски",
            "games": "Игры и стратегии"
        }
    },
    "number_theory": {
        "title": "Теория чисел",
        "subtopics": {
            "divisibility": "Делимость",
            "remainders": "Остатки",
            "primes": "Простые числа",
            "diophantine": "Диофантовы уравнения"
        }
    },
    "movement": {
        "title": "Задачи на движение",
        "subtopics": {
            "basic": "Базовые задачи",
            "meeting": "Встречное движение",
            "special": "Движение по воде и эскалаторы"
        }
    },
    "knights_liars": {
        "title": "Рыцари и лжецы",
        "subtopics": {
            "basic": "Базовая логика",
            "complex": "Сложные цепочки"
        }
    }
}

GRADES = [5, 6, 7, 8, 9, 10, 11]
DIFFICULTIES = list(range(1, 11))  # 1-10

# Context elements for variety
CONTEXTS = [
    "в контексте реальной жизненной ситуации",
    "с использованием необычных чисел",
    "с элементами логической головоломки",
    "с практическим применением",
    "с нестандартной формулировкой"
]


def clean_json_response(text: str) -> str:
    """
    Clean JSON response from markdown code blocks.
    
    Args:
        text: Raw response text
        
    Returns:
        Cleaned JSON string
    """
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = text.strip()
    return text


def generate_task(client: DeepSeekClient, subject_key: str, subject_data: dict, 
                  subtopic_key: str, subtopic_title: str, grade: int, difficulty: int,
                  task_id: int) -> dict:
    """
    Generate a single task using DeepSeek API.
    
    Args:
        client: DeepSeekClient instance
        subject_key: Subject key (e.g., 'algebra')
        subject_data: Subject metadata
        subtopic_key: Subtopic key
        subtopic_title: Subtopic title
        grade: Grade level (5-11)
        difficulty: Difficulty level (1-10)
        task_id: Unique task ID
        
    Returns:
        Task dictionary
        
    Raises:
        DeepSeekAPIError: If generation fails
    """
    subject_title = subject_data["title"]
    context = random.choice(CONTEXTS)
    
    system_prompt = """Ты эксперт по российской школьной программе (ФГОС) и олимпиадной математике. 
Твоя задача — генерировать уникальные математические задачи. 
Запрещено использовать стандартные имена (Петя, Вася) и типовые шаблоны. 
Каждая задача должна быть структурно уникальной.

Твой ответ должен быть СТРОГО валидным JSON объектом с полями:
- "title": краткое название задачи
- "text": полное условие задачи
- "answer": краткий правильный ответ
- "solution": подробное пошаговое решение с объяснениями

Выводи ТОЛЬКО JSON, без дополнительного текста."""
    
    user_prompt = f"""Сгенерируй задачу по математике.

Параметры:
- Предмет: {subject_title} ({subject_key})
- Подтема: {subtopic_title}
- Класс: {grade}
- Уровень сложности: {difficulty} из 10
  (где 1 - базовая школьная программа ФГОС, 
   5 - уровень ОГЭ/ЕГЭ профильного уровня,
   10 - уровень регионального этапа ВсОШ)

Дополнительное требование: создай задачу {context}.

Выведи результат в формате JSON."""
    
    # Try to generate with retries
    max_parse_attempts = 3
    for parse_attempt in range(max_parse_attempts):
        try:
            response_text = client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,  # Higher for more variety
                max_tokens=1500
            )
            
            # Clean and parse JSON
            cleaned = clean_json_response(response_text)
            task_data = json.loads(cleaned)
            
            # Validate required fields
            required_fields = ['title', 'text', 'answer', 'solution']
            if not all(field in task_data for field in required_fields):
                raise ValueError(f"Missing required fields. Got: {list(task_data.keys())}")
            
            # Add metadata
            task_data['id'] = task_id
            task_data['subject'] = subject_key
            task_data['subject_title'] = subject_title
            task_data['subtopic'] = subtopic_key
            task_data['subtopic_title'] = subtopic_title
            task_data['grade'] = grade
            task_data['difficulty'] = difficulty
            
            return task_data
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [WARNING] Parse attempt {parse_attempt + 1}/{max_parse_attempts} failed: {e}")
            if parse_attempt < max_parse_attempts - 1:
                time.sleep(2)
                continue
            else:
                raise DeepSeekAPIError(f"Failed to parse JSON after {max_parse_attempts} attempts")
    
    raise DeepSeekAPIError("Unexpected error in generate_task")


def main():
    """Main generation function."""
    print("=" * 70)
    print("FORMYLA Task Generator - DeepSeek API")
    print("=" * 70)
    
    if TEST_MODE:
        print(f"\n⚠️  TEST MODE: Will generate only {TEST_LIMIT} tasks")
    else:
        print("\n🚀 PRODUCTION MODE: Will generate full database")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Initialize client and checkpoint
    try:
        client = DeepSeekClient()
        print("✓ DeepSeek client initialized")
    except ValueError as e:
        print(f"✗ Error: {e}")
        print("\nPlease set DEEPSEEK_API_KEY environment variable")
        return 1
    
    checkpoint = CheckpointManager(CHECKPOINT_FILE)
    checkpoint_data = checkpoint.load()
    processed = set(checkpoint_data.get('processed', []))
    
    print(f"✓ Checkpoint loaded: {len(processed)} tasks already processed")
    
    # Generate task list
    tasks_to_generate = []
    task_id = 1
    
    for subject_key, subject_data in SUBJECTS.items():
        for subtopic_key, subtopic_title in subject_data["subtopics"].items():
            for grade in GRADES:
                for difficulty in DIFFICULTIES:
                    task_key = f"{subject_key}_{subtopic_key}_{grade}_{difficulty}"
                    if task_key not in processed:
                        tasks_to_generate.append({
                            'id': task_id,
                            'subject_key': subject_key,
                            'subject_data': subject_data,
                            'subtopic_key': subtopic_key,
                            'subtopic_title': subtopic_title,
                            'grade': grade,
                            'difficulty': difficulty,
                            'key': task_key
                        })
                    task_id += 1
    
    total_tasks = len(tasks_to_generate)
    print(f"\n📊 Tasks to generate: {total_tasks}")
    
    if TEST_MODE:
        tasks_to_generate = tasks_to_generate[:TEST_LIMIT]
        print(f"   (Limited to {TEST_LIMIT} for testing)")
    
    # Generation loop
    generated_count = 0
    failed_count = 0
    
    try:
        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
            for i, task_config in enumerate(tasks_to_generate, 1):
                print(f"\n[{i}/{len(tasks_to_generate)}] Generating task...")
                print(f"  Subject: {task_config['subject_key']}")
                print(f"  Grade: {task_config['grade']}, Difficulty: {task_config['difficulty']}")
                
                try:
                    task = generate_task(
                        client,
                        task_config['subject_key'],
                        task_config['subject_data'],
                        task_config['subtopic_key'],
                        task_config['subtopic_title'],
                        task_config['grade'],
                        task_config['difficulty'],
                        task_config['id']
                    )
                    
                    # Write to JSONL
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
                    f.flush()  # Force write to disk
                    
                    # Update checkpoint
                    processed.add(task_config['key'])
                    checkpoint.save({
                        'processed': list(processed),
                        'last_id': task_config['id'],
                        'generated_count': generated_count + 1
                    })
                    
                    generated_count += 1
                    print(f"  ✓ Task generated and saved (ID: {task['id']})")
                    
                    # Small delay to avoid overwhelming API
                    time.sleep(1)
                    
                except DeepSeekAPIError as e:
                    print(f"  ✗ Failed: {e}")
                    failed_count += 1
                    
                except Exception as e:
                    print(f"  ✗ Unexpected error: {e}")
                    failed_count += 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Generation stopped by user (Ctrl+C)")
        print(f"Generated: {generated_count}, Failed: {failed_count}")
        print(f"Progress saved to checkpoint: {CHECKPOINT_FILE}")
        return 0
    
    # Final summary
    print("\n" + "=" * 70)
    print("GENERATION COMPLETE")
    print("=" * 70)
    print(f"✓ Generated: {generated_count}")
    print(f"✗ Failed: {failed_count}")
    print(f"📁 Output file: {OUTPUT_FILE}")
    print(f"💾 Checkpoint: {CHECKPOINT_FILE}")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
