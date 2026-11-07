# -*- coding: utf-8 -*-
"""routes/probnik_assign.py — назначенный пробник (PROBNIK_ASSIGN_V1).

Ученик:  /probnik-assign/<id>            — страница работы / итогов
         POST .../start | swap | text | photo | photo/<pid>/delete | submit
         GET  .../state                  — опрос: таймер, распознавание фото, проверка
Админ:   /probnik-assign/admin           — назначить пробник любому ученику на дату
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from models import db

logger = logging.getLogger('formyla.probnik_assign_routes')

probnik_assign_bp = Blueprint('probnik_assign', __name__, url_prefix='/probnik-assign')


@probnik_assign_bp.app_context_processor
def _csrf_helper():
    """csrf_token() для карточки пробника в задачах дня и страниц пробника
    (то же, что даёт services.security.init_security; дублируем на случай,
    если блюпринт подключён к приложению без него)."""
    from services.security import get_csrf_token
    return {'csrf_token': get_csrf_token}


def _svc():
    from services import probnik_assign as svc
    return svc


def _PA():
    from models_probnik_assign import ProbnikAssignment
    return ProbnikAssignment


def _today():
    try:
        from daily_tasks.services import today_in_user_tz
        return today_in_user_tz()
    except Exception:  # noqa: BLE001
        return date.today()


def _load(aid: int, owner_only: bool = False):
    a = db.session.get(_PA(), aid)
    if a is None:
        abort(404)
    if a.user_id != current_user.id and (owner_only or not current_user.is_admin):
        abort(404)
    return a


def _csrf_ok() -> bool:
    from services.security import validate_csrf
    tok = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token') or ''
    return validate_csrf(tok)


def _err(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': msg}), code


def _state_json(a):
    svc = _svc()
    return {
        'ok': True,
        'status': a.status,
        'seconds_left': svc.seconds_left(a),
        'total_score': a.total_score,
        'max_score': a.max_score,
        'tasks': [{
            'idx': t['idx'], 'student_text': t['student_text'],
            'photos': t['photos'], 'score': t['score'], 'verdict': t['verdict'],
            'feedback': t['feedback'],
        } for t in svc.work_state(a)],
    }


# ─── Ученик ───────────────────────────────────────────────────────────────

@probnik_assign_bp.route('/<int:aid>')
@login_required
def page(aid):
    svc = _svc()
    a = _load(aid)
    svc.refresh(a)
    if a.status == 'reviewed' and a.user_id == current_user.id and not a.review_seen_at:
        a.review_seen_at = datetime.utcnow()
        db.session.commit()
    return render_template(
        'probnik_assign/work.html', a=a, tasks=svc.work_state(a),
        intro=svc.intro_for(a), seconds_left=svc.seconds_left(a),
        hours=svc.hours_text(a.duration_minutes), task_max=svc.TASK_MAX,
        is_owner=(a.user_id == current_user.id),
        not_yet=(a.assigned_date > _today() and not current_user.is_admin),
        nav=svc.variant_nav(a),
    )


@probnik_assign_bp.route('/<int:aid>/state')
@login_required
def state(aid):
    a = _load(aid)
    _svc().refresh(a)
    return jsonify(_state_json(a))


@probnik_assign_bp.route('/<int:aid>/start', methods=['POST'])
@login_required
def start(aid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    a = _load(aid, owner_only=True)
    if a.assigned_date > _today():
        return _err(f'Пробник откроется {a.assigned_date:%d.%m}.')
    _svc().start(a)
    return jsonify({'ok': True, 'url': url_for('probnik_assign.page', aid=a.id)})


@probnik_assign_bp.route('/<int:aid>/swap', methods=['POST'])
@login_required
def swap(aid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    svc = _svc()
    a = _load(aid, owner_only=True)
    svc.refresh(a)
    if a.status not in ('assigned', 'started') or (a.status == 'started' and not svc.can_edit(a)):
        return _err('Работа уже сдана — сменить вариант нельзя.')
    direction = -1 if (request.get_json(silent=True) or {}).get('dir') == -1 else 1
    if not svc.switch_variant(a, direction):
        return _err('Это первый вариант в списке.' if direction < 0
                    else 'Другого полного варианта для вашего класса нет.')
    nav = svc.variant_nav(a)
    return jsonify({'ok': True, 'title': a.title, 'can_prev': nav['can_prev'],
                    'url': url_for('probnik_assign.page', aid=a.id)})


@probnik_assign_bp.route('/<int:aid>/text', methods=['POST'])
@login_required
def save_text(aid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    svc = _svc()
    a = _load(aid, owner_only=True)
    svc.refresh(a)
    if not svc.can_edit(a):
        return _err('Время вышло — работа уже сдана.', 409)
    data = request.get_json(silent=True) or {}
    try:
        idx = int(data.get('idx'))
    except (TypeError, ValueError):
        return _err('bad idx')
    if not 0 <= idx < len(svc.tasks_of(a)):
        return _err('bad idx')
    svc.save_text(a, idx, str(data.get('text') or ''))
    return jsonify({'ok': True})


@probnik_assign_bp.route('/<int:aid>/photo', methods=['POST'])
@login_required
def add_photo(aid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    svc = _svc()
    a = _load(aid, owner_only=True)
    svc.refresh(a)
    if not svc.can_edit(a):
        return _err('Время вышло — работа уже сдана.', 409)
    try:
        idx = int(request.form.get('idx'))
    except (TypeError, ValueError):
        return _err('bad idx')
    if not 0 <= idx < len(svc.tasks_of(a)):
        return _err('bad idx')
    files = request.files.getlist('photo')
    if not files:
        return _err('Выберите фото.')
    from services.photo_upload import PhotoError
    added = 0
    app = current_app._get_current_object()
    for f in files:
        try:
            svc.add_photo(a, idx, f.read(), f.content_type or '', f.filename or '', app=app)
            added += 1
        except PhotoError as e:
            return _err(str(getattr(e, 'message', None) or e.args[0]))
        except ValueError as e:
            return _err(str(e))
    return jsonify({'ok': True, 'added': added, **_state_json(a)})


@probnik_assign_bp.route('/<int:aid>/photo/<int:pid>/delete', methods=['POST'])
@login_required
def delete_photo(aid, pid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    from models_probnik_assign import ProbnikAssignmentPhoto
    svc = _svc()
    a = _load(aid, owner_only=True)
    if not svc.can_edit(a):
        return _err('Время вышло — работа уже сдана.', 409)
    p = db.session.get(ProbnikAssignmentPhoto, pid)
    if p is None or p.assignment_id != a.id or p.variant_key != a.variant_key:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(_state_json(a))


@probnik_assign_bp.route('/<int:aid>/submit', methods=['POST'])
@login_required
def submit(aid):
    if not _csrf_ok():
        return _err('Обновите страницу и попробуйте ещё раз.', 403)
    a = _load(aid, owner_only=True)
    _svc().submit(a, auto=False, app=current_app._get_current_object())
    return jsonify({'ok': True, 'status': a.status})


# ─── Админ ────────────────────────────────────────────────────────────────

def _admin_only():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(404)


@probnik_assign_bp.route('/admin')
@login_required
def admin():
    _admin_only()
    from models import User
    svc = _svc()
    PA = _PA()
    rows = PA.query.order_by(PA.assigned_date.desc(), PA.id.desc()).limit(100).all()
    users = {u.id: u for u in User.query.filter(User.id.in_({r.user_id for r in rows} or {0})).all()}
    found = []
    q = (request.args.get('q') or '').strip()
    if q:
        if q.isdigit():
            found = User.query.filter(User.id == int(q)).all()
        else:
            pat = f'%{q}%'
            found = User.query.filter((User.name.ilike(pat)) | (User.nickname.ilike(pat))
                                      | (User.email.ilike(pat))).limit(20).all()
    return render_template('probnik_assign/admin.html', rows=rows, users=users,
                           found=found, q=q, svc=svc, today=_today(),
                           default_intro=svc.DEFAULT_INTRO,
                           stages=svc.STAGE_LABELS, seed_log=request.args.get('log'))


@probnik_assign_bp.route('/admin/create', methods=['POST'])
@login_required
def admin_create():
    _admin_only()
    if not _csrf_ok():
        abort(403)
    svc = _svc()
    f = request.form
    try:
        user_id = int(f.get('user_id'))
        on = date.fromisoformat(f.get('date'))
        grade = int(f['grade']) if (f.get('grade') or '').strip() else None
        dur = int(f.get('duration') or svc.DEFAULT_DURATION_MIN)
        a = svc.assign(user_id, on, slug=(f.get('slug') or 'rosatom').strip(),
                       stage=(f.get('stage') or 'final').strip(), duration_minutes=dur,
                       intro_text=(f.get('intro') or '').strip() or None, grade=grade,
                       created_by=current_user.id)
        msg = f'Назначено: #{a.id} {a.title}'
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        msg = f'Ошибка: {e}'
    return redirect(url_for('probnik_assign.admin', log=msg))


@probnik_assign_bp.route('/admin/<int:aid>/delete', methods=['POST'])
@login_required
def admin_delete(aid):
    _admin_only()
    if not _csrf_ok():
        abort(403)
    from models_probnik_assign import ProbnikAssignmentAnswer, ProbnikAssignmentPhoto
    a = _load(aid)
    ProbnikAssignmentAnswer.query.filter_by(assignment_id=a.id).delete()
    ProbnikAssignmentPhoto.query.filter_by(assignment_id=a.id).delete()
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('probnik_assign.admin', log=f'Удалено #{aid}'))


@probnik_assign_bp.route('/admin/<int:aid>/regrade', methods=['POST'])
@login_required
def admin_regrade(aid):
    _admin_only()
    if not _csrf_ok():
        abort(403)
    a = _load(aid)
    if a.status not in ('grading', 'reviewed'):
        return redirect(url_for('probnik_assign.admin', log='Перепроверить можно только сданную работу'))
    a.status = 'grading'
    a.review_seen_at = None
    db.session.commit()
    _svc()._launch_grading(a.id, current_app._get_current_object())
    return redirect(url_for('probnik_assign.admin', log=f'#{aid}: проверка запущена заново'))
