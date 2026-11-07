# -*- coding: utf-8 -*-
"""День пробника: задачи назначенного варианта из каталога — в задачах дня.

PROBNIK_DAILY_V1 (02.11.2026, владелец): занятие-пробник не уводит
ученика на отдельную страницу и на «страницу курсов». Задачи
НАЗНАЧЕННОГО варианта берутся из каталога олимпиад (через Probnik +
OlympiadTask, созданные ensure_real_probnik) и выдаются прямо в
задачах дня: условие, ответ и решение — все поля; сверху в сводке
написано, что за пробник: олимпиада, год, класс.

Ответы идут через обычный конвейер банка задач дня (DailyTaskBank +
BankIssue): ИИ-проверка, серия, XP — тот же путь, что у обычных
банковских задач. Занятие-пробник засчитывается, когда на все задачи
варианта дан ответ (maybe_finish_probnik_day → maybe_complete_probnik).

Модуль изолирован: точки подключения — ветка дня пробника на дашборде
задач дня (daily_tasks/routes.py) и зачёт после ответа. Крупные
routes.py/services.py правятся только в этих точках.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Маркер строк банка для задач пробника: subtopic = 'probnik:<код>'.
# Обычная выдача банка эти строки не подхватывает (подбор идёт по
# подтемам плана месяца), поэтому конфликта с обычными днями нет.
PROBNIK_BANK_PREFIX = 'probnik:'

# Сложность задач олимпиады → уровень банка (1..4).
_DIFFICULTY_TO_LEVEL = {
    'green': 1,
    'yellow': 2,
    'orange': 3,
    'red': 4,
}


def _current_probnik_lesson(user_id: int) -> Optional[Dict[str, Any]]:
    """Занятие-пробник, назначенное на сегодня (или None).

    Смотрим curator_lessons напрямую: занятие должно выдаваться и ПОСЛЕ
    завершения (повторный заход в тот же день показывает тот же вариант
    с ответами, а не новый обычный сет). Пилот-гейт обязателен: вне
    пилота дня пробника не бывает.
    """
    try:
        from services.pilot import is_pilot_user
        if not is_pilot_user(user_id):
            return None
    except Exception:  # noqa: BLE001
        return None
    try:
        from curator.session_plan import TABLE_NAME
        from models import db
        # База дат занятия — серверная date.today(), как в session_plan
        # (_insert_lesson пишет assigned_date = date.today()): часовой
        # пояс ученика здесь не участвует, чтобы не разъезжаться с
        # планом занятий.
        from datetime import date as _date
        row = db.session.execute(
            db.text(
                f'SELECT probnik_code, probnik_title FROM {TABLE_NAME} '
                'WHERE user_id = :uid AND lesson_type = \'probnik\' '
                'AND assigned_date = :d AND probnik_code IS NOT NULL '
                'ORDER BY id DESC LIMIT 1'),
            {'uid': user_id, 'd': _date.today().isoformat()},
        ).fetchone()
        if not row:
            return None
        return {'probnik_code': row[0], 'probnik_title': row[1]}
    except Exception:  # noqa: BLE001
        logger.exception('[probnik_daily] lesson lookup failed')
        return None


def _bank_subtopic(code: str) -> str:
    return f'{PROBNIK_BANK_PREFIX}{code}'


def _ensure_bank_rows(code: str, probnik, tasks) -> List[Any]:
    """Идемпотентно создать строки daily_task_bank из задач варианта.

    Строки глобальные (один вариант — один набор строк): разные ученики
    с одним вариантом получают одни и те же строки, а ответы у каждого
    свои (bank_issues). Возвращает строки, упорядоченные по position.
    """
    from models import db, DailyTaskBank

    subtopic = _bank_subtopic(code)
    rows = DailyTaskBank.query.filter_by(subtopic=subtopic).all()
    if rows:
        return sorted(rows, key=lambda r: (r.position or 999, r.id))

    created: List[DailyTaskBank] = []
    try:
        for i, t in enumerate(tasks, start=1):
            row = DailyTaskBank(
                subtopic=subtopic,
                # section ограничен 50 символами — ставим маркер варианта
                section=(probnik.title or code)[:50],
                level=_DIFFICULTY_TO_LEVEL.get(
                    (t.difficulty or 'green'), 2) or 2,
                statement=t.condition_md or '',
                answer=(t.answer or None),
                solution=t.solution_md or None,
                position=i,
                needs_figure=False,
            )
            db.session.add(row)
            created.append(row)
        db.session.commit()
        logger.info('[probnik_daily] bank rows for %s: %d tasks',
                    code, len(created))
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[probnik_daily] bank rows failed for %s', code)
        return []
    return created


def _ensure_bank_issues(user_id: int, today, rows: List[Any]) -> None:
    """Идемпотентно выдать строки банка ученику на сегодня (bank_issues)."""
    from models import db, BankIssue

    try:
        for row in rows:
            exists = BankIssue.query.filter_by(
                user_id=user_id, task_id=row.id, issued_date=today,
            ).first()
            if exists:
                continue
            db.session.add(BankIssue(
                user_id=user_id,
                task_id=row.id,
                subtopic=row.subtopic,
                level=row.level or 1,
                issued_date=today,
            ))
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[probnik_daily] bank issues failed for user=%d',
                         user_id)


def _summary_text(probnik, task_count: int) -> str:
    """Сводка сверху: что за пробник — олимпиада, год, класс.

    Название варианта уже содержит олимпиаду, год, этап и класс
    (например «ВсОШ 2025, Школьный этап, 9 класс») — дублируем поля
    явно, чтобы «что за пробник» читалось с первого взгляда.
    """
    head = probnik.title or probnik.code
    extra = []
    if probnik.season_year and str(probnik.season_year) not in head:
        extra.append(f'{probnik.season_year} год')
    if probnik.grade and f'{probnik.grade} класс' not in head:
        extra.append(f'{probnik.grade} класс')
    if extra:
        head += ' · ' + ' · '.join(extra)
    return (f'Пробник: {head}. {task_count} задач — сдавай как на '
            'олимпиаде: к каждой задаче ответ и решение.')


def get_probnik_day_data(user_id: int, today) -> Optional[Dict[str, Any]]:
    """Данные дня пробника для дашборда задач дня.

    Возвращает dict в форме банковской ветки дашборда (status/target_date/
    progress/items/summary) или None, если сегодня не день пробника,
    вариант не назначен или не найден в каталоге (тогда день работает
    как обычно — по плану месяца).
    """
    lesson = _current_probnik_lesson(user_id)
    if not lesson:
        return None
    code = lesson['probnik_code']

    from models_olympiad import Probnik, OlympiadTask

    probnik = Probnik.query.filter_by(code=code).first()
    if not probnik:
        logger.warning('[probnik_daily] probnik %s not found — обычный день',
                       code)
        return None
    tasks = (OlympiadTask.query
             .filter_by(probnik_id=probnik.id)
             .order_by(OlympiadTask.sort_order)
             .all())
    if not tasks:
        logger.warning('[probnik_daily] probnik %s has no tasks', code)
        return None

    rows = _ensure_bank_rows(code, probnik, tasks)
    if not rows:
        return None
    _ensure_bank_issues(user_id, today, rows)

    # Сериализация и прогресс — те же функции, что у обычного банка
    # (ленивый импорт: модуль вызывается из обработчика запроса).
    from daily_tasks.routes import _bank_progress, _serialize_bank_items
    items = _serialize_bank_items(user_id, rows)

    # Подпись задач: «Пробник · год · класс» вместо служебного маркера
    label = 'Пробник'
    if probnik.season_year:
        label += f' · {probnik.season_year}'
    if probnik.grade:
        label += f' · {probnik.grade} класс'
    for it in items:
        it['subtopic'] = label
        it['topic'] = label

    return {
        'status': 'ready',
        'daily_set_id': None,
        'target_date': today.isoformat(),
        'class_level': probnik.grade,
        'summary': _summary_text(probnik, len(rows)),
        'generated_at': datetime.utcnow().isoformat(),
        'total_cost_usd': None,
        'progress': _bank_progress(user_id, rows),
        'items': items,
        'probnik_code': code,
    }


def maybe_finish_probnik_day(user_id: int) -> bool:
    """Занятие-пробник завершается, когда на все задачи варианта дан ответ.

    Вызывается после сохранения ответа на банковскую задачу. Идемпотентно:
    повторные вызовы ничего не меняют. Внутри — maybe_complete_probnik
    из плана занятий (проверяет назначенный вариант, никакого «любого»
    пробника).
    """
    lesson = _current_probnik_lesson(user_id)
    if not lesson:
        return False
    code = lesson['probnik_code']
    try:
        from models import BankIssue, DailyTaskBank
        subtopic = _bank_subtopic(code)
        rows = DailyTaskBank.query.filter_by(subtopic=subtopic).all()
        if not rows:
            return False
        answered = BankIssue.query.filter(
            BankIssue.user_id == user_id,   # раньше считались ответы ВСЕХ учеников
            BankIssue.task_id.in_([r.id for r in rows]),
            BankIssue.user_answer.isnot(None),
        ).count()
        if answered < len(rows):
            return False
        from curator.session_plan import maybe_complete_probnik
        return bool(maybe_complete_probnik(user_id, code))
    except Exception:  # noqa: BLE001
        logger.exception('[probnik_daily] finish check failed')
        return False
