# -*- coding: utf-8 -*-
"""
services/daily_task_rotation.py — Связь задач дня с анкетой и level_engine.

Подбор задач дня по логике:
  - количество задач = daily_tasks из анкеты (CuratorState.prep_state.onboarding.daily_tasks), дефолт 5
  - уровень = level_engine.allowed_difficulty(round(mu), source), но не выше route_ceiling
  - разделы: приоритет разделам с наименьшим mu в level_by_section
    раздел без данных считается приоритетным (mu=1.0)
    не более 2 задач подряд из одного раздела
  - исключать task_id, уже выданные этому ученику ранее (диагностика + прошлые задачи дня)
  - каждый ответ пишется в level_engine.record_result с разделом

Также предоставляет build_student_card(user_id) -> dict для промпта куратора DeepSeek.
"""

from __future__ import annotations

import json
import logging
import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import current_app
from models import db, AdaptiveTask, AdaptiveTestResult, TaskSolution
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem

logger = logging.getLogger(__name__)

# Часовой пояс МСК
MSK_TZ = timezone(timedelta(hours=3))

# ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ: сколько задач в день получает ученик.
# ПРАВИЛО:
#   - дни 1..7: утренний срез (5 задач) + задачи дня.
#     Задач дня = max(норма - 5, 5), минимум 5.
#     >часа (10): срез 5 + 5 задач дня = 10
#     час (8):    срез 5 + 5 задач дня = 10 (min 5)
#     30мин (10): срез 5 + 5 задач дня = 10
#     15мин (5):  срез 5 + 0 задач дня → но min 5 → 5
#   - после дня 7: полная норма из анкеты
#   - если цикл не начат -> день 1
CUTOFF_DAILY_TASKS = 5       # минимум в первые 7 дней
DEFAULT_DAILY_TASKS = 5      # дефолт после дня 7 (30 мин)
MIN_DAILY_TASKS = 5          # абсолютный минимум

def get_daily_task_count(user_id: int) -> int:
    """ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ: сколько задач получает ученик сегодня.

    Правило:
      - дни 1..7: утренний срез (5 задач) + задачи дня.
        Задач дня = max(дневная_норма - 5, 5)
      - после 7-го дня цикла -> полная норма из анкеты
      - если цикл ещё не начат -> день 1
    """
    from curator.monthly_cycle import get_cycle_info

    cycle = get_cycle_info(user_id)
    day_index = cycle.get('day_index', 1) if cycle.get('active') else 1

    # Дневная норма из анкеты
    onboard = _get_onboarding(user_id)
    daily_norm = DEFAULT_DAILY_TASKS
    if onboard:
        n = onboard.get('daily_tasks')
        if isinstance(n, (int, float)) and n > 0:
            daily_norm = int(n)

    if day_index <= 7:
        # Режим зондирования: срез 5 + задачи дня
        tasks_after_probe = max(daily_norm - 5, MIN_DAILY_TASKS)
        return tasks_after_probe

    # День 8+: полная норма
    return max(daily_norm, MIN_DAILY_TASKS)

# Канонические разделы level_engine
CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

# Русские названия разделов
SECTION_NAMES_RU: Dict[str, str] = {
    'algebra':        'алгебра',
    'geometry':       'геометрия',
    'combinatorics':  'комбинаторика',
    'logic':          'логика',
    'number_theory':  'теория чисел',
}

# Названия целевых уровней (этапов)
TARGET_LEVEL_NAMES: Dict[int, str] = {
    1: 'Вводный уровень',
    2: 'Школьный этап ВОШ',
    3: 'Муниципальный этап',
    4: 'Региональный этап',
    5: 'Заключительный этап',
}


# ══════════════════════════════════════════════════════════════════════
# ЧАСТЬ 1: pick_daily_set — подбор задач дня
# ══════════════════════════════════════════════════════════════════════


def _get_onboarding(user_id: int) -> Optional[Dict[str, Any]]:
    """Извлечь onboarding из CuratorState.prep_state.
    
    P9: сначала ищет новый ключ 'intake', затем старый 'onboarding'.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs or not cs.prep_state:
        return None
    prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
    return prep.get('intake') or prep.get('onboarding')


def _get_daily_tasks_count(user_id: int) -> int:
    """Количество задач в день — делегирует единому источнику правды."""
    return get_daily_task_count(user_id)


def _get_route_ceiling(user_id: int) -> int:
    """Потолок маршрута из анкеты (1..5)."""
    onboard = _get_onboarding(user_id)
    if onboard:
        c = onboard.get('route_ceiling')
        if isinstance(c, (int, float)):
            return max(1, min(5, int(c)))
    return 5


def _get_level_state(user_id: int) -> Dict[str, Any]:
    """Обёртка над level_engine.get_state."""
    from services.level_engine import get_state
    return get_state(user_id)


def _get_allowed_difficulty(user_id: int, ceiling: int) -> List[int]:
    """Разрешённые difficulty_level для этого ученика."""
    state = _get_level_state(user_id)
    mu = state.get('mu', 3.0)
    rounded_level = max(1, min(5, int(round(mu))))
    # Берём allowed из level_engine
    from services.level_engine import allowed_difficulty
    allowed = allowed_difficulty(rounded_level, 'formyla_L1_L5_TOP5')
    # Капим потолком
    allowed = [l for l in allowed if l <= ceiling]
    if not allowed:
        allowed = [ceiling]
    return allowed


def _section_priorities(by_section: Dict[str, Any]) -> List[Tuple[str, float]]:
    """Вернуть разделы, отсортированные по mu (наименьший первым).
    Раздел без данных считается приоритетным (mu=1.0)."""
    priorities: List[Tuple[str, float]] = []
    for sec in CANONICAL_SECTIONS:
        sec_data = by_section.get(sec)
        if sec_data and isinstance(sec_data, dict):
            mu_val = float(sec_data.get('mu', 1.0))
        else:
            mu_val = 1.0  # без данных — приоритет
        priorities.append((sec, mu_val))
    priorities.sort(key=lambda x: x[1])
    return priorities


def _get_seen_task_ids(user_id: int) -> Set[int]:
    """Все task_id, уже показанные этому ученику — одним запросом к истории.

    Использует task_assignment_history с индексом ix_tah_user_id.
    """
    from models import TaskAssignmentHistory
    rows = (
        TaskAssignmentHistory.query
        .filter_by(user_id=user_id)
        .with_entities(TaskAssignmentHistory.task_id)
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def _record_assignment(
    user_id: int,
    task_id: int,
    source: str = 'daily_set',
    result: Optional[str] = None,
) -> None:
    """Записать выдачу задачи в task_assignment_history (INSERT OR IGNORE)."""
    from models import TaskAssignmentHistory
    today = datetime.now(MSK_TZ).date()
    existing = TaskAssignmentHistory.query.filter_by(
        user_id=user_id, task_id=task_id,
    ).first()
    if existing:
        return
    entry = TaskAssignmentHistory(
        user_id=user_id,
        task_id=task_id,
        assigned_date=today,
        source=source,
        result=result,
    )
    db.session.add(entry)
    # Не коммитим здесь — вызывающая сторона делает commit


def _get_least_assigned_task_ids(
    candidate_task_ids: List[int],
    exclude_user_id: int,
) -> Dict[int, int]:
    """Для списка task_id вернуть {task_id: global_assignment_count},
    отсортированный по возрастанию счётчика.

    Использует GROUP BY с индексом ix_tah_task_id — один запрос.
    Задачи, которые ещё никому не выдавались, получают count=0.
    """
    if not candidate_task_ids:
        return {}
    from models import TaskAssignmentHistory
    from sqlalchemy import func

    # Получаем счётчики выдач для всех кандидатов
    rows = (
        TaskAssignmentHistory.query
        .filter(TaskAssignmentHistory.task_id.in_(candidate_task_ids))
        .with_entities(
            TaskAssignmentHistory.task_id,
            func.count(TaskAssignmentHistory.id).label('cnt'),
        )
        .group_by(TaskAssignmentHistory.task_id)
        .all()
    )
    counts = {int(r[0]): r[1] for r in rows}
    # Задачи без записей в истории получают 0
    result = {}
    for tid in candidate_task_ids:
        result[tid] = counts.get(tid, 0)
    return result


def _normalize_section(raw: str) -> str:
    """Преобразовать topic (русский или латинский) в канонический slug раздела."""
    from services.level_engine import SECTION_RU_TO_SLUG as _map, CANONICAL_SECTIONS as _cs
    s = (raw or '').strip()
    if s in _cs:
        return s
    return _map.get(s, s)


def _classify_section(task: AdaptiveTask) -> str:
    """Определить канонический раздел задачи, используя subject как основной сигнал.

    subject в БД — канонический slug (algebra/geometry/combinatorics/logic/number_theory).
    topic — русское название, которое не всегда содержит ключевые слова (особенно logic).
    Поэтому: subject -> прямой slug (если канонический), иначе topic -> keyword matching.
    """
    # PRIMARY: subject уже канонический slug в БД
    subj = (task.subject or '').strip()
    sec = _normalize_section(subj)
    if sec in CANONICAL_SECTIONS:
        return sec
    # FALLBACK: keyword matching по topic
    return _normalize_section(task.topic or '')


def _pick_tasks_for_section(
    grade: int,
    section: str,
    allowed_levels: List[int],
    seen_ids: Set[int],
    count: int,
    user_id: int = None,
) -> List[Dict[str, Any]]:
    """Выбрать задачи из раздела нужных уровней, исключая seen_ids.

    Сортировка: сначала задачи, которые ещё не видел этот ученик,
    затем среди них — с наименьшим глобальным счётчиком выдач
    (least-assigned-first). Повторы внутри ученика запрещены полностью.
    """
    tasks: List[Dict[str, Any]] = []

    # P7 FIX: убран .limit(500) — он резал кандидатов до фильтрации
    # по разделу и до сортировки least-assigned-first.
    # Вместо этого берём всех кандидатов, фильтруем, сортируем по
    # частоте выдач, и только потом берём нужное количество count.
    candidates = (
        AdaptiveTask.query
        .filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.difficulty_level.in_(allowed_levels),
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
            db.or_(
                AdaptiveTask.source.is_(None),
                AdaptiveTask.source != 'formyla_anchors',
            ),
        )
        .order_by(AdaptiveTask.id)
        .all()
    )

    # Фильтруем по разделу, исключаем seen
    section_fresh: List[AdaptiveTask] = []
    for task in candidates:
        if task.id in seen_ids:
            continue
        if _classify_section(task) != section:
            continue
        section_fresh.append(task)

    if not section_fresh:
        return tasks

    # Сортируем по глобальной частоте выдач (least-assigned-first)
    fresh_ids = [t.id for t in section_fresh]
    global_counts = _get_least_assigned_task_ids(fresh_ids, user_id) if fresh_ids else {}
    section_fresh.sort(key=lambda t: global_counts.get(t.id, 0))

    # P7: защитный лимит ПОСЛЕ сортировки — берём достаточно много,
    # чтобы охватить всё разнообразие, но не уйти в бесконечность
    section_fresh = section_fresh[:10000]

    for task in section_fresh:
        if len(tasks) >= count:
            break
        tasks.append({
            'task_id': task.id,
            'task_text': task.task_text,
            'correct_answer': task.correct_answer,
            'solution': task.solution or '',
            'subject': task.subject or '',
            'topic': task.topic or '',
            'method': getattr(task, 'methods_json', None) or '',
            'class_level': task.class_level,
            'difficulty_level': task.difficulty_level,
            'section': section,
        })

    if len(tasks) < count:
        logger.info(
            "shortage: section=%s fresh=%d needed=%d missing=%d",
            section, len(tasks), count, count - len(tasks),
        )

    return tasks


def _get_bank_day(user_id: int) -> int:
    """Детерминированный номер дня для банка задач (1–100).

    Вычисляется от даты начала цикла или даты регистрации пользователя.
    Если ни того ни другого нет — от 2025-09-01 (начало учебного года).
    """
    from datetime import date as dt_date
    today = dt_date.today()

    # Пробуем дату начала цикла
    try:
        from curator.monthly_cycle import _get_monthly_cycle
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs:
            mc = _get_monthly_cycle(cs)
            started = mc.get('started_at')
            if started:
                started_date = dt_date.fromisoformat(started[:10])
                delta = (today - started_date).days
                if delta >= 0:
                    return (delta % 100) + 1
    except Exception:
        pass

    # Пробуем дату регистрации
    try:
        from models import User
        user = User.query.get(user_id)
        if user and user.created_at:
            created_date = user.created_at.date() if hasattr(user.created_at, 'date') else dt_date.fromisoformat(str(user.created_at)[:10])
            delta = (today - created_date).days
            if delta >= 0:
                return (delta % 100) + 1
    except Exception:
        pass

    # Абсолютный fallback: от начала учебного года
    school_start = dt_date(2025, 9, 1)
    delta = (today - school_start).days
    return (max(0, delta) % 100) + 1


def _map_canonical_to_bank_level(canonical_level: int) -> int:
    """Отобразить канонический уровень (1–5) в банковский (1–5).

    Банк задач оперирует уровнями сложности 1–5 (каноническая шкала).
    Отображение: тождественное (bank level = canonical level), зажато в [1, 5].
    """
    return max(1, min(5, canonical_level))


def pick_daily_set(user_id: int, force_regenerate: bool = False) -> Dict[str, Any]:
    """Подобрать набор задач дня в соответствии с анкетой и level_engine.

    ПРИОРИТЕТ: банк задач (JSON) -> AdaptiveTask (SQL) -> AI-генерация.
    Банк вызывается синхронно, прямо в запросе, без фоновых потоков
    и без единого обращения к нейросети.

    Параметры:
        user_id: ID пользователя
        force_regenerate: принудительно новый набор

    Возвращает:
        { tasks: [...], subject: str, shown_date: str, count: int }
    """
    today = datetime.now(MSK_TZ).date()

    # ═══════════════════════════════════════════════════════════════
    # ШАГ -1: Утренний срез — если день 1-7 и зонд не пройден
    # ═══════════════════════════════════════════════════════════════
    try:
        from curator.monthly_cycle import get_cycle_info
        from services.theme_probe import has_active_probe, get_active_probe_theme
        cycle = get_cycle_info(user_id)
        if cycle.get('active'):
            day_idx = cycle.get('day_index', 1)
            current_theme = cycle.get('current_theme')
            if day_idx <= 7 and current_theme:
                probe_active = has_active_probe(user_id)
                probe_theme = get_active_probe_theme(user_id)
                if not probe_active or probe_theme != current_theme:
                    return {
                        'probe_required': True,
                        'theme_id': current_theme,
                        'theme_name': current_theme,
                        'grade': grade,
                        'day_index': day_idx,
                        'shown_date': today.isoformat(),
                    }
    except Exception as _pe:
        logger.warning("daily_rotation: probe check failed: %s", _pe)

    # Проверяем существующий сет на сегодня
    if not force_regenerate:
        existing = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=today,
        ).first()
        if existing:
            # Возвращаем уже существующие задачи
            items = (
                DailyTaskItem.query
                .filter_by(daily_set_id=existing.id)
                .order_by(DailyTaskItem.position)
                .all()
            )
            tasks_out = []
            for it in items:
                tasks_out.append({
                    'task_id': it.id,
                    'task_text': it.task_text,
                    'solution': it.solution,
                    'correct_answer': it.correct_answer,
                    'subject': it.subject,
                    'topic': it.topic,
                    'difficulty_level': it.difficulty_level,
                })
            return {
                'tasks': tasks_out,
                'subject': tasks_out[0]['subject'] if tasks_out else 'math',
                'shown_date': today.isoformat(),
                'count': len(tasks_out),
            }

    # ── Сбор параметров ───────────────────────────────────────────
    count = _get_daily_tasks_count(user_id)
    ceiling = _get_route_ceiling(user_id)
    state = _get_level_state(user_id)
    by_section = state.get('by_section', {})
    allowed_levels = _get_allowed_difficulty(user_id, ceiling)
    seen_ids = _get_seen_task_ids(user_id)

    # Класс ученика
    onboard = _get_onboarding(user_id)
    grade = 9  # дефолт
    if onboard and onboard.get('grade'):
        try:
            grade = int(onboard['grade'])
        except (ValueError, TypeError):
            grade = 9
    else:
        # Попытка извлечь из User
        from models import User
        user = User.query.get(user_id)
        if user:
            g = getattr(user, 'preferred_grade', None) or getattr(user, 'class_level', None) or getattr(user, 'grade', None)
            try:
                grade = int(g) if g else 9
            except (ValueError, TypeError):
                grade = 9

    # ═══════════════════════════════════════════════════════════════
    # ШАГ 0 — JSONL-банк: (grade, topic, week_level)
    # ═══════════════════════════════════════════════════════════════
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if cycle.get('active') and grade >= 5:
            current_theme = cycle.get('current_theme')
            day_idx = cycle.get('day_index', 1)
            # week_level: 1..4 in 28-day cycle
            week_level = min((day_idx - 1) // 7 + 1, 4)
            if current_theme:
                from daily_tasks.jsonl_bank import get_tasks as jb_get, load as jb_load
                jb_load()
                tasks = jb_get(grade, current_theme, week_level, count=count)
                if tasks and len(tasks) >= count:
                    daily_set = DailyTaskSet(
                        user_id=user_id, target_date=today, status='ready',
                        triggered_by='jsonl_bank', generated_at=datetime.utcnow(),
                        class_level=grade,
                        reason_summary=f'JSONL: G{grade} {current_theme} W{week_level} L{week_level} ({len(tasks)} tasks)',
                    )
                    db.session.add(daily_set); db.session.flush()
                    for pos, t in enumerate(tasks[:count], start=1):
                        item = DailyTaskItem(
                            daily_set_id=daily_set.id, position=pos,
                            slot_kind='jsonl_bank', subject='math',
                            topic=t.get('topic', current_theme),
                            difficulty_level=week_level,
                            task_text=t.get('task_text', ''),
                            correct_answer=t.get('correct_answer', ''),
                            solution='', hints=json.dumps([], ensure_ascii=False),
                            gemini_spec_json=json.dumps({'source':'jsonl_bank','grade':grade,'topic':current_theme,'level':week_level}, ensure_ascii=False),
                            status='approved',
                        )
                        db.session.add(item)
                    db.session.commit()
                    logger.info("daily_rotation JSONL: user=%d G%d topic=%s W%d count=%d", user_id, grade, current_theme, week_level, len(tasks))
                    return {'tasks': [{'task_id': t.get('position', i), 'task_text': t.get('task_text', ''), 'correct_answer': t.get('correct_answer', ''), 'solution': '', 'subject': 'math', 'topic': t.get('topic', current_theme), 'difficulty_level': week_level} for i, t in enumerate(tasks[:count])], 'subject': 'math', 'shown_date': today.isoformat(), 'count': len(tasks)}
    except Exception as _jl_err:
        logger.warning("daily_rotation: jsonl_bank failed: %s", _jl_err)

    # ═══════════════════════════════════════════════════════════════
    # P11 FIX: ШАГ 1 — пробуем JSON-банк задач (синхронно, без AI)
    # ═══════════════════════════════════════════════════════════════
    try:
        from daily_tasks.task_bank import get_tasks as bank_get_tasks

        mu = state.get('mu', 3.0)
        canonical_level = max(1, min(5, int(round(mu))))
        bank_level = _map_canonical_to_bank_level(canonical_level)
        bank_day = _get_bank_day(user_id)

        bank_tasks = bank_get_tasks(grade, bank_level, bank_day)

        if bank_tasks:
            # Берём первые <count> задач из банка (пробник содержит 10)
            take_count = min(count, len(bank_tasks))
            selected_tasks: List[Dict[str, Any]] = []
            for i in range(take_count):
                t = bank_tasks[i]
                selected_tasks.append({
                    'task_id': -(i + 1),   # отрицательный ID = источник «банк»
                    'task_text': t.get('text', ''),
                    'correct_answer': t.get('answer', ''),
                    'solution': t.get('solution', ''),
                    'subject': 'math',
                    'topic': t.get('method', ''),
                    'difficulty_level': bank_level,
                    'section': 'algebra',
                    'source': 'task_bank',
                })

            # Сохраняем DailyTaskSet в БД
            daily_set = DailyTaskSet(
                user_id=user_id,
                target_date=today,
                status='ready',
                triggered_by='task_bank',
                generated_at=datetime.utcnow(),
                class_level=grade,
                reason_summary=(
                    f'Банк задач: {take_count} задач '
                    f'(grade={grade}, level={bank_level}, day={bank_day})'
                ),
            )
            db.session.add(daily_set)
            db.session.flush()

            for pos, t in enumerate(selected_tasks, start=1):
                item = DailyTaskItem(
                    daily_set_id=daily_set.id,
                    position=pos,
                    slot_kind='task_bank',
                    subject=t.get('subject', 'math'),
                    topic=t.get('topic', ''),
                    difficulty_level=t.get('difficulty_level', 1),
                    task_text=t.get('task_text', ''),
                    correct_answer=t.get('correct_answer', ''),
                    solution=t.get('solution', ''),
                    hints=json.dumps([], ensure_ascii=False),
                    gemini_spec_json=json.dumps({
                        'source': 'task_bank',
                        'bank_level': bank_level,
                        'bank_day': bank_day,
                        'grade': grade,
                    }, ensure_ascii=False),
                    status='approved',
                )
                db.session.add(item)

            db.session.commit()

            logger.info(
                "daily_rotation BANK: user=%d grade=%d bank_level=%d bank_day=%d count=%d",
                user_id, grade, bank_level, bank_day, take_count,
            )

            tasks_out = []
            for t in selected_tasks:
                tasks_out.append({
                    'task_id': t['task_id'],
                    'task_text': t['task_text'],
                    'solution': t.get('solution', ''),
                    'correct_answer': t.get('correct_answer', ''),
                    'subject': t.get('subject', 'math'),
                    'topic': t.get('topic', ''),
                    'method': t.get('method', ''),
                    'class_level': grade,
                    'difficulty_level': t.get('difficulty_level', 1),
                })

            return {
                'tasks': tasks_out,
                'subject': tasks_out[0]['subject'] if tasks_out else 'math',
                'shown_date': today.isoformat(),
                'count': len(tasks_out),
            }

        logger.info(
            "daily_rotation: bank returned 0 tasks for grade=%d level=%d day=%d — falling back to AdaptiveTask DB",
            grade, bank_level, bank_day,
        )

    except Exception as _bank_err:
        logger.warning(
            "daily_rotation: bank lookup failed for user=%d: %s — falling back to AdaptiveTask DB",
            user_id, _bank_err,
        )

    # ── Распределение слотов по разделам ──────────────────────────
    sections_ordered = _section_priorities(by_section)

    # Равномерное распределение: не более 2 подряд из одного раздела
    selected_tasks: List[Dict[str, Any]] = []
    section_task_counts: Dict[str, int] = {s: 0 for s, _ in sections_ordered}
    last_section = ''

    remaining = count
    while remaining > 0 and sections_ordered:
        # Выбираем раздел: приоритет = тот, у которого меньше задач и не 2 подряд
        chosen_sec = None
        for sec, _ in sections_ordered:
            if sec == last_section and section_task_counts.get(sec, 0) >= 2:
                continue
            chosen_sec = sec
            break

        if chosen_sec is None:
            # Все разделы заблокированы — сбрасываем last_section
            for sec, _ in sections_ordered:
                chosen_sec = sec
                break

        if chosen_sec is None:
            break

        # Сколько задач берём из этого раздела
        take = min(2 if chosen_sec != last_section else 1, remaining)
        new_tasks = _pick_tasks_for_section(grade, chosen_sec, allowed_levels, seen_ids, take, user_id=user_id)
        if not new_tasks:
            # Fallback: ищем без фильтра раздела
            fallback = _pick_tasks_fallback(grade, allowed_levels, seen_ids, take)
            new_tasks = fallback
            if new_tasks:
                for t in new_tasks:
                    t['section'] = chosen_sec

        for t in new_tasks:
            seen_ids.add(t['task_id'])
            selected_tasks.append(t)
            section_task_counts[chosen_sec] = section_task_counts.get(chosen_sec, 0) + 1

        actual_take = len(new_tasks)
        remaining -= actual_take
        last_section = chosen_sec

        if actual_take == 0:
            # Не смогли найти задачи в этом разделе — убираем его из приоритетов
            sections_ordered = [(s, m) for s, m in sections_ordered if s != chosen_sec]
            if not sections_ordered:
                break

    # Если задач всё ещё не хватает — fallback без ограничений
    if len(selected_tasks) < count:
        remaining = count - len(selected_tasks)
        fallback = _pick_tasks_fallback(grade, allowed_levels, seen_ids, remaining)
        for t in fallback:
            seen_ids.add(t['task_id'])
            t['section'] = _normalize_section(t.get('topic', ''))
        selected_tasks.extend(fallback)

    # ── DIVERSITY CHECK: гарантия ≥3 разделов ─────────────────────
    # Если в пуле есть задачи хотя бы в 3 разделах класса ученика,
    # набор ДОЛЖЕН содержать ≥3 разных разделов.
    # Если разрешённые уровни слишком узкие -> расширяем окно на ±1
    # внутри раздела, но не выше route_ceiling.
    unique_sections = set(
        _normalize_section(t.get('topic', '')) for t in selected_tasks
    )
    if len(unique_sections) < 3:
        logger.info(
            "diversity_check: всего %d разделов в наборе (нужно >=3) — "
            "запускаем diversity fix", len(unique_sections),
        )
        # Расширяем окно уровней на ±1, не выше ceiling
        expanded_levels = set(allowed_levels)
        for lv in list(allowed_levels):
            if lv - 1 >= 1:
                expanded_levels.add(lv - 1)
            if lv + 1 <= ceiling:
                expanded_levels.add(lv + 1)
        expanded_levels_list = sorted(expanded_levels)
        logger.info(
            "diversity_check: expanded_levels %s -> %s",
            allowed_levels, expanded_levels_list,
        )

        # Определяем недопредставленные разделы (нет в наборе)
        all_section_names = [s for s, _ in _section_priorities(by_section)]
        missing_sections = [s for s in all_section_names if s not in unique_sections]

        # Определяем перенасыщенные разделы (>=3 задач)
        over_sections = sorted(
            [(sec, cnt) for sec, cnt in section_task_counts.items() if cnt >= 3],
            key=lambda x: -x[1],
        )

        for over_sec, over_cnt in over_sections:
            if len(unique_sections) >= 3:
                break
            if not missing_sections:
                break

            # Убираем одну задачу из перенасыщенного раздела
            removed = None
            for i in range(len(selected_tasks) - 1, -1, -1):
                t_sec = _normalize_section(selected_tasks[i].get('topic', ''))
                if t_sec == over_sec:
                    removed = selected_tasks.pop(i)
                    seen_ids.discard(removed['task_id'])
                    section_task_counts[over_sec] -= 1
                    break

            if removed is None:
                continue

            # Добавляем задачу из недопредставленного раздела
            target_sec = missing_sections.pop(0)
            new_tasks = _pick_tasks_for_section(
                grade, target_sec, expanded_levels_list,
                seen_ids.copy(), 1, user_id=user_id,
            )
            if new_tasks:
                t = new_tasks[0]
                seen_ids.add(t['task_id'])
                selected_tasks.append(t)
                section_task_counts[target_sec] = section_task_counts.get(target_sec, 0) + 1
                t_lvl = t.get('difficulty_level', '?')
                logger.info(
                    "diversity_check: zamenen 1 slot %s->%s(L%s) dlya raznoobraziya",
                    over_sec, target_sec, t_lvl,
                )

        # Пересчитываем уникальные разделы
        unique_sections = set(
            _normalize_section(t.get('topic', '')) for t in selected_tasks
        )
        logger.info(
            "diversity_check: posle fixa razdelov=%d -> %s",
            len(unique_sections), unique_sections,
        )

    # ── Сохраняем DailyTaskSet в БД ───────────────────────────────
    daily_set = DailyTaskSet(
        user_id=user_id,
        target_date=today,
        status='ready',
        triggered_by='daily_rotation',
        generated_at=datetime.utcnow(),
        class_level=grade,
        reason_summary=f'Автоподбор {len(selected_tasks)} задач по анкете и level_engine',
    )
    db.session.add(daily_set)
    db.session.flush()

    for pos, t in enumerate(selected_tasks, start=1):
        item = DailyTaskItem(
            daily_set_id=daily_set.id,
            position=pos,
            slot_kind='daily_rotation',
            subject=t.get('subject', 'math'),
            topic=t.get('topic', ''),
            difficulty_level=t.get('difficulty_level', 1),
            task_text=t.get('task_text', ''),
            correct_answer=t.get('correct_answer', ''),
            solution=t.get('solution', ''),
            hints=json.dumps([], ensure_ascii=False),
            gemini_spec_json=json.dumps({
                'slot_kind': 'daily_rotation',
                'subject': t.get('subject', 'math'),
                'topic': t.get('topic', ''),
                'section': t.get('section', ''),
                'difficulty_level': t.get('difficulty_level', 1),
                'source': 'daily_rotation',
            }, ensure_ascii=False),
            status='approved',
        )
        db.session.add(item)

    # Записываем факт выдачи в историю
    for t in selected_tasks:
        _record_assignment(user_id, t['task_id'], source='daily_set')

    db.session.commit()

    logger.info(
        "daily_rotation: user=%d grade=%d count=%d ceiling=%d levels=%s",
        user_id, grade, len(selected_tasks), ceiling, allowed_levels,
    )

    tasks_out = []
    for t in selected_tasks:
        tasks_out.append({
            'task_id': t['task_id'],
            'task_text': t['task_text'],
            'solution': t.get('solution', ''),
            'correct_answer': t.get('correct_answer', ''),
            'subject': t.get('subject', 'math'),
            'topic': t.get('topic', ''),
            'method': t.get('method', ''),
            'class_level': t.get('class_level', grade),
            'difficulty_level': t.get('difficulty_level', 1),
        })

    return {
        'tasks': tasks_out,
        'subject': tasks_out[0]['subject'] if tasks_out else 'math',
        'shown_date': today.isoformat(),
        'count': len(tasks_out),
    }


def _pick_tasks_fallback(
    grade: int,
    allowed_levels: List[int],
    seen_ids: Set[int],
    count: int,
) -> List[Dict[str, Any]]:
    """Fallback: выбрать любые задачи нужных уровней без фильтрации по разделу."""
    tasks: List[Dict[str, Any]] = []
    # P7 FIX: убран .limit(500) — см. _pick_tasks_for_section
    candidates = (
        AdaptiveTask.query
        .filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.difficulty_level.in_(allowed_levels),
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
            db.or_(
                AdaptiveTask.source.is_(None),
                AdaptiveTask.source != 'formyla_anchors',
            ),
        )
        .order_by(AdaptiveTask.id)
        .all()
    )
    for task in candidates:
        if task.id in seen_ids:
            continue
        tasks.append({
            'task_id': task.id,
            'task_text': task.task_text,
            'correct_answer': task.correct_answer,
            'solution': task.solution or '',
            'subject': task.subject or '',
            'topic': task.topic or '',
            'method': getattr(task, 'methods_json', None) or '',
            'class_level': task.class_level,
            'difficulty_level': task.difficulty_level,
            'section': _normalize_section(task.topic or ''),
        })
        if len(tasks) >= count:
            break
    return tasks


def record_daily_answer(user_id: int, item_id: int, correct: bool) -> Dict[str, Any]:
    """Записать результат ответа на задачу дня в level_engine.

    Получает раздел из DailyTaskItem:
      - PRIMARY: _normalize_section(item.topic)
        (новый slot_planner пишет topic = канонический slug раздела)
      - FALLBACK: gemini_spec_json['section']
        (старый LLM-пайплайн мог записать section внутрь JSON)
    """
    item = DailyTaskItem.query.get(item_id)
    if not item:
        return {'error': 'Задача не найдена'}

    # PRIMARY: нормализовать topic (уже slug для новых слотов,
    #           русское название для старых — _normalize_section обработает оба)
    section = _normalize_section(item.topic or '')

    # FALLBACK: если topic не дал канонический раздел — смотрим gemini_spec_json
    if section not in CANONICAL_SECTIONS and item.gemini_spec_json:
        try:
            spec = json.loads(item.gemini_spec_json)
            spec_section = str(spec.get('section', '')).strip()
            if spec_section in CANONICAL_SECTIONS:
                section = spec_section
        except (json.JSONDecodeError, TypeError):
            pass

    # Last resort: если раздел определить не удалось — обновляем только глобальный mu
    if section not in CANONICAL_SECTIONS:
        logger.warning(
            "record_daily_answer: cannot determine section for item_id=%d, "
            "topic=%r. Updating global mu only.",
            item_id, (item.topic or ''),
        )
        level = item.difficulty_level or 1
        from services.level_engine import record_result
        return record_result(user_id, None, level, correct)

    level = item.difficulty_level or 1

    from services.level_engine import record_result
    return record_result(user_id, section, level, correct)


# ══════════════════════════════════════════════════════════════════════
# ЧАСТЬ 3: build_student_card — карточка ученика для промпта куратора
# ══════════════════════════════════════════════════════════════════════


def build_student_card(user_id: int) -> Dict[str, Any]:
    """Собрать карточку ученика для промпта куратора DeepSeek.

    Возвращает dict с ключами:
        grade, target_level, target_level_name, level_mu, level_sigma,
        level_by_section (с русскими названиями), weakest_sections (3 самых слабых),
        daily_tasks, deadline_date, days_left, last_test (дата и итог),
        tasks_solved_total, tasks_solved_7d
    """
    card: Dict[str, Any] = {}

    # ── Из анкеты ──────────────────────────────────────────────────
    onboard = _get_onboarding(user_id)
    if onboard:
        card['grade'] = onboard.get('grade')
        card['target_level'] = onboard.get('target_level')
        card['target_level_name'] = TARGET_LEVEL_NAMES.get(
            onboard.get('target_level', 1), f"Уровень {onboard.get('target_level', '?')}"
        )
        card['daily_tasks'] = onboard.get('daily_tasks', DEFAULT_DAILY_TASKS)
        card['deadline_date'] = onboard.get('deadline_date')
        card['days_left'] = onboard.get('days_left')
        card['deadline_bucket'] = onboard.get('deadline_bucket')
    else:
        card['grade'] = None
        card['target_level'] = None
        card['target_level_name'] = 'Неизвестно'
        card['daily_tasks'] = DEFAULT_DAILY_TASKS
        card['deadline_date'] = None
        card['days_left'] = None
        card['deadline_bucket'] = 'none'

    # ── Из level_engine ────────────────────────────────────────────
    from services.level_engine import get_state
    state = get_state(user_id)
    card['level_mu'] = round(state.get('mu', 3.0), 2)
    card['level_sigma'] = round(state.get('sigma', 1.5), 2)

    by_section = state.get('by_section', {})
    by_section_ru: Dict[str, Any] = {}
    for sec in CANONICAL_SECTIONS:
        sec_data = by_section.get(sec, {})
        if isinstance(sec_data, dict):
            by_section_ru[SECTION_NAMES_RU.get(sec, sec)] = {
                'mu': round(float(sec_data.get('mu', 1.0)), 2),
                'sigma': round(float(sec_data.get('sigma', 1.5)), 2),
                'n': int(sec_data.get('n', 0)),
            }
        else:
            by_section_ru[SECTION_NAMES_RU.get(sec, sec)] = {
                'mu': 1.0, 'sigma': 1.5, 'n': 0,
            }
    card['level_by_section'] = by_section_ru

    # Три самых слабых раздела (по mu)
    sorted_sections = sorted(
        by_section_ru.items(),
        key=lambda x: x[1]['mu'],
    )
    card['weakest_sections'] = [
        {'name': name, 'mu': data['mu'], 'n': data['n']}
        for name, data in sorted_sections[:3]
    ]

    # ── Последний тест ─────────────────────────────────────────────
    last_result = (
        AdaptiveTestResult.query
        .filter_by(user_id=user_id)
        .order_by(AdaptiveTestResult.completed_at.desc().nullslast())
        .first()
    )
    if last_result:
        card['last_test'] = {
            'date': last_result.completed_at.isoformat() if last_result.completed_at else None,
            'topic': last_result.topic,
            'correct': last_result.tasks_correct,
            'total': last_result.tasks_total,
            'final_level': last_result.final_level,
        }
    else:
        card['last_test'] = None

    # ── Сколько задач решено всего ─────────────────────────────────
    total_solved = TaskSolution.query.filter_by(user_id=user_id).count()
    card['tasks_solved_total'] = total_solved

    # За 7 дней
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    solved_7d = (
        TaskSolution.query
        .filter(
            TaskSolution.user_id == user_id,
            TaskSolution.created_at >= seven_days_ago,
        )
        .count()
    )
    # ── Monthly cycle subtopics (for curator system prompt) ─────────
    try:
        from curator.monthly_cycle import get_cycle_info as _gci
        from daily_tasks.monthly_plan import subtopic_title as _st_title
        from services.level_engine import get_level_by_theme as _lbt_fn
        ci = _gci(user_id)
        if ci.get('active'):
            lbt = _lbt_fn(user_id)
            cycle_themes = []
            for tid in ci.get('themes', []):
                t_data = {'id': tid, 'name': _st_title(tid)}
                if tid in lbt:
                    t_data['mu'] = lbt[tid].get('mu')
                cycle_themes.append(t_data)
            card['cycle_themes'] = cycle_themes
            card['cycle_measured_count'] = len(ci.get('done_themes', []))
            card['cycle_total'] = len(ci.get('themes', []))
            card['cycle_current_theme'] = ci.get('current_theme')
            if ci.get('current_theme'):
                card['cycle_current_theme_name'] = _st_title(ci['current_theme'])
    except Exception:
        pass

    card['tasks_solved_7d'] = solved_7d

    return card


def format_student_card_for_prompt(card: Dict[str, Any]) -> str:
    """Форматировать карточку ученика как текст для system_prompt."""
    lines: List[str] = []
    lines.append("=== КАРТОЧКА УЧЕНИКА ===")
    lines.append(f"Класс: {card.get('grade', '?')}")
    lines.append(f"Целевой уровень: {card.get('target_level', '?')}/5 — {card.get('target_level_name', '?')}")
    lines.append(f"Уровень (mu): {card.get('level_mu', '?')} (σ={card.get('level_sigma', '?')})")
    lines.append(f"Задач в день: {card.get('daily_tasks', '?')}")

    if card.get('deadline_date'):
        lines.append(f"Дедлайн: {card['deadline_date']} (осталось {card.get('days_left', '?')} дней)")
    else:
        lines.append("Дедлайн: не установлен")

    lines.append("")
    lines.append("Уровень по разделам (1..5):")
    for name, data in card.get('level_by_section', {}).items():
        lines.append(f"  {name}: mu={data['mu']} σ={data['sigma']} задач={data['n']}")

    lines.append("")
    lines.append("Три самых слабых раздела:")
    for ws in card.get('weakest_sections', []):
        lines.append(f"  {ws['name']}: mu={ws['mu']} (задач: {ws['n']})")

    # ── Monthly cycle subtopics ────────────────────────────────────
    if card.get('cycle_themes'):
        lines.append("")
        lines.append("Подтемы текущего цикла:")
        lines.append(f"  Замерено: {card.get('cycle_measured_count', 0)} из {card.get('cycle_total', 0)}")
        current_tname = card.get('cycle_current_theme_name', '')
        for t in card['cycle_themes']:
            mu_str = f" — уровень {t['mu']:.1f}" if t.get('mu') is not None else ""
            is_today = " <- СЕГОДНЯ" if t['id'] == card.get('cycle_current_theme') else ""
            lines.append(f"  {t['name']}{mu_str}{is_today}")

    lines.append("")
    if card.get('last_test'):
        lt = card['last_test']
        lines.append(f"Последний тест: {lt.get('date', '?')}, тема «{lt.get('topic', '?')}», "
                      f"результат {lt.get('correct', '?')}/{lt.get('total', '?')}, "
                      f"финальный уровень {lt.get('final_level', '?')}")
    else:
        lines.append("Последний тест: не пройден")

    lines.append(f"Решено задач всего: {card.get('tasks_solved_total', 0)}")
    lines.append(f"Решено задач за 7 дней: {card.get('tasks_solved_7d', 0)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# ЧАСТЬ 4: cell_deficit — дефицит ячеек (класс × раздел × уровень)
# ══════════════════════════════════════════════════════════════════════


def cell_deficit_for_student(
    user_id: int,
    grade: int = None,
) -> List[Dict[str, Any]]:
    """Посчитать по каждой ячейке (класс × раздел × уровень),
    сколько задач в пуле и сколько из них ещё не видел ученик.

    Возвращает список dict: {grade, section, level, pool_total, unseen}.
    """
    from models import TaskAssignmentHistory, AdaptiveTask

    if grade is None:
        onboard = _get_onboarding(user_id)
        grade = 9
        if onboard and onboard.get('grade'):
            try:
                grade = int(onboard['grade'])
            except (ValueError, TypeError):
                pass

    # Все задачи пула (без formyla_anchors)
    pool = (
        AdaptiveTask.query
        .filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
            db.or_(
                AdaptiveTask.source.is_(None),
                AdaptiveTask.source != 'formyla_anchors',
            ),
        )
        .all()
    )

    # task_ids, которые ученик уже видел
    seen = _get_seen_task_ids(user_id)

    # Группируем по (section, level)
    from collections import defaultdict
    pool_map: Dict[Tuple[str, int], int] = defaultdict(int)
    unseen_map: Dict[Tuple[str, int], int] = defaultdict(int)

    for task in pool:
        sec = _classify_section(task)
        lvl = task.difficulty_level or 1
        if sec not in CANONICAL_SECTIONS:
            sec = _normalize_section(task.topic or '')
            if sec not in CANONICAL_SECTIONS:
                sec = 'other'
        pool_map[(sec, lvl)] += 1
        if task.id not in seen:
            unseen_map[(sec, lvl)] += 1

    result = []
    for sec in CANONICAL_SECTIONS:
        for lvl in range(1, 6):
            pool_n = pool_map.get((sec, lvl), 0)
            unseen_n = unseen_map.get((sec, lvl), 0)
            result.append({
                'grade': grade,
                'section': sec,
                'level': lvl,
                'pool_total': pool_n,
                'unseen': unseen_n,
            })

    result.sort(key=lambda r: r['unseen'])
    return result


def cell_deficit_report() -> List[Dict[str, Any]]:
    """Общесистемный отчёт: все ячейки всех классов, отсортированы по дефициту.

    Дефицит = pool_total - max(unseen по всем ученикам с этим классом).
    Возвращает список dict: {grade, section, level, pool_total, max_unseen, deficit}.
    """
    from models import AdaptiveTask

    # Все классы в пуле
    grades = (
        AdaptiveTask.query
        .with_entities(AdaptiveTask.class_level)
        .filter(
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
            db.or_(
                AdaptiveTask.source.is_(None),
                AdaptiveTask.source != 'formyla_anchors',
            ),
        )
        .distinct()
        .all()
    )
    grade_list = sorted([g[0] for g in grades if g[0] is not None])

    if not grade_list:
        return []

    result = []
    for grade in grade_list:
        # pool count per cell
        tasks = (
            AdaptiveTask.query
            .filter(
                AdaptiveTask.class_level == grade,
                AdaptiveTask.correct_answer.isnot(None),
                AdaptiveTask.correct_answer != '',
                AdaptiveTask.task_text.isnot(None),
                AdaptiveTask.task_text != '',
                db.or_(
                    AdaptiveTask.source.is_(None),
                    AdaptiveTask.source != 'formyla_anchors',
                ),
            )
            .all()
        )

        from collections import defaultdict
        pool_map: Dict[Tuple[str, int], int] = defaultdict(int)
        for task in tasks:
            sec = _classify_section(task)
            lvl = task.difficulty_level or 1
            if sec not in CANONICAL_SECTIONS:
                sec = _normalize_section(task.topic or '')
                if sec not in CANONICAL_SECTIONS:
                    sec = 'other'
            pool_map[(sec, lvl)] += 1

        for sec in CANONICAL_SECTIONS:
            for lvl in range(1, 6):
                pool_n = pool_map.get((sec, lvl), 0)
                deficit = pool_n  # если пул 0 -> дефицит 0 (но видно пустые ячейки)
                result.append({
                    'grade': grade,
                    'section': sec,
                    'level': lvl,
                    'pool_total': pool_n,
                    'deficit': deficit if pool_n > 0 else 0,
                })

    result.sort(key=lambda r: (r['pool_total'], r['grade'], r['section'], r['level']))
    return result
