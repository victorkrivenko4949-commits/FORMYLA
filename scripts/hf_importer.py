#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HuggingFace Dataset Importer for Mathematical Olympiad Problems
Downloads problems from HuggingFace datasets, classifies them using DeepSeek AI,
and saves them in our standard format.
"""

import os
import sys
import json
import time
from typing import Dict, Any, Optional, List

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system environment variables

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


# Complete list of all subtopics from our architecture
SUBTOPICS_LIST = [
    # Алгебра
    "Уравнения",
    "Неравенства",
    "Последовательности",
    "Функции",
    "Системы уравнений",
    
    # Геометрия
    "Треугольники",
    "Окружности",
    "Площади",
    "Четырёхугольники",
    "Координатная геометрия",
    
    # Комбинаторика
    "Подсчёт и перебор",
    "Принцип Дирихле",
    "Графы и раскраски",
    "Игры и стратегии",
    
    # Теория чисел
    "Делимость",
    "Остатки",
    "Простые числа",
    "Диофантовы уравнения",
    
    # Рыцари и лжецы
    "Классические задачи",
    "Задачи с условиями",
    "Задачи на острове",
    
    # Задачи на движение
    "Равномерное движение",
    "Движение навстречу и вдогонку",
    "Движение по воде и эскалаторы",
    
    # Разное (если не подходит ни одна категория)
    "Разное"
]

# Subject mapping
SUBJECT_MAPPING = {
    "алгебра": "algebra",
    "геометрия": "geometry",
    "комбинаторика": "combinatorics",
    "теория чисел": "number_theory",
    "рыцари и лжецы": "knights_liars",
    "движение": "movement",
    "разное": "other"
}

# System prompt for DeepSeek classification
CLASSIFICATION_SYSTEM_PROMPT = f"""Ты — эксперт по классификации математических олимпиадных задач.

Твоя задача: проанализировать задачу и определить:
1. Класс (grade): 5, 6, 7, 8 или 9
2. Раздел математики (topic): Алгебра, Геометрия, Комбинаторика, Теория чисел, Рыцари и лжецы, Движение, или Разное
3. Подтему (subtopic): СТРОГО одну из следующего списка:

{chr(10).join(f"- {s}" for s in SUBTOPICS_LIST)}

ВАЖНО:
- Выбирай подтему ТОЛЬКО из этого списка
- Если задача не подходит ни под одну категорию, используй "Разное"
- Отвечай ТОЛЬКО валидным JSON без markdown разметки
- Формат ответа:
{{"grade": 7, "topic": "Алгебра", "subtopic": "Уравнения", "difficulty": 5}}

где difficulty — сложность от 1 до 10:
  1-2: Простые школьные задачи
  3-4: Задачи среднего уровня
  5-6: Сложные школьные задачи
  7-8: Олимпиадные задачи регионального уровня
  9-10: Задачи уровня международных олимпиад (IMO)"""


def classify_problem(client: DeepSeekClient, problem_text: str) -> Optional[Dict[str, Any]]:
    """
    Classify a problem using DeepSeek AI.
    
    Args:
        client: DeepSeek API client
        problem_text: Problem text to classify
        
    Returns:
        Classification dict or None if failed
    """
    prompt = f"""Проанализируй эту олимпиадную задачу и классифицируй её:

{problem_text}

Верни JSON с полями: grade, topic, subtopic, difficulty"""

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
        
        # Validate required fields
        if not all(k in classification for k in ["grade", "topic", "subtopic", "difficulty"]):
            print(f"⚠️  Missing required fields in classification: {classification}")
            return None
            
        return classification
        
    except json.JSONDecodeError as e:
        print(f"⚠️  Failed to parse JSON response: {e}")
        print(f"Response was: {response}")
        return None
    except DeepSeekAPIError as e:
        print(f"⚠️  DeepSeek API error: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Unexpected error during classification: {e}")
        return None


def format_problem(raw_problem: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a problem into our standard structure.
    
    Args:
        raw_problem: Raw problem from dataset
        classification: Classification from DeepSeek
        
    Returns:
        Formatted problem dict
    """
    # Map topic to subject key
    topic_lower = classification["topic"].lower()
    subject = SUBJECT_MAPPING.get(topic_lower, "other")
    
    # Extract problem data (handle different dataset formats)
    problem_text = raw_problem.get("task_text", raw_problem.get("problem", raw_problem.get("question", raw_problem.get("text", ""))))
    solution = raw_problem.get("solution", raw_problem.get("answer_text", ""))
    answer = raw_problem.get("correct_answer", raw_problem.get("answer", raw_problem.get("short_answer", "")))
    
    return {
        "subject": subject,
        "subtopic": classification["subtopic"],
        "grade": classification["grade"],
        "difficulty": classification["difficulty"],
        "title": "Олимпиадная задача",
        "text": problem_text,
        "answer": answer if answer else "",
        "solution": solution if solution else "",
        "source": "HuggingFace",
        "source_dataset": raw_problem.get("_dataset_name", "unknown")
    }


def load_dataset_safe(dataset_name: str, split: str = "train"):
    """
    Safely load a dataset with error handling.
    
    Args:
        dataset_name: Name of the dataset
        split: Dataset split to load
        
    Returns:
        Dataset or None if failed
    """
    try:
        from datasets import load_dataset
        print(f"📥 Loading dataset: {dataset_name}")
        
        # Try the specified split first
        try:
            dataset = load_dataset(dataset_name, split=split)
            print(f"✓ Loaded {len(dataset)} problems from {dataset_name} ({split} split)")
            return dataset
        except ValueError as e:
            # If split doesn't exist, try "test" split
            if "train" in str(e) and split == "train":
                print(f"⚠️  'train' split not found, trying 'test' split...")
                dataset = load_dataset(dataset_name, split="test")
                print(f"✓ Loaded {len(dataset)} problems from {dataset_name} (test split)")
                return dataset
            raise
            
    except Exception as e:
        print(f"⚠️  Failed to load {dataset_name}: {e}")
        return None


def main():
    """Main execution function."""
    print("=" * 70)
    print("HuggingFace Dataset Importer for Mathematical Olympiad Problems")
    print("=" * 70)
    
    # Initialize DeepSeek client
    try:
        client = DeepSeekClient()
        print("✓ DeepSeek client initialized")
    except ValueError as e:
        print(f"❌ Failed to initialize DeepSeek client: {e}")
        print("Make sure DEEPSEEK_API_KEY is set in your environment or .env file")
        return
    
    # Try to load datasets
    dataset = None
    dataset_name = None
    
    # Try first dataset
    dataset = load_dataset_safe("d0rj/ROMB-1.0")
    if dataset:
        dataset_name = "d0rj/ROMB-1.0"
    else:
        # Try second dataset
        dataset = load_dataset_safe("Vikhrmodels/russian_math")
        if dataset:
            dataset_name = "Vikhrmodels/russian_math"
    
    if not dataset:
        print("❌ Failed to load any dataset. Please check your internet connection.")
        return
    
    # Show first 2 problems to understand structure
    print("\n" + "=" * 70)
    print("Dataset Structure - First 2 Problems:")
    print("=" * 70)
    for i in range(min(2, len(dataset))):
        print(f"\n--- Problem {i+1} ---")
        problem = dataset[i]
        for key, value in problem.items():
            value_str = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
            print(f"{key}: {value_str}")
    
    # Ask user how many problems to process
    print("\n" + "=" * 70)
    print("Starting mass processing with ALL problems from dataset...")
    print("=" * 70)
    
    # Загружаем ВСЕ задачи из датасета
    num_problems = len(dataset)
    print(f"Total problems in dataset: {num_problems}")
    processed_problems = []
    
    # Process problems
    for i in range(min(num_problems, len(dataset))):
        print(f"\n[{i+1}/{num_problems}] Processing problem...")
        
        raw_problem = dataset[i]
        raw_problem["_dataset_name"] = dataset_name
        
        # Extract problem text (handle different formats)
        problem_text = raw_problem.get("task_text", raw_problem.get("problem", raw_problem.get("question", raw_problem.get("text", ""))))
        
        if not problem_text:
            print(f"⚠️  Skipping problem {i+1}: no text found")
            continue
        
        print(f"Problem text preview: {problem_text[:150]}...")
        
        # Classify with DeepSeek
        print("🤖 Classifying with DeepSeek...")
        classification = classify_problem(client, problem_text)
        
        if not classification:
            print(f"⚠️  Skipping problem {i+1}: classification failed")
            continue
        
        print(f"✓ Classification: {classification}")
        
        # Format problem
        formatted = format_problem(raw_problem, classification)
        processed_problems.append(formatted)
        
        # Delay to avoid rate limiting (1 second between API calls)
        if i < num_problems - 1:
            time.sleep(1)
        
        # Save checkpoint every 50 problems
        if (i + 1) % 50 == 0:
            os.makedirs("data", exist_ok=True)
            checkpoint_file = "data/hf_problems.jsonl"
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                for problem in processed_problems:
                    f.write(json.dumps(problem, ensure_ascii=False) + '\n')
            print(f"💾 Checkpoint: Saved {len(processed_problems)} problems")
    
    # Save results
    if processed_problems:
        os.makedirs("data", exist_ok=True)
        output_file = "data/hf_problems.jsonl"
        
        print(f"\n{'=' * 70}")
        print(f"💾 Saving {len(processed_problems)} problems to {output_file}")
        print("=" * 70)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for problem in processed_problems:
                f.write(json.dumps(problem, ensure_ascii=False) + '\n')
        
        print(f"✓ Saved to {output_file}")
        
        # Display one example
        print(f"\n{'=' * 70}")
        print("Example Problem (for verification):")
        print("=" * 70)
        print(json.dumps(processed_problems[0], ensure_ascii=False, indent=2))
        
        print(f"\n{'=' * 70}")
        print(f"✅ SUCCESS! Processed {len(processed_problems)} problems")
        print(f"Results saved to: {output_file}")
        print("=" * 70)
    else:
        print("\n❌ No problems were successfully processed")


if __name__ == "__main__":
    main()
