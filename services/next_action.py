# -*- coding: utf-8 -*-
"""
services/next_action.py — ЕДИНСТВЕННЫЙ следующий шаг для ученика.

Куратор говорит ОДНО действие. Ученик не выбирает, что проходить.
Никаких LLM-вызовов — функция мгновенная (чистые чтения из БД).

Публичный API:
    get_next_action(user_id) -> dict
        {
            "kind": str,        # onboarding | test | daily | idle
            "title": str,       # короткий заголовок действия
            "cta_label": str,   # текст кнопки
            "url": str,         # реальный маршрут из routes/ или app.py
            "reason": str,      # ОДНО предложение — почему именно это сейчас
            "meta": dict,       # дополнительные данные (length, level_hint, remaining)
        }

Порядок проверок СТРОГО — первое сработавшее возвращаем:
    1. onboarding_done != True  -> kind="onboarding"
    2. test_queue непустая      -> kind="test"
    3. задачи дня не завершены   -> kind="daily"
    4. иначе                    -> kind="idle"
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from models import db
from models_curator import CuratorState

logger = logging.getLogger(__name__)


def _get_cs(user_id: int) -> Optional[CuratorState]:
    """Получить CuratorState или None."""
    return CuratorState.query.filter_by(user_id=user_id).first()


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 задача, 2 задачи, 5 задач."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _tasks_word(n: int) -> str:
    return _plural(n, "задача", "задачи", "задач")


def _daily_not_created() -> Dict[str, Any]:
    """Набор задач дня ещё не сформирован (квеста нет или он пустой)."""
    return {
        "kind": "daily",
        "title": "Задачи дня",
        "cta_label": "Перейти к задачам дня",
        "url": "/daily_tasks",
        "reason": "Набор задач дня ещё не создан. "
                   "Перейди — система подберёт задачи под твой уровень.",
        "meta": {"remaining": 0, "total": 0, "completed": 0},
    }


def _idle() -> Dict[str, Any]:
    """Всё на сегодня сделано."""
    return {
        "kind": "idle",
        "title": "На сегодня всё",
        "cta_label": "Повторить теорию",
        "url": "/prep/coach",
        "reason": "Ты завершил все задачи дня. Отдохни или повтори теорию — "
                   "завтра будет новый набор!",
        "meta": {},
    }


def _live_daily_progress(user_id: int) -> Optional[tuple]:
    """(total, completed) по реальным задачам дня со страницы /daily_tasks.

    2026-10-15 (lavrik #18): ответы на /daily_tasks сохраняются в BankIssue
    (банк) или DailyTaskItem (запасной контур), а не в DailyQuest, поэтому
    DailyQuest.completed_count оставался 0 и куратор показывал
    «Задачи дня: 5 задач» даже после решённых задач.

    Возвращает None, если на сегодня в этих источниках задач нет
    (тогда вызывающий код падает обратно на DailyQuest).
    """
    try:
        from daily_tasks.services import today_in_user_tz
        today = today_in_user_tz()
    except Exception:
        today = date.today()

    total = 0
    completed = 0

    try:
        from models import BankIssue
        issues = BankIssue.query.filter_by(
            user_id=user_id, issued_date=today,
        ).all()
        total += len(issues)
        completed += sum(1 for i in issues if i.user_answer is not None)
    except Exception as e:
        logger.warning("next_action: bank_issues progress failed: %s", e)

    try:
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        ds = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=today,
        ).first()
        if ds is not None:
            items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).all()
            total += len(items)
            completed += sum(
                1 for i in items
                if i.is_correct is not None
                or getattr(i, "user_answer", None) is not None
            )
    except Exception as e:
        logger.warning("next_action: daily_set progress failed: %s", e)

    if total == 0:
        return None
    return total, min(completed, total)


def get_next_action(user_id: int) -> Dict[str, Any]:
    """Определить единственное следующее действие для ученика.

    Возвращает dict с kind, title, cta_label, url, reason, meta.
    """
    cs = _get_cs(user_id)

    # ── 1. Онбординг не завершён ───────────────────────────────────────
    onboarding_done = cs.onboarding_done if cs else False
    if not onboarding_done:
        return {
            "kind": "onboarding",
            "title": "Анкета и знакомство",
            "cta_label": "Пройти анкету",
            "url": "/prep/onboarding",
            "reason": "Сначала нужно познакомиться — анкета и пара якорных задач "
                       "займут 5 минут и заменят длинную диагностику.",
            "meta": {},
        }

    # ── 1.5. Monthly cycle: morning probe pending ──────────────────────
    # 2026-09-15: срез временно отключён — не рекомендуем его действием.
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if False and cycle.get('active') and cycle.get('blocked') and not cycle.get('finished'):
            current_theme = cycle.get('current_theme', '')
            from daily_tasks.monthly_plan import subtopic_title
            theme_title = subtopic_title(current_theme) if current_theme else 'тема дня'
            return {
                "kind": "probe",
                "title": f"Утренний срез: {theme_title}",
                "cta_label": "Пройти утренний срез",
                "url": "/prep/probe",
                "reason": f"Сначала утренний срез: «{theme_title}». 5 задач, "
                           f"примерно 15 минут.",
                "meta": {
                    "current_theme": current_theme,
                    "theme_title": theme_title,
                },
            }
    except Exception:
        pass

    # ── 1.6. Active probe exists (even if not blocked) — resume it ─────
    # 2026-09-15: срез временно отключён — не предлагаем его продолжать.
    try:
        from services.theme_probe import has_active_probe, get_active_probe_theme
        if False and has_active_probe(user_id):
            probe_theme = get_active_probe_theme(user_id) or ''
            from daily_tasks.monthly_plan import subtopic_title
            theme_title = subtopic_title(probe_theme) if probe_theme else 'тема дня'
            return {
                "kind": "probe",
                "title": f"Утренний срез: {theme_title}",
                "cta_label": "Продолжить утренний срез",
                "url": "/prep/probe",
                "reason": f"Утренний срез не завершён. Продолжи: «{theme_title}», "
                           f"примерно 15 минут.",
                "meta": {
                    "current_theme": probe_theme,
                    "theme_title": theme_title,
                },
            }
    except Exception:
        pass

    # ── 2. Очередь тестов непустая ─────────────────────────────────────
    prep_state = getattr(cs, 'prep_state', None) or {}
    if not isinstance(prep_state, dict):
        prep_state = {}

    test_queue = prep_state.get('test_queue', [])
    if test_queue:
        from services.onboarding_tree import next_test, TestTask

        # Восстанавливаем объекты TestTask из словарей очереди
        tasks = []
        for item in test_queue:
            tasks.append(TestTask(
                kind=item.get('kind', 'diagnostic'),
                scope=item.get('scope', 'all_sections'),
                length=item.get('length', 10),
                level_hint=item.get('level_hint', 2),
                reason=item.get('reason', ''),
                created=item.get('created', ''),
            ))

        top = next_test(tasks)
        if top is not None:
            url = f"/olympiad-test?length={top.length}&level_hint={top.level_hint}&scope={top.scope}"
            return {
                "kind": "test",
                "title": f"Адаптивный тест: {top.length} задач",
                "cta_label": "Пройти тест",
                "url": url,
                "reason": top.reason or "Пора проверить уровень.",
                "meta": {
                    "length": top.length,
                    "level_hint": top.level_hint,
                    "kind": top.kind,
                    "scope": top.scope,
                },
            }

    # ── 3. Задачи дня на сегодня не выданы или не завершены ────────────
    # lavrik #18: сначала смотрим реальные задачи дня со страницы
    # /daily_tasks (BankIssue / DailyTaskItem) — именно туда пишутся
    # ответы. DailyQuest остаётся запасным источником.
    live = _live_daily_progress(user_id)
    if live is not None:
        total, completed = live
        completed_at = None
    else:
        today = date.today()
        from models import DailyQuest
        dq = DailyQuest.query.filter_by(
            user_id=user_id, date=today
        ).first()

        if dq is None:
            # Квест на сегодня ещё не создан
            return _daily_not_created()

        # Нормализуем счётчики: None/отрицательные/completed > total
        # раньше давали «осталось 0 из 0» или отрицательные числа.
        try:
            total = int(dq.total_count or 0)
        except (TypeError, ValueError):
            total = 0
        try:
            completed = int(dq.completed_count or 0)
        except (TypeError, ValueError):
            completed = 0
        total = max(0, total)
        completed = min(max(0, completed), total)
        completed_at = dq.completed_at

    remaining = total - completed

    if total == 0:
        # Квест есть, но задачи в него ещё не положены — для ученика это
        # то же самое, что «набор не создан».
        return _daily_not_created()

    if completed_at is None and remaining > 0:
        if completed == 0:
            title = f"Задачи дня: {total} {_tasks_word(total)}"
            reason = (f"Сегодня тебя ждут {total} {_tasks_word(total)}. "
                      f"Начни сейчас — набор обновится завтра.")
            cta = "Начать задачи дня"
        else:
            title = f"Задачи дня: осталось {remaining} из {total}"
            reason = (f"Ты решил {completed} из {total} {_tasks_word(total)}. "
                      f"Осталось {remaining} — добей до конца!")
            cta = "Продолжить задачи дня"
        return {
            "kind": "daily",
            "title": title,
            "cta_label": cta,
            "url": "/daily_tasks",
            "reason": reason,
            "meta": {
                "remaining": remaining,
                "total": total,
                "completed": completed,
            },
        }

    # ── 4. Всё сделано — idle ──────────────────────────────────────────
    # Сюда попадаем и когда completed_at проставлен, и когда все задачи
    # решены, но флаг завершения ещё не записан (remaining == 0).
    return _idle()
