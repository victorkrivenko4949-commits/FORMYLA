# -*- coding: utf-8 -*-
"""
Сид-скрипт: заполнение таблицы olympiad_prep 8 олимпиадами.
UPSERT по slug — безопасно запускать повторно.

Запуск:
    python scripts/seed_olympiads.py
"""
import json
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, OlympiadPrep
from app import app

OLYMPIADS = [
    {
        "slug": "vsosh",
        "name": "Всероссийская олимпиада школьников по математике",
        "short_name": "ВсОШ",
        "description": (
            "Главная олимпиада страны. Победители и призёры заключительного этапа "
            "получают льготы при поступлении в вузы. Проводится в 4 этапа: школьный, "
            "муниципальный, региональный и заключительный. Охватывает все классы с 5 по 11."
        ),
        "grades": [5, 6, 7, 8, 9, 10, 11],
        "stages": [
            {"name": "Школьный", "date_range": "1 сен – 1 ноя 2026"},
            {"name": "Школьный (Сириус)", "date_range": "14–17 окт 2026"},
            {"name": "Муниципальный", "date_range": "8 ноя 2026"},
            {"name": "Региональный", "date_range": "2–3 фев 2027"},
            {"name": "Заключительный", "date_range": "14–20 апр 2027, Москва"},
        ],
        "official_url": "https://vos.olimpiada.ru",
        "logo_path": "/static/olympiads/vsosh.svg",
        "color_hex": "#22d3a6",
        "sort_order": 1,
    },
    {
        "slug": "turnir-gorodov",
        "name": "Международный математический Турнир городов",
        "short_name": "Турнир городов",
        "description": (
            "Международная математическая олимпиада для школьников 8–11 классов. "
            "Проводится в два тура — осенний и весенний, каждый с базовым и сложным вариантом. "
            "Задачи отличаются оригинальностью и нестандартным подходом."
        ),
        "grades": [8, 9, 10, 11],
        "stages": [
            {"name": "Осенний базовый (O-level)", "date_range": "Конец октября 2026"},
            {"name": "Осенний сложный (A-level)", "date_range": "Середина ноября 2026"},
            {"name": "Весенний базовый (O-level)", "date_range": "1 марта 2027"},
            {"name": "Весенний сложный (A-level)", "date_range": "15 марта 2027"},
            {"name": "Устный финал 11 кл", "date_range": "Конец марта 2027"},
        ],
        "official_url": "https://turgor.ru",
        "logo_path": "/static/olympiads/turnir-gorodov.svg",
        "color_hex": "#8b5cf6",
        "sort_order": 2,
    },
    {
        "slug": "euler",
        "name": "Олимпиада Эйлера",
        "short_name": "Эйлер",
        "description": (
            "Олимпиада для 8-классников, организованная Математическим институтом им. Эйлера "
            "в Санкт-Петербурге. Включает региональный и заключительный этапы. "
            "Отличный старт для будущих участников ВсОШ."
        ),
        "grades": [8],
        "stages": [
            {"name": "Региональный", "date_range": "Конец января 2027"},
            {"name": "Заключительный", "date_range": "Март – апрель 2027"},
        ],
        "official_url": "https://olimpiada.ru/activity/84",
        "logo_path": "/static/olympiads/euler.svg",
        "color_hex": "#3b82f6",
        "sort_order": 3,
    },
    {
        "slug": "lomonosov",
        "name": "Олимпиада школьников «Ломоносов»",
        "short_name": "Ломоносов",
        "description": (
            "Олимпиада МГУ им. М. В. Ломоносова для школьников 5–11 классов. "
            "Входит в перечень олимпиад РСОШ (I уровень). Победители получают "
            "значительные льготы при поступлении в МГУ и другие ведущие вузы."
        ),
        "grades": [5, 6, 7, 8, 9, 10, 11],
        "stages": [
            {"name": "Отборочный онлайн", "date_range": "Ноябрь – декабрь 2026"},
            {"name": "Заключительный очный", "date_range": "Февраль 2027"},
        ],
        "official_url": "https://olymp.msu.ru",
        "logo_path": "/static/olympiads/lomonosov.svg",
        "color_hex": "#ef4444",
        "sort_order": 4,
    },
    {
        "slug": "vysshaya-proba",
        "name": "Высшая проба (НИУ ВШЭ)",
        "short_name": "Высшая проба",
        "description": (
            "Олимпиада НИУ ВШЭ для школьников 7–11 классов. Входит в перечень РСОШ. "
            "Проводится в два этапа: отборочный (онлайн) и заключительный (очно). "
            "Даёт льготы при поступлении в ВШЭ и другие вузы."
        ),
        "grades": [7, 8, 9, 10, 11],
        "stages": [
            {"name": "Отборочный онлайн", "date_range": "Ноябрь 2026"},
            {"name": "Заключительный очный", "date_range": "Февраль 2027"},
        ],
        "official_url": "https://olymp.hse.ru",
        "logo_path": "/static/olympiads/vysshaya-proba.svg",
        "color_hex": "#f59e0b",
        "sort_order": 5,
    },
    {
        "slug": "matprazdnik",
        "name": "Математический праздник",
        "short_name": "Матпраздник",
        "description": (
            "Олимпиада для учеников 6–7 классов, организованная мехматом МГУ. "
            "Одна из самых массовых и любимых олимпиад для младших школьников. "
            "Задачи интересные и доступные, но требуют смекалки."
        ),
        "grades": [6, 7],
        "stages": [
            {"name": "Очный тур в МГУ", "date_range": "21 февраля 2027, 10:00, 2 часа"},
        ],
        "official_url": "https://mmo.mccme.ru/matprazdnik/",
        "logo_path": "/static/olympiads/matprazdnik.svg",
        "color_hex": "#ec4899",
        "sort_order": 6,
    },
    {
        "slug": "mmo",
        "name": "Московская математическая олимпиада",
        "short_name": "ММО",
        "description": (
            "Одна из старейших математических олимпиад России (с 1935 года). "
            "Проводится для школьников 8–11 классов. Задачи ММО славятся "
            "красотой и глубиной — отличная подготовка к ВсОШ."
        ),
        "grades": [8, 9, 10, 11],
        "stages": [
            {"name": "Регистрация", "date_range": "Декабрь 2026"},
            {"name": "Основной тур", "date_range": "Март 2027"},
        ],
        "official_url": "https://mmo.mccme.ru",
        "logo_path": "/static/olympiads/mmo.svg",
        "color_hex": "#14b8a6",
        "sort_order": 7,
    },
    {
        "slug": "pokori-vorobievy-gory",
        "name": "Покори Воробьёвы горы!",
        "short_name": "Покори Воробьёвы горы",
        "description": (
            "Олимпиада МГУ и «Московского комсомольца» для школьников 5–11 классов. "
            "Входит в перечень РСОШ (I уровень). Два этапа: отборочный (дистанционный) "
            "и заключительный (очный в МГУ и региональных площадках)."
        ),
        "grades": [5, 6, 7, 8, 9, 10, 11],
        "stages": [
            {"name": "Отборочный", "date_range": "Декабрь 2026"},
            {"name": "Заключительный", "date_range": "Март – апрель 2027"},
        ],
        "official_url": "https://pvg.mk.ru",
        "logo_path": "/static/olympiads/pokori-vorobievy-gory.svg",
        "color_hex": "#6366f1",
        "sort_order": 8,
    },
]


def seed():
    """Заполнить / обновить 8 олимпиад (UPSERT по slug)."""
    with app.app_context():
        # Ensure table exists
        db.create_all()

        created = 0
        updated = 0

        for data in OLYMPIADS:
            existing = OlympiadPrep.query.filter_by(slug=data["slug"]).first()
            if existing:
                # Update all fields except id
                existing.name = data["name"]
                existing.short_name = data["short_name"]
                existing.description = data["description"]
                existing.grades = json.dumps(data["grades"], ensure_ascii=False)
                existing.stages = json.dumps(data["stages"], ensure_ascii=False)
                existing.official_url = data["official_url"]
                existing.logo_path = data["logo_path"]
                existing.color_hex = data["color_hex"]
                existing.sort_order = data["sort_order"]
                existing.is_active = True
                updated += 1
            else:
                olympiad = OlympiadPrep(
                    slug=data["slug"],
                    name=data["name"],
                    short_name=data["short_name"],
                    description=data["description"],
                    grades=json.dumps(data["grades"], ensure_ascii=False),
                    stages=json.dumps(data["stages"], ensure_ascii=False),
                    official_url=data["official_url"],
                    logo_path=data["logo_path"],
                    color_hex=data["color_hex"],
                    sort_order=data["sort_order"],
                    is_active=True,
                )
                db.session.add(olympiad)
                created += 1

        db.session.commit()
        print(f"✅ Сид олимпиад завершён: создано {created}, обновлено {updated}")
        print(f"   Всего в БД: {OlympiadPrep.query.count()} олимпиад")


if __name__ == '__main__':
    seed()
