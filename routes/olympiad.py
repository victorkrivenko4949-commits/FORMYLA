# -*- coding: utf-8 -*-
"""Blueprint olympiad_bp вЂ” СЂР°Р·РґРµР» В«РћР»РёРјРїРёР°РґС‹В» (/olympiads/*)."""

import json
import logging
from datetime import datetime, date

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from flask_login import current_user, login_required

from models import db, User
from models_olympiad import (
    Probnik, OlympiadTask, TheoryBlock, ProbnikTheory,
    TaskAttempt, StageAttempt, MethodTask, VserossCourseEntry,
    ATTEMPT_STATUSES, STAGE_RESULTS,
)
from services.figures_manifest import get_figures_for_probnik_task

logger = logging.getLogger(__name__)

olympiad_bp = Blueprint("olympiad", __name__, url_prefix="/olympiads")

_COMPETITION = "Р’СЃРћРЁ"
_SEASON_YEAR = 2027

_STAGES = ['Школьный', 'Муниципальный', 'Региональный', 'Заключительный']
_STAGE_ICONS = {
    'Школьный': '',
    'Муниципальный': '️',
    'Региональный': '️',
    'Заключительный': '',
}


def _course_view(grade: int):
    """РћР±С‰Р°СЏ Р»РѕРіРёРєР° РґР»СЏ course / course/10 / course/11."""
    probniks = (Probnik.query
                .filter_by(competition=_COMPETITION, grade=grade, season_year=_SEASON_YEAR)
                .order_by(Probnik.sort_order).all())
    # Р’РђР–РќРћ: TheoryBlock.grades вЂ” db.JSON (РЅР° РїСЂРѕРґРµ в†’ JSONB).
    # .contains(str(grade)) РЅР° JSONB РіРµРЅРµСЂРёСЂСѓРµС‚ РѕРїРµСЂР°С‚РѕСЂ @> Рё РїР°РґР°РµС‚ СЃ
    # InvalidParameterValue: invalid input syntax for type json.
    # РСЃРїРѕР»СЊР·СѓРµРј cast РІ TEXT Рё LIKE (СЂР°Р±РѕС‚Р°РµС‚ Рё РЅР° SQLite, Рё РЅР° PostgreSQL).
    # try/except + rollback: СЃРїРёСЃРѕРє СЂР°Р·РґРµР»РѕРІ РѕРїС†РёРѕРЅР°Р»РµРЅ вЂ” Р»СѓС‡С€Рµ РїСѓСЃС‚РѕР№
    # СЃРїРёСЃРѕРє, С‡РµРј 500 РЅР° СЃС‚СЂР°РЅРёС†Рµ РєСѓСЂСЃР°.
    method_sections = []
    try:
        from sqlalchemy import cast, String
        sections_q = (db.session.query(TheoryBlock.section)
                      .filter(cast(TheoryBlock.grades, String)
                              .like(f'%{grade}%'),
                              TheoryBlock.method_code.isnot(None))
                      .distinct().order_by(TheoryBlock.section).all())
        method_sections = [r[0] for r in sections_q if r[0]]
    except Exception as _sec_err:
        logger.warning(
            '[_course_view] failed to load method_sections for grade=%s: %s',
            grade, _sec_err,
        )
        try:
            db.session.rollback()
        except Exception:
            pass
        method_sections = []
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


@olympiad_bp.route('/course-probnik')
def course_probnik():
    return _course_view(9)


@olympiad_bp.route('/course-probnik/10')
def course_probnik_10():
    return _course_view(10)


@olympiad_bp.route('/course-probnik/11')
def course_probnik_11():
    return _course_view(11)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 3. PROBNIK вЂ” СЃС‚СЂР°РЅРёС†Р° РїСЂРѕР±РЅРёРєР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/probnik/<code>')
def probnik(code):
    """РЎС‚СЂР°РЅРёС†Р° РїСЂРѕР±РЅРёРєР°: СЃРїРёСЃРѕРє Р·Р°РґР°С‡, С‚РµРѕСЂРёСЏ, С‡РµСЂС‚РµР¶Рё."""
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
    # РўРµРѕСЂРёСЏ РґР»СЏ РїСЂРѕР±РЅРёРєР°
    pt_links = (ProbnikTheory.query
                .filter_by(probnik_id=p.id)
                .order_by(ProbnikTheory.display_order)
                .all())
    theory_links = []
    for pt in pt_links:
        tb = TheoryBlock.query.get(pt.theory_block_id)
        if tb:
            theory_links.append(tb)
    # Р§РµСЂС‚РµР¶Рё Рє Р·Р°РґР°С‡Р°Рј
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 4. TASK вЂ” СЃС‚СЂР°РЅРёС†Р° Р·Р°РґР°С‡Рё
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/task/<int:task_id>')
def task(task_id):
    """РЎС‚СЂР°РЅРёС†Р° РѕРґРЅРѕР№ Р·Р°РґР°С‡Рё."""
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 5. TASK_ATTEMPT вЂ” СЃРѕС…СЂР°РЅРёС‚СЊ РїРѕРїС‹С‚РєСѓ (JSON)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/task/<int:task_id>/attempt', methods=['POST'])
@login_required
def task_attempt(task_id):
    """РЎРѕС…СЂР°РЅРёС‚СЊ/РѕР±РЅРѕРІРёС‚СЊ РїРѕРїС‹С‚РєСѓ СЂРµС€РµРЅРёСЏ Р·Р°РґР°С‡Рё."""
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 6. TASK_SUBMIT вЂ” С„РёРЅР°Р»СЊРЅР°СЏ РѕС‚РїСЂР°РІРєР° РѕС‚РІРµС‚Р° (JSON)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/task/<int:task_id>/submit', methods=['POST'])
@login_required
def task_submit(task_id):
    """Р¤РёРЅР°Р»СЊРЅР°СЏ РѕС‚РїСЂР°РІРєР° РѕС‚РІРµС‚Р° Р·Р°РґР°С‡Рё.

    РЎСЂР°РІРЅРёРІР°РµС‚ РѕС‚РІРµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃ task.answer (РїРѕСЃР»Рµ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё).
    Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃС‚СЂСѓРєС‚СѓСЂСѓ, РєРѕС‚РѕСЂСѓСЋ РѕР¶РёРґР°РµС‚ С„СЂРѕРЅС‚:
      {success, is_correct, correct_answer, xp_earned, ai_feedback}
    РўР°РєР¶Рµ РїСЂРѕСЃС‚Р°РІР»СЏРµС‚ TaskAttempt.status:
      - 'solved'    вЂ” РµСЃР»Рё РѕС‚РІРµС‚ СЃРѕРІРїР°Р»;
      - 'attempted' вЂ” РµСЃР»Рё РЅРµ СЃРѕРІРїР°Р».
    """
    import re as _re
    t = OlympiadTask.query.get_or_404(task_id)
    data = request.get_json(force=True, silent=True) or {}
    user_answer_raw = (data.get('answer') or '').strip()
    user_solution = (data.get('solution') or '').strip()

    correct_raw = (getattr(t, 'answer', '') or '').strip()

    def _norm(s):
        if s is None:
            return ''
        s = str(s).strip().lower()
        # СЃРЅРёРјР°РµРј $...$, \(...\), РїСЂРѕР±РµР»С‹ Рё РїРѕРїСѓР»СЏСЂРЅСѓСЋ РєРѕСЃРјРµС‚РёРєСѓ
        s = s.replace('$', '').replace('\\(', '').replace('\\)', '')
        s = s.replace('\\[', '').replace('\\]', '')
        s = s.replace(',', '.')
        s = _re.sub(r'\s+', '', s)
        # 1/2 СЌРєРІРёРІР°Р»РµРЅС‚РЅРѕ \frac{1}{2}
        s = _re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', s)
        # \cdot в†’ *
        s = s.replace('\\cdot', '*').replace('\\times', '*')
        # СѓР±РёСЂР°РµРј С„РёРЅР°Р»СЊРЅСѓСЋ С‚РѕС‡РєСѓ
        s = s.rstrip('.')
        return s

    is_correct = bool(correct_raw) and _norm(user_answer_raw) == _norm(correct_raw)
    ai_comment_extra = ''

    # в”Ђв”Ђ AI-СЌРєРІРёРІР°Р»РµРЅС‚РЅРѕСЃС‚СЊ РѕС‚РІРµС‚Р° (РµСЃР»Рё СЃС‚СЂРѕРіРѕРµ СЃСЂР°РІРЅРµРЅРёРµ РЅРµ СЃРѕРІРїР°Р»Рѕ) в”Ђв”Ђ
    # РСЃРїРѕР»СЊР·СѓРµРј DeepSeek, С‡С‚РѕР±С‹ РїСЂРёР·РЅР°С‚СЊ РѕС‚РІРµС‚С‹ РІСЂРѕРґРµ В«y=39В» СЌРєРІРёРІР°Р»РµРЅС‚РѕРј В«39В»,
    # В«в€љ2В», В«sqrt(2)В», В«1.414вЂ¦В» Рё С‚.Рї. Р•СЃР»Рё РєР»СЋС‡Р° РЅРµС‚ / СЃРµС‚СЊ СѓРїР°Р»Р° вЂ” С‚РёС…Рѕ
    # РїСЂРѕРїСѓСЃРєР°РµРј (is_correct РѕСЃС‚Р°С‘С‚СЃСЏ РєР°Рє Р±С‹Р»).
    if (not is_correct) and correct_raw and user_answer_raw:
        try:
            import os as _os
            if _os.environ.get('DEEPSEEK_API_KEY'):
                from ai.deepseek_client import DeepSeekClient
                import json
                _client = DeepSeekClient()
                _sys = (
                    'РўС‹ РїСЂРѕРІРµСЂСЏРµС€СЊ С€РєРѕР»СЊРЅС‹Р№ РѕС‚РІРµС‚ РЅР° РѕР»РёРјРїРёР°РґРЅСѓСЋ Р·Р°РґР°С‡Сѓ. '
                    'РўРµР±Рµ РґР°СЋС‚ СЌС‚Р°Р»РѕРЅРЅС‹Р№ РѕС‚РІРµС‚ Рё РѕС‚РІРµС‚ СѓС‡РµРЅРёРєР°. Р РµС€Рё, СЌРєРІРёРІР°Р»РµРЅС‚РЅС‹ Р»Рё РѕРЅРё РјР°С‚РµРјР°С‚РёС‡РµСЃРєРё. '
                    'РРіРЅРѕСЂРёСЂСѓР№: Р»РёС€РЅРёРµ РїСЂРѕР±РµР»С‹, СЂРµРіРёСЃС‚СЂ, С„РѕСЂРјР°С‚ (В«РѕС‚РІРµС‚:В», В«=В», В«x=В», В«y=В» Рё С‚.Рї.), '
                    'СЂР°Р·РЅС‹Рµ Р·Р°РїРёСЃРё РґСЂРѕР±РµР№ (1/2 = 0.5 = \\frac{1}{2}), РєРѕСЂРЅРµР№ (sqrt(2) = \\sqrt{2}), '
                    'РµРґРёРЅРёС†С‹ РёР·РјРµСЂРµРЅРёСЏ РµСЃР»Рё РѕРЅРё СЃРѕРІРїР°РґР°СЋС‚ РїРѕ СЃРјС‹СЃР»Сѓ. '
                    'Р•СЃР»Рё СѓС‡РµРЅРёРє РґР°Р» РјРЅРѕР¶РµСЃС‚РІРѕ СЂРµС€РµРЅРёР№ РёР»Рё РґРёР°РїР°Р·РѕРЅ, РїСЂРѕРІРµСЂСЊ РїРѕР»РЅРѕРµ СЃРѕРІРїР°РґРµРЅРёРµ СЃ СЌС‚Р°Р»РѕРЅРѕРј. '
                    'Р’РµСЂРЅРё РЎРўР РћР“Рћ JSON-РѕР±СЉРµРєС‚ Р±РµР· markdown Рё РєРѕРґР°: '
                    '{"is_equivalent": true|false, "comment": "РєСЂР°С‚РєРёР№ РєРѕРјРјРµРЅС‚Р°СЂРёР№ 1-2 РїСЂРµРґР»РѕР¶РµРЅРёСЏ"}'
                )
                _user = (
                    'Р­С‚Р°Р»РѕРЅРЅС‹Р№ РѕС‚РІРµС‚: ' + str(correct_raw) + '\n' +
                    'РћС‚РІРµС‚ СѓС‡РµРЅРёРєР°: ' + str(user_answer_raw) + '\n' +
                    'Р­РєРІРёРІР°Р»РµРЅС‚РЅС‹?'
                )
                _raw = _client.generate(prompt=_user, system_prompt=_sys, temperature=0.0, max_tokens=200)
                _m = _re.search(r'\{[\s\S]*?\}', _raw or '')
                if _m:
                    _data = _json.loads(_m.group(0))
                    if _data.get('is_equivalent') is True:
                        is_correct = True
                    ai_comment_extra = (_data.get('comment') or '').strip()
        except Exception as _e:
            _lg.getLogger(__name__).warning('AI-equivalence check failed: %r', _e)

    # в”Ђв”Ђ upsert TaskAttempt в”Ђв”Ђ
    new_status = 'solved' if is_correct else 'attempted'
    attempt = (TaskAttempt.query
               .filter_by(user_id=current_user.id, task_id=task_id)
               .first())
    if not attempt:
        attempt = TaskAttempt(
            user_id=current_user.id, task_id=task_id,
            status=new_status, note=user_answer_raw,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow() if is_correct else None,
        )
        db.session.add(attempt)
    else:
        # РЅРµ РїРѕРЅРёР¶Р°РµРј СЃС‚Р°С‚СѓСЃ СЃ solved в†’ attempted
        if attempt.status != 'solved':
            attempt.status = new_status
        attempt.note = user_answer_raw
        if is_correct:
            attempt.finished_at = datetime.utcnow()
    db.session.commit()

    xp_earned = 10 if is_correct else 0
    if is_correct:
        ai_feedback = 'РњРѕР»РѕРґРµС†! РћС‚РІРµС‚ СЃРѕРІРїР°Р» СЃ СЌС‚Р°Р»РѕРЅРѕРј.'
    else:
        ai_feedback = (
            'РћС‚РІРµС‚ РЅРµ СЃРѕРІРїР°Р» СЃ СЌС‚Р°Р»РѕРЅРѕРј. Р—Р°РіР»СЏРЅРё РІ В«рџ’Ў РРґРµСЏ СЂРµС€РµРЅРёСЏВ» вЂ” РѕРЅР° С‚РµРїРµСЂСЊ '
            'РѕС‚РєСЂС‹С‚Р°. РџРѕРїСЂРѕР±СѓР№ РµС‰С‘ СЂР°Р· РёР»Рё СЃРІРµСЂСЊСЃСЏ СЃ РїРѕР»РЅС‹Рј СЂРµС€РµРЅРёРµРј.'
        )
    if ai_comment_extra:
        ai_feedback = ai_comment_extra + ' ' + ai_feedback

    return jsonify({
        'success': True,
        'ok': True,
        'is_correct': is_correct,
        'correct_answer': correct_raw,
        'xp_earned': xp_earned,
        'ai_feedback': ai_feedback,
        'status': attempt.status,
    })


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 7. STAGE_START вЂ” РЅР°С‡Р°С‚СЊ РїСЂРѕС…РѕР¶РґРµРЅРёРµ РїСЂРѕР±РЅРёРєР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/probnik/<code>/start', methods=['POST'])
@login_required
def stage_start(code):
    """РќР°С‡Р°С‚СЊ С‚Р°Р№РјРёСЂРѕРІР°РЅРЅРѕРµ РїСЂРѕС…РѕР¶РґРµРЅРёРµ РїСЂРѕР±РЅРёРєР°."""
    p = Probnik.query.filter_by(code=code).first_or_404()
    # Р—Р°РІРµСЂС€Р°РµРј РїСЂРµРґС‹РґСѓС‰РёРµ Р°РєС‚РёРІРЅС‹Рµ РїРѕРїС‹С‚РєРё
    active = (StageAttempt.query
              .filter_by(user_id=current_user.id, probnik_id=p.id, result=None)
              .all())
    for sa in active:
        sa.result = 'abandoned'
    # РЎРѕР·РґР°С‘Рј РЅРѕРІСѓСЋ РїРѕРїС‹С‚РєСѓ
    attempt = StageAttempt(
        user_id=current_user.id,
        probnik_id=p.id,
        started_at=datetime.utcnow(),
    )
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for('olympiad.stage_active', code=code))


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 8. STAGE_ACTIVE вЂ” Р°РєС‚РёРІРЅР°СЏ РїРѕРїС‹С‚РєР° (С‚Р°Р№РјРµСЂ)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/probnik/<code>/active')
@login_required
def stage_active(code):
    """РЎС‚СЂР°РЅРёС†Р° Р°РєС‚РёРІРЅРѕРіРѕ РїСЂРѕС…РѕР¶РґРµРЅРёСЏ РїСЂРѕР±РЅРёРєР°."""
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 9. STAGE_SUBMIT вЂ” СЃРґР°С‚СЊ РїСЂРѕР±РЅРёРє / СЃС‚СЂР°РЅРёС†Р° РѕС‚С‡С‘С‚Р°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/probnik/<code>/submit', methods=['GET', 'POST'])
@login_required
def stage_submit(code):
    """РЎРґР°С‡Р° РїСЂРѕР±РЅРёРєР° (POST) РёР»Рё СЃС‚СЂР°РЅРёС†Р° РѕС‚С‡С‘С‚Р° (GET)."""
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
    # GET вЂ” СЃС‚СЂР°РЅРёС†Р° РѕС‚С‡С‘С‚Р°
    tasks = (OlympiadTask.query
             .filter_by(probnik_id=p.id)
             .order_by(OlympiadTask.sort_order)
             .all())
    return render_template('olympiad/stage_report.html',
                           probnik=p, attempt=attempt, tasks=tasks)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 10. METHODS вЂ” РєР°С‚Р°Р»РѕРі РјРµС‚РѕРґРѕРІ
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/methods')
def methods():
    """РЎРїРёСЃРѕРє РІСЃРµС… СЂР°Р·РґРµР»РѕРІ РјРµС‚РѕРґРѕРІ СЃ РіСЂСѓРїРїРёСЂРѕРІРєРѕР№."""
    blocks = (TheoryBlock.query
              .order_by(TheoryBlock.section, TheoryBlock.sort_order)
              .all())
    # Р“СЂСѓРїРїРёСЂРѕРІРєР° РїРѕ СЂР°Р·РґРµР»Р°Рј
    grouped = {}
    for b in blocks:
        sec = b.section or 'Р‘РµР· СЂР°Р·РґРµР»Р°'
        grouped.setdefault(sec, []).append(b)
    return render_template('olympiad/method.html',
                           sections=grouped, blocks=blocks, detail_block=None,
                           related_blocks=None, tasks_for_method=None)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 11. METHOD_DETAIL вЂ” СЃС‚СЂР°РЅРёС†Р° РѕРґРЅРѕРіРѕ РјРµС‚РѕРґР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/methods/<method_code>')
def method_detail(method_code):
    """РџРѕРґСЂРѕР±РЅР°СЏ СЃС‚СЂР°РЅРёС†Р° РјРµС‚РѕРґР° (РѕРїСЂРµРґРµР»РµРЅРёРµ, С‚РµРѕСЂРµРјС‹, Р·Р°РґР°С‡Рё)."""
    block = TheoryBlock.query.filter_by(method_code=method_code).first_or_404()
    # РЎРІСЏР·Р°РЅРЅС‹Рµ РјРµС‚РѕРґС‹
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
    # Р—Р°РґР°С‡Рё РїРѕ СЌС‚РѕРјСѓ РјРµС‚РѕРґСѓ.
    # Р’РђР–РќРћ: OlympiadTask.method_codes РѕР±СЉСЏРІР»РµРЅРѕ РєР°Рє db.JSON (РЅР° РїСЂРѕРґРµ в†’ JSONB).
    # РџСЂСЏРјРѕР№ `.contains(str)` РЅР° JSONB РіРµРЅРµСЂРёСЂСѓРµС‚ РѕРїРµСЂР°С‚РѕСЂ `@>` Рё РїР°РґР°РµС‚
    # СЃ InvalidParameterValue: "invalid input syntax for type json".
    # РСЃРїРѕР»СЊР·СѓРµРј cast РІ TEXT Рё LIKE вЂ” СЂР°Р±РѕС‚Р°РµС‚ Рё РЅР° SQLite (TEXT-С…СЂР°РЅРёР»РёС‰Рµ),
    # Рё РЅР° PostgreSQL (РїСЂРёРІРµРґРµРЅРёРµ jsonb в†’ text). Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ РѕР±РѕСЂР°С‡РёРІР°РµРј РІ
    # try/except: Р»СЋР±РѕР№ DB-СЃР±РѕР№ РЅРµ РґРѕР»Р¶РµРЅ Р»РѕРјР°С‚СЊ СЃС‚СЂР°РЅРёС†Сѓ РјРµС‚РѕРґР° вЂ”
    # В«СЃРІСЏР·Р°РЅРЅС‹Рµ Р·Р°РґР°С‡РёВ» РѕРїС†РёРѕРЅР°Р»СЊРЅС‹.
    tasks_for_method = []
    try:
        from sqlalchemy import cast, String
        tasks_for_method = (
            OlympiadTask.query
            .filter(cast(OlympiadTask.method_codes, String)
                    .like(f'%"{method_code}"%'))
            .order_by(OlympiadTask.sort_order)
            .limit(50)
            .all()
        )
    except Exception as _tasks_err:
        import logging
        logging.warning(
            '[method_detail] failed to load tasks for %s: %s',
            method_code, _tasks_err,
        )
        try:
            from app import db as _db
            _db.session.rollback()
        except Exception:
            pass
        tasks_for_method = []
    # Р’СЃРµ Р±Р»РѕРєРё РґР»СЏ grouped (РєР°С‚Р°Р»РѕРі РјРµС‚РѕРґРѕРІ)
    all_blocks = (TheoryBlock.query
                  .order_by(TheoryBlock.section, TheoryBlock.sort_order)
                  .all())
    grouped = {}
    for b in all_blocks:
        sec = b.section or 'Р‘РµР· СЂР°Р·РґРµР»Р°'
        grouped.setdefault(sec, []).append(b)
    # CRITICAL FIX: pass sections=None so the template enters DETAIL MODE.
    # The template uses `{% if sections is not none %}` to switch between
    # catalog and detail. Previously sections=grouped (non-None), so clicking
    # any method opened the catalog page instead of the method's detail page
    # вЂ” root cause of the "102 methods don't open" bug.
    # Also rename kwargs to what the template expects:
    #   block (was detail_block), related (was related_blocks),
    #   linked_tasks (was tasks_for_method).
    return render_template('olympiad/method.html',
                           sections=None,
                           block=block,
                           # РќРѕРІС‹Р№ С€Р°Р±Р»РѕРЅ (Group C) РѕР±СЂР°С‰Р°РµС‚СЃСЏ Рє {{ theory.* }} вЂ”
                           # РїРµСЂРµРґР°С‘Рј alias, С‡С‚РѕР±С‹ СЂР°Р±РѕС‚Р°Р»Рё РѕР±Рµ РІРµСЂСЃРёРё СЂР°Р·РјРµС‚РєРё.
                           theory=block,
                           related=related_blocks,
                           linked_tasks=tasks_for_method,
                           # legacy aliases (in case anything else reads them):
                           blocks=all_blocks,
                           detail_block=block,
                           related_blocks=related_blocks,
                           tasks_for_method=tasks_for_method)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 12. METHOD_SECTION вЂ” Р·Р°РґР°С‡Рё РїРѕ СЂР°Р·РґРµР»Сѓ РјРµС‚РѕРґРѕРІ
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/methods/section/<int:grade>/<section_name>')
def method_section(grade, section_name):
    """РЎРїРёСЃРѕРє Р·Р°РґР°С‡ РёР· СЂР°Р·РґРµР»Р° РјРµС‚РѕРґРѕРІ РґР»СЏ СѓРєР°Р·Р°РЅРЅРѕРіРѕ РєР»Р°СЃСЃР°."""
    blocks = (TheoryBlock.query
              .filter(TheoryBlock.section == section_name,
                      TheoryBlock.method_code.isnot(None))
              .order_by(TheoryBlock.sort_order)
              .all())
    # Р’СЃРµ MethodTask РґР»СЏ СЌС‚РѕР№ СЃРµРєС†РёРё
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 13. METHOD_TASK вЂ” СЃС‚СЂР°РЅРёС†Р° РѕРґРЅРѕР№ Р·Р°РґР°С‡Рё РёР· РјРµС‚РѕРґРѕРІ
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
@olympiad_bp.route('/methods/task/<method_task_id>')
def method_task(method_task_id):
    """РЎС‚СЂР°РЅРёС†Р° РѕРґРЅРѕР№ MethodTask."""
    t = MethodTask.query.get_or_404(method_task_id)
    has_aux = getattr(t, 'has_aux', False)
    aux_svg_path = getattr(t, 'aux_svg_path', None) if has_aux else None
    aux_reason = getattr(t, 'aux_reason', None) if has_aux else None
    return render_template('olympiad/method_task.html', task=t,
                           has_aux=has_aux, aux_svg_path=aux_svg_path,
                           aux_reason=aux_reason)


