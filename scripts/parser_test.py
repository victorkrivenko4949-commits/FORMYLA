#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for parser - creates mock problems to test the pipeline.
"""

import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock problems for testing
MOCK_PROBLEMS = [
    {
        "source": "problems.ru",
        "url": "https://problems.ru/view_problem.php?id=1",
        "title": "Задача 1: Уравнение",
        "text": "Решите уравнение: 2x + 5 = 13. Найдите значение x.",
        "answer": "x = 4",
        "solution": "Вычтем 5 из обеих частей: 2x = 8. Разделим на 2: x = 4."
    },
    {
        "source": "problems.ru",
        "url": "https://problems.ru/view_problem.php?id=2",
        "title": "Задача 2: Треугольник",
        "text": "В треугольнике ABC угол A равен 60°, угол B равен 80°. Найдите угол C.",
        "answer": "40°",
        "solution": "Сумма углов треугольника равна 180°. Угол C = 180° - 60° - 80° = 40°."
    },
    {
        "source": "mccme.ru",
        "url": "https://mccme.ru/problem/3",
        "title": "Задача 3: Комбинаторика",
        "text": "Сколькими способами можно выбрать 2 человека из группы 5 человек?",
        "answer": "10",
        "solution": "Используем формулу сочетаний: C(5,2) = 5!/(2!*3!) = 10."
    },
    {
        "source": "problems.ru",
        "url": "https://problems.ru/view_problem.php?id=4",
        "title": "Задача 4: Делимость",
        "text": "Докажите, что число 111111 делится на 3.",
        "answer": "Доказано",
        "solution": "Сумма цифр: 1+1+1+1+1+1 = 6, которая делится на 3. Значит, число делится на 3."
    },
    {
        "source": "mccme.ru",
        "url": "https://mccme.ru/problem/5",
        "title": "Задача 5: Движение",
        "text": "Два велосипедиста выехали навстречу друг другу. Скорость первого 15 км/ч, второго 20 км/ч. Расстояние между ними 70 км. Через сколько часов они встретятся?",
        "answer": "2 часа",
        "solution": "Скорость сближения: 15 + 20 = 35 км/ч. Время: 70 / 35 = 2 часа."
    }
]

def main():
    """Create mock parsed problems for testing."""
    output_file = "data/parsed_problems.jsonl"
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Try to import AI client
    try:
        from ai.deepseek_client import DeepSeekClient
        ai_client = DeepSeekClient()
        use_ai = True
        print("✓ AI client available")
    except Exception as e:
        print(f"⚠️  AI client not available: {e}")
        use_ai = False
    
    # Process mock problems
    classified_problems = []
    
    for idx, problem in enumerate(MOCK_PROBLEMS, 1):
        print(f"\n[{idx}/{len(MOCK_PROBLEMS)}] Processing: {problem['title']}")
        
        # Classify with AI or use fallback
        if use_ai:
            try:
                system_prompt = """Ты эксперт по классификации математических задач.
Доступные предметы и подтемы:
- algebra: equations, inequalities, sequences, functions, systems
- geometry: triangles, circles, areas, quadrilaterals, coordinate
- combinatorics: counting, pigeonhole, graphs, games
- number_theory: divisibility, remainders, primes, diophantine
- knights_liars: classic, conditions, island
- movement: uniform, encounter, special

Верни ТОЛЬКО валидный JSON: {"subject": "...", "subtopic": "..."}"""

                user_prompt = f"Задача: {problem['text']}\n\nВерни JSON с классификацией."
                
                response = ai_client.generate(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.1,
                    max_tokens=100
                )
                
                # Extract JSON
                import re
                json_match = re.search(r'\{[^}]+\}', response)
                if json_match:
                    classification = json.loads(json_match.group(0))
                    subject = classification.get('subject', 'algebra')
                    subtopic = classification.get('subtopic', 'equations')
                    print(f"  AI classified as: {subject}/{subtopic}")
                else:
                    subject, subtopic = 'algebra', 'equations'
                    print(f"  Using fallback classification")
            except Exception as e:
                print(f"  AI error: {e}, using fallback")
                subject, subtopic = 'algebra', 'equations'
        else:
            # Fallback classification based on keywords
            text_lower = problem['text'].lower()
            if 'треугольник' in text_lower or 'угол' in text_lower or 'окружност' in text_lower:
                subject, subtopic = 'geometry', 'triangles'
            elif 'способ' in text_lower or 'выбрать' in text_lower or 'перестановк' in text_lower:
                subject, subtopic = 'combinatorics', 'counting'
            elif 'делится' in text_lower or 'делимость' in text_lower or 'остаток' in text_lower:
                subject, subtopic = 'number_theory', 'divisibility'
            elif 'скорость' in text_lower or 'движение' in text_lower or 'встреч' in text_lower:
                subject, subtopic = 'movement', 'encounter'
            else:
                subject, subtopic = 'algebra', 'equations'
            print(f"  Keyword classified as: {subject}/{subtopic}")
        
        # Subject titles
        subject_titles = {
            "algebra": "Алгебра",
            "geometry": "Геометрия",
            "combinatorics": "Комбинаторика",
            "number_theory": "Теория чисел",
            "movement": "Задачи на движение",
            "knights_liars": "Рыцари и лжецы"
        }
        
        # Subtopic titles
        subtopic_titles = {
            "algebra": {"equations": "Уравнения", "inequalities": "Неравенства", "sequences": "Последовательности", "functions": "Функции", "systems": "Системы уравнений"},
            "geometry": {"triangles": "Треугольники", "circles": "Окружности", "areas": "Площади", "quadrilaterals": "Четырёхугольники", "coordinate": "Координатная геометрия"},
            "combinatorics": {"counting": "Подсчёт и перебор", "pigeonhole": "Принцип Дирихле", "graphs": "Графы и раскраски", "games": "Игры и стратегии"},
            "number_theory": {"divisibility": "Делимость", "remainders": "Остатки", "primes": "Простые числа", "diophantine": "Диофантовы уравнения"},
            "knights_liars": {"classic": "Классические задачи", "conditions": "Задачи с условиями", "island": "Задачи на острове"},
            "movement": {"uniform": "Равномерное движение", "encounter": "Движение навстречу и вдогонку", "special": "Движение по воде и эскалаторы"},
        }
        
        # Build classified problem
        classified = {
            "source": problem["source"],
            "source_url": problem["url"],
            "subject": subject,
            "subject_title": subject_titles.get(subject, subject),
            "subtopic": subtopic,
            "subtopic_title": subtopic_titles.get(subject, {}).get(subtopic, subtopic),
            "title": problem["title"],
            "text": problem["text"],
            "answer": problem["answer"],
            "solution": problem["solution"],
            "grade": 7,  # Default grade
            "difficulty": 5,  # Default difficulty
        }
        
        classified_problems.append(classified)
    
    # Write to JSONL
    with open(output_file, 'w', encoding='utf-8') as f:
        for problem in classified_problems:
            f.write(json.dumps(problem, ensure_ascii=False) + '\n')
    
    print(f"\n{'='*70}")
    print(f"✅ Created {len(classified_problems)} test problems")
    print(f"📁 Output: {output_file}")
    print(f"{'='*70}")
    print(f"\nNext step: Run migration")
    print(f"  python scripts/migrator.py --source parsed")

if __name__ == "__main__":
    main()
