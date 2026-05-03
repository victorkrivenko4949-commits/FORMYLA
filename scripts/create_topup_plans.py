#!/usr/bin/env python3
"""Create top-up plans for grades that need more tasks to reach 1050."""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_DIR = os.path.join(BASE, 'data', 'audit')

# Grade 10: need 588 more tasks
# Topics for grade 10 (school program: all algebra, geometry, trig, etc.)
grade10_plan = []
topics_10 = [
    ("Алгебра (уравнения, неравенства, системы)", 120),
    ("Геометрия (планиметрия, окружности)", 100),
    ("Тригонометрия", 80),
    ("Комбинаторика и теория вероятностей", 80),
    ("Теория чисел (делимость, остатки)", 70),
    ("Логика и инварианты", 60),
    ("Функции и графики", 50),
    ("Последовательности и прогрессии", 28),
]
# Level weights: L1=11%, L2=20%, L3=29%, L4=23%, L5=17%
weights = {1: 0.11, 2: 0.20, 3: 0.29, 4: 0.23, 5: 0.17}
for topic, total in topics_10:
    for lvl, w in weights.items():
        count = max(1, round(total * w))
        grade10_plan.append({"topic": topic, "difficulty": lvl, "count": count, "priority": 1})

# Grade 11: need 93 more tasks
grade11_plan = []
topics_11 = [
    ("Алгебра (полиномы, системы, параметры)", 25),
    ("Планиметрия (окружности, подобие, площади)", 25),
    ("Стереометрия (объёмы, сечения, расстояния)", 20),
    ("Тригонометрия (уравнения, неравенства, тождества)", 10),
    ("Комбинаторика и вероятность", 8),
    ("Теория чисел (делимость, сравнения, диофантовы)", 5),
]
for topic, total in topics_11:
    for lvl, w in weights.items():
        count = max(1, round(total * w))
        if count > 0:
            grade11_plan.append({"topic": topic, "difficulty": lvl, "count": count, "priority": 1})

# Grade 8: need 12 more
grade8_plan = [
    {"topic": "Алгебраические тождества и преобразования", "difficulty": 3, "count": 4, "priority": 1},
    {"topic": "Геометрические доказательства", "difficulty": 3, "count": 4, "priority": 1},
    {"topic": "Теория чисел", "difficulty": 3, "count": 4, "priority": 1},
]

# Grade 9: need 4 more
grade9_plan = [
    {"topic": "Алгебраические тождества и преобразования", "difficulty": 3, "count": 2, "priority": 1},
    {"topic": "Геометрические доказательства", "difficulty": 3, "count": 2, "priority": 1},
]

# Save plans
plans = {
    10: grade10_plan,
    11: grade11_plan,
    8: grade8_plan,
    9: grade9_plan,
}

for grade, plan in plans.items():
    total = sum(p['count'] for p in plan)
    path = os.path.join(AUDIT_DIR, f'grade{grade}_gen_plan.json')
    json.dump(plan, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"Grade {grade}: {total} tasks planned -> {path}")

# Reset checkpoints for fresh run
for grade in [8, 9, 10, 11]:
    cp_path = os.path.join(AUDIT_DIR, f'gen_progress_grade{grade}.json')
    if os.path.exists(cp_path):
        os.rename(cp_path, cp_path + '.bak')
        print(f"  Backed up checkpoint: {cp_path}")

print("\nDone! Now run: python scripts/generate_grade.py <grade>")
