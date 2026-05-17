# -*- coding: utf-8 -*-
"""Проверка покрытия задач адаптивного теста по всем (grade, тема)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db
from models_grade import GradeTask, GRADE_DOMAINS, DOMAIN_LABELS

# Та же логика что в app.adaptive_test_select_topic (для 7-11):
from services.adaptive_topic_mapping import get_keywords_for_grade_topic
from models import AdaptiveTask  # type: ignore

CLASSIC = [
    ('algebra',       'Алгебра'),
    ('geometry',      'Геометрия'),
    ('combinatorics', 'Комбинаторика'),
    ('number_theory', 'Теория чисел'),
    ('kl_movement',   'Задачи на движение'),
    ('knights_liars', 'Рыцари и лжецы'),
]
FALLBACK = {
    'algebra': ['алгебра', 'выражения', 'одночлен', 'многочлен', 'формул'],
    'geometry': ['геометрия', 'треугольник', 'четырехугольник', 'окружность',
                 'вектор', 'площад', 'стереометр', 'многогранник',
                 'тела вращения', 'объем'],
    'combinatorics': ['комбинатор', 'вероятност', 'перестановк', 'размещен', 'сочетан'],
    'number_theory': ['натуральн', 'делимост', 'положительн', 'отрицательн',
                      'рациональн', 'числ', 'НОД', 'НОК'],
    'kl_movement': ['движен', 'текстовые задачи', 'совместная работа'],
    'knights_liars': ['рыцар', 'лжец'],
}
MIN_TASKS = 10


def main():
    with app.app_context():
        print('=' * 70)
        print('ПОКРЫТИЕ АДАПТИВНОГО ТЕСТА (>=', MIN_TASKS, 'задач = доступно)')
        print('=' * 70)

        # 5–6 классы → GradeTask
        for g in (5, 6):
            print('\n--- %d класс (GradeTask) ---' % g)
            for d in GRADE_DOMAINS.get(g, ()):
                n = GradeTask.query.filter_by(grade=g, domain=d).count()
                ok = '[OK]' if n >= MIN_TASKS else '[LOW]'
                lbl = DOMAIN_LABELS.get(d, d)
                print('  %s grade=%d %-38s %5d  %s' % (ok, g, d, n, lbl))

        # 7–11 классы → AdaptiveTask + keyword-фильтр
        for g in (7, 8, 9, 10, 11):
            print('\n--- %d класс (AdaptiveTask, keyword filter) ---' % g)
            all_t = AdaptiveTask.query.filter_by(
                class_level=g, is_flagged=False
            ).all()
            for key, name in CLASSIC:
                internal = 'movement' if key == 'kl_movement' else key
                kws = get_keywords_for_grade_topic(g, internal) \
                      or FALLBACK.get(key, [])
                kws_l = [k.lower() for k in kws]
                if not kws_l:
                    n = len(all_t)
                else:
                    n = sum(1 for t in all_t
                            if t.topic and any(k in t.topic.lower() for k in kws_l))
                ok = '[OK]' if n >= MIN_TASKS else '[LOW]'
                print('  %s grade=%d %-18s %5d  %s' % (ok, g, key, n, name))


if __name__ == '__main__':
    main()
