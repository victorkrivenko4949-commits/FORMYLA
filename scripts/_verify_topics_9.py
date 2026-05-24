# -*- coding: utf-8 -*-
"""
Smoke-тест: проверяем, что для 9 класса страница выбора темы адаптивного теста
вернёт ровно 7 тем из реестра, все с count > 0, среди них есть
«Логика, инварианты, стратегии», и нет «Задач на движение» и «Рыцарей и лжецов».

Запуск:
    python -c "import sys; sys.path.insert(0,'.'); exec(open('scripts/_verify_topics_9.py', encoding='utf-8').read())"
"""

import sys
sys.path.insert(0, '.')

from app import app
from models import AdaptiveTask
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE

GRADE = 9
MIN_TASKS = 10


def main():
    with app.app_context():
        registry = ADAPTIVE_TOPICS_BY_GRADE.get(GRADE, [])
        assert len(registry) == 7, f"Ожидаем 7 тем для {GRADE} класса, получили {len(registry)}"

        all_tasks = AdaptiveTask.query.filter_by(
            class_level=GRADE, is_flagged=False
        ).all()
        by_topic = {}
        for t in all_tasks:
            if t.topic:
                k = t.topic.strip()
                by_topic[k] = by_topic.get(k, 0) + 1

        print(f"=== Smoke-test: класс {GRADE} ===")
        print(f"Всего задач в БД для класса {GRADE} (без флагов): {len(all_tasks)}")
        print(f"Уникальных тем в БД: {len(by_topic)}\n")

        print("Темы из реестра → счётчик в БД:")
        ok = True
        topics_view = []
        for entry in registry:
            count = by_topic.get(entry['db_topic'], 0)
            available = count >= MIN_TASKS
            topics_view.append({
                'name': entry['name'],
                'count': count,
                'available': available,
                'emoji': entry['emoji'],
                'key': entry['key'],
            })
            status = '✅' if available else '❌'
            print(f"  {status} {entry['emoji']} {entry['name']:55s} → {count:4d} задач  (key={entry['key']})")
            if not available:
                ok = False

        # Главное: «Логика, инварианты, стратегии» должна быть и быть доступна
        logic_entry = next(
            (t for t in topics_view if 'Логика, инварианты, стратегии' in t['name']),
            None
        )
        assert logic_entry is not None, "Тема 'Логика, инварианты, стратегии' отсутствует в реестре 9 класса!"
        assert logic_entry['available'], (
            f"Тема 'Логика, инварианты, стратегии' недоступна: count={logic_entry['count']}"
        )

        # Не должно быть «движения» и «рыцарей и лжецов» среди отображаемых тем
        names = [t['name'].lower() for t in topics_view]
        assert not any('движен' in n for n in names), "В реестре 9 класса не должно быть «Движения»"
        assert not any('рыцар' in n or 'лжец' in n for n in names), (
            "В реестре 9 класса не должно быть «Рыцарей и лжецов»"
        )

        assert ok, "Не все темы 9 класса доступны (count >= 10)!"

        print("\n✅ Smoke-test пройден: для 9 класса все 7 тем имеют ≥ 10 задач,")
        print("   среди них «Логика, инварианты, стратегии», без «Движения» и «Рыцарей и лжецов».")
        return 0


if __name__ == '__main__':
    sys.exit(main())
else:
    main()
