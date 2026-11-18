# -*- coding: utf-8 -*-
"""Страницы конструктора листка (этап 4): /teacher/worksheet/new, /teacher/worksheet/<id>, /teacher/worksheets.
Плюс вспомогательный GET /api/teacher/worksheet/topics?grade=N (темы класса из банка)."""
from __future__ import annotations

import json

from flask import jsonify, render_template, request
from flask_login import current_user

from models import T10Group
from teacher import teacher_bp
from teacher.worksheets import bank_index
from teacher.worksheets.api import teacher_required, _own_worksheet, _ws_payload


def _groups():
    return [{"id": g.id, "name": g.name} for g in
            T10Group.query.filter_by(teacher_id=current_user.id).order_by(T10Group.name).all()]


@teacher_bp.route("/api/teacher/worksheet/topics", methods=["GET"])
@teacher_required
def api_worksheet_topics():
    try:
        grade = int(request.args.get("grade", 0))
    except ValueError:
        grade = 0
    topics = bank_index.topics_for_grade(grade) if 5 <= grade <= 11 else []
    counts = {}
    for t in topics:
        counts[t] = sum(len(bank_index.by_grade_topic_level.get((grade, t, lv), [])) for lv in (1, 2, 3, 4))
    return jsonify({"grade": grade, "topics": [{"name": t, "count": counts[t]} for t in topics]})


@teacher_bp.route("/teacher/worksheet/new", methods=["GET"])
@teacher_required
def worksheet_new_page():
    return render_template("teacher_worksheets/constructor.html",
                           groups=_groups(), worksheet_json="null", page_title="Новый листок")


@teacher_bp.route("/teacher/worksheet/<int:ws_id>", methods=["GET"])
@teacher_required
def worksheet_edit_page(ws_id: int):
    ws = _own_worksheet(ws_id)
    return render_template("teacher_worksheets/constructor.html",
                           groups=_groups(), worksheet_json=json.dumps(_ws_payload(ws), ensure_ascii=False),
                           page_title=ws.title)


@teacher_bp.route("/teacher/worksheets", methods=["GET"])
@teacher_required
def worksheets_list_page():
    return render_template("teacher_worksheets/list.html", groups=_groups(), page_title="Мои листки")
