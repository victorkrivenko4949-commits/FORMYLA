# -*- coding: utf-8 -*-
"""
Seed-скрипт для таблицы reviews.

Запуск:
    python -m scripts.seed_reviews
или:
    python scripts/seed_reviews.py

Создаёт 6 заготовок отзывов (is_published=False) — администратор заполнит
реальными текстами/именами вручную через /admin/reviews, либо просто
переключит is_published=True.

Идемпотентно: если в таблице уже есть >=6 записей — не делает ничего.
"""
from __future__ import annotations

import os
import sys

# Make project root importable when run as a script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app  # noqa: E402
from models import db, Review  # noqa: E402


SEEDS = [
    {
        'name': 'Артём К.',
        'role': 'ученик',
        'grade': '9 класс',
        'text': 'За 2 месяца на FORMYLA подтянул комбинаторику и геометрию — '
                'на муниципальном этапе ВсОШ вышел в призёры. ИИ-тьютор '
                'разъясняет каждый шаг, не приходится ждать репетитора.',
        'rating': 5,
        'sort_order': 10,
    },
    {
        'name': 'Мария О.',
        'role': 'родитель',
        'grade': '7 класс',
        'text': 'Ребёнок сам стал садиться за задачи — это уже победа. '
                'Понравился радар сильных/слабых сторон после теста: видно, '
                'над чем работать, без размытых рекомендаций.',
        'rating': 5,
        'sort_order': 20,
    },
    {
        'name': 'Илья В.',
        'role': 'преподаватель',
        'grade': '',
        'text': 'Использую платформу как банк задач для кружка. Разборы по '
                '89 методам — отличный материал для теории, ребята легко '
                'находят аналоги школьных конструкций.',
        'rating': 5,
        'sort_order': 30,
    },
    {
        'name': 'София Л.',
        'role': 'ученица',
        'grade': '10 класс',
        'text': 'Главное — это персональный план на 12 недель. Я не теряюсь '
                '"с чего начать", открываю приложение и сразу решаю свою '
                'дневную задачу. Streak уже 47 дней.',
        'rating': 5,
        'sort_order': 40,
    },
    {
        'name': 'Дмитрий П.',
        'role': 'родитель',
        'grade': '8 класс',
        'text': 'Сравнивали с очным репетитором — FORMYLA даёт более '
                'структурную программу за в 5 раз меньшую цену. Сын прошёл '
                'школьный этап на полные баллы впервые в жизни.',
        'rating': 5,
        'sort_order': 50,
    },
    {
        'name': 'Алина Ш.',
        'role': 'ученица',
        'grade': '11 класс',
        'text': 'Готовилась к региональному этапу. Бесплатный пробник '
                'показал реальный уровень, без иллюзий. План подготовки '
                'действительно адаптируется — задачи становятся сложнее '
                'постепенно.',
        'rating': 5,
        'sort_order': 60,
    },
]


def main() -> None:
    with app.app_context():
        db.create_all()  # safety net, если таблица ещё не создана
        existing = Review.query.count()
        if existing >= len(SEEDS):
            print(f'[seed_reviews] уже есть {existing} отзывов — пропускаю.')
            return

        created = 0
        for item in SEEDS:
            # уникальность по (name, grade) — чтобы повторный запуск не плодил дубли.
            q = Review.query.filter_by(
                name=item['name'],
                grade=item['grade'] or None,
            )
            if q.first():
                continue
            r = Review(
                name=item['name'],
                role=item['role'] or None,
                grade=item['grade'] or None,
                text=item['text'],
                rating=item.get('rating', 5),
                avatar_url=None,
                is_published=False,   # admin вручную проверит и опубликует
                sort_order=item.get('sort_order', 0),
            )
            db.session.add(r)
            created += 1
        db.session.commit()
        print(f'[seed_reviews] создано: {created}, всего в БД: {Review.query.count()}')


if __name__ == '__main__':
    main()
