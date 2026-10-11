# -*- coding: utf-8 -*-
"""Этап 6: выдача листка ученику и интеграция с «задачами дня».

Принцип: ИИ-тьютор и daily_tasks НЕ меняются. Задачи листка «вливаются» в сегодняшний
DailyTaskSet ученика как DailyTaskItem (тот же slot_kind='formyla_bank', что и у задач из
FORMYLA_BANK.jsonl в services/daily_task_rotation.py), с отрицательными position — поэтому они
стоят ВЫШЕ адаптивных. Решение идёт через существующий поток daily_tasks и пишется в
DailyTaskItem.user_answer / is_correct / answered_at (основа ведомости спринта 2).
Связь «задача листка ↔ DailyTaskItem» — в своей таблице worksheet_daily_items.

Вливание происходит только в УЖЕ существующий сет на сегодня (его создаёт штатная ротация) —
мы не создаём DailyTaskSet сами, чтобы не перебить генерацию адаптивных задач.

API ученика:
  GET  /api/student/worksheets          — активные и просроченные листки с задачами и статусом решения
  POST /api/student/worksheets/sync     — влить задачи активных листков в сегодняшний сет; вернуть сколько
  GET  /teacher/worksheets/static/student.js — виджет (вставляется в HTML через after_app_request)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from flask import Response, jsonify
from flask_login import current_user, login_required

from models import db
from teacher import teacher_bp
from teacher.worksheets import bank_index
from teacher.worksheets.models import WorksheetAssignment, WorksheetDailyItem

logger = logging.getLogger(__name__)

SLOT_KIND = "formyla_bank"   # как у банка в daily_task_rotation.py — тот же поток проверки/тьютора
POSITION_BASE = -100         # позиции -100, -99, ... => выше адаптивных (position >= 1)


# ─────────────────────────── статусы назначений ─────────────────────────────

def expire_assignments(student_id: Optional[int] = None, now: Optional[datetime] = None) -> int:
    """active -> expired, если due_at прошёл. Нерешённые задачи остаются видимыми в блоке листка."""
    now = now or datetime.utcnow()
    q = WorksheetAssignment.query.filter(WorksheetAssignment.status == "active",
                                         WorksheetAssignment.due_at.isnot(None),
                                         WorksheetAssignment.due_at < now)
    if student_id is not None:
        q = q.filter(WorksheetAssignment.student_id == student_id)
    n = 0
    for a in q.all():
        a.status = "expired"
        n += 1
    if n:
        db.session.commit()
    return n


def _solved_map(assignment_ids: List[int]) -> Dict[int, Dict[int, Any]]:
    """{assignment_id: {worksheet_task_id: DailyTaskItem}} по связям worksheet_daily_items."""
    out: Dict[int, Dict[int, Any]] = {}
    if not assignment_ids:
        return out
    try:
        from daily_tasks.models import DailyTaskItem
        links = WorksheetDailyItem.query.filter(WorksheetDailyItem.assignment_id.in_(assignment_ids)).all()
        items = {i.id: i for i in DailyTaskItem.query.filter(
            DailyTaskItem.id.in_([l.daily_item_id for l in links])).all()} if links else {}
        for l in links:
            out.setdefault(l.assignment_id, {})[l.worksheet_task_id] = items.get(l.daily_item_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("worksheets.student: solved_map failed: %s", e)
    return out


def mark_done(assignment: WorksheetAssignment, solved: Dict[int, Any]) -> None:
    ws_task_ids = {t.id for t in assignment.worksheet.tasks}
    if ws_task_ids and all(getattr(solved.get(tid), "is_correct", None) is True for tid in ws_task_ids):
        if assignment.status != "done":
            assignment.status = "done"
            db.session.commit()


# ─────────────────────────── вливание в задачи дня ──────────────────────────

def sync_into_daily(student_id: int, today: Optional[date] = None) -> Dict[str, Any]:
    """Влить задачи активных листков ученика в его сегодняшний DailyTaskSet (если он уже есть)."""
    today = today or date.today()
    expire_assignments(student_id)
    try:
        from daily_tasks.models import DailyTaskItem, DailyTaskSet
    except Exception as e:  # noqa: BLE001
        return {"injected": 0, "error": f"daily_tasks недоступны: {e}"}

    daily_set = (DailyTaskSet.query.filter_by(user_id=student_id, target_date=today)
                 .order_by(DailyTaskSet.id.desc()).first())
    if daily_set is None:
        return {"injected": 0, "reason": "no_daily_set_today"}

    active = (WorksheetAssignment.query.filter_by(student_id=student_id, status="active")
              .order_by(WorksheetAssignment.due_at.asc()).all())
    if not active:
        return {"injected": 0, "reason": "no_active_assignments"}

    linked = {(l.assignment_id, l.worksheet_task_id)
              for l in WorksheetDailyItem.query.filter(
                  WorksheetDailyItem.assignment_id.in_([a.id for a in active])).all()}
    existing_min = db.session.query(db.func.min(DailyTaskItem.position)).filter_by(daily_set_id=daily_set.id).scalar()
    pos = min(POSITION_BASE, (existing_min or 0) - 1)
    injected = 0
    for a in active:
        for t in sorted(a.worksheet.tasks, key=lambda r: r.position):
            if (a.id, t.id) in linked:
                continue
            rec = bank_index.get(t.task_id)
            if rec is None:
                continue
            item = DailyTaskItem(daily_set_id=daily_set.id, position=pos, slot_kind=SLOT_KIND, subject="math",
                                 topic=rec.get("topic") or a.worksheet.title,
                                 difficulty_level=int(rec.get("level") or t.target_level),
                                 task_text=rec.get("task_text") or "", correct_answer=rec.get("correct_answer") or "",
                                 solution=rec.get("solution") or "")
            svg = (rec.get("figure_svg_path") or "").strip()
            if svg and hasattr(item, "figure_svg_path"):
                item.figure_svg_path = svg
            db.session.add(item)
            db.session.flush()
            db.session.add(WorksheetDailyItem(assignment_id=a.id, worksheet_task_id=t.id, daily_item_id=item.id))
            pos += 1
            injected += 1
    if injected:
        db.session.commit()
    return {"injected": injected, "daily_set_id": daily_set.id}


# ──────────────────────────────── payload ───────────────────────────────────

def student_payload(student_id: int) -> List[Dict[str, Any]]:
    expire_assignments(student_id)
    rows = (WorksheetAssignment.query.filter(WorksheetAssignment.student_id == student_id,
                                             WorksheetAssignment.status.in_(["active", "expired", "done"]))
            .order_by(WorksheetAssignment.due_at.asc()).all())
    solved = _solved_map([a.id for a in rows])
    out = []
    for a in rows:
        s = solved.get(a.id, {})
        if a.status == "active":
            mark_done(a, s)
        tasks = []
        for t in sorted(a.worksheet.tasks, key=lambda r: r.position):
            rec = bank_index.get(t.task_id)
            item = s.get(t.id)
            tasks.append({
                "position": t.position, "task_id": t.task_id, "level": int(rec["level"]) if rec else t.target_level,
                "topic": (rec or {}).get("topic"),
                "statement_html": _statement_html((rec or {}).get("task_text") or ""),
                "daily_item_id": getattr(item, "id", None),
                "solved": getattr(item, "is_correct", None) is True,
                "answered": getattr(item, "answered_at", None) is not None,
            })
        out.append({
            "assignment_id": a.id, "worksheet_id": a.worksheet_id, "title": a.worksheet.title,
            "grade": a.worksheet.grade, "status": a.status,
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "overdue": a.status == "expired",
            "solved_count": sum(1 for x in tasks if x["solved"]), "total": len(tasks),
            "pdf_url": f"/teacher/worksheet/{a.worksheet_id}.pdf",
            "tasks": tasks,
        })
    return out


def _statement_html(text: str) -> str:
    try:
        from utils.math_text_fixer import wrap_bare_math
        return wrap_bare_math(text or "")
    except Exception:  # noqa: BLE001
        return text or ""


# ──────────────────────────────── роуты ─────────────────────────────────────

@teacher_bp.route("/api/student/worksheets", methods=["GET"])
@login_required
def api_student_worksheets():
    return jsonify({"worksheets": student_payload(current_user.id), "now": datetime.utcnow().isoformat()})


@teacher_bp.route("/api/student/worksheets/sync", methods=["POST"])
@login_required
def api_student_worksheets_sync():
    try:
        return jsonify(sync_into_daily(current_user.id))
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception("worksheets.student: sync failed")
        return jsonify({"injected": 0, "error": str(e)}), 500


_STUDENT_JS = r"""
(function(){
  if (window.__wsStudentLoaded) return; window.__wsStudentLoaded = true;
  var onDaily = location.pathname.indexOf('/daily_tasks') === 0;
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
  function fmt(iso){ if(!iso) return ''; var d=new Date(iso.indexOf('Z')>0||iso.indexOf('+')>0?iso:iso+'Z'); return d.toLocaleDateString('ru-RU',{day:'numeric',month:'long'})+' '+d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}); }
  function css(){ var s=document.createElement('style'); s.textContent='.wsb{margin:12px auto;max-width:1000px;padding:14px 16px;border-radius:14px;background:rgba(30,41,59,.94);border:1px solid rgba(244,162,89,.45);color:#fff;font-family:inherit}.wsb h3{margin:0 0 6px;font-size:1.05em}.wsb h3 span{color:#f4a259}.wsb-meta{color:#94a3b8;font-size:.85em;margin-bottom:8px}.wsb-over{color:#fca5a5}.wsb-bar{height:6px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin:6px 0 10px}.wsb-bar div{height:100%;background:#38ef7d}.wsb ol{margin:0;padding-left:1.3em;color:#e2e8f0;line-height:1.5}.wsb li.done{color:#86efac;text-decoration:line-through}.wsb a{color:#ffc98f}.wsb-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px;font-size:.9em}'; document.head.appendChild(s); }
  function render(list){ if(!list.length) return; css();
    var host = document.querySelector('main') || document.querySelector('.container') || document.body;
    var wrap = document.createElement('div'); wrap.id='wsStudentBlock';
    list.forEach(function(w){ var pct = w.total? Math.round(100*w.solved_count/w.total):0;
      var li = w.tasks.map(function(t){ return '<li class="'+(t.solved?'done':'')+'">'+(t.statement_html||'').slice(0,140)+(t.statement_html&&t.statement_html.length>140?'…':'')+'</li>'; }).join('');
      var el=document.createElement('section'); el.className='wsb';
      el.innerHTML='<h3>📝 Листок от учителя <span>до '+esc(fmt(w.due_at))+'</span></h3><div class="wsb-meta">'+esc(w.title)+' · '+w.grade+' класс · решено '+w.solved_count+' из '+w.total+(w.overdue?' · <b class="wsb-over">срок истёк — задачи остаются доступны</b>':'')+(w.status==='done'?' · ✅ всё решено':'')+'</div><div class="wsb-bar"><div style="width:'+pct+'%"></div></div><ol>'+li+'</ol><div class="wsb-row">'+(onDaily?'<span>Задачи листка стоят первыми в списке задач дня.</span>':'<a href="/daily_tasks/">Решать в задачах дня →</a>')+'<a href="'+w.pdf_url+'" target="_blank">PDF</a></div>';
      wrap.appendChild(el); });
    host.insertBefore(wrap, host.firstChild);
    if (window.renderMathInElement) { try{ renderMathInElement(wrap,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true},{left:'$',right:'$',display:false}],throwOnError:false}); }catch(e){} }
  }
  function load(){ fetch('/api/student/worksheets',{credentials:'same-origin'}).then(function(r){return r.ok?r.json():{worksheets:[]};}).then(function(d){ render(d.worksheets||[]); }).catch(function(){}); }
  if (onDaily && !sessionStorage.getItem('wsSynced:'+new Date().toDateString())) {
    fetch('/api/student/worksheets/sync',{method:'POST',credentials:'same-origin'}).then(function(r){return r.json();}).then(function(d){
      sessionStorage.setItem('wsSynced:'+new Date().toDateString(),'1'); if (d && d.injected>0) { location.reload(); } else { load(); } }).catch(load);
  } else { load(); }
})();
"""


@teacher_bp.route("/teacher/worksheets/static/student.js", methods=["GET"])
def student_widget_js():
    resp = Response(_STUDENT_JS, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


_INJECT_TAG = b'<script src="/teacher/worksheets/static/student.js" defer></script>'


@teacher_bp.after_app_request
def _inject_student_widget(resp):
    """Как SECTION_STATS_V1 вставляет трекер в каждую HTML-страницу — вставляем виджет листков
    ученику (role student) перед </body>. Ничего не ломаем: только если это полный HTML 200."""
    try:
        if (resp.status_code != 200 or not resp.mimetype == "text/html" or resp.direct_passthrough
                or not getattr(current_user, "is_authenticated", False)
                or (getattr(current_user, "role", "student") or "student") != "student"):
            return resp
        body = resp.get_data()
        idx = body.rfind(b"</body>")
        if idx < 0 or _INJECT_TAG in body:
            return resp
        resp.set_data(body[:idx] + _INJECT_TAG + body[idx:])
    except Exception as e:  # noqa: BLE001
        logger.debug("worksheets.student: inject skipped: %s", e)
    return resp
