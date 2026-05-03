#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Load 7271 tasks from data/adaptive_full_db.json into problems.py.

Maps:
  - topic → subject + subtopic
  - level → difficulty
  - question → text
  - grade → grade
  - Assigns unique IDs starting from max(existing) + 1

Usage:
  python scripts/load_adaptive_to_problems.py
"""

import json
import sys
import os
import re

sys.stdout.reconfigure(encoding='utf-8')

# ─── Topic → Subject/Subtopic mapping ────────────────────────────────────────
# The 42 topics from adaptive_full_db.json mapped to subject categories

TOPIC_MAP = {
    # Grade 5
    "Натуральные числа и действия с ними": ("algebra", "natural_numbers"),
    "Обыкновенные дроби": ("algebra", "fractions"),
    "Десятичные дроби": ("algebra", "decimal_fractions"),
    "Проценты": ("algebra", "percentages"),
    "Площади и объемы": ("geometry", "areas_volumes"),
    "Уравнения и задачи": ("algebra", "equations_word_problems"),

    # Grade 6
    "Делимость чисел": ("number_theory", "divisibility"),
    "Положительные и отрицательные числа": ("algebra", "positive_negative"),
    "Рациональные числа и действия с ними": ("algebra", "rational_numbers"),
    "Отношения и пропорции": ("algebra", "ratios_proportions"),
    "Координаты на плоскости": ("geometry", "coordinates"),
    "Линейные уравнения": ("algebra", "linear_equations"),

    # Grade 7
    "Алгебраические выражения": ("algebra", "algebraic_expressions"),
    "Линейные уравнения и системы": ("algebra", "linear_systems"),
    "Степени и одночлены": ("algebra", "powers_monomials"),
    "Многочлены и формулы сокращенного умножения": ("algebra", "polynomials_fsu"),
    "Функции и графики": ("algebra", "functions_graphs"),
    "Геометрия: треугольники и параллельные прямые": ("geometry", "triangles_parallel"),

    # Grade 8
    "Рациональные дроби": ("algebra", "rational_fractions"),
    "Квадратные корни": ("algebra", "square_roots"),
    "Квадратные уравнения": ("algebra", "quadratic_equations"),
    "Степени с целым показателем": ("algebra", "integer_powers"),
    "Неравенства": ("algebra", "inequalities"),
    "Геометрия: четырехугольники и площади": ("geometry", "quadrilaterals_areas"),

    # Grade 9
    "Системы уравнений": ("algebra", "equation_systems"),
    "Элементы комбинаторики и теории вероятностей": ("combinatorics", "probability_basics"),
    "Квадратичная функция": ("algebra", "quadratic_function"),
    "Уравнения и неравенства с одной переменной": ("algebra", "equations_inequalities"),
    "Геометрия: окружность и векторы": ("geometry", "circles_vectors"),
    "Арифметическая и геометрическая прогрессии": ("algebra", "progressions"),

    # Grade 10
    "Показательная и логарифмическая функции": ("algebra", "exp_log_functions"),
    "Многогранники": ("geometry", "polyhedra"),
    "Тригонометрия": ("algebra", "trigonometry"),
    "Комбинаторика и вероятность": ("combinatorics", "combinatorics_probability"),
    "Производная и её применение": ("algebra", "derivatives"),
    "Стереометрия: параллельность и перпендикулярность": ("geometry", "stereometry_parallel_perp"),

    # Grade 11
    "Объемы тел": ("geometry", "volumes"),
    "Первообразная и интеграл": ("algebra", "integrals"),
    "Показательные и логарифмические уравнения": ("algebra", "exp_log_equations"),
    "Тела вращения": ("geometry", "solids_of_revolution"),
    "Задачи на оптимизацию": ("algebra", "optimization"),
    "Комплексные числа и уравнения": ("algebra", "complex_numbers"),
}


def convert_latex_format(text):
    """Convert \\( ... \\) to $...$ format for consistency with existing PROBLEMS_DB."""
    if not text:
        return text
    # \\[ ... \\] → $$...$$
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    # \\( ... \\) → $...$
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text


def main():
    # Load source data
    src_path = os.path.join('data', 'adaptive_full_db.json')
    if not os.path.exists(src_path):
        print(f"ERROR: {src_path} not found!")
        sys.exit(1)

    with open(src_path, 'r', encoding='utf-8') as f:
        tasks = json.load(f)

    print(f"Loaded {len(tasks)} tasks from {src_path}")

    # Find max existing ID by parsing the file directly (avoid import issues)
    problems_path = 'problems.py'
    max_id = 0
    existing_count = 0
    try:
        with open(problems_path, 'r', encoding='utf-8') as f:
            content_check = f.read()
        # Count existing entries by "id": pattern
        id_matches = re.findall(r'"id":\s*(\d+)', content_check)
        if id_matches:
            ids = [int(x) for x in id_matches]
            max_id = max(ids)
            existing_count = len(ids)
    except FileNotFoundError:
        pass

    print(f"Existing PROBLEMS_DB: {existing_count} tasks, max ID: {max_id}")

    # Convert tasks
    next_id = max_id + 1
    converted = []
    unmapped_topics = set()

    for task in tasks:
        topic = task.get('topic', '')
        mapping = TOPIC_MAP.get(topic)

        if not mapping:
            unmapped_topics.add(topic)
            # Fallback: use generic mapping
            subject = 'algebra'
            subtopic = topic.lower().replace(' ', '_')[:30]
        else:
            subject, subtopic = mapping

        grade = int(task.get('grade', 5))
        level = int(task.get('level', 1))
        question = task.get('question', '')
        answer = str(task.get('answer', ''))

        # Convert LaTeX format
        question = convert_latex_format(question)
        answer = convert_latex_format(answer)

        converted.append({
            'id': next_id,
            'subject': subject,
            'subtopic': subtopic,
            'grade': grade,
            'difficulty': level,  # level 1-7 maps directly to difficulty
            'text': question,
            'answer': answer,
        })
        next_id += 1

    if unmapped_topics:
        print(f"\nWARNING: {len(unmapped_topics)} unmapped topics:")
        for t in sorted(unmapped_topics):
            print(f"  - {t}")

    print(f"\nConverted {len(converted)} tasks (IDs {max_id + 1} to {next_id - 1})")

    # Stats
    subjects = {}
    for t in converted:
        s = t['subject']
        subjects[s] = subjects.get(s, 0) + 1
    print("\nBy subject:")
    for s, c in sorted(subjects.items()):
        print(f"  {s}: {c}")

    grades = {}
    for t in converted:
        g = t['grade']
        grades[g] = grades.get(g, 0) + 1
    print("\nBy grade:")
    for g, c in sorted(grades.items()):
        print(f"  Grade {g}: {c}")

    # Write to problems.py — append to existing
    # Read existing file
    problems_path = 'problems.py'
    with open(problems_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the closing bracket of PROBLEMS_DB list
    # The file ends with something like:
    #     },
    # ]
    # We need to insert before the final ]

    # Remove trailing ] and whitespace
    content = content.rstrip()
    if content.endswith(']'):
        content = content[:-1].rstrip()
        # Make sure last entry has a comma
        if not content.endswith(','):
            content += ','
    else:
        print(f"ERROR: problems.py doesn't end with ']'. Last 50 chars: {content[-50:]}")
        sys.exit(1)

    # Generate new entries
    new_entries = []
    for task in converted:
        # Escape text for Python string
        text_escaped = task['text'].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        answer_escaped = task['answer'].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        entry = (
            f'    {{\n'
            f'        "id": {task["id"]},\n'
            f'        "subject": "{task["subject"]}",\n'
            f'        "subtopic": "{task["subtopic"]}",\n'
            f'        "grade": {task["grade"]},\n'
            f'        "difficulty": {task["difficulty"]},\n'
            f'        "text": "{text_escaped}",\n'
            f'        "answer": "{answer_escaped}"\n'
            f'    }}'
        )
        new_entries.append(entry)

    # Append
    new_content = content + '\n' + ',\n'.join(new_entries) + '\n]\n'

    # Backup
    backup_path = 'problems_backup_before_adaptive.py'
    with open(backup_path, 'w', encoding='utf-8') as f:
        with open(problems_path, 'r', encoding='utf-8') as orig:
            f.write(orig.read())
    print(f"\nBackup saved to {backup_path}")

    # Write
    with open(problems_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Written {len(converted)} new tasks to {problems_path}")
    print(f"Total tasks now: {existing_count + len(converted)}")

    # Verify
    try:
        # Quick syntax check
        compile(open(problems_path, 'r', encoding='utf-8').read(), problems_path, 'exec')
        print("\n✅ Syntax check PASSED")
    except SyntaxError as e:
        print(f"\n❌ Syntax error in {problems_path}: {e}")
        print("Restoring backup...")
        with open(backup_path, 'r', encoding='utf-8') as f:
            with open(problems_path, 'w', encoding='utf-8') as out:
                out.write(f.read())
        print("Backup restored.")
        sys.exit(1)

    # Final verification
    exec_globals = {}
    exec(compile(open(problems_path, 'r', encoding='utf-8').read(), problems_path, 'exec'), exec_globals)
    final_count = len(exec_globals['PROBLEMS_DB'])
    print(f"✅ Final verification: PROBLEMS_DB has {final_count} tasks")


if __name__ == '__main__':
    main()
