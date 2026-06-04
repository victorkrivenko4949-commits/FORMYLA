# -*- coding: utf-8 -*-
"""Blueprint olympiad_bp — раздел «Олимпиады» (/olympiads/*)."""

import json
import logging
from datetime import datetime, date

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from flask_login import current_user, login_required

from models import db, User
from models_olympiad import (
    Probnik, OlympiadTask, TheoryBlock, ProbnikTheory,
    TaskAttempt, StageAttempt, MethodTask,
    ATTEMPT_STATUSES, STAGE_RESULTS,
)
from services.figures_manifest import get_figures_for_probnik_task

logger = logging.getLogger(__name__)

olympiad_bp = Blueprint("olympiad", __name__, url_prefix="/olympiads")

_COMPETITION = "ВсОШ"
_SEASON_YEAR = 2027

# ──────────────────────────────────────────────
# 1. CATALOG — список курсов
# ──────────────────────────────────────────────
@olympiad_bp.route('/courses')
def catalog():
    """Список доступных курсов (9, 10, 11 класс)."""
    return render_template('olympiad/catalog.html')


def _course_view(grade: int):
    """Общая логика для course / course/10 / course/11."""
    probniks = (Probnik.query
                .filter_by(competition=_COMPETITION, grade=grade, season_year=_SEASON_YEAR)
                .order_by(Probnik.sort_order).all())
    sections_q = (db.session.query(TheoryBlock.section)
                  .filter(TheoryBlock.grades.contains(str(grade)),
                          TheoryBlock.method_code.isnot(None))
                  .distinct().order_by(TheoryBlock.section).all())
    method_sections = [r[0] for r in sections_q if r[0]]
    progress_by_probnik = {}
    if current_user.is_authenticated:
        for p in probniks:
            total = OlympiadTask.query.filter_by(probnik_id=p.id).count()
            if total == 0:
                continue
            done = (TaskAttempt.query
                    .filter_by(user_id=current_user.id, status='done')
                    .join(OlympiadTask, OlympiadTask.id == TaskAttempt.task_id)
                    .filter(OlympiadTask.probnik_id == p.id).count())
            progress_by_probnik[p.code] = int(round(done / total * 100))
    return render_template('olympiad/course.html',
                           competition=_COMPETITION, grade=grade,
                           season_year=_SEASON_YEAR,
                           topic_probniks=probniks,
                           progress_by_probnik=progress_by_probnik,
                           method_sections=method_sections)


@olympiad_bp.route('/course')
def course():
    return _course_view(9)


@olympiad_bp.route('/course/10')
def course_10():
    return _course_view(10)


@olympiad_bp.route('/course/11')
def course_11():
    return _course_view(11)


# ──────────────────────────────────────────────
# 3. PROBNIK — страница пробника
# ──────────────────────────────────────────────
@olympiad_bp.route('/probnik/<code>')
def probnik(code):
    """Страница пробника: список задач, теория, чертежи."""
    p = Probnik.query.filter_by(code=code).first_or_404()
    tasks = (OlympiadTask.query
             .filter_by(probnik_id=p.id)
             .order_by(OlympiadTask.sort_order)
             .all())
    attempt_map = {}
    if current_user.is_authenticated:
        attempts = (TaskAttempt.query
                    .filter_by(user_id=current_user.id)
                    .filter(TaskAttempt.task_id.in_([t.id for t in tasks]))
                    .all())
        attempt_map = {a.task_id: a.status for a in attempts}
    # Теория для пробника
    pt_links = (ProbnikTheory.query
                .filter_by(probnik_id=p.id)
                .order_by(ProbnikTheory.display_order)
                .all())
    theory_links = []
    for pt in pt_links:
        tb = TheoryBlock.query.get(pt.theory_block_id)
        if tb:
            theory_links.append(tb)
    # Чертежи к задачам
    task_figures = {}
    for t in tasks:
        figs = get_figures_for_probnik_task(p, t)
        if figs:
            task_figures[t.id] = figs
    return render_template('olympiad/probnik.html',
                           probnik=p, tasks=tasks,
                           attempt_map=attempt_map,
                           theory_links=theory_links,
                           task_figures=task_figures)


# ──────────────────────────────────────────────
# 4. TASK — страница задачи
# ──────────────────────────────────────────────
@olympiad_bp.route('/task/<int:task_id>')
def task(task_id):
    """Страница одной задачи."""
    t = OlympiadTask.query.get_or_404(task_id)
    p = Probnik.query.get(t.probnik_id)
    attempt = None
    if current_user.is_authenticated:
        attempt = (TaskAttempt.query
                   .filter_by(user_id=current_user.id, task_id=task_id)
                   .first())
    condition_figures = get_figures_for_probnik_task(p, t)
    return render_template('olympiad/task.html',
                           task=t, probnik=p,
                           attempt=attempt,
                           condition_figures=condition_figures)


# ──────────────────────────────────────────────
# 5. TASK_ATTEMPT — сохранить попытку (JSON)
# ──────────────────────────────────────────────
@olympiad_bp.route('/task/<int:task_id>/attempt', methods=['POST'])
@login_required
def task_attempt(task_id):
    """Сохранить/обновить попытку решения задачи."""
    t = OlympiadTask.query.get_or_404(task_id)
    data = request.get_json(force=True, silent=True) or {}
    status = data.get('status', 'started')
    self_score = data.get('self_score')
    note = data.get('note', '')
    attempt = (TaskAttempt.query
               .filter_by(user_id=current_user.id, task_id=task_id)
               .first())
    if attempt:
        attempt.status = status
        if self_score is not None:
            attempt.self_score = self_score
        attempt.note = note
    else:
        attempt = TaskAttempt(
            user_id=current_user.id, task_id=task_id,
            status=status, self_score=self_score, note=note,
            started_at=datetime.utcnow(),
        )
        db.session.add(attempt)
    db.session.commit()
    return jsonify({'ok': True, 'status': attempt.status})


# ──────────────────────────────────────────────
# 6. TASK_SUBMIT — финальная отправка ответа (JSON)
# ──────────────────────────────────────────────
@olympiad_bp.route('/task/<int:task_id>/submit', methods=['POST'])
@login_required
def task_submit(task_id):
    """Финальная отправка ответа задачи."""
    t = OlympiadTask.query.get_or_404(task_id)
    data = request.get_json(force=True, silent=True) or {}
    answer_text = data.get('answer', '')
    attempt = (TaskAttempt.query
               .filter_by(user_id=current_user.id, task_id=task_id)
               .first())
    if not attempt:
        attempt = TaskAttempt(
            user_id=current_user.id, task_id=task_id,
            status='submitted', note=answer_text,
            started_at=datetime.utcnow(), finished_at=datetime.utcnow(),
        )
        db.session.add(attempt)
    else:
        attempt.status = 'submitted'
        attempt.note = answer_text
        attempt.finished_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'status': 'submitted'})


# ──────────────────────────────────────────────
# 7. STAGE_START — начать прохождение пробника
# ──────────────────────────────────────────────
@olympiad_bp.route('/probnik/<code>/start', methods=['POST'])
@login_required
def stage_start(code):
    """Начать таймированное прохождение пробника."""
    p = Probnik.query.filter_by(code=code).first_or_404()
    # Завершаем предыдущие активные попытки
    active = (StageAttempt.query
              .filter_by(user_id=current_user.id, probnik_id=p.id, result=None)
              .all())
    for sa in active:
        sa.result = 'abandoned'
    # Создаём новую попытку
    attempt = StageAttempt(
        user_id=current_user.id,
        probnik_id=p.id,
        started_at=datetime.utcnow(),
    )
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for('olympiad.stage_active', code=code))


# ──────────────────────────────────────────────
# 8. STAGE_ACTIVE — активная попытка (таймер)
# ──────────────────────────────────────────────
@olympiad_bp.route('/probnik/<code>/active')
@login_required
def stage_active(code):
    """Страница активного прохождения пробника."""
    p = Probnik.query.filter_by(code=code).first_or_404()
    attempt = (StageAttempt.query
               .filter_by(user_id=current_user.id, probnik_id=p.id, result=None)
               .order_by(StageAttempt.started_at.desc())
               .first())
    if not attempt:
        return redirect(url_for('olympiad.probnik', code=code))
    tasks = (OlympiadTask.query
             .filter_by(probnik_id=p.id)
             .order_by(OlympiadTask.sort_order)
             .all())
    return render_template('olympiad/stage_active.html',
                           probnik=p, attempt=attempt, tasks=tasks)


# ──────────────────────────────────────────────
# 9. STAGE_SUBMIT — сдать пробник / страница отчёта
# ──────────────────────────────────────────────
@olympiad_bp.route('/probnik/<code>/submit', methods=['GET', 'POST'])
@login_required
def stage_submit(code):
    """Сдача пробника (POST) или страница отчёта (GET)."""
    p = Probnik.query.filter_by(code=code).first_or_404()
    attempt = (StageAttempt.query
               .filter_by(user_id=current_user.id, probnik_id=p.id)
               .order_by(StageAttempt.started_at.desc())
               .first())
    if not attempt:
        return redirect(url_for('olympiad.probnik', code=code))
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        attempt.finished_at = datetime.utcnow()
        attempt.total_score = data.get('total_score')
        attempt.task_scores = json.dumps(data.get('task_scores', {}), ensure_ascii=False)
        result = data.get('result')
        if result in ('winner', 'prize', 'participant'):
            attempt.result = result
        else:
            attempt.result = 'participant'
        db.session.commit()
        return jsonify({'ok': True, 'result': attempt.result})
    # GET — страница отчёта
    tasks = (OlympiadTask.query
             .filter_by(probnik_id=p.id)
             .order_by(OlympiadTask.sort_order)
             .all())
    return render_template('olympiad/stage_report.html',
                           probnik=p, attempt=attempt, tasks=tasks)


# ──────────────────────────────────────────────
# 10. METHODS — каталог методов
# ──────────────────────────────────────────────
@olympiad_bp.route('/methods')
def methods():
    """Список всех разделов методов с группировкой."""
    blocks = (TheoryBlock.query
              .order_by(TheoryBlock.section, TheoryBlock.sort_order)
              .all())
    # Группировка по разделам
    grouped = {}
    for b in blocks:
        sec = b.section or 'Без раздела'
        grouped.setdefault(sec, []).append(b)
    return render_template('olympiad/method.html',
                           sections=grouped, blocks=blocks, detail_block=None,
                           related_blocks=None, tasks_for_method=None)


# ──────────────────────────────────────────────
# 11. METHOD_DETAIL — страница одного метода
# ──────────────────────────────────────────────
@olympiad_bp.route('/methods/<method_code>')
def method_detail(method_code):
    """Подробная страница метода (определение, теоремы, задачи)."""
    block = TheoryBlock.query.filter_by(method_code=method_code).first_or_404()
    # Связанные методы
    related_codes = []
    if block.related_methods:
        try:
            related_codes = json.loads(block.related_methods)
        except (json.JSONDecodeError, TypeError):
            related_codes = []
    related_blocks = []
    if related_codes:
        related_blocks = (TheoryBlock.query
                          .filter(TheoryBlock.method_code.in_(related_codes))
                          .all())
    # Задачи по этому методу
    tasks_for_method = (OlympiadTask.query
                        .filter(OlympiadTask.method_codes.contains(method_code))
                        .order_by(OlympiadTask.sort_order)
                        .limit(50)
                        .all())
    # Все блоки для grouped (каталог методов)
    all_blocks = (TheoryBlock.query
                  .order_by(TheoryBlock.section, TheoryBlock.sort_order)
                  .all())
    grouped = {}
    for b in all_blocks:
        sec = b.section or 'Без раздела'
        grouped.setdefault(sec, []).append(b)
    return render_template('olympiad/method.html',
                           sections=grouped, blocks=all_blocks, detail_block=block,
                           related_blocks=related_blocks,
                           tasks_for_method=tasks_for_method)


# ──────────────────────────────────────────────
# 12. METHOD_SECTION — задачи по разделу методов
# ──────────────────────────────────────────────
@olympiad_bp.route('/methods/section/<int:grade>/<section_name>')
def method_section(grade, section_name):
    """Список задач из раздела методов для указанного класса."""
    blocks = (TheoryBlock.query
              .filter(TheoryBlock.section == section_name,
                      TheoryBlock.method_code.isnot(None))
              .order_by(TheoryBlock.sort_order)
              .all())
    # Все MethodTask для этой секции
    method_codes = [b.method_code for b in blocks if b.method_code]
    from sqlalchemy import or_
    grouped = {}
    for mc in method_codes:
        tasks = (MethodTask.query
                 .filter(MethodTask.method_code == mc,
                         MethodTask.grade == str(grade))
                 .order_by(MethodTask.difficulty)
                 .all())
        if tasks:
            grouped[mc] = tasks
    return render_template('olympiad/method_section.html',
                           competition=_COMPETITION, grade=grade,
                           section=section_name, grouped=grouped)


# ──────────────────────────────────────────────
# 13. METHOD_TASK — страница одной задачи из методов
# ──────────────────────────────────────────────
@olympiad_bp.route('/methods/task/<method_task_id>')
def method_task(method_task_id):
    """Страница одной MethodTask."""
    t = MethodTask.query.get_or_404(method_task_id)
    return render_template('olympiad/method_task.html', task=t)


# ──────────────────────────────────────────────
# 14. MY_PROGRESS — страница прогресса пользователя
# ──────────────────────────────────────────────
@olympiad_bp.route('/my-progress')
@login_required
def my_progress():
    """Сводка прогресса по всем пробникам."""
    probniks = (Probnik.query
                .filter_by(competition=_COMPETITION, season_year=_SEASON_YEAR)
                .order_by(Probnik.grade, Probnik.sort_order)
                .all())
    stage_attempts = (StageAttempt.query
                      .filter_by(user_id=current_user.id)
                      .order_by(StageAttempt.started_at.desc())
                      .limit(50)
                      .all())
    # Агрегация
    total_tasks = 0
    total_done = 0
    by_probnik = []
    for p in probniks:
        cnt = OlympiadTask.query.filter_by(probnik_id=p.id).count()
        if cnt == 0:
            continue
        done = (TaskAttempt.query
                .filter_by(user_id=current_user.id, status='done')
                .join(OlympiadTask, OlympiadTask.id == TaskAttempt.task_id)
                .filter(OlympiadTask.probnik_id == p.id)
                .count())
        total_tasks += cnt
        total_done += done
        by_probnik.append({
            'code': p.code,
            'title': p.title,
            'grade': p.grade,
            'total': cnt,
            'done': done,
        })
    totals = {
        'total_tasks': total_tasks,
        'total_done': total_done,
        'total_probniks': len(probniks),
    }
    return render_template('olympiad/my_progress.html',
                           totals=totals,
                           by_probnik=by_probnik,
                           stage_attempts=stage_attempts)
