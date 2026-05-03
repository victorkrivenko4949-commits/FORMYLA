#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create generation plan for grade 11 adaptive test (1050 tasks)."""
import json, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_FILE = os.path.join(BASE_DIR, 'data', 'audit', 'grade11_gen_plan.json')

# Grade 11: 1050 tasks, 8 topics, 5 levels (L1-L5)
# Target per level: L1=120, L2=180, L3=200, L4=200, L5=180, L6=120, L7=50
# But we only do L1-L5 for now (total 880), rest later
# Actually let's do all 1050 in L1-L5 with proper distribution:
# L1: 120, L2: 210, L3: 300, L4: 240, L5: 180 = 1050

TOPICS_WITH_COUNTS = [
    # (topic_name, total_count)
    ('Алгебра (полиномы, системы, параметры)', 250),
    ('Комбинаторика и вероятность', 130),
    ('Теория чисел (делимость, сравнения, диофантовы)', 120),
    ('Планиметрия (окружности, подобие, площади)', 150),
    ('Стереометрия (объёмы, сечения, расстояния)', 180),
    ('Тригонометрия (уравнения, неравенства, тождества)', 100),
    ('Функции и анализ (производная, экстремумы, интеграл)', 80),
    ('Комплексные числа и продвинутая алгебра', 40),
]
# Total: 250+130+120+150+180+100+80+40 = 1050 ✓

# Level weights (proportional distribution within each topic)
LEVEL_WEIGHTS = {1: 0.11, 2: 0.20, 3: 0.29, 4: 0.23, 5: 0.17}
# 0.11+0.20+0.29+0.23+0.17 = 1.00

plan = []
total = 0

for topic, topic_total in TOPICS_WITH_COUNTS:
    remaining = topic_total
    level_counts = {}
    
    # Assign counts per level
    for lvl in [1, 2, 3, 4]:
        count = round(topic_total * LEVEL_WEIGHTS[lvl])
        level_counts[lvl] = count
        remaining -= count
    level_counts[5] = remaining  # Give remainder to L5
    
    for lvl, count in sorted(level_counts.items()):
        if count > 0:
            plan.append({
                'topic': topic,
                'difficulty': lvl,
                'count': count,
                'priority': 1
            })
            total += count

print(f'Grade 11 plan: {len(plan)} items, {total} tasks')

os.makedirs(os.path.dirname(PLAN_FILE), exist_ok=True)
json.dump(plan, open(PLAN_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Saved to {PLAN_FILE}')

print('\nBy level:')
for lvl in range(1, 6):
    c = sum(p['count'] for p in plan if p['difficulty'] == lvl)
    print(f'  L{lvl}: {c}')

print('\nBy topic:')
for topic, expected in TOPICS_WITH_COUNTS:
    c = sum(p['count'] for p in plan if p['topic'] == topic)
    print(f'  {topic}: {c} (target {expected})')
