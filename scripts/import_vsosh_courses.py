# -*- coding: utf-8 -*-
"""
Импорт курсов ВсОШ 2027 из CSV → таблица vsosh_course_entries.

Запуск:
    cd <project_root>
    flask shell
    >>> exec(open('scripts/import_vsosh_courses.py', encoding='utf-8').read())

Или напрямую:
    python -c "exec(open('scripts/import_vsosh_courses.py', encoding='utf-8').read())"
    (при условии, что в PYTHONPATH есть app)
"""
import csv
import logging
import os
import sys

# ── Bootstrap Flask app ────────────────────────────────────────────────
# Позволяет запускать скрипт напрямую: python scripts/import_vsosh_courses.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app as _flask_app

with _flask_app.app_context():
    from models import db
    from models_olympiad import VserossCourseEntry

    logger = logging.getLogger('import_vsosh_courses')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler(sys.stdout))

    CSV_PATH = os.path.expanduser(r'~\Downloads\vsosh_kursy_2027_full.csv')

    # ── Читаем CSV ─────────────────────────────────────────────────────
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    logger.info('CSV прочитан: %d строк', len(rows))

    # ── Фильтр: только Включить_2027 == True ──────────────────────────
    included = [
        r for r in rows
        if r.get('Включить_2027', '').strip().lower() == 'true'
    ]
    logger.info('Включить_2027=True: %d строк', len(included))

    # ── Confidence mapping ─────────────────────────────────────────────
    def _map_confidence(label):
        """Маппинг текстовой уверенности → числовой уровень (3/2/1)."""
        if '🟢' in label:
            return 3
        if '🟡' in label:
            return 2
        if '⚪' in label:
            return 1
        return 0

    # ── Сортируем: confidence_level DESC, Прогноз2027 DESC ────────────
    def _sort_key(r):
        conf = _map_confidence(r.get('Уверенность', ''))
        forecast_str = r.get('Прогноз2027', '0').replace(',', '.')
        try:
            forecast = float(forecast_str)
        except (ValueError, TypeError):
            forecast = 0.0
        return (-conf, -forecast)

    included.sort(key=_sort_key)

    # ── UPSERT ─────────────────────────────────────────────────────────
    created = 0
    updated = 0

    for idx, r in enumerate(included):
        grade_str = r.get('Класс', '').strip()
        try:
            grade = int(grade_str)
        except (ValueError, TypeError):
            logger.warning('  [skip] строка %d: неверный класс "%s"', idx, grade_str)
            continue

        stage = r.get('Этап', '').strip()
        method_code = r.get('Код', '').strip()
        method_name = r.get('Метод', '').strip()
        section = r.get('Раздел', '').strip() or None
        confidence_label = r.get('Уверенность', '').strip() or None
        confidence_level = _map_confidence(confidence_label or '')
        forecast_str = r.get('Прогноз2027', '0').replace(',', '.')
        try:
            forecast = float(forecast_str)
        except (ValueError, TypeError):
            forecast = None

        study_order = r.get('Очередь_изучения', '').strip() or None
        importance = r.get('Приоритет', '').strip() or None
        reason = r.get('Почему', '').strip() or None
        regularity = r.get('Закономерность', '').strip() or None
        trend_str = r.get('Тренд', '0').replace(',', '.')
        try:
            trend = float(trend_str)
        except (ValueError, TypeError):
            trend = None

        def _int(val):
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        appearances = _int(r.get('Появлений', ''))
        last_year = _int(r.get('Последний', ''))
        total_count = _int(r.get('Всего', ''))
        sum_2021_25 = _int(r.get('Сумма2021_25', ''))

        # Поиск существующей записи (UPSERT)
        entry = VserossCourseEntry.query.filter_by(
            grade=grade,
            stage=stage,
            method_code=method_code,
        ).first()

        if entry:
            # UPDATE
            entry.method_name = method_name
            entry.section = section
            entry.forecast_2027 = forecast
            entry.study_order = study_order
            entry.importance = importance
            entry.confidence_label = confidence_label
            entry.confidence_level = confidence_level
            entry.appearances = appearances
            entry.last_year = last_year
            entry.total_count = total_count
            entry.sum_2021_25 = sum_2021_25
            entry.trend = trend
            entry.regularity = regularity
            entry.reason = reason
            entry.sort_order = idx
            updated += 1
        else:
            # CREATE
            entry = VserossCourseEntry(
                grade=grade,
                stage=stage,
                method_code=method_code,
                method_name=method_name,
                section=section,
                forecast_2027=forecast,
                study_order=study_order,
                importance=importance,
                confidence_label=confidence_label,
                confidence_level=confidence_level,
                appearances=appearances,
                last_year=last_year,
                total_count=total_count,
                sum_2021_25=sum_2021_25,
                trend=trend,
                regularity=regularity,
                reason=reason,
                sort_order=idx,
            )
            db.session.add(entry)
            created += 1

    db.session.commit()

    # ── ПРОВЕРКА ──────────────────────────────────────────────────────
    logger.info('')
    logger.info('═' * 60)
    logger.info('РЕЗУЛЬТАТ ИМПОРТА')
    logger.info('═' * 60)
    logger.info('Создано: %d | Обновлено: %d', created, updated)

    # Проверка: 3 курса (grade: 9, 10, 11)
    grades_in_db = (
        db.session.query(VserossCourseEntry.grade)
        .distinct()
        .order_by(VserossCourseEntry.grade)
        .all()
    )
    grades_in_db = [g[0] for g in grades_in_db]
    logger.info('Классы (курсы) в БД: %s', grades_in_db)
    assert len(grades_in_db) == 3, (
        f'Ожидалось 3 курса (9, 10, 11), получено {len(grades_in_db)}'
    )

    # Проверка: у каждого курса 4 этапа
    for g in grades_in_db:
        stages = (
            db.session.query(VserossCourseEntry.stage)
            .filter_by(grade=g)
            .distinct()
            .all()
        )
        stages = [s[0] for s in stages]
        logger.info('  Класс %d: этапы %s (всего %d)', g, stages, len(stages))
        assert len(stages) == 4, (
            f'Класс {g}: ожидалось 4 этапа, получено {len(stages)}'
        )

    # Проверка: суммарно методов = числу строк Включить_2027==True
    total_entries = VserossCourseEntry.query.count()
    logger.info('Всего записей в БД: %d', total_entries)
    logger.info('Всего строк Включить_2027=True в CSV: %d', len(included))
    assert total_entries == len(included), (
        f'Несовпадение: в БД {total_entries}, в CSV {len(included)}'
    )

    # Детальная статистика
    for g in grades_in_db:
        for s in ['Школьный', 'Муниципальный', 'Региональный', 'Заключительный']:
            cnt = VserossCourseEntry.query.filter_by(grade=g, stage=s).count()
            if cnt:
                confs = (
                    db.session.query(VserossCourseEntry.confidence_level)
                    .filter_by(grade=g, stage=s)
                    .order_by(VserossCourseEntry.confidence_level.desc())
                    .all()
                )
                levels = [c[0] for c in confs]
                logger.info(
                    '  Класс %d | %s: %d методов (уверенность: '
                    '🟢=%d 🟡=%d ⚪=%d)',
                    g, s, cnt,
                    levels.count(3), levels.count(2), levels.count(1),
                )

    logger.info('')
    logger.info('✅ ИМПОРТ ЗАВЕРШЁН УСПЕШНО')
