#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Шаг 0: Нормализация и импорт OLYMPIADS_DB → problems_archive.

Запуск:
    python scripts/import_archive.py [--dry-run]

Что делает:
1. Загружает OLYMPIADS_DB (798 комбо, ~4000+ задач)
2. Нормализует olympiad_title и round
3. Группирует по (olympiad_slug, grade, round_normalized)
4. Импортирует в таблицу problems_archive
5. Выводит статистику по комбинациям

Идемпотентность: перед импортом очищает таблицу (TRUNCATE/DELETE).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict

# ─── Нормализация round ──────────────────────────────────────────────────────

ROUND_NORMALIZATION = {
    # Прямые маппинги
    'school': 'school',
    'municipal': 'municipal',
    'regional': 'regional',
    'final': 'final',
    'qualifying': 'selection',
    'selection': 'selection',
    'distance': 'distance',
    # Сезонные туры
    'spring_hard': 'spring_hard',
    'spring_base': 'spring_basic',
    'spring_basic': 'spring_basic',
    'autumn_hard': 'autumn_hard',
    'autumn_base': 'autumn_basic',
    'autumn_basic': 'autumn_basic',
    'fall_hard': 'autumn_hard',
    'fall_basic': 'autumn_basic',
    # Нумерованные раунды → selection
    '1': 'selection',
    '2': 'selection',
}


def normalize_round(raw_round: str) -> str:
    """Нормализует значение round к стандартному enum."""
    if not raw_round:
        return 'unknown'

    raw = raw_round.strip().lower()

    # Прямой маппинг
    if raw in ROUND_NORMALIZATION:
        return ROUND_NORMALIZATION[raw]

    # Паттерны для русских названий (на случай если в БД есть)
    if 'школьн' in raw:
        return 'school'
    if 'муниципальн' in raw:
        return 'municipal'
    if 'региональн' in raw:
        return 'regional'
    if 'заключительн' in raw or 'финал' in raw:
        return 'final'
    if 'отборочн' in raw:
        return 'selection'
    if 'дистанционн' in raw:
        return 'distance'
    if 'весенн' in raw and 'базов' in raw:
        return 'spring_basic'
    if 'весенн' in raw and 'сложн' in raw:
        return 'spring_hard'
    if 'осенн' in raw and 'базов' in raw:
        return 'autumn_basic'
    if 'осенн' in raw and 'сложн' in raw:
        return 'autumn_hard'

    # Fallback
    return raw


# ─── Нормализация olympiad_title ─────────────────────────────────────────────

OLYMPIAD_TITLES = {
    'euler': 'Олимпиада Эйлера',
    'formula_unity': 'Формула Единства',
    'kurchatov': 'Курчатов',
    'lomonosov': 'Ломоносов',
    'phystech': 'МФТИ',
    'pvg': 'Покори Воробьёвы горы',
    'spbgu': 'СПбГУ',
    'turgor': 'Турнир городов',
    'vsosh': 'ВсОШ',
    'vysshaya_proba': 'Высшая проба',
}


def normalize_title(slug: str, raw_title: str) -> str:
    """Возвращает каноническое название олимпиады."""
    return OLYMPIAD_TITLES.get(slug, raw_title or slug)


# ─── Основная логика ─────────────────────────────────────────────────────────

def load_and_normalize():
    """Загружает OLYMPIADS_DB и нормализует."""
    from olympiads import OLYMPIADS_DB

    records = []
    combos = defaultdict(list)

    for combo in OLYMPIADS_DB:
        slug = combo.get('olympiad', '')
        raw_title = combo.get('olympiad_title', '')
        grade = combo.get('grade')
        raw_round = combo.get('round', '')
        round_title = combo.get('round_title', '')
        year = combo.get('year')
        combo_id = combo.get('id')

        # Нормализация
        norm_round = normalize_round(raw_round)
        norm_title = normalize_title(slug, raw_title)

        # Ensure grade is int
        try:
            grade = int(grade)
        except (TypeError, ValueError):
            grade = 0

        # Ensure year is int
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None

        problems = combo.get('problems', [])
        for prob in problems:
            text = prob.get('text', '').strip()
            if not text:
                continue

            record = {
                'olympiad_slug': slug,
                'olympiad_title': norm_title,
                'grade': grade,
                'round': norm_round,
                'round_title': round_title,
                'year': year,
                'num': prob.get('num'),
                'text': text,
                'answer': prob.get('answer', ''),
                'solution': prob.get('solution', ''),
                'source': 'olympiads.py',
                'combo_id': combo_id,
            }
            records.append(record)
            combos[(slug, grade, norm_round)].append(record)

    return records, combos


def import_to_db(records, dry_run=False):
    """Импортирует записи в problems_archive."""
    from app import app
    from models import db

    with app.app_context():
        db_url = str(db.engine.url)
        is_postgres = 'postgresql' in db_url or 'postgres' in db_url

        # Check table exists
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'problems_archive' not in inspector.get_table_names():
            print("❌ Таблица problems_archive не найдена!")
            print("   Сначала запустите: python migrations/add_daily_pool_tables.py")
            return False

        if dry_run:
            print(f"🔍 DRY RUN: {len(records)} записей готовы к импорту")
            return True

        # Clear existing data
        count_before = db.session.execute(
            db.text("SELECT COUNT(*) FROM problems_archive")
        ).scalar()

        if count_before > 0:
            print(f"⚠️  Очистка {count_before} существующих записей...")
            db.session.execute(db.text("DELETE FROM problems_archive"))
            db.session.commit()

        # Batch insert
        BATCH_SIZE = 100
        inserted = 0

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]

            for rec in batch:
                db.session.execute(
                    db.text("""
                        INSERT INTO problems_archive 
                            (olympiad_slug, olympiad_title, grade, round, 
                             round_title, year, num, text, answer, solution, 
                             source, combo_id)
                        VALUES 
                            (:olympiad_slug, :olympiad_title, :grade, :round,
                             :round_title, :year, :num, :text, :answer, :solution,
                             :source, :combo_id)
                    """),
                    rec
                )
                inserted += 1

            db.session.commit()

            if (i + BATCH_SIZE) % 500 == 0 or i + BATCH_SIZE >= len(records):
                print(f"  📥 Imported {inserted}/{len(records)}...")

        print(f"\n✅ Импорт завершён: {inserted} задач в problems_archive")
        return True


def print_stats(combos):
    """Выводит статистику по комбинациям."""
    print("\n" + "=" * 70)
    print(f"📊 СТАТИСТИКА НОРМАЛИЗАЦИИ")
    print("=" * 70)
    print(f"\nВсего уникальных комбинаций (olympiad, grade, round): {len(combos)}")
    print(f"Всего задач: {sum(len(v) for v in combos.values())}")

    # По олимпиадам
    print("\n── По олимпиадам ──")
    by_olympiad = defaultdict(int)
    for (slug, grade, rnd), problems in combos.items():
        by_olympiad[slug] += len(problems)
    for slug, cnt in sorted(by_olympiad.items(), key=lambda x: -x[1]):
        title = OLYMPIAD_TITLES.get(slug, slug)
        print(f"  {title:25s} ({slug:20s}): {cnt:4d} задач")

    # По раундам
    print("\n── По раундам (нормализованным) ──")
    by_round = defaultdict(int)
    for (slug, grade, rnd), problems in combos.items():
        by_round[rnd] += len(problems)
    for rnd, cnt in sorted(by_round.items(), key=lambda x: -x[1]):
        print(f"  {rnd:15s}: {cnt:4d} задач")

    # По классам
    print("\n── По классам ──")
    by_grade = defaultdict(int)
    for (slug, grade, rnd), problems in combos.items():
        by_grade[grade] += len(problems)
    for grade, cnt in sorted(by_grade.items()):
        print(f"  {grade:2d} класс: {cnt:4d} задач")

    # Топ-10 комбинаций по количеству задач
    print("\n── Топ-20 комбинаций (больше всего задач) ──")
    sorted_combos = sorted(combos.items(), key=lambda x: -len(x[1]))
    for (slug, grade, rnd), problems in sorted_combos[:20]:
        title = OLYMPIAD_TITLES.get(slug, slug)
        print(f"  {title:20s} {grade:2d}кл {rnd:15s}: {len(problems):3d} задач")

    # Комбинации с малым количеством задач (< 10)
    small = [(k, v) for k, v in combos.items() if len(v) < 10]
    if small:
        print(f"\n⚠️  Комбинации с < 10 задачами ({len(small)} шт):")
        for (slug, grade, rnd), problems in sorted(small, key=lambda x: len(x[1])):
            title = OLYMPIAD_TITLES.get(slug, slug)
            print(f"  {title:20s} {grade:2d}кл {rnd:15s}: {len(problems):3d} задач")


def main():
    dry_run = '--dry-run' in sys.argv

    print("🔄 Загрузка и нормализация OLYMPIADS_DB...")
    records, combos = load_and_normalize()

    print_stats(combos)

    if dry_run:
        print("\n🔍 DRY RUN — в БД ничего не записано")
        print(f"   Готово к импорту: {len(records)} задач")
    else:
        print("\n📥 Импорт в problems_archive...")
        import_to_db(records)


if __name__ == '__main__':
    main()
