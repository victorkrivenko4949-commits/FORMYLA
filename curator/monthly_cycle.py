# -*- coding: utf-8 -*-
"""
curator/monthly_cycle.py — 30-day monthly preparation cycle orchestrator.

Сценарий:
  1. Куратор выбирает 7 подтем из 15–21 (через build_monthly_plan()).
  2. Начинается месяц подготовки (~30 дней).
  3. Утром ученик проходит адаптивный тест (5 задач) по подтеме дня.
  4. Вечером генерируются «Задачи дня» по той же подтеме.
  5. Первые 7 дней (цикла) — тестовые дни (по одной подтеме каждый день).
  6. Остальные 23 дня — только задачи (без тестов).
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from models import db, User
from models_curator import CuratorState
from daily_tasks.monthly_plan import (
    build_monthly_plan,
    get_or_build_plan,
    pick_day_subtopic,
    subtopic_title,
    parent_topic_for_subtopic,
    current_month_index,
)
from daily_tasks.services import enqueue_daily_generation
from daily_tasks.profile import build_profile, score_to_target_level, CALIBRATION_START_LEVEL
from routes.prep import get_subtopic_test

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

CYCLE_DAYS = 30          # Total days in one monthly cycle
TEST_DAYS = 7            # First 7 days are test days
TASK_ONLY_DAYS = 23      # Remaining 23 days are task-only
CYCLE_VERSION = 1

# ─── Prep State helpers ─────────────────────────────────────────────────────


def _default_prep_state() -> Dict[str, Any]:
    """Вернуть структуру prep_state по умолчанию."""
    return {
        "version": CYCLE_VERSION,
        "cycle_day": 1,
        "tested_subtopics": [],
        "current_subtopic": None,
        "is_test_day": True,
        "level": CALIBRATION_START_LEVEL,
        "generated_today": False,
    }


def _get_or_create_prep_state(curator_state: CuratorState) -> Dict[str, Any]:
    """Вернуть prep_state из CuratorState, создав при отсутствии."""
    state = getattr(curator_state, "prep_state", None) or {}
    if not isinstance(state, dict) or state.get("version") != CYCLE_VERSION:
        state = _default_prep_state()
        curator_state.prep_state = state
    return state


def _save_prep_state(curator_state: CuratorState, state: Dict[str, Any]) -> None:
    """Записать prep_state в CuratorState (в памяти, без коммита)."""
    curator_state.prep_state = state


# ─── Intelligent subtopic selection ──────────────────────────────────────────


def _select_weakest_subtopics(user_id: int, grade: int, count: int = 7) -> List[str]:
    """Выбрать ``count`` слабейших подтем ученика через анализ профиля.

    Алгоритм:
      1. Строит профиль через ``build_profile(user_id)``.
      2. Извлекает ``topics_full`` — список всех подтем с ``pct`` (0–100) и ``measured``.
      3. Сортирует:
         - Сначала измеренные (``measured=True``) по возрастанию ``pct`` (самые слабые).
         - Затем неизмеренные (``measured=False``) — тоже по ``pct`` (или 50, если None).
      4. Берёт первые ``count`` подтем.
      5. Если в профиле меньше ``count`` подтем — дополняет из полного списка класса.

    Возвращает список slug-ов подтем (не более ``count``).
    """
    profile = build_profile(user_id)
    topics_full: List[Dict[str, Any]] = profile.get("topics_full", [])

    # Фильтр: оставляем только те подтемы, которые есть в списке класса
    from daily_tasks.monthly_plan import _ordered_subtopics_for_grade
    grade_subs = set(_ordered_subtopics_for_grade(grade))

    def _sort_key(t: Dict[str, Any]) -> tuple:
        topic = t.get("topic", "")
        pct = t.get("pct")
        measured = t.get("measured", False)
        # measured=False → группа 1 (после измеренных)
        # measured=True  → группа 0
        group = 0 if measured else 1
        # pct=None → ставим 50 как нейтральное значение
        pct_val = float(pct) if pct is not None else 50.0
        return (group, pct_val, topic)

    # Сортируем, отбираем слабейшие
    candidates = sorted(topics_full, key=_sort_key)
    chosen = []
    for t in candidates:
        slug = t.get("topic")
        if slug and slug in grade_subs:
            chosen.append(slug)
        if len(chosen) >= count:
            break

    # Если не хватило — добираем из полного списка класса
    if len(chosen) < count:
        for sub in _ordered_subtopics_for_grade(grade):
            if sub not in chosen:
                chosen.append(sub)
            if len(chosen) >= count:
                break

    return chosen[:count]


# ─── Public API ──────────────────────────────────────────────────────────────


def get_curator_state(user_id: int) -> Optional[CuratorState]:
    """Получить CuratorState для пользователя."""
    return CuratorState.query.filter_by(user_id=user_id).first()


def ensure_monthly_plan(user_id: int) -> Optional[Dict[str, Any]]:
    """Убедиться, что у пользователя есть monthly plan.

    Если плана нет — строит интеллектуально: куратор анализирует профиль
    ученика, выбирает 7 самых слабых подтем (через ``_select_weakest_subtopics``)
    и строит план ровно из них на один месяц.
    Возвращает dict плана или None, если grade не определён.
    """
    cs = get_curator_state(user_id)
    if cs is None:
        logger.warning("ensure_monthly_plan: no CuratorState for user_id=%s", user_id)
        return None

    grade = cs.grade
    if not grade:
        user = User.query.get(user_id)
        if user and hasattr(user, 'grade') and user.grade:
            grade = user.grade
        else:
            logger.warning("ensure_monthly_plan: grade not set for user_id=%s", user_id)
            return None

    # Проверить, есть ли уже валидный план
    plan = getattr(cs, "prep_plan", None)
    if (
        isinstance(plan, dict)
        and plan.get("months")
        and plan.get("version") == 1
    ):
        return plan

    # Строим новый план с интеллектуальным подбором слабых подтем
    today = date.today()
    chosen = _select_weakest_subtopics(user_id, int(grade))
    logger.info(
        "ensure_monthly_plan: user_id=%s grade=%s chosen=%s",
        user_id, grade, chosen,
    )
    plan = build_monthly_plan(int(grade), anchor=today, subtopics=chosen)
    cs.prep_plan = plan
    db.session.commit()
    return plan


def get_today_info(user_id: int) -> Dict[str, Any]:
    """Получить информацию о сегодняшнем дне в цикле подготовки.

    Returns:
        {
            "subtopic": str | None,       # slug подтемы дня
            "subtopic_title": str | None,  # русское название
            "is_test_day": bool,           # нужно ли проходить тест
            "tested": bool,                # подтема уже протестирована
            "cycle_day": int,              # день в цикле (1-30)
            "has_tasks": bool,             # задачи уже сгенерированы
            "level": int,                  # текущий уровень сложности
        }
    """
    cs = get_curator_state(user_id)
    if cs is None:
        return {"subtopic": None, "is_test_day": False, "cycle_day": 0}

    plan = ensure_monthly_plan(user_id)
    if plan is None:
        return {"subtopic": None, "is_test_day": False, "cycle_day": 0}

    today = date.today()
    subtopic_slug = pick_day_subtopic(plan, today)
    if not subtopic_slug:
        return {"subtopic": None, "is_test_day": False, "cycle_day": 0}

    state = _get_or_create_prep_state(cs)

    # Определить день цикла по календарю от anchor
    from daily_tasks.monthly_plan import current_month_index
    from datetime import date as _date
    anchor = today  # fallback
    try:
        anchor = _date.fromisoformat(str(plan.get("anchor_date")))
    except (TypeError, ValueError):
        pass
    days_since_anchor = max(0, (today - anchor).days)
    cycle_day = (days_since_anchor % CYCLE_DAYS) + 1

    is_test_day = cycle_day <= TEST_DAYS
    tested = subtopic_slug in (state.get("tested_subtopics") or [])

    # Обновить состояние, если день изменился
    if state.get("cycle_day") != cycle_day:
        state["cycle_day"] = cycle_day
        state["current_subtopic"] = subtopic_slug
        state["is_test_day"] = is_test_day
        state["generated_today"] = False

        # При переходе на новый месяц — сбросить tested_subtopics
        if cycle_day == 1:
            state["tested_subtopics"] = []

        # Если подтема уже протестирована — это не тестовый день
        if tested and is_test_day:
            state["is_test_day"] = False

        _save_prep_state(cs, state)
        db.session.commit()

    title = subtopic_title(subtopic_slug)

    return {
        "subtopic": subtopic_slug,
        "subtopic_title": title,
        "is_test_day": state.get("is_test_day", False) and not tested,
        "tested": tested,
        "cycle_day": cycle_day,
        "has_tasks": state.get("generated_today", False),
        "level": state.get("level", CALIBRATION_START_LEVEL),
    }


def get_morning_test(user_id: int) -> Dict[str, Any]:
    """Получить тестовые задачи для утреннего теста.

    Если сегодня тестовый день и подтема ещё не протестирована —
    возвращает 5 задач для адаптивного теста.

    Returns:
        {
            "subtopic": str,
            "subtopic_title": str,
            "tasks": [{"id": int, "task_text": str, "topic": str, "difficulty_level": int}, ...],
            "is_test_day": bool,
        }
        или {"is_test_day": False} если сегодня не тестовый день.
    """
    info = get_today_info(user_id)
    if not info.get("subtopic"):
        return {"is_test_day": False, "reason": "Нет подтемы на сегодня"}

    if not info.get("is_test_day"):
        return {"is_test_day": False, "reason": "Сегодня не тестовый день"}

    if info.get("tested"):
        return {"is_test_day": False, "reason": "Подтема уже протестирована"}

    cs = get_curator_state(user_id)
    grade = cs.grade if cs else None
    if not grade:
        user = User.query.get(user_id)
        if user and hasattr(user, 'grade') and user.grade:
            grade = user.grade

    if not grade:
        return {"is_test_day": False, "reason": "Класс не определён"}

    tasks = get_subtopic_test(int(grade), info["subtopic"], count=5)
    return {
        "subtopic": info["subtopic"],
        "subtopic_title": info.get("subtopic_title"),
        "tasks": tasks,
        "is_test_day": True,
    }


def submit_test_and_generate_tasks(
    user_id: int,
    results: List[Dict[str, Any]],
    subtopic: Optional[str] = None,
) -> Dict[str, Any]:
    """Принять результаты теста и запустить вечернюю генерацию задач.

    Results: список dict с ключами:
        - task_id (int): ID задачи из утреннего теста
        - is_correct (bool): правильный/неправильный ответ
        - user_answer (str, optional): ответ ученика
        - difficulty_level (int, optional): оценка сложности учеником

    Returns:
        {
            "success": bool,
            "subtopic": str,
            "level": int,              # определённый уровень
            "generation_queued": bool, # поставлена ли генерация в очередь
            "message": str,
        }
    """
    cs = get_curator_state(user_id)
    if cs is None:
        return {"success": False, "message": "CuratorState не найден"}

    plan = ensure_monthly_plan(user_id)
    if plan is None:
        return {"success": False, "message": "План не найден"}

    today = date.today()
    if subtopic:
        slug = subtopic
    else:
        slug = pick_day_subtopic(plan, today)
    if not slug:
        return {"success": False, "message": "Не удалось определить подтему дня"}

    state = _get_or_create_prep_state(cs)

    # Вычислить уровень из результатов теста
    correct = sum(1 for r in results if r.get("is_correct"))
    total = len(results) if results else 5
    level = score_to_target_level(correct, total)
    if level is None:
        level = CALIBRATION_START_LEVEL

    # Сохранить уровень и отметить подтему как протестированную
    state["level"] = level
    tested = state.get("tested_subtopics") or []
    if slug not in tested:
        tested.append(slug)
    state["tested_subtopics"] = tested

    # Поставить генерацию задач дня в очередь
    try:
        enqueue_daily_generation(
            user_id,
            force_now=False,
            forced_topic=slug,
        )
        state["generated_today"] = True
        gen_status = "queued"
    except Exception as e:
        logger.exception("submit_test_and_generate_tasks: enqueue failed for user=%s", user_id)
        gen_status = f"error: {e}"

    _save_prep_state(cs, state)
    db.session.commit()

    return {
        "success": True,
        "subtopic": slug,
        "subtopic_title": subtopic_title(slug),
        "level": level,
        "correct": correct,
        "total": total,
        "generation_queued": gen_status == "queued",
        "generation_status": gen_status,
        "message": (
            f"Тест по теме «{subtopic_title(slug)}» завершён. "
            f"Решено {correct}/{total}. Уровень: {level}. "
            f"{'Задачи поставлены в очередь генерации.' if gen_status == 'queued' else 'Ошибка генерации: ' + str(gen_status)}"
        ),
    }


def generate_tasks_only(user_id: int, subtopic: Optional[str] = None) -> Dict[str, Any]:
    """Сгенерировать задачи дня без теста (для дней 8-30).

    Вызывается вечером в task-only дни.
    """
    cs = get_curator_state(user_id)
    if cs is None:
        return {"success": False, "message": "CuratorState не найден"}

    plan = ensure_monthly_plan(user_id)
    if plan is None:
        return {"success": False, "message": "План не найден"}

    today = date.today()
    slug = subtopic or pick_day_subtopic(plan, today)
    if not slug:
        return {"success": False, "message": "Не удалось определить подтему дня"}

    state = _get_or_create_prep_state(cs)
    level = state.get("level", CALIBRATION_START_LEVEL)

    try:
        enqueue_daily_generation(
            user_id,
            force_now=False,
            forced_topic=slug,
        )
        state["generated_today"] = True
        gen_status = "queued"
    except Exception as e:
        logger.exception("generate_tasks_only: enqueue failed for user=%s", user_id)
        gen_status = f"error: {e}"

    _save_prep_state(cs, state)
    db.session.commit()

    return {
        "success": gen_status == "queued",
        "subtopic": slug,
        "subtopic_title": subtopic_title(slug),
        "level": level,
        "generation_queued": gen_status == "queued",
        "generation_status": gen_status,
        "message": (
            f"Задачи по теме «{subtopic_title(slug)}» "
            f"{'поставлены в очередь' if gen_status == 'queued' else 'ошибка: ' + str(gen_status)}."
        ),
    }


def get_cycle_progress(user_id: int) -> Dict[str, Any]:
    """Получить общий прогресс по циклу подготовки.

    Returns:
        {
            "cycle_day": int,
            "total_days": 30,
            "tested_subtopics": [str, ...],
            "remaining_tests": int,
            "subtopics_total": int,
            "level": int,
            "is_complete": bool,
        }
    """
    cs = get_curator_state(user_id)
    if cs is None:
        return {"cycle_day": 0, "total_days": CYCLE_DAYS}

    state = _get_or_create_prep_state(cs)
    plan = ensure_monthly_plan(user_id)

    subtopics_total = TEST_DAYS  # 7 подтем в месяц
    if plan:
        months = plan.get("months") or []
        if months:
            month_subs = months[0].get("subtopics") or []
            subtopics_total = len(month_subs)

    tested = state.get("tested_subtopics") or []
    remaining = max(0, subtopics_total - len(tested))
    is_complete = remaining == 0 and state.get("cycle_day", 0) >= CYCLE_DAYS

    return {
        "cycle_day": state.get("cycle_day", 0),
        "total_days": CYCLE_DAYS,
        "tested_subtopics": tested,
        "remaining_tests": remaining,
        "subtopics_total": subtopics_total,
        "level": state.get("level", CALIBRATION_START_LEVEL),
        "is_complete": is_complete,
    }
