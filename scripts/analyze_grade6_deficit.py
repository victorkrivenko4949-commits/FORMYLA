#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализ дефицита задач для 6 класса и создание плана балансировки.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from models import db, AdaptiveTask

# Целевое распределение
TARGET_PER_TOPIC = 90  # задач на тему (10 тем × 90 = 900 всего)
TARGET_PER_LEVEL = 13  # задач на уровень в теме (90 / 7 ≈ 13)

TOPICS_GRADE6 = [
    'Признаки делимости и остатки',
    'НОД, НОК и основная теорема арифметики',
    'Дроби, доли и пропорции',
    'Графы (знакомства, турниры, маршруты)',
    'Принцип Дирихле',
    'Логика (рыцари и лжецы, логические таблицы)',
    'Разрезания и замощения',
    'Инварианты (четность, раскраски)',
    'Геометрия (периметры и площади)',
    'Комбинаторика (правило суммы и произведения)',
]


def analyze():
    with app.app_context():
        print("\n" + "="*70)
        print("АНАЛИЗ ЗАДАЧ 6 КЛАССА")
        print("="*70)

        total = AdaptiveTask.query.filter_by(class_level=6).count()
        print(f"\nВсего задач: {total}")
        print(f"Цель: {TARGET_PER_TOPIC * len(TOPICS_GRADE6)} задач")
        print(f"\n{'Тема':<45} {'Есть':>6} {'Цель':>6} {'Дефицит':>8}")
        print("-"*70)

        deficit_by_topic = {}
        total_deficit = 0

        for topic in TOPICS_GRADE6:
            count = AdaptiveTask.query.filter_by(
                class_level=6, topic=topic
            ).count()
            deficit = max(0, TARGET_PER_TOPIC - count)
            deficit_by_topic[topic] = deficit
            total_deficit += deficit
            status = "✅" if deficit == 0 else "❌"
            print(f"{status} {topic[:43]:<43} {count:>6} {TARGET_PER_TOPIC:>6} {deficit:>8}")

        print("-"*70)
        print(f"{'ИТОГО':<45} {total:>6} {TARGET_PER_TOPIC * len(TOPICS_GRADE6):>6} {total_deficit:>8}")

        # Анализ по уровням
        print(f"\n\n{'Уровень':<10} {'Есть':>6} {'Цель':>6} {'Дефицит':>8}")
        print("-"*35)
        for level in range(1, 8):
            count = AdaptiveTask.query.filter_by(
                class_level=6, difficulty_level=level
            ).count()
            target = TARGET_PER_LEVEL * len(TOPICS_GRADE6)
            deficit = max(0, target - count)
            print(f"Уровень {level}  {count:>6} {target:>6} {deficit:>8}")

        # Детальный план догенерации
        print(f"\n\n{'='*70}")
        print("ПЛАН ДОГЕНЕРАЦИИ")
        print("="*70)
        print(f"\nНужно сгенерировать: {total_deficit} задач")
        print("\nПо темам:")
        for topic, deficit in sorted(deficit_by_topic.items(), key=lambda x: -x[1]):
            if deficit > 0:
                print(f"  - {topic}: +{deficit} задач")

        # Сохраняем план в JSON
        import json
        plan = {
            'total_current': total,
            'total_target': TARGET_PER_TOPIC * len(TOPICS_GRADE6),
            'total_deficit': total_deficit,
            'by_topic': {
                topic: {
                    'current': AdaptiveTask.query.filter_by(
                        class_level=6, topic=topic
                    ).count(),
                    'target': TARGET_PER_TOPIC,
                    'deficit': deficit
                }
                for topic, deficit in deficit_by_topic.items()
            }
        }

        with open('grade6_deficit_plan.json', 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

        print(f"\n[OK] План сохранен в grade6_deficit_plan.json")
        return plan


if __name__ == "__main__":
    analyze()
