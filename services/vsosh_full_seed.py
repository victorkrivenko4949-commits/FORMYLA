# -*- coding: utf-8 -*-
r"""Production-сидер ВсОШ-9/10/11 (сезон 2027) для Render.

Идемпотентно перезаливает данные из двух JSON-файлов в репозитории:
  data/olympiads/vsosh9_full.json     — 7 topic-пробников × 20 задач = 140
  data/olympiads/vsosh_10_11_full.json — 43 method-пробника × 20 = 860

При каждом старте:
  1. Считает Probnik с code LIKE 'vsosh-%-2027-%'.
  2. Если совпадает с ожидаемым (50 пробников, 1000 OlympiadTask) — пропускает.
  3. Иначе: удаляет старые vsosh-2027 пробники + связанные задачи,
     вставляет свежие из JSON.

Вызывается из app.py при VSOSH9_2027_FORCE_IMPORT=1. Защищён от падений
(try/except + rollback), чтобы не валить старт сервера.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# difficulty маппинг для 10/11: число 1..4 -> цвет
_DIFF_NUM_TO_COLOR = {1: 'green', 2: 'yellow', 3: 'orange', 4: 'red'}
_VALID_DIFF_COLORS = {'green', 'yellow', 'orange', 'red'}

# Заголовки тем для 9 класса
_TOPIC_TITLES_9 = {
    1: 'Тема 1: Алгебра — преобразования и тождества',
    2: 'Тема 2: Уравнения и системы',
    3: 'Тема 3: Неравенства и оценки',
    4: 'Тема 4: Числа и делимость',
    5: 'Тема 5: Комбинаторика и логика',
    6: 'Тема 6: Геометрия I',
    7: 'Тема 7: Геометрия II',
}

# Секции для 10/11 по первой букве method_code
_SECTION_BY_LETTER = {
    'A': 'Алгебра',
    'B': 'Базовая школа',
    'C': 'Геометрия',
    'D': 'Делимость и числа',
    'E': 'Комбинаторика',
    'F': 'Логика и игры',
    'G': 'Геометрия II',
    'H': 'Прочее',
}

EXPECTED_PROBNIKS_TOTAL = 50      # 7 (9 кл) + 43 (10/11 кл)
EXPECTED_OLY_TASKS_TOTAL = 1000   # 140 + 860


def _file_paths(app):
    """Пути к JSON-файлам в репо."""
    root = Path(app.root_path) if hasattr(app, 'root_path') else Path.cwd()
    return (
        root / 'data' / 'olympiads' / 'vsosh9_full.json',
        root / 'data' / 'olympiads' / 'vsosh_10_11_full.json',
    )


def _is_db_already_correct(db, Probnik, OlympiadTask) -> bool:
    """Проверить, что в БД уже лежат 50 пробников × 20 задач = 1000."""
    try:
        probniks = (Probnik.query
                    .filter(Probnik.code.like('vsosh-%-2027-%'))
                    .all())
        if len(probniks) != EXPECTED_PROBNIKS_TOTAL:
            return False
        pids = [p.id for p in probniks]
        n_tasks = OlympiadTask.query.filter(OlympiadTask.probnik_id.in_(pids)).count()
        if n_tasks != EXPECTED_OLY_TASKS_TOTAL:
            return False
        # Проверим что каждый probnik имеет ровно 20 задач
        for p in probniks:
            n = OlympiadTask.query.filter_by(probnik_id=p.id).count()
            if n != 20:
                return False
        return True
    except Exception as e:
        logger.warning('[VSOSH-FULL] _is_db_already_correct failed: %s', e)
        return False


def _cleanup_old(db, Probnik, OlympiadTask, MethodTask, ProbnikTheory) -> dict:
    """Удалить все vsosh-2027 Probnik (cascade-задачи) + все MethodTask."""
    old_probniks = (Probnik.query
                    .filter(Probnik.code.like('vsosh-%-2027-%'))
                    .all())
    old_pids = [p.id for p in old_probniks]
    n_tasks = 0
    if old_pids:
        n_tasks = OlympiadTask.query.filter(OlympiadTask.probnik_id.in_(old_pids)).count()
        OlympiadTask.query.filter(OlympiadTask.probnik_id.in_(old_pids)).delete(
            synchronize_session=False
        )
        ProbnikTheory.query.filter(ProbnikTheory.probnik_id.in_(old_pids)).delete(
            synchronize_session=False
        )
        Probnik.query.filter(Probnik.id.in_(old_pids)).delete(synchronize_session=False)

    n_method_tasks = MethodTask.query.count()
    MethodTask.query.delete(synchronize_session=False)

    db.session.flush()
    return {
        'probniks': len(old_pids),
        'oly_tasks': n_tasks,
        'method_tasks': n_method_tasks,
    }


def _load_9_class(db, Probnik, OlympiadTask, items: list) -> dict:
    """Создать 7 topic-пробников для 9 класса (по 20 задач каждый)."""
    by_code = defaultdict(list)
    for t in items:
        by_code[t['probnik_code']].append(t)

    stats = {'probniks_created': 0, 'tasks_created': 0}

    for code, tasks in sorted(by_code.items()):
        suffix = code.rsplit('-', 1)[-1]
        try:
            topic_num = int(suffix)
        except ValueError:
            continue

        p = Probnik(
            code=code,
            type='topic',
            number=topic_num,
            title=_TOPIC_TITLES_9.get(topic_num, f'Тема {topic_num}'),
            description=None,
            competition='ВсОШ',
            grade=9,
            season_year=2027,
            sort_order=topic_num,
            is_published=True,
        )
        db.session.add(p)
        db.session.flush()
        stats['probniks_created'] += 1

        for t in tasks:
            diff = t.get('difficulty')
            if diff not in _VALID_DIFF_COLORS:
                diff = None
            db.session.add(OlympiadTask(
                probnik_id=p.id,
                number=str(t.get('number') or ''),
                sort_order=int(t.get('sort_order', 0) or 0),
                difficulty=diff,
                method_primary=t.get('method_primary') or '',
                method_secondary=t.get('method_secondary'),
                condition_md=t.get('condition_md') or '',
                idea_md=t.get('idea_md') or '',
                solution_md=t.get('solution_md') or '',
                answer=(t.get('answer') or '')[:500],
                source_prototype=t.get('source_prototype'),
                estimated_minutes=t.get('estimated_minutes'),
                max_score=int(t.get('max_score', 7) or 7),
            ))
            stats['tasks_created'] += 1

    return stats


def _load_10_11_class(db, Probnik, OlympiadTask, MethodTask, items: list) -> dict:
    """Создать 43 method-пробника для 10/11 + параллельно MethodTask."""
    by_code = defaultdict(list)
    for t in items:
        by_code[t['probnik_code']].append(t)

    stats = {'probniks_created': 0, 'oly_tasks_created': 0, 'method_tasks_created': 0}

    sorted_codes = sorted(by_code.keys())
    grade_counter = defaultdict(int)

    for code in sorted_codes:
        tasks = by_code[code]
        first = tasks[0]
        grade = int(first.get('grade') or 10)
        method_code = first.get('method_code') or code.rsplit('-', 1)[-1]
        method_name = first.get('method_name') or method_code
        section = first.get('section') or _SECTION_BY_LETTER.get(
            (method_code[:1] or '').upper(), 'Прочее'
        )

        grade_counter[grade] += 1
        topic_number = grade_counter[grade]

        p = Probnik(
            code=code,
            type='topic',
            number=topic_number,
            title=f'Метод {method_code}: {method_name}',
            description=f'{section} — метод {method_code}',
            competition='ВсОШ',
            grade=grade,
            season_year=2027,
            sort_order=topic_number,
            is_published=True,
        )
        db.session.add(p)
        db.session.flush()
        stats['probniks_created'] += 1

        for t in tasks:
            diff_num = t.get('difficulty')
            diff_color = _DIFF_NUM_TO_COLOR.get(int(diff_num) if diff_num else 0)
            if diff_color not in _VALID_DIFF_COLORS:
                diff_color = None

            db.session.add(OlympiadTask(
                probnik_id=p.id,
                number=str(t.get('number') or ''),
                sort_order=int(t.get('sort_order', 0) or 0),
                difficulty=diff_color,
                method_primary=method_code,
                method_secondary=None,
                condition_md=t.get('text') or '',
                idea_md=t.get('idea') or '',
                solution_md=t.get('solution') or '',
                answer=(t.get('answer') or '')[:500],
                source_prototype=None,
                estimated_minutes=t.get('estimated_minutes'),
                max_score=7,
            ))
            stats['oly_tasks_created'] += 1

            json_id = t.get('id') or stats['method_tasks_created'] + 1
            mt_id = f'{grade}-{method_code}-{json_id}'
            db.session.add(MethodTask(
                id=mt_id[:20],
                grade=grade,
                olympiad='ВсОШ',
                subject='math',
                year=2027,
                num=int(t.get('sort_order', 0) or 0) or None,
                stage=t.get('stage'),
                method_code=method_code,
                method_name=method_name,
                section=section,
                difficulty=int(diff_num) if diff_num else None,
                difficulty_label=t.get('difficulty_label'),
                difficulty_color=t.get('difficulty_color'),
                text=t.get('text') or '',
                answer=t.get('answer'),
                solution_idea=t.get('idea'),
                task_type=None,
            ))
            stats['method_tasks_created'] += 1

    return stats


def run_vsosh_full_seed(app, db) -> dict:
    """Главная функция: запускается на старте Flask.

    Идемпотентно: если БД уже содержит ровно 50 пробников × 20 задач —
    ничего не делает. Иначе делает CLEANUP + INSERT.
    """
    try:
        with app.app_context():
            from models_olympiad import Probnik, OlympiadTask, MethodTask, ProbnikTheory

            if _is_db_already_correct(db, Probnik, OlympiadTask):
                logger.info(
                    '[VSOSH-FULL-SEED] БД уже содержит 50 пробников × 20 задач — пропуск'
                )
                return {'status': 'skipped', 'reason': 'already_seeded'}

            p9, p1011 = _file_paths(app)
            if not p9.exists() or not p1011.exists():
                logger.warning(
                    '[VSOSH-FULL-SEED] JSON-файлы не найдены: %s, %s — пропуск',
                    p9, p1011,
                )
                return {'status': 'error', 'reason': 'json_missing'}

            data9 = json.loads(p9.read_text(encoding='utf-8'))
            data10_11 = json.loads(p1011.read_text(encoding='utf-8'))
            logger.info(
                '[VSOSH-FULL-SEED] Источники: 9кл=%d, 10/11=%d',
                len(data9), len(data10_11),
            )

            deleted = _cleanup_old(db, Probnik, OlympiadTask, MethodTask, ProbnikTheory)
            logger.info(
                '[VSOSH-FULL-SEED] Cleanup: probniks=%d, oly_tasks=%d, method_tasks=%d',
                deleted['probniks'], deleted['oly_tasks'], deleted['method_tasks'],
            )

            s9 = _load_9_class(db, Probnik, OlympiadTask, data9)
            logger.info(
                '[VSOSH-FULL-SEED] 9кл: probniks=%d, tasks=%d',
                s9['probniks_created'], s9['tasks_created'],
            )

            s10 = _load_10_11_class(db, Probnik, OlympiadTask, MethodTask, data10_11)
            logger.info(
                '[VSOSH-FULL-SEED] 10/11кл: probniks=%d, oly_tasks=%d, method_tasks=%d',
                s10['probniks_created'], s10['oly_tasks_created'], s10['method_tasks_created'],
            )

            # Финальная проверка ПЕРЕД commit
            if not _is_db_already_correct(db, Probnik, OlympiadTask):
                db.session.rollback()
                logger.error(
                    '[VSOSH-FULL-SEED] Verify failed после INSERT — ROLLBACK'
                )
                return {'status': 'error', 'reason': 'verify_failed'}

            db.session.commit()
            logger.info('[VSOSH-FULL-SEED] OK: данные сохранены в БД')
            return {
                'status': 'ok',
                'deleted': deleted,
                '9class': s9,
                '10_11class': s10,
            }
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception('[VSOSH-FULL-SEED] FATAL: %s', e)
        return {'status': 'error', 'reason': str(e)}
