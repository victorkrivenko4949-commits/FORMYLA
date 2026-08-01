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
    1. onboarding_done != True  → kind="onboarding"
    2. test_queue непустая      → kind="test"
    3. задачи дня не завершены   → kind="daily"
    4. иначе                    → kind="idle"
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
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if cycle.get('active') and cycle.get('blocked') and not cycle.get('finished'):
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
    try:
        from services.theme_probe import has_active_probe, get_active_probe_theme
        if has_active_probe(user_id):
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
    today = date.today()
    from models import DailyQuest
    dq = DailyQuest.query.filter_by(
        user_id=user_id, date=today
    ).first()

    if dq is None:
        # Квест на сегодня ещё не создан
        return {
            "kind": "daily",
            "title": "Задачи дня",
            "cta_label": "Перейти к задачам дня",
            "url": "/daily_tasks",
            "reason": "Набор задач дня ещё не создан. "
                       "Перейди — система подберёт задачи под твой уровень.",
            "meta": {"remaining": 0, "total": 0},
        }

    if dq.completed_at is None:
        remaining = dq.total_count - dq.completed_count
        return {
            "kind": "daily",
            "title": f"Задачи дня: осталось {remaining} из {dq.total_count}",
            "cta_label": "Продолжить задачи дня",
            "url": "/daily_tasks",
            "reason": f"Ты решил {dq.completed_count} из {dq.total_count} задач. "
                       f"Осталось {remaining} — добей до конца!",
            "meta": {
                "remaining": remaining,
                "total": dq.total_count,
                "completed": dq.completed_count,
            },
        }

    # ── 4. Всё сделано — idle ──────────────────────────────────────────
    return {
        "kind": "idle",
        "title": "На сегодня всё",
        "cta_label": "Повторить теорию",
        "url": "/prep/coach",
        "reason": "Ты завершил все задачи дня. Отдохни или повтори теорию — "
                   "завтра будет новый набор!",
        "meta": {},
    }
