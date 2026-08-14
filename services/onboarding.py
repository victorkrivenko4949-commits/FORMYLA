# -*- coding: utf-8 -*-
"""
services/onboarding.py — Оркестратор линейной анкеты онбординга (5 вопросов + 3 якоря).

API:
  start(user_id) -> dict          # первый вопрос (или пропуск Q1 если класс известен)
  answer(user_id, qid, key) -> dict   # следующий вопрос / якорная задача / финал
  submit_anchor(user_id, task_id, user_answer) -> dict  # проверка якоря
  finish(user_id) -> dict         # финализация: compute_prior, set_prior, запись в prep_state

Состояние держится в session['onboarding']. По завершении ключ очищается.
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from services.onboarding_tree import (
    Q1_GRADE,
    Q2_TARGET,
    Q3_OLYMP_REACH,
    Q4_LOAD,
    Q5_DEADLINE,
    ANCHOR_PLAN,
    DEADLINE_RU,
    compute_prior,
    compute_route_ceiling,
    build_initial_queue,
    OnboardingResult,
    TestTask,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Канонические разделы level_engine (латинские slug-и)
# ══════════════════════════════════════════════════════════════════════════════

CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

# Русские названия разделов для отображения на экране
SECTION_RU = {
    'algebra': 'алгебра',
    'geometry': 'геометрия',
    'combinatorics': 'комбинаторика',
    'logic': 'логика',
    'number_theory': 'теория чисел',
}

# ТОЧНЫЙ порядок разделов для якорей (все 5, по одному на раздел)
ANCHOR_SECTION_ORDER = ('algebra', 'number_theory', 'geometry', 'combinatorics', 'logic')

# Маппинг КЛЮЧЕВЫХ СЛОВ topic -> section slug
SECTION_KEYWORDS: Dict[str, str] = {
    # number_theory
    'делимость':    'number_theory',
    'сравнения':    'number_theory',
    'простые числа': 'number_theory',
    'числа':        'number_theory',
    'цифры':        'number_theory',
    'системы счисления': 'number_theory',
    'диофантов':    'number_theory',
    'арифметические': 'number_theory',
    'нок':          'number_theory',
    'нод':          'number_theory',
    'остатки':      'number_theory',
    'чётность':     'number_theory',
    'теория чисел': 'number_theory',
    'числовые':     'number_theory',
    # geometry
    'геометр':      'geometry',
    'углы':         'geometry',
    'отрезки':      'geometry',
    'площади':      'geometry',
    'периметры':    'geometry',
    'длины':        'geometry',
    'вписанные':    'geometry',
    'построения':   'geometry',
    'разрезания':   'geometry',
    'клетчатая':    'geometry',
    'замощения':    'geometry',
    'покрытия':     'geometry',
    'пространственные': 'geometry',
    'конфигурации': 'geometry',
    # combinatorics
    'комбинатор':   'combinatorics',
    'инвариант':    'combinatorics',
    'раскраски':    'combinatorics',
    'игры':         'combinatorics',
    'стратегии':    'combinatorics',
    'процессы':     'combinatorics',
    'алгоритмы':    'combinatorics',
    'принцип дирихле': 'combinatorics',
    'графы':        'combinatorics',
    'турниры':      'combinatorics',
    'подсчёт':      'combinatorics',
    'перебор':      'combinatorics',
    'оценка и построение': 'combinatorics',
    'взвешивания':  'combinatorics',
    'переливания':  'combinatorics',
    'ребусы':       'combinatorics',
    # logic
    'логические':   'logic',
    'логика':       'logic',
    'рыцари':       'logic',
    'лжецы':        'logic',
    'методы':       'logic',
    # algebra (catch-all for everything else)
    'алгебра':      'algebra',
    'анализ':       'algebra',
    'уравнения':    'algebra',
    'неравенства':  'algebra',
    'функциональные': 'algebra',
    'многочлены':   'algebra',
    'последовательности': 'algebra',
    'рекуррент':    'algebra',
    'тригонометр':  'algebra',
    'проценты':     'algebra',
    'смеси':        'algebra',
    'концентрации': 'algebra',
    'работа':       'algebra',
    'производительность': 'algebra',
    'движение':     'algebra',
    'части':        'algebra',
    'отношения':    'algebra',
    'пропорции':    'algebra',
    'тождества':    'algebra',
    'преобразования': 'algebra',
    'текстовые':    'algebra',
    'арифметика':   'algebra',
    'время':        'algebra',
    'возраст':      'algebra',
    'календарь':    'algebra',
    'экстремаль':   'algebra',
}


def _normalize_section(raw: str) -> str:
    """Преобразовать topic (русский или латинский) в канонический slug раздела.
    Использует keyword matching — ищет ключевые слова в названии темы."""
    s = raw.strip()
    if s in CANONICAL_SECTIONS:
        return s
    s_lower = s.lower()
    # Try longest keywords first for best match
    for keyword, slug in sorted(SECTION_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if keyword in s_lower:
            return slug
    # Fallback: algebra (most topics are algebra-adjacent)
    return 'algebra'

# ══════════════════════════════════════════════════════════════════════════════
# Шаг 3: нормализация ответа
# ══════════════════════════════════════════════════════════════════════════════


def normalize_answer(raw: str) -> str:
    """Нормализовать ответ ученика для сравнения с эталоном."""
    if not raw:
        return ""
    s = raw.strip().lower()
    s = s.replace(" ", "")
    s = s.replace("$", "")
    s = s.replace("\\(", "")
    s = s.replace("\\)", "")
    s = s.replace(",", ".")
    s = s.lstrip("+")
    s = s.rstrip(".")
    return s


def _check_anchor_answer(user_answer: str, correct_answer: str) -> bool:
    """Сравнить ответ ученика с эталонным после нормализации."""
    return normalize_answer(user_answer) == normalize_answer(correct_answer)


def _is_answer_anchor_eligible(correct_answer: str) -> bool:
    """Проверить, что ответ задачи подходит для якоря."""
    norm = normalize_answer(correct_answer)
    if not norm:
        return False
    if len(norm) > 20:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Внутренние хелперы
# ══════════════════════════════════════════════════════════════════════════════


def _get_session_state() -> dict:
    """Получить состояние онбординга из Flask-сессии (с fallback в БД)."""
    from flask import session
    state = session.get('onboarding', None)
    if state is not None:
        return state
    # Fallback: recover from CuratorState.prep_state (session lost by cookie issues)
    try:
        from flask_login import current_user
        from models_curator import CuratorState
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if cs and cs.prep_state:
                ps = cs.prep_state if isinstance(cs.prep_state, dict) else {}
                saved = ps.get('_onboarding_session')
                if isinstance(saved, dict) and saved.get('step') and saved.get('step') != 'done':
                    session['onboarding'] = saved
                    return saved
    except Exception:
        pass
    return None


def _save_session_state(state: dict) -> None:
    """Сохранить состояние онбординга в Flask-сессию и CuratorState."""
    from flask import session
    from flask_login import current_user
    session['onboarding'] = state
    # Persist in CuratorState as safe fallback
    try:
        from models_curator import CuratorState
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if cs:
                ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
                ps['_onboarding_session'] = state
                cs.prep_state = ps
                from models import db
                db.session.commit()
    except Exception:
        pass


def _clear_session_state() -> None:
    """Очистить состояние онбординга из Flask-сессии и CuratorState."""
    from flask import session
    from flask_login import current_user
    session.pop('onboarding', None)
    try:
        from models_curator import CuratorState
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if cs:
                ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
                ps.pop('_onboarding_session', None)
                cs.prep_state = ps
                from models import db
                db.session.commit()
    except Exception:
        pass


def _get_user_grade(user_id: int) -> Optional[int]:
    """Получить класс ученика по user_id."""
    from models import db, User
    user = db.session.get(User, user_id)
    if user is None:
        return None
    grade = (
        getattr(user, 'preferred_grade', None)
        or getattr(user, 'class_level', None)
        or getattr(user, 'grade', None)
    )
    try:
        return int(grade) if grade is not None else None
    except (TypeError, ValueError):
        return None


def _save_non_student_role(user_id: int, role: str) -> None:
    """Сохранить роль teacher/parent в User.role и отметку onboarded_at."""
    from models import db, User
    user = db.session.get(User, user_id)
    if user is not None:
        user.role = role
        if not user.onboarded_at:
            user.onboarded_at = datetime.utcnow()
        db.session.commit()
        logger.info(
            f"onboarding: user={user_id} set role={role}, onboarded_at set"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Выбор якорных задач из adaptive_tasks (с учётом разделов)
# ══════════════════════════════════════════════════════════════════════════════


def _pick_anchor_task_for_section(
    grade: int,
    target_level: int,
    section: str,
    exclude_ids: set,
    source: str = 'formyla_anchors',
) -> Optional[dict]:
    """Выбрать одну якорную задачу для заданного класса, уровня и РАЗДЕЛА.

    ТОЛЬКО из источника formyla_anchors. Без фолбэка.

    Параметры:
        grade:         класс ученика (5-11)
        target_level:  желаемый канонический уровень (1..5)
        section:       канонический slug раздела (algebra, geometry, ...)
        exclude_ids:   множество id задач, которые нельзя выбирать
        source:        источник задач (formyla_anchors)

    Возвращает:
        Словарь {id, task_text, correct_answer, difficulty_level, section}
        или None если подходящей задачи нет.
    """
    from models import AdaptiveTask
    import logging
    _log = logging.getLogger(__name__)

    # Якоря ТОЛЬКО из formyla_anchors, фильтруем без level_engine
    candidates = (
        AdaptiveTask.query
        .filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.source == source,
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
        )
        .order_by(AdaptiveTask.id)
        .limit(200)
        .all()
    )

    if not candidates:
        _log.warning(
            f"_pick_anchor_task_for_section: NO formyla_anchors tasks "
            f"for grade={grade} section={section}"
        )
        return None

    # Фильтруем: нужный раздел, короткий ответ, не в exclude_ids
    for task in candidates:
        if task.id in exclude_ids:
            continue
        task_section = _normalize_section(task.topic or '')
        if task_section != section:
            continue
        if not _is_answer_anchor_eligible(task.correct_answer or ''):
            continue
        return {
            'id': task.id,
            'task_text': task.task_text,
            'correct_answer': task.correct_answer,
            'difficulty_level': task.difficulty_level,
            'section': section,
            'source_id': task.source_id or '',
        }

    return None


def _pick_anchor_fallback_level(
    grade: int,
    section: str,
    desired_level: int,
    exclude_ids: set,
) -> Optional[dict]:
    """Если нет задачи нужного уровня в разделе — ищем ближайший уровень в том же разделе."""
    for delta in range(1, 6):
        for sign in [1, -1]:
            candidate_level = desired_level + sign * delta
            if candidate_level < 1 or candidate_level > 5:
                continue
            task = _pick_anchor_task_for_section(
                grade, candidate_level, section, exclude_ids
            )
            if task is not None:
                return task
    return None


def _pick_all_anchors(grade: int, base_mu: float, ceiling: int) -> tuple:
    """Выбрать ВСЕ 5 якорных задач — по одной на каждый раздел в фиксированном порядке.

    Уровень для всех якорей = clamp(1..ceiling, round(base_mu - 0.35)).

    Возвращает:
        (list_of_tasks, anchor_level, list_of_sections, list_of_fallback_reasons)
        Если хотя бы одна задача не найдена — возвращает пустой список задач
        и заполненный список причин.
    """
    anchor_level = max(1, min(ceiling, int(round(base_mu - 0.35))))
    tasks = []
    sections = []
    fallback_reasons = []
    exclude_ids = set()

    for section in ANCHOR_SECTION_ORDER:
        task = _pick_anchor_task_for_section(grade, anchor_level, section, exclude_ids)
        if task is None:
            task = _pick_anchor_fallback_level(grade, section, anchor_level, exclude_ids)
            if task is not None:
                fallback_reasons.append(
                    f"Уровень {anchor_level} недоступен в разделе {section}, взят ближайший"
                )
        if task is None:
            reason = (
                f"Нет якорной задачи для класса {grade} раздел {section}"
            )
            logger.warning(f"onboarding anchor missing: {reason}")
            fallback_reasons.append(reason)
            return [], anchor_level, [], fallback_reasons
        tasks.append(task)
        sections.append(section)
        exclude_ids.add(task['id'])

    return tasks, anchor_level, sections, fallback_reasons


# ══════════════════════════════════════════════════════════════════════════════
# Публичный API
# ══════════════════════════════════════════════════════════════════════════════


def start(user_id: int) -> dict:
    """Начать поток онбординга. Возвращает первый вопрос.

    Если класс уже известен из профиля — берёт его и пропускает Q1.
    """
    from flask import session

    grade_from_profile = _get_user_grade(user_id)

    state = {
        'step': 'q1',
        'answers': {},
        'anchor_tasks': [],
        'anchor_results': [],
        'anchor_task_ids': [],
        'anchor_sections': [],
        'current_anchor_idx': 0,
        'anchors_unavailable': False,
        'anchor_fallback_reasons': [],
    }

    # Если класс уже известен из профиля — вопрос Q1 НЕ показываем,
    # записываем в ответы и переходим к Q2.
    if grade_from_profile is not None:
        state['answers']['grade'] = str(grade_from_profile)
        state['step'] = 'q2'
        _save_session_state(state)

        logger.info(
            f"onboarding start: user={user_id} grade={grade_from_profile} (from profile, Q1 skipped)"
        )

        return {
            'done': False,
            'question': {
                'id': Q2_TARGET['id'],
                'text': Q2_TARGET['text'],
                'options': [{'key': o['key'], 'label': o['label']}
                            for o in Q2_TARGET['options']],
            },
            'step': 'q2',
            'grade_auto': grade_from_profile,
        }

    _save_session_state(state)

    logger.info(f"onboarding start: user={user_id} (no grade in profile)")

    return {
        'done': False,
        'question': {
            'id': Q1_GRADE['id'],
            'text': Q1_GRADE['text'],
            'options': [{'key': o['key'], 'label': o['label']}
                        for o in Q1_GRADE['options']],
        },
        'step': 'q1',
    }


def answer(user_id: int, qid: str, key: str) -> dict:
    """Записать ответ на вопрос анкеты и вернуть следующий шаг."""
    state = _get_session_state()
    if not state:
        logger.warning(f"onboarding answer: no session state for user={user_id}")
        return {'done': True, 'question': None, 'anchor': None,
                'step': 'done', 'error': 'Сессия истекла. Начните заново.'}

    state['answers'][qid] = key
    current_step = state['step']

    # ── Q1: teacher/parent -> сразу завершаем и ставим роль ──────────
    if current_step == 'q1' and qid == 'grade' and key in ('teacher', 'parent'):
        _save_non_student_role(user_id, key)
        _clear_session_state()
        redirect_url = (
            '/teacher' if key == 'teacher'
            else '/parent'
        )
        return {
            'done': True,
            'role': key,
            'redirect_url': redirect_url,
            'message': (
                'Вы зарегистрированы как учитель. Добро пожаловать в панель учителя!'
                if key == 'teacher'
                else 'Вы зарегистрированы как родитель. Добро пожаловать в панель родителя!'
            ),
        }

    # ── Q1 (grade) -> Q2 (target) ────────────────────────────────────────
    if current_step == 'q1' and qid == 'grade':
        state['step'] = 'q2'
        _save_session_state(state)

        return {
            'done': False,
            'question': {
                'id': Q2_TARGET['id'],
                'text': Q2_TARGET['text'],
                'options': [{'key': o['key'], 'label': o['label']}
                            for o in Q2_TARGET['options']],
            },
            'anchor': None,
            'step': 'q2',
        }

    # ── Q2 (target) -> Q3 (olymp_reach) ──────────────────────────────────
    if current_step == 'q2' and qid == 'target':
        state['step'] = 'q3'
        _save_session_state(state)

        return {
            'done': False,
            'question': {
                'id': Q3_OLYMP_REACH['id'],
                'text': Q3_OLYMP_REACH['text'],
                'options': [{'key': o['key'], 'label': o['label']}
                            for o in Q3_OLYMP_REACH['options']],
            },
            'anchor': None,
            'step': 'q3',
        }

    # ── Q3 (olymp_reach) -> Q4 (load) ────────────────────────────────────
    if current_step == 'q3' and qid == 'olymp_reach':
        state['step'] = 'q4'
        _save_session_state(state)

        return {
            'done': False,
            'question': {
                'id': Q4_LOAD['id'],
                'text': Q4_LOAD['text'],
                'options': [{'key': o['key'], 'label': o['label']}
                            for o in Q4_LOAD['options']],
            },
            'anchor': None,
            'step': 'q4',
        }

    # ── Q4 (load) -> Q5 (deadline) ───────────────────────────────────────
    if current_step == 'q4' and qid == 'load':
        state['step'] = 'q5'
        _save_session_state(state)

        return {
            'done': False,
            'question': {
                'id': Q5_DEADLINE['id'],
                'text': Q5_DEADLINE['text'],
                'options': [{'key': o['key'], 'label': o['label']}
                            for o in Q5_DEADLINE['options']],
                'has_date_input': True,
            },
            'anchor': None,
            'step': 'q5',
        }

    # ── Q5 (deadline) -> первая якорная задача ───────────────────────────
    if current_step == 'q5' and qid == 'deadline':
        # deadline answer может быть "none" или конкретной датой YYYY-MM-DD
        # Всё уже сохранено в state['answers']['deadline'] = key

        grade_val = state['answers'].get('grade', '')
        try:
            grade = int(grade_val)
        except (ValueError, TypeError):
            return {'done': True, 'question': None, 'anchor': None,
                    'step': 'done', 'error': 'Класс не выбран.'}

        # Вычисляем prior_mu из olymp_reach ответа
        olymp_key = state['answers'].get('olymp_reach', 'none')
        olymp_opt = next(
            (o for o in Q3_OLYMP_REACH['options'] if o['key'] == olymp_key),
            Q3_OLYMP_REACH['options'][0],
        )
        base_mu = olymp_opt['mu']

        # Вычисляем ceiling
        target_key = state['answers'].get('target', 'lvl1')
        target_opt = next(
            (o for o in Q2_TARGET['options'] if o['key'] == target_key),
            Q2_TARGET['options'][0],
        )
        ceiling = compute_route_ceiling(target_opt['target_level'])

        all_tasks, anchor_level, all_sections, fallback_reasons = _pick_all_anchors(
            grade, base_mu, ceiling
        )

        if not all_tasks:
            state['anchors_unavailable'] = True
            state['anchor_tasks'] = []
            state['anchor_results'] = []
            state['anchor_sections'] = []
            state['anchor_fallback_reasons'] = fallback_reasons
            state['step'] = 'anchor_done'
            _save_session_state(state)

            reasons_text = '; '.join(fallback_reasons) if fallback_reasons else 'неизвестная причина'
            logger.error(
                f"onboarding: ALL anchors unavailable for grade={grade}: {reasons_text}"
            )
            return {
                'done': False,
                'question': None,
                'anchor': None,
                'step': 'anchor1_unavailable',
                'anchors_unavailable': True,
                'message': f'Не удалось подобрать якорные задачи для класса {grade}. '
                           f'Сообщите администратору.',
            }

        # Сохраняем все 5 якорей
        state['anchor_tasks'] = all_tasks
        state['anchor_task_ids'] = [t['id'] for t in all_tasks]
        state['anchor_sections'] = all_sections
        state['anchor_results'] = []
        state['current_anchor_idx'] = 0
        state['anchor_fallback_reasons'] = fallback_reasons
        state['ceiling'] = ceiling
        state['step'] = 'anchor1'
        _save_session_state(state)

        section_ru = SECTION_RU.get(all_sections[0], all_sections[0])
        return {
            'done': False,
            'question': None,
            'anchor': {
                'task_id': all_tasks[0]['id'],
                'task_text': all_tasks[0]['task_text'],
                'correct_answer': all_tasks[0]['correct_answer'],
                'level': all_tasks[0]['difficulty_level'],
                'section': all_sections[0],
                'section_ru': section_ru,
                'idx': 1,
                'total': 5,
            },
            'step': 'anchor1',
        }

    # ── Защита: возврат текущего состояния при повторных запросах ───────
    if current_step in ('anchor1', 'anchor2', 'anchor3', 'anchor4', 'anchor5'):
        current_idx = state.get('current_anchor_idx', 0)
        anchors = state.get('anchor_tasks', [])
        if current_idx < len(anchors):
            anchor = anchors[current_idx]
            section_slug = anchor.get('section', '')
            section_ru = SECTION_RU.get(section_slug, section_slug)
            logger.info(
                f"onboarding answer: recovery anchor step={current_step} "
                f"user={user_id} idx={current_idx}"
            )
            return {
                'done': False,
                'question': None,
                'anchor': {
                    'task_id': anchor['id'],
                    'task_text': anchor['task_text'],
                    'correct_answer': anchor.get('correct_answer', ''),
                    'level': anchor.get('difficulty_level', 1),
                    'section': section_slug,
                    'section_ru': section_ru,
                    'idx': current_idx + 1,
                    'total': len(anchors),
                },
                'step': current_step,
            }
        # anchors exhausted
        state['step'] = 'anchor_done'
        _save_session_state(state)
        return {
            'done': False,
            'question': None,
            'anchor': None,
            'step': 'anchor_done',
            'finish_ready': True,
        }

    if current_step == 'anchor_done':
        return {
            'done': False,
            'question': None,
            'anchor': None,
            'step': 'anchor_done',
            'finish_ready': True,
        }

    # ── Неизвестный шаг ─────────────────────────────────────────────────
    logger.warning(f"onboarding answer: unknown step={current_step} qid={qid}")
    return {'done': True, 'question': None, 'anchor': None,
            'step': 'done', 'error': f'Неизвестный шаг: {current_step}',
            '_debug': {'state_step': current_step, 'qid': qid,
                       'answers': state.get('answers', {})}}


def submit_anchor(user_id: int, task_id: int, user_answer: str) -> dict:
    """Проверить ответ на якорную задачу и вернуть следующую или сигнал финала.

    Правила:
      - 5 якорей из 5 РАЗНЫХ разделов (все разделы, фиксированный порядок)
      - Все 5 якорей предвыбраны в _pick_all_anchors
      - Уровень одинаков для всех якорей
      - Каждый якорь пишет результат в level_engine.record_result
    """
    state = _get_session_state()
    if not state:
        return {'done': True, 'correct': None, 'anchor': None,
                'step': 'done', 'finish_ready': False,
                'error': 'Сессия истекла.'}

    current_idx = state.get('current_anchor_idx', 0)
    anchors = state.get('anchor_tasks', [])

    if current_idx >= len(anchors):
        return {'done': True, 'correct': None, 'anchor': None,
                'step': 'done', 'finish_ready': True,
                'error': 'Все якоря уже отвечены.'}

    current_anchor = anchors[current_idx]
    if current_anchor['id'] != task_id:
        return {'done': False, 'correct': None, 'anchor': None,
                'step': state['step'], 'finish_ready': False,
                'error': f'Неверный task_id: ожидался {current_anchor["id"]}'}

    # Проверка ответа
    correct = _check_anchor_answer(user_answer, current_anchor['correct_answer'])
    state['anchor_results'].append(correct)

    # Сохраняем ответ ученика для финишного разбора
    state.setdefault('anchor_user_answers', []).append({
        'anchor_uid': current_anchor.get('source_id', ''),
        'section': current_anchor.get('section', ''),
        'level': current_anchor.get('difficulty_level', 1),
        'user_answer': user_answer,
        'correct_answer': current_anchor.get('correct_answer', ''),
        'correct': correct,
    })

    section_slug = current_anchor.get('section', '?')
    logger.info(
        f"onboarding anchor: user={user_id} task={task_id} "
        f"correct={correct} idx={current_idx} section={section_slug}"
    )

    # ── Записать результат в level_engine ───────────────────────────────
    try:
        from services.level_engine import record_result
        section = current_anchor.get('section', 'algebra')
        level = current_anchor.get('difficulty_level', 1)
        record_result(user_id, section, level, correct)
        logger.info(
            f"onboarding anchor record_result: user={user_id} "
            f"section={section} level={level} correct={correct}"
        )
    except Exception as e:
        logger.warning(f"onboarding anchor record_result failed: {e}")

    # ── Продвигаем индекс к следующему якорю ────────────────────────────
    next_idx = current_idx + 1

    if next_idx < len(anchors):
        # Есть следующий якорь
        next_anchor = anchors[next_idx]
        next_section = next_anchor.get('section', '')
        anchor_step = f'anchor{next_idx + 1}'
        state['current_anchor_idx'] = next_idx
        state['step'] = anchor_step
        _save_session_state(state)

        section_ru = SECTION_RU.get(next_section, next_section)
        return {
            'done': False,
            'correct': correct,
            'anchor': {
                'task_id': next_anchor['id'],
                'task_text': next_anchor['task_text'],
                'correct_answer': next_anchor.get('correct_answer', ''),
                'level': next_anchor['difficulty_level'],
                'section': next_section,
                'section_ru': section_ru,
                'idx': next_idx + 1,
                'total': 5,
            },
            'step': anchor_step,
            'finish_ready': False,
        }
    else:
        # Все 5 якорей отвечены — финиш
        state['current_anchor_idx'] = next_idx
        state['step'] = 'anchor_done'
        _save_session_state(state)

        return {
            'done': False,
            'correct': correct,
            'anchor': None,
            'step': 'anchor_done',
            'finish_ready': True,
        }


def finish(user_id: int) -> dict:
    """Завершить онбординг: вычислить приор, записать в БД, построить очередь."""
    from flask import session
    from models import db
    from models_curator import CuratorState

    state = _get_session_state()
    if not state:
        return {'done': True, 'result': None,
                'error': 'Нет активной сессии онбординга.'}

    answers = state.get('answers', {})
    anchor_results = state.get('anchor_results', [])
    anchor_tasks = state.get('anchor_tasks', [])
    anchor_sections = state.get('anchor_sections', [])
    fallback_reasons = state.get('anchor_fallback_reasons', [])

    if state.get('anchors_unavailable') and not anchor_results:
        anchor_results = []

    # Строим структуру anchors для compute_prior
    anchor_info = []
    anchor_user_answers = state.get('anchor_user_answers', [])
    for i, task in enumerate(anchor_tasks):
        correct = anchor_results[i] if i < len(anchor_results) else None
        ua = anchor_user_answers[i] if i < len(anchor_user_answers) else {}
        info = {
            'task_id': task['id'],
            'section': task.get('section', anchor_sections[i] if i < len(anchor_sections) else ''),
            'level': task.get('difficulty_level', 1),
            'correct': correct,
            'user_answer': ua.get('user_answer', ''),
            'correct_answer': ua.get('correct_answer', ''),
        }
        anchor_info.append(info)

    # Вычисляем итоговый результат
    result: OnboardingResult = compute_prior(answers, anchor_info)

    # Определяем сильнейший и слабейший раздел по mu из level_engine
    strongest_section = ''
    weakest_section = ''
    strongest_mu = -1.0
    weakest_mu = 999.0
    try:
        cs_before = CuratorState.query.filter_by(user_id=user_id).first()
        if cs_before:
            lbs = getattr(cs_before, 'level_by_section', None)
            if lbs and lbs != '{}':
                if isinstance(lbs, str):
                    import json as _json
                    lbs = _json.loads(lbs)
                if isinstance(lbs, dict):
                    for sec, sec_data in lbs.items():
                        mu_val = sec_data.get('mu', 0) if isinstance(sec_data, dict) else float(sec_data)
                        if mu_val > strongest_mu:
                            strongest_mu = mu_val
                            strongest_section = sec
                        if mu_val < weakest_mu:
                            weakest_mu = mu_val
                            weakest_section = sec
    except Exception:
        pass

    # Получаем CuratorState ДО set_prior (чтобы не потерять prep_state)
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
        db.session.flush()  # ensure id assigned

    # Сохраняем prep_state
    prep_state = getattr(cs, 'prep_state', None)
    if not isinstance(prep_state, dict):
        prep_state = {}

    prep_state['onboarding'] = {
        'grade': result.grade,
        'target_level': result.target_level,
        'olymp_reach': result.olymp_reach,
        'daily_tasks': result.daily_tasks,
        'deadline_date': result.deadline_date,
        'days_left': result.days_left,
        'deadline_bucket': result.deadline_bucket,
        'prior_mu': result.prior_mu,
        'prior_sigma': result.prior_sigma,
        'start_level': result.start_level,
        'route_ceiling': result.route_ceiling,
        'conflict': result.conflict,
        'anchors': anchor_info,
        'anchor_user_answers': anchor_user_answers,
        'anchor_fallback_reasons': fallback_reasons,
        'answers': answers,
        'completed_at': datetime.utcnow().isoformat(),
    }

    # Строим очередь тестов
    today = date.today()
    queue = build_initial_queue(result, today)
    prep_state['test_queue'] = [
        {
            'kind': t.kind,
            'scope': t.scope,
            'length': t.length,
            'level_hint': t.level_hint,
            'reason': t.reason,
            'created': t.created,
        }
        for t in queue
    ]

    cs.prep_state = prep_state

    # Цель в goal_text для совместимости
    if not getattr(cs, 'goal_text', None):
        target_labels = {
            1: 'Вводный уровень',
            2: 'Школьный этап ВОШ',
            3: 'Муниципальный этап',
            4: 'Региональный этап',
            5: 'Заключительный этап',
        }
        cs.goal_text = target_labels.get(result.target_level, f'Уровень {result.target_level}')

    db.session.commit()

    # set_prior уже вызван авто-инициализацией в record_result (DEFAULT_MU=3.0).
    # Повторный вызов set_prior ЗАТИРАЕТ level_mu значением ANCHOR_PLAN (1.95).
    # Оставляем level_mu накопленным в record_result (3.20), ставим onboarding_done.
    cs_after = CuratorState.query.filter_by(user_id=user_id).first()
    if cs_after:
        cs_after.onboarding_done = True
        db.session.commit()

    # Очищаем сессию
    _clear_session_state()

    # Получаем level_by_section после record_result для mu по разделам
    section_mu_map = {}
    try:
        cs_mu = CuratorState.query.filter_by(user_id=user_id).first()
        if cs_mu:
            lbs = getattr(cs_mu, 'level_by_section', None)
            if lbs and lbs != '{}':
                import json as _json
                if isinstance(lbs, str):
                    lbs = _json.loads(lbs)
                if isinstance(lbs, dict):
                    for sec, sec_data in lbs.items():
                        section_mu_map[sec] = round(
                            sec_data.get('mu', 0) if isinstance(sec_data, dict) else float(sec_data),
                            2
                        )
    except Exception:
        pass

    # Вычисляем среднее по разделам (согласовано с таблицей разбора)
    if section_mu_map:
        display_mu = round(sum(section_mu_map.values()) / len(section_mu_map), 2)
    else:
        display_mu = result.prior_mu

    # Строим таблицу разбора якорей
    anchor_breakdown = []
    for i, a in enumerate(anchor_info):
        section_slug = a.get('section', '')
        section_ru = SECTION_RU.get(section_slug, section_slug)
        section_mu = section_mu_map.get(section_slug, None)
        anchor_breakdown.append({
            'section_ru': section_ru,
            'level': a.get('level', 1),
            'user_answer': a.get('user_answer', ''),
            'correct_answer': a.get('correct_answer', ''),
            'correct': a.get('correct', False),
            'section_mu': section_mu,
        })

    # Определяем сильнейший/слабейший по anchor_info
    if strongest_section:
        strongest_ru = SECTION_RU.get(strongest_section, strongest_section)
    else:
        # fallback: по anchor_info
        sec_mu = {}
        try:
            cs_fb = CuratorState.query.filter_by(user_id=user_id).first()
            if cs_fb:
                lbs = getattr(cs_fb, 'level_by_section', None)
                if lbs and lbs != '{}':
                    import json as _json
                    if isinstance(lbs, str):
                        lbs = _json.loads(lbs)
                    if isinstance(lbs, dict):
                        for sec, sec_data in lbs.items():
                            mu_val = sec_data.get('mu', 0) if isinstance(sec_data, dict) else float(sec_data)
                            sec_mu[sec] = mu_val
        except Exception:
            pass
        if sec_mu:
            sorted_sec = sorted(sec_mu.items(), key=lambda x: x[1])
            strongest_section = sorted_sec[-1][0]
            weakest_section = sorted_sec[0][0]
            strongest_ru = SECTION_RU.get(strongest_section, strongest_section)
        else:
            # Last resort: based on correctness
            correct_by_section = {}
            for a in anchor_info:
                sec = a.get('section', '')
                correct_by_section.setdefault(sec, []).append(a.get('correct', False))
            if correct_by_section:
                sec_rates = {s: sum(v)/len(v) for s, v in correct_by_section.items()}
                sorted_sec = sorted(sec_rates.items(), key=lambda x: x[1])
                weakest_section = sorted_sec[0][0]
                strongest_section = sorted_sec[-1][0]
                strongest_ru = SECTION_RU.get(strongest_section, strongest_section)
    weakest_ru = SECTION_RU.get(weakest_section, weakest_section) if weakest_section else ''

    deadline_ru = DEADLINE_RU.get(result.deadline_bucket, result.deadline_bucket)

    logger.info(
        f"onboarding finish: user={user_id} grade={result.grade} "
        f"target_level={result.target_level} mu={result.prior_mu} "
        f"sigma={result.prior_sigma} start={result.start_level} "
        f"test_len={result.test_length} anchors={len(anchor_info)}"
    )

    return {
        'done': True,
        'result': result.to_json(),
        'display_mu': display_mu,
        'anchor_breakdown': anchor_breakdown,
        'strongest_ru': strongest_ru,
        'weakest_ru': weakest_ru,
        'deadline_ru': deadline_ru,
        'message': (
            f" Онбординг завершён!\n\n"
            f" Класс: {result.grade}\n"
            f" Целевой уровень: {result.target_level}/5 "
            f"(потолок маршрута: {result.route_ceiling})\n"
            f" Твой уровень: {display_mu} "
            f"(среднее по разделам, стартовый уровень задач: {result.start_level})\n"
            f"⏱ Задач в день: {result.daily_tasks}\n"
            f" Дедлайн: {deadline_ru}"
        ),
    }
