# -*- coding: utf-8 -*-
"""Спринт 2, этап 2: автообновление отметок из решений ученика (2.1.2).

Источник правды о решении — DailyTaskItem (туда пишет штатный поток daily_tasks:
services.submit_answer -> user_answer / is_correct / answered_at / time_spent_seconds).
Связь задача листка <-> DailyTaskItem — worksheet_daily_items (этап 6 спринта 1).

Хуки (ничего в daily_tasks не меняется):
  * SQLAlchemy `before_flush` на db.session: если у DailyTaskItem изменился answered_at
    (или user_answer), находим отметку и применяем переход apply_attempt().
  * after_app_request на GET /daily_tasks/<item_id>/hint (200): hints_used += 1,
    not_started -> in_progress.

Переходы (apply_attempt):
  первый заход (подсказка/неверный ответ)        -> in_progress
  верно, hints_used == 0                          -> solved_self
  верно, hints_used > 0                           -> solved_hint
  неверно и (attempts >= 3 или прошёл due_at)     -> failed
  верно после due_at (т.е. из failed)             -> homework_done
  teacher_override=True: статус не трогаем, счётчики (attempts/hints/time) обновляем.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from flask import request
from sqlalchemy import event, inspect

from models import db
from teacher import teacher_bp
from teacher.worksheets.marks import WorksheetMark
from teacher.worksheets.models import WorksheetAssignment, WorksheetDailyItem, WorksheetTask

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


# ────────────────────────────── чистая логика ───────────────────────────────

def apply_attempt(mark, is_correct: Optional[bool], due_at: Optional[datetime] = None,
                  now: Optional[datetime] = None, time_spent_sec: int = 0, hint: bool = False) -> str:
    """Применить одно событие (ответ или подсказку) к отметке. Возвращает новый статус.
    mark — любой объект с полями status, teacher_override, hints_used, time_spent_sec, attempts."""
    now = now or datetime.utcnow()
    overdue = bool(due_at and now > due_at)

    if hint:
        mark.hints_used = int(mark.hints_used or 0) + 1
    else:
        mark.attempts = int(mark.attempts or 0) + 1
    if time_spent_sec:
        mark.time_spent_sec = int(mark.time_spent_sec or 0) + int(time_spent_sec)

    if mark.teacher_override:
        return mark.status

    if hint:
        if mark.status == "not_started":
            mark.status = "in_progress"
        return mark.status

    if is_correct:
        if overdue or mark.status == "failed":
            mark.status = "homework_done"
        else:
            mark.status = "solved_hint" if mark.hints_used else "solved_self"
    else:
        if mark.status in ("solved_self", "solved_hint", "oral_passed", "homework_done"):
            return mark.status  # уже сдано — повторный неверный ответ не откатывает
        if overdue or mark.attempts >= MAX_ATTEMPTS:
            mark.status = "failed"
        else:
            mark.status = "in_progress"
    return mark.status


def expire_marks_for_assignment(assignment) -> int:
    """После due_at: всё, что не сдано (not_started/in_progress), помечаем failed (кроме override)."""
    n = 0
    for m in WorksheetMark.query.filter_by(worksheet_id=assignment.worksheet_id,
                                          student_id=assignment.student_id).all():
        if not m.teacher_override and m.status in ("not_started", "in_progress"):
            m.status = "failed"
            n += 1
    return n


# ────────────────────────────── поиск отметки ───────────────────────────────

def _mark_for_daily_item(session, daily_item_id: int):
    """DailyTaskItem.id -> (mark, assignment) через worksheet_daily_items; None если задача не из листка."""
    link = session.query(WorksheetDailyItem).filter_by(daily_item_id=daily_item_id).first()
    if link is None:
        return None, None
    a = session.get(WorksheetAssignment, link.assignment_id)
    t = session.get(WorksheetTask, link.worksheet_task_id)
    if a is None or t is None:
        return None, None
    mark = session.query(WorksheetMark).filter_by(worksheet_id=a.worksheet_id, student_id=a.student_id,
                                                  task_id=t.task_id).first()
    if mark is None:
        mark = WorksheetMark(worksheet_id=a.worksheet_id, student_id=a.student_id, task_id=t.task_id)
        session.add(mark)
    return mark, a


# ────────────────────────────── хук на ответ ────────────────────────────────

def _changed(state, attr: str) -> bool:
    try:
        return bool(state.attrs[attr].history.has_changes())
    except Exception:  # noqa: BLE001
        return False


def _on_before_flush(session, flush_context, instances):
    try:
        from daily_tasks.models import DailyTaskItem
    except Exception:  # noqa: BLE001
        return
    for obj in list(session.dirty):
        if isinstance(obj, WorksheetAssignment):
            st = inspect(obj)
            if _changed(st, "status") and obj.status == "expired":
                with session.no_autoflush:
                    try:
                        expire_marks_for_assignment(obj)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("marks_sync: expire marks failed: %s", e)
            continue
        if not isinstance(obj, DailyTaskItem):
            continue
        state = inspect(obj)
        if not (_changed(state, "answered_at") or _changed(state, "user_answer") or _changed(state, "is_correct")):
            continue
        if obj.answered_at is None:
            continue
        with session.no_autoflush:
            try:
                mark, a = _mark_for_daily_item(session, obj.id)
                if mark is None:
                    continue
                hist = state.attrs["time_spent_seconds"].history
                spent = int(obj.time_spent_seconds or 0)
                if hist.has_changes() and hist.deleted and hist.deleted[0]:
                    spent = max(0, spent - int(hist.deleted[0] or 0))
                apply_attempt(mark, bool(obj.is_correct), due_at=a.due_at, now=obj.answered_at,
                              time_spent_sec=spent)
            except Exception as e:  # noqa: BLE001
                logger.warning("marks_sync: before_flush failed for item %s: %s", getattr(obj, "id", None), e)


def register_listeners() -> None:
    """Идемпотентная регистрация before_flush на сессии проекта."""
    if not event.contains(db.session, "before_flush", _on_before_flush):
        event.listen(db.session, "before_flush", _on_before_flush)


register_listeners()


# ────────────────────────────── хук на подсказку ────────────────────────────

@teacher_bp.after_app_request
def _on_hint_request(resp):
    try:
        if request.method != "GET" or resp.status_code != 200:
            return resp
        parts = request.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "daily_tasks" or parts[2] != "hint" or not parts[1].isdigit():
            return resp
        with db.session.no_autoflush:
            mark, a = _mark_for_daily_item(db.session, int(parts[1]))
        if mark is None:
            return resp
        apply_attempt(mark, None, due_at=a.due_at, hint=True)
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning("marks_sync: hint hook failed: %s", e)
    return resp
