# -*- coding: utf-8 -*-
"""Спринт 2, этап 3: API ведомости."""
import json
from flask import abort, jsonify, render_template, request
from models import db, T10GroupMember, User
from teacher import teacher_bp
from teacher.worksheets import bank_index
from teacher.worksheets.api import teacher_required, _own_worksheet
from teacher.worksheets.marks import DONE_STATUSES, MARK_STATUSES, WorksheetMark, ensure_marks_for_worksheet, marks_matrix

GLYPHS={"not_started":"·","in_progress":"…","solved_self":"✓","solved_hint":"±","oral_passed":"+","homework_done":"✓д","failed":"−"}
LABELS={"not_started":"не начинал","in_progress":"в работе","solved_self":"решил сам","solved_hint":"решил с подсказкой","oral_passed":"сдал устно","homework_done":"сделал дома","failed":"не решил"}

def _name(u):
    return next((str(getattr(u,a)) for a in ("display_name","nickname","name","username") if getattr(u,a,None)),getattr(u,"email",None) or f"id {u.id}")
def _students(ws):
    ids={a.student_id for a in ws.assignments.all()}
    if ws.group_id: ids|={m.user_id for m in T10GroupMember.query.filter_by(group_id=ws.group_id).all()}
    return User.query.filter(User.id.in_(ids)).all() if ids else []
def _cell(m):
    return {"id":m.id,"status":m.status,"glyph":GLYPHS[m.status],"label":LABELS[m.status],"override":bool(m.teacher_override),"hints":m.hints_used or 0,"attempts":m.attempts or 0,"time_sec":m.time_spent_sec or 0,"done":m.status in DONE_STATUSES}
def marks_payload(ws):
    students=_students(ws); ensure_marks_for_worksheet(ws,[u.id for u in students]); matrix=marks_matrix(ws,[u.id for u in students]); tasks=sorted(ws.tasks,key=lambda t:t.position); rows=[]
    for u in students:
        cells=[_cell(matrix.get(u.id,{}).get(t.task_id)) for t in tasks]
        rows.append({"student_id":u.id,"name":_name(u),"cells":cells,"done":sum(c["done"] for c in cells),"total":len(tasks)})
    rows.sort(key=lambda r:(-r["done"],r["name"].lower())); cols=[]
    for i,t in enumerate(tasks):
        rec=bank_index.get(t.task_id) or {}; n=sum(r["cells"][i]["done"] for r in rows)
        cols.append({"task_id":t.task_id,"position":t.position,"level":int(rec.get("level") or t.target_level),"topic":rec.get("topic"),"statement":(rec.get("task_text") or "")[:160],"done":n,"pct":round(100*n/len(rows)) if rows else 0})
    return {"worksheet_id":ws.id,"title":ws.title,"grade":ws.grade,"tasks":cols,"students":rows,"statuses":[{"code":s,"glyph":GLYPHS[s],"label":LABELS[s]} for s in MARK_STATUSES]}
@teacher_bp.route("/api/teacher/worksheet/<int:ws_id>/marks")
@teacher_required
def api_worksheet_marks(ws_id): return jsonify(marks_payload(_own_worksheet(ws_id)))
@teacher_bp.route("/api/teacher/marks/<int:mark_id>",methods=["PATCH"])
@teacher_required
def api_mark_patch(mark_id):
    m=db.session.get(WorksheetMark,mark_id)
    if m is None: abort(404)
    _own_worksheet(m.worksheet_id); status=(request.get_json(silent=True) or {}).get("status")
    if status=="auto": m.teacher_override=False
    elif status in MARK_STATUSES: m.status=status; m.teacher_override=True
    else: abort(400,description="status: один из статусов или 'auto'")
    db.session.commit(); return jsonify({"mark":_cell(m)})
@teacher_bp.route("/teacher/worksheet/<int:ws_id>/marks")
@teacher_required
def worksheet_marks_page(ws_id):
    ws=_own_worksheet(ws_id); return render_template("teacher_worksheets/marks.html",page_title=f"Ведомость: {ws.title}",payload_json=json.dumps(marks_payload(ws),ensure_ascii=False),ws=ws)
