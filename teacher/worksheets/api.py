# -*- coding: utf-8 -*-
"""API конструктора листка (этап 3). Все роуты: роль teacher + владение листком/группой, иначе 403.

POST  /api/teacher/worksheet/generate
POST  /api/teacher/worksheet/<id>/replace_task      {task_id, direction}
PATCH /api/teacher/worksheet/<id>                   {title?, order?: [task_id], theory_after?, remove_task_id?}
POST  /api/teacher/worksheet/<id>/assign            {group_id, due_at, student_ids?}
GET   /api/teacher/worksheets?group_id&status
POST  /api/teacher/worksheet/<id>/duplicate
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import abort, jsonify, request
from flask_login import current_user, login_required

from models import db, T10Group, T10GroupMember
from teacher import teacher_bp
from teacher.worksheets import bank_index, selector
from teacher.worksheets.models import (Worksheet, WorksheetTask, WorksheetAssignment,
                                       WORKSHEET_MODES)

logger = logging.getLogger(__name__)


# ───────────────────────────── доступ ────────────────────────────────────

def _user_role() -> str:
    # Та же логика, что в routes/parent_teacher.py::_user_role / _require_role.
    return getattr(current_user, "role", "student") or "student"


def teacher_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if _user_role() != "teacher":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def _own_worksheet(ws_id: int) -> Worksheet:
    ws = db.session.get(Worksheet, ws_id)
    if ws is None:
        abort(404)
    if ws.teacher_id != current_user.id:
        abort(403)
    return ws


def _own_group(group_id: Optional[int]) -> Optional[T10Group]:
    if group_id in (None, "", 0):
        return None
    g = db.session.get(T10Group, int(group_id))
    if g is None:
        abort(404)
    if g.teacher_id != current_user.id:
        abort(403)
    return g


# ─────────────────────────── сериализация ───────────────────────────────

def _statement_html(text: str) -> str:
    try:
        from utils.math_text_fixer import wrap_bare_math
        return wrap_bare_math(text or "")
    except Exception:  # noqa: BLE001
        return text or ""


def _task_payload(row: WorksheetTask) -> Dict[str, Any]:
    rec = bank_index.get(row.task_id)
    if rec is None:
        return {"position": row.position, "task_id": row.task_id, "level": row.target_level,
                "topic": None, "methods": [], "source": None, "statement_html": "", "has_figure": False,
                "added_by": row.added_by, "missing_in_bank": True}
    t = selector.to_task(rec, row.target_level)
    return {"position": row.position, "task_id": t["task_id"], "level": t["level"],
            "target_level": t["target_level"], "topic": t["topic"], "methods": t["methods"],
            "source": t["source"], "statement_html": _statement_html(t["statement"]),
            "has_figure": t["has_figure"], "added_by": row.added_by}


def _ws_payload(ws: Worksheet, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "worksheet_id": ws.id, "title": ws.title, "grade": ws.grade, "mode": ws.mode,
        "topics": json.loads(ws.topics_json or "[]"), "level_min": ws.level_min, "level_max": ws.level_max,
        "theory_after": ws.theory_after, "status": ws.status, "group_id": ws.group_id,
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
        "tasks": [_task_payload(t) for t in sorted(ws.tasks, key=lambda r: r.position)],
        "warnings": warnings or [],
    }


def _json() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        abort(400, description="due_at: ожидается ISO-8601")


# ───────────────────────────── роуты ────────────────────────────────────

@teacher_bp.route("/api/teacher/worksheet/generate", methods=["POST"])
@teacher_required
def api_worksheet_generate():
    d = _json()
    try:
        grade = int(d.get("grade"))
    except (TypeError, ValueError):
        abort(400, description="grade обязателен (5–11)")
    if not 5 <= grade <= 11:
        abort(400, description="grade 5–11")
    n = max(6, min(10, int(d.get("n", 8))))
    level_min = max(1, min(4, int(d.get("level_min", 1))))
    level_max = max(1, min(4, int(d.get("level_max", 4))))
    mode = d.get("mode", "topic")
    if mode not in WORKSHEET_MODES:
        abort(400, description="mode: topic|mixed")
    topics = [str(t).strip() for t in (d.get("topics") or []) if str(t).strip()]
    group = _own_group(d.get("group_id"))
    seed = d.get("seed")

    tasks, warnings = selector.select_tasks(
        grade, topics, n=n, level_min=level_min, level_max=level_max,
        only_olympiad=bool(d.get("only_olympiad", False)),
        exclude_group_id=group.id if group else None, mode=mode,
        seed=int(seed) if seed is not None else None, teacher_id=current_user.id,
    )
    if not tasks:
        return jsonify({"error": "по заданным параметрам кандидатов нет", "warnings": warnings}), 422

    ws = Worksheet(teacher_id=current_user.id, group_id=group.id if group else None,
                   title=(d.get("title") or f"Листок, {grade} класс").strip()[:200],
                   grade=grade, mode=mode, topics_json=json.dumps(topics, ensure_ascii=False),
                   level_min=min(level_min, level_max), level_max=max(level_min, level_max),
                   theory_after=bool(d.get("theory_after", False)), status="draft")
    for t in tasks:
        ws.tasks.append(WorksheetTask(task_id=t["task_id"], position=t["position"],
                                      target_level=t["target_level"], added_by="selector"))
    db.session.add(ws)
    db.session.commit()
    return jsonify(_ws_payload(ws, warnings)), 201


@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>", methods=["GET"])
@teacher_required
def api_worksheet_get(ws_id: int):
    return jsonify(_ws_payload(_own_worksheet(ws_id)))


@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>/replace_task", methods=["POST"])
@teacher_required
def api_worksheet_replace_task(ws_id: int):
    ws = _own_worksheet(ws_id)
    d = _json()
    direction = d.get("direction", "same")
    if direction not in ("same", "harder", "easier"):
        abort(400, description="direction: same|harder|easier")
    try:
        task_id = int(d.get("task_id"))
    except (TypeError, ValueError):
        abort(400, description="task_id обязателен")
    new, warnings = selector.replace_task(ws, task_id, direction,
                                          seed=int(d["seed"]) if d.get("seed") is not None else None)
    if new is None:
        db.session.rollback()
        return jsonify({"error": "замена не найдена", "warnings": warnings}), 422
    ws.updated_at = datetime.utcnow()
    db.session.commit()
    row = next(t for t in ws.tasks if t.task_id == new["task_id"])
    return jsonify({"task": _task_payload(row), "warnings": warnings})


@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>", methods=["PATCH"])
@teacher_required
def api_worksheet_patch(ws_id: int):
    ws = _own_worksheet(ws_id)
    d = _json()
    if "title" in d:
        ws.title = (str(d["title"]).strip() or ws.title)[:200]
    if "theory_after" in d:
        ws.theory_after = bool(d["theory_after"])
    if d.get("remove_task_id") is not None:
        rid = int(d["remove_task_id"])
        row = next((t for t in ws.tasks if t.task_id == rid), None)
        if row is None:
            abort(404, description="задачи нет в листке")
        ws.tasks.remove(row)
        db.session.flush()
        for pos, t in enumerate(sorted(ws.tasks, key=lambda r: r.position), start=1):
            t.position = pos
    if d.get("order") is not None:
        order = [int(x) for x in d["order"]]
        current = {t.task_id for t in ws.tasks}
        if set(order) != current or len(order) != len(current):
            abort(400, description="order должен содержать все task_id листка ровно по одному разу")
        by_id = {t.task_id: t for t in ws.tasks}
        for i, tid in enumerate(order):
            by_id[tid].position = 1000 + i
        db.session.flush()
        for i, tid in enumerate(order, start=1):
            by_id[tid].position = i
    ws.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_ws_payload(ws))


@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>/assign", methods=["POST"])
@teacher_required
def api_worksheet_assign(ws_id: int):
    ws = _own_worksheet(ws_id)
    d = _json()
    group = _own_group(d.get("group_id") or ws.group_id)
    if group is None:
        abort(400, description="group_id обязателен")
    due_at = _parse_dt(d.get("due_at"))
    if due_at is None:
        abort(400, description="due_at обязателен")
    members = {m.user_id for m in T10GroupMember.query.filter_by(group_id=group.id).all()}
    if d.get("student_ids"):
        wanted = {int(x) for x in d["student_ids"]}
        if not wanted <= members:
            abort(403, description="ученик не из этой группы")
        members = wanted
    if not members:
        abort(422, description="в группе нет учеников")

    existing = {a.student_id: a for a in ws.assignments.all()}
    created = 0
    for sid in members:
        a = existing.get(sid)
        if a is None:
            db.session.add(WorksheetAssignment(worksheet_id=ws.id, student_id=sid, due_at=due_at, status="active"))
            created += 1
        else:
            a.due_at, a.status = due_at, "active"
    ws.group_id = group.id
    ws.status = "assigned"
    ws.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"worksheet_id": ws.id, "status": ws.status, "group_id": group.id,
                    "due_at": due_at.isoformat(), "assigned": len(members), "created": created})


@teacher_bp.route("/api/teacher/worksheets", methods=["GET"])
@teacher_required
def api_worksheets_list():
    q = Worksheet.query.filter_by(teacher_id=current_user.id)
    if request.args.get("group_id"):
        g = _own_group(request.args.get("group_id"))
        q = q.filter_by(group_id=g.id)
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    rows = q.order_by(Worksheet.created_at.desc()).limit(200).all()
    return jsonify({"worksheets": [{
        "worksheet_id": w.id, "title": w.title, "grade": w.grade, "mode": w.mode, "status": w.status,
        "group_id": w.group_id, "topics": json.loads(w.topics_json or "[]"),
        "tasks_count": len(w.tasks), "created_at": w.created_at.isoformat() if w.created_at else None,
        "assigned": w.assignments.count(),
    } for w in rows]})


@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>/duplicate", methods=["POST"])
@teacher_required
def api_worksheet_duplicate(ws_id: int):
    src = _own_worksheet(ws_id)
    copy = Worksheet(teacher_id=current_user.id, group_id=src.group_id, title=f"{src.title} (копия)"[:200],
                     grade=src.grade, mode=src.mode, topics_json=src.topics_json,
                     level_min=src.level_min, level_max=src.level_max, theory_after=src.theory_after,
                     status="draft")
    for t in sorted(src.tasks, key=lambda r: r.position):
        copy.tasks.append(WorksheetTask(task_id=t.task_id, position=t.position,
                                        target_level=t.target_level, added_by=t.added_by))
    db.session.add(copy)
    db.session.commit()
    return jsonify(_ws_payload(copy)), 201
