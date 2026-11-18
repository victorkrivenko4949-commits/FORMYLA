# -*- coding: utf-8 -*-
"""История группы для исключений при выборке (read-only запросы к БД).

* group_student_ids(group_id)           — ученики группы (T10GroupMember.user_id).
* group_solved_task_ids(group_id)       — id задач банка, верно решённых хотя бы одним
  учеником группы. Источник: DailyTaskItem (is_correct=True), сопоставление с банком
  по тексту условия (task_text), т.к. DailyTaskItem не хранит id записи банка —
  так же делает services/daily_task_rotation.py через exclude_texts.
* group_recent_worksheet_task_ids(group_id, days=60) — задачи из листков группы за N дней.
* group_recent_topics(group_id, limit=4) — темы последних листков (для mode='mixed').
Любая ошибка БД -> пустое множество + warning в лог (выборка не должна падать).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Set

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def group_student_ids(group_id: int) -> List[int]:
    try:
        from models import T10GroupMember
        return [m.user_id for m in T10GroupMember.query.filter_by(group_id=group_id).all()]
    except Exception as e:  # noqa: BLE001
        logger.warning("worksheets.history: group_student_ids failed: %s", e)
        return []


def group_solved_task_ids(group_id: int) -> Set[int]:
    if not group_id:
        return set()
    try:
        from models import db
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        from teacher.worksheets import bank_index
        uids = group_student_ids(group_id)
        if not uids:
            return set()
        rows = (db.session.query(DailyTaskItem.task_text)
                .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
                .filter(DailyTaskSet.user_id.in_(uids),
                        DailyTaskItem.is_correct.is_(True))
                .all())
        texts = {_norm(r[0]) for r in rows if r and r[0]}
        if not texts:
            return set()
        bank_index.load()
        return {tid for tid, rec in bank_index.by_id.items()
                if _norm(rec.get("task_text", "")) in texts}
    except Exception as e:  # noqa: BLE001
        logger.warning("worksheets.history: group_solved_task_ids failed: %s", e)
        return set()


def group_recent_worksheet_task_ids(group_id: int, days: int = 60) -> Set[int]:
    if not group_id:
        return set()
    try:
        from models import db
        from teacher.worksheets.models import Worksheet, WorksheetTask
        since = datetime.utcnow() - timedelta(days=days)
        rows = (db.session.query(WorksheetTask.task_id)
                .join(Worksheet, WorksheetTask.worksheet_id == Worksheet.id)
                .filter(Worksheet.group_id == group_id, Worksheet.created_at >= since)
                .all())
        return {int(r[0]) for r in rows}
    except Exception as e:  # noqa: BLE001
        logger.warning("worksheets.history: group_recent_worksheet_task_ids failed: %s", e)
        return set()


def group_recent_topics(group_id: int, limit: int = 4) -> List[str]:
    if not group_id:
        return []
    try:
        from teacher.worksheets.models import Worksheet
        rows = (Worksheet.query.filter_by(group_id=group_id)
                .order_by(Worksheet.created_at.desc()).limit(limit).all())
        out: List[str] = []
        for w in rows:
            try:
                for t in json.loads(w.topics_json or "[]"):
                    if t and t not in out:
                        out.append(t)
            except ValueError:
                continue
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("worksheets.history: group_recent_topics failed: %s", e)
        return []
