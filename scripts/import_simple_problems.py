#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Импорт простых школьных задач из d0rj/gsm8k-ru
Классификация через DeepSeek с ограничением уровней 1-6
"""

import os
import sys
import json
import time
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Список подтем (тот же, что в hf_importer.py)
SUBTOPICS_LIST = [
    "Уравнения", "Неравенства", "Последовательности", "Функции", "Системы уравнений",
    "Треугольники", "Окружности", "Площади", "Четырёхугольники", "Координатная геометрия",
    "Подсчёт и перебор", "Принцип Дирихле", "Графы и раскраски", "Игры и стратегии",
    "Делимость", "Остатки", "Простые числа", "Диофантовы уравнения",
    "Классические задачи", "Задачи с условиями", "Задачи на острове",
    "Равномерное движение", "Движение навстречу и вдогонку", "Движение по воде и эскалаторы",
    "Разное"
]

# Системный промпт для ПРОСТЫХ задач (уровни 1-6)
CLASSIFICATION_SYSTEM_PROMPT = f"""Ты — эксперт по классификации математических школьных задач.

Твоя задача: проанализировать ПРОСТУЮ школьную задачу и определить:
1. Класс (grade): 5, 6, 7, 8 или 9
2. Раздел математики (topic): Алгебра, Геометрия, Комбинаторика, Теория чисел, Рыцари и лжецы, Движение, или Разное
3. Подтему (subtopic): СТРОГО одну из следующего списка:

{chr(10).join(f"- {s}" for s in SUBTOPICS_LIST)}

ВАЖНО:
- Это ПРОСТЫЕ школьные задачи, НЕ олимпиадные
- Выбирай подтему ТОЛЬКО из этого списка
- Если задача не подходит ни под одну категорию, используй "Разное"
- Отвечай ТОЛЬКО валидным JSON без markdown разметки
- Формат ответа:
{{"grade": 5, "topic": "Алгебра", "subtopic": "Уравнения", "difficulty": 3}}

где difficulty — сложность от 1 до 6 (ТОЛЬКО простые задачи):
  1: Очень простые задачи для начальной школы
  2: Простые задачи для 5-6 класса
  3: Задачи среднего уровня для 6-7 класса
  4: Задачи для 7-8 класса
  5: Сложные школьные задачи для 8-9 класса
  6: Максимально сложные школьные задачи (но НЕ олимпиадные)"""

SUBJECT_MAPPING = {
    "алгебра": "algebra",
    "геометрия": "geometry",
    "комбинаторика": "combinatorics",
    "теория чисел": "number_theory",
    "рыцари и лжецы": "knights_liars",
    "движение": "movement",
    "разное": "other"
}


def classify_problem(client: DeepSeekClient, problem_text: str) -> Optional[Dict[str, Any]]:
    """Классификация задачи через DeepSeek"""
    prompt = f"""Проанализируй эту простую школьную задачу и классифицируй её:

{problem_text}

Верни JSON с полями: grade, topic, subtopic, difficulty (1-6)"""

    try:
        response = client.generate(
            prompt=prompt,
            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=200
        )
        
        # Clean response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        # Parse JSON
        classification = json.loads(response)
        
        # Validate and cap difficulty at 6
        if 'difficulty' in classification:
            classification['difficulty'] = min(classification['difficulty'], 6)
        
        return classification
        
    except Exception as e:
        print(f"⚠️  Ошибка классификации: {e}")
        return None


def format_problem(raw_problem: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    """Форматирование задачи"""
    topic_lower = classification["topic"].lower()
    subject = SUBJECT_MAPPING.get(topic_lower, "other")
    
    # Извлекаем текст задачи и решение
    question = raw_problem.get("question", "")
    answer = raw_problem.get("answer", "")
    
    # Разделяем ответ на короткий ответ и решение
    short_answer = ""
    solution = answer
    
    if "####" in answer:
        parts = answer.split("####")
        solution = parts[0].strip()
        short_answer = parts[1].strip() if len(parts) > 1 else ""
    
    return {
        "subject": subject,
        "subtopic": classification["subtopic"],
        "grade": classification["grade"],
        "difficulty": min(classification["difficulty"], 6),  # Гарантируем макс 6
        "title": "Школьная задача",
        "text": question,
        "answer": short_answer,
        "solution": solution,
        "source": "HuggingFace",
        "source_dataset": "d0rj/gsm8k-ru"
    }


def main():
    print("=" * 70)
    print("Импорт простых школьных задач из d0rj/gsm8k-ru")
    print("=" * 70)
    
    # Initialize DeepSeek
    try:
        client = DeepSeekClient()
        print("✓ DeepSeek client initialized")
    except ValueError as e:
        print(f"❌ Failed to initialize DeepSeek: {e}")
        return
    
    # Load dataset
    print("\n📥 Loading dataset d0rj/gsm8k-ru...")
    from datasets import load_dataset
    
    try:
        dataset = load_dataset("d0rj/gsm8k-ru", split="train")
        print(f"✓ Loaded {len(dataset)} problems")
    except Exception as e:
        print(f"❌ Failed to load dataset: {e}")
        return
    
    # Show first problem
    print("\n" + "=" * 70)
    print("Пример задачи:")
    print("=" * 70)
    print(f"Вопрос: {dataset[0]['question']}")
    print(f"Ответ: {dataset[0]['answer'][:100]}...")
    
    # Process problems
    print("\n" + "=" * 70)
    print("Обработка задач (первые 5000)...")
    print("=" * 70)
    
    num_problems = min(5000, len(dataset))
    processed = []
    
    for i in range(num_problems):
        print(f"\n[{i+1}/{num_problems}] Processing...")
        
        raw = dataset[i]
        question = raw.get("question", "")
        
        if not question:
            print("⚠️  Skipping: no question")
            continue
        
        print(f"Question preview: {question[:100]}...")
        
        # Classify
        print("🤖 Classifying...")
        classification = classify_problem(client, question)
        
        if not classification:
            print("⚠️  Skipping: classification failed")
            continue
        
        print(f"✓ Classification: {classification}")
        
        # Format
        formatted = format_problem(raw, classification)
        processed.append(formatted)
        
        # Save checkpoint every 50
        if (i + 1) % 50 == 0:
            os.makedirs("data", exist_ok=True)
            with open("data/simple_problems.jsonl", 'w', encoding='utf-8') as f:
                for p in processed:
                    f.write(json.dumps(p, ensure_ascii=False) + '\n')
            print(f"💾 Checkpoint: Saved {len(processed)} problems")
        
        # Delay
        time.sleep(1)
    
    # Final save
    if processed:
        os.makedirs("data", exist_ok=True)
        with open("data/simple_problems.jsonl", 'w', encoding='utf-8') as f:
            for p in processed:
                f.write(json.dumps(p, ensure_ascii=False) + '\n')
        
        print("\n" + "=" * 70)
        print(f"✅ SUCCESS! Processed {len(processed)} problems")
        print(f"Saved to: data/simple_problems.jsonl")
        print("=" * 70)
        
        # Show example
        print("\nПример обработанной задачи:")
        print(json.dumps(processed[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
