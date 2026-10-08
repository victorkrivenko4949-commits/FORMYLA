# -*- coding: utf-8 -*-
"""
routes/parent_teacher.py — T10 parent / teacher blueprint.

Registered in app.py via:
    from routes.parent_teacher import parent_teacher_bp
    app.register_blueprint(parent_teacher_bp)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required

from models import db, User, T10Group, T10GroupMember, StreakRecord, ParentChildLink
from services.user_helpers import display_name_from_email
from services.parent_teacher_helpers import generate_invite_code, student_streak

parent_teacher_bp = Blueprint(
    'parent_teacher', __name__,
    template_folder='../templates',
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_role() -> str:
    """Return role string for current_user or 'student' if field missing."""
    return getattr(current_user, 'role', 'student') or 'student'


def _require_role(*roles: str) -> None:
    if _user_role() not in roles:
        abort(403)


def _week_avg_tasks(user: User, today: date) -> float:
    """Average number of answered daily tasks per day over the last 7 days.

    Counts DailyTaskItem rows with a non-null ``user_answer`` and
    ``is_correct`` field (i.e. the item was attempted).
    """
    from daily_tasks.models import DailyTaskItem, DailyTaskSet

    start = today - timedelta(days=6)  # today + 6 prior days = rolling 7
    sets = DailyTaskSet.query.filter(
        DailyTaskSet.user_id == user.id,
        DailyTaskSet.target_date >= start,
        DailyTaskSet.target_date <= today,
    ).all()
    set_ids = [s.id for s in sets]
    if not set_ids:
        return 0.0

    total = DailyTaskItem.query.filter(
        DailyTaskItem.daily_set_id.in_(set_ids),
        DailyTaskItem.user_answer.isnot(None),
    ).count()
    return round(total / 7.0, 2)


def _latest_mu_sigma(user_id: int) -> dict:
    """Return {anchor: {'mu': float, 'sigma': float}} for the latest snapshot."""
    from sqlalchemy import desc

    anchors_order = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']
    # The curator_state / level_by_section stores per-anchor levels.
    # We read from curator_state where user_id matches.
    try:
        from models_curator import CuratorState
        state = CuratorState.query.filter_by(user_id=user_id).first()
        if state and state.level_by_section:
            import json as _json
            sections = _json.loads(state.level_by_section) if isinstance(
                state.level_by_section, str
            ) else state.level_by_section
            out = {}
            for anchor in anchors_order:
                sec = sections.get(anchor, {})
                out[anchor] = {
                    'mu': round(float(sec.get('mu', 3.0)), 2),
                    'sigma': round(float(sec.get('sigma', 1.5)), 2),
                }
            return out
    except Exception:
        pass
    return {a: {'mu': 3.0, 'sigma': 1.5} for a in anchors_order}


# ---------------------------------------------------------------------------
# Teacher routes
# ---------------------------------------------------------------------------

@parent_teacher_bp.route('/teacher')
@login_required
def teacher_dashboard():
    _require_role('teacher')

    groups = T10Group.query.filter_by(teacher_id=current_user.id).all()

    # Build per-group stats
    group_stats = []
    today = date.today()
    for g in groups:
        members = T10GroupMember.query.filter_by(group_id=g.id).all()
        student_ids = [m.user_id for m in members]
        students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
        student_data = []
        group_total = 0.0
        for s in students:
            avg = _week_avg_tasks(s, today)
            group_total += avg
            student_data.append({
                'id': s.id,
                'name': display_name_from_email(s.email),
                'avg_tasks': avg,
                'row_color': 'green' if avg >= 4 else 'red',
                'streak': student_streak(s.id),
                'anchors': _latest_mu_sigma(s.id),
            })

        n = len(student_data) or 1
        group_avg = round(group_total / n, 2)
        group_stats.append({
            'group': g,
            'students': student_data,
            'group_avg': group_avg,
            'student_count': len(student_data),
        })

    return render_template(
        'teacher/dashboard.html',
        group_stats=group_stats,
        invite_code_generator=True,  # flag for template
    )


@parent_teacher_bp.route('/teacher/group/create', methods=['POST'])
@login_required
def teacher_group_create():
    _require_role('teacher')
    name = (request.form.get('name', '') or '').strip()
    if not name:
        flash('Название группы не может быть пустым', 'error')
        return redirect(url_for('parent_teacher.teacher_dashboard'))

    code = generate_invite_code()
    g = T10Group(
        name=name,
        teacher_id=current_user.id,
        invite_code=code,
    )
    db.session.add(g)
    db.session.commit()
    flash(f'Группа "{name}" создана. Код приглашения: {code}', 'success')
    return redirect(url_for('parent_teacher.teacher_dashboard'))


@parent_teacher_bp.route('/teacher/group/<int:gid>')
@login_required
def teacher_group_view(gid: int):
    _require_role('teacher')
    g = T10Group.query.get(gid)
    if g is None:
        abort(404)
    if g.teacher_id != current_user.id:
        abort(404)

    members = T10GroupMember.query.filter_by(group_id=g.id).all()
    student_ids = [m.user_id for m in members]
    students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []

    today = date.today()
    student_data = []
    group_total = 0.0
    for s in students:
        # Приватность: если ученик отключил share_progress, его метрики
        # не показываем даже учителю группы (раньше группа этот флаг
        # игнорировала — учитель видел прогресс вопреки настройке).
        if getattr(s, 'share_progress', True) in (False, 0):
            student_data.append({
                'id': s.id,
                'name': display_name_from_email(s.email),
                'avg_tasks': None,
                'row_color': 'gray',
                'streak': None,
                'anchors': {},
                'progress_hidden': True,
            })
            continue
        avg = _week_avg_tasks(s, today)
        group_total += avg
        student_data.append({
            'id': s.id,
            'name': display_name_from_email(s.email),
            'avg_tasks': avg,
            'row_color': 'green' if avg >= 4 else 'red',
            'streak': student_streak(s.id),
            'anchors': _latest_mu_sigma(s.id),
            'progress_hidden': False,
        })

    n = len(student_data) or 1
    group_avg = round(group_total / n, 2)

    return render_template(
        'teacher/group.html',
        group=g,
        students=student_data,
        group_avg=group_avg,
    )


@parent_teacher_bp.route('/teacher/group/<int:gid>/add-student', methods=['POST'])
@login_required
def teacher_group_add_student(gid: int):
    _require_role('teacher')
    g = T10Group.query.get(gid)
    if g is None or g.teacher_id != current_user.id:
        abort(404)

    nickname = (request.form.get('nickname', '') or '').strip()
    if not nickname:
        flash('Введите никнейм ученика', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    student = User.query.filter_by(nickname=nickname).first()
    if student is None:
        flash(f'Ученик с никнеймом "{nickname}" не найден', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    existing = T10GroupMember.query.filter_by(
        group_id=g.id, user_id=student.id
    ).first()
    if existing:
        flash(f'{nickname} уже в группе', 'info')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    gm = T10GroupMember(group_id=g.id, user_id=student.id, role='student')
    db.session.add(gm)
    db.session.commit()
    flash(f'{nickname} добавлен в группу', 'success')
    return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))


@parent_teacher_bp.route('/teacher/group/<int:gid>/rename', methods=['POST'])
@login_required
def teacher_group_rename(gid: int):
    _require_role('teacher')
    g = T10Group.query.get(gid)
    if g is None or g.teacher_id != current_user.id:
        abort(404)

    name = (request.form.get('name', '') or '').strip()
    if not name:
        flash('Название не может быть пустым', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    g.name = name
    db.session.commit()
    flash('Название группы обновлено', 'success')
    return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))


@parent_teacher_bp.route('/teacher/group/<int:gid>/delete', methods=['POST'])
@login_required
def teacher_group_delete(gid: int):
    _require_role('teacher')
    g = T10Group.query.get(gid)
    if g is None or g.teacher_id != current_user.id:
        abort(404)

    T10GroupMember.query.filter_by(group_id=g.id).delete()
    db.session.delete(g)
    db.session.commit()
    flash('Группа удалена', 'success')
    return redirect(url_for('parent_teacher.teacher_dashboard'))


# ---------------------------------------------------------------------------
# Parent routes
# ---------------------------------------------------------------------------

@parent_teacher_bp.route('/parent')
@login_required
def parent_dashboard():
    _require_role('parent')

    # Основная привязка — подтверждённая связь ParentChildLink (по id,
    # не по никнейму: никнейм ребёнок может сменить, связь не ломается).
    link = ParentChildLink.query.filter_by(
        parent_id=current_user.id, status='accepted'
    ).order_by(ParentChildLink.responded_at.desc()).first()

    child = User.query.get(link.child_id) if link else None

    if child is None:
        # Легаси-путь: раньше привязка хранилась в User.child_email
        # (никнейм ребёнка) без таблицы связей.
        child_nick = getattr(current_user, 'child_email', None)
        if child_nick:
            child = User.query.filter_by(nickname=child_nick).first()

    if child is None:
        # Привязанного ребёнка нет. Покажем форму добавления, а если есть
        # pending-запрос — его статус («ждём ответа ребёнка»).
        pending = ParentChildLink.query.filter_by(
            parent_id=current_user.id, status='pending'
        ).order_by(ParentChildLink.created_at.desc()).first()
        pending_child = User.query.get(pending.child_id) if pending else None
        return render_template(
            'parent/dashboard.html',
            child=None,
            no_child_bound=True,
            pending_child_nickname=(pending_child.nickname if pending_child else None),
            pending_since=(pending.created_at if pending else None),
        )

    if not getattr(child, 'share_progress', True):
        return render_template(
            'parent/dashboard.html',
            child=child,
            share_blocked=True,
            not_found=False,
        )

    today = date.today()
    avg = _week_avg_tasks(child, today)
    return render_template(
        'parent/dashboard.html',
        child=child,
        child_display=display_name_from_email(child.email),
        avg_tasks=avg,
        streak=student_streak(child.id),
        anchors=_latest_mu_sigma(child.id),
        not_found=False,
        share_blocked=False,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Student detail page (accessible by teacher / parent)
# ---------------------------------------------------------------------------

SECTION_NAMES_RU = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'combinatorics': 'Комбинаторика',
    'logic': 'Логика',
    'number_theory': 'Теория чисел',
}


def _section_radar(student_id: int) -> list:
    """Собрать данные для радара по 5 разделам (mu из level_engine)."""
    from services.level_engine import get_state
    state = get_state(student_id)
    by_section = state.get('by_section', {}) or {}
    radar = []
    for section in ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory'):
        sec = by_section.get(section) or {}
        mu = sec.get('mu', state.get('mu', 3.0))
        try:
            mu = float(mu)
        except (TypeError, ValueError):
            mu = 3.0
        radar.append({
            'name': SECTION_NAMES_RU.get(section, section),
            'value': round(mu, 2),
        })
    return radar


def _theme_radars(student_id: int, grade: int) -> list:
    """Собрать по одному радару на раздел: точки = подтемы (mu)."""
    from services.level_engine import get_level_by_theme
    from services.theme_registry import themes_of_section, theme_title
    lbt = get_level_by_theme(student_id) or {}

    radars = []
    for section in ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory'):
        theme_ids = themes_of_section(grade, section)
        points = []
        for tid in theme_ids:
            mu = None
            entry = lbt.get(tid)
            if isinstance(entry, dict):
                mu = entry.get('mu')
            if mu is None:
                mu = 0
            try:
                mu = float(mu)
            except (TypeError, ValueError):
                mu = 0.0
            points.append({
                'name': theme_title(tid),
                'value': round(mu, 2),
            })
        if points:
            radars.append({
                'section': section,
                'section_name': SECTION_NAMES_RU.get(section, section),
                'points': points,
            })
    return radars


def _month_calendar(student_id: int) -> list:
    """Календарь текущего месяца: сколько задач решено / выдано за день."""
    from calendar import monthrange
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from collections import defaultdict

    today = date.today()
    year, month = today.year, today.month
    last_day = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)

    sets = DailyTaskSet.query.filter(
        DailyTaskSet.user_id == student_id,
        DailyTaskSet.target_date >= start,
        DailyTaskSet.target_date <= end,
    ).all()

    by_day = defaultdict(lambda: {'solved': 0, 'total': 0})
    set_ids = [s.id for s in sets]
    if set_ids:
        items = DailyTaskItem.query.filter(
            DailyTaskItem.daily_set_id.in_(set_ids)
        ).all()
        set_map = {s.id: s for s in sets}
        for it in items:
            ds = set_map.get(it.daily_set_id)
            if not ds:
                continue
            d = ds.target_date
            by_day[d]['total'] += 1
            if it.is_correct:
                by_day[d]['solved'] += 1

    days = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        info = by_day.get(d, {'solved': 0, 'total': 0})
        days.append({
            'day': day,
            'solved': info['solved'],
            'total': info['total'],
            'is_today': d == today,
        })
    return days


@parent_teacher_bp.route('/student/<int:sid>')
@login_required
def student_detail(sid: int):
    student = User.query.get(sid)
    if student is None:
        abort(404)

    role = _user_role()

    # STUDENT_VIEW_FIX_V1: явное разделение доступа.
    # Раньше любой student получал 403 даже на собственный профиль, а у
    # учителя/родителя падало из-за share_progress=NULL в старых строках
    # PostgreSQL (поле nullable=False, но исторические записи могли быть NULL).
    is_self = current_user.id == student.id
    if role == 'teacher':
        # Teacher must have this student in one of their groups
        member = T10GroupMember.query.join(T10Group).filter(
                T10GroupMember.user_id == sid,
                T10Group.teacher_id == current_user.id,
        ).first()
        if member is None:
            abort(403)
    elif role == 'parent':
        # Доступ по подтверждённой связи ParentChildLink (устойчиво к смене
        # никнейма) или по легаси-полю child_email для старых привязок.
        _link = ParentChildLink.query.filter_by(
            parent_id=current_user.id, child_id=student.id, status='accepted',
        ).first()
        _legacy_ok = (
            getattr(current_user, 'child_email', None) is not None
            and current_user.child_email == student.nickname
        )
        if _link is None and not _legacy_ok:
            abort(403)
    elif not is_self:
        # Обычный ученик может видеть только свой профиль.
        abort(403)

    # share_progress: NULL/отсутствует трактуем как «разрешено» (default=True).
    # Блокируем только явный False/0 при чужом просмотре.
    if not is_self and getattr(student, 'share_progress', True) in (False, 0):
        abort(403)

    today = date.today()
    avg = _week_avg_tasks(student, today)

    grade = getattr(student, 'preferred_grade', None)
    try:
        grade = int(grade) if grade else 7
    except (TypeError, ValueError):
        grade = 7

    return render_template(
        'student/profile_detail.html',
        student=student,
        student_display=display_name_from_email(student.email),
        avg_tasks=avg,
        streak=student_streak(student.id),
        anchors=_latest_mu_sigma(student.id),
        section_radar=_section_radar(student.id),
        theme_radars=_theme_radars(student.id, grade),
        calendar_days=_month_calendar(student.id),
    )


# ---------------------------------------------------------------------------
# Profile actions (group join / share toggle)
# ---------------------------------------------------------------------------

@parent_teacher_bp.route('/profile/join-group', methods=['POST'])
@login_required
def profile_join_group():
    code = (request.form.get('invite_code', '') or '').strip().upper()
    if len(code) != 6:
        flash('NOT FOUND: неверный код приглашения', 'error')
        return redirect('/profile')

    g = T10Group.query.filter_by(invite_code=code).first()
    if g is None:
        flash('NOT FOUND: группа с таким кодом не найдена', 'error')
        return redirect('/profile')

    existing = T10GroupMember.query.filter_by(
        group_id=g.id, user_id=current_user.id
    ).first()
    if existing:
        flash('Вы уже состоите в этой группе', 'info')
        return redirect('/profile')

    gm = T10GroupMember(group_id=g.id, user_id=current_user.id, role='student')
    db.session.add(gm)
    db.session.commit()
    flash(f'Вы вступили в группу "{g.name}"', 'success')
    return redirect('/profile')


@parent_teacher_bp.route('/profile/share', methods=['POST'])
@login_required
def profile_share_toggle():
    val = request.form.get('share_progress', '0')
    current_user.share_progress = (val == '1')
    db.session.commit()
    flash('Настройки доступа обновлены', 'success')
    return redirect('/profile')


@parent_teacher_bp.route('/parent/bind-child', methods=['POST'])
@login_required
def parent_bind_child():
    """Отправить ребёнку ЗАПРОС на привязку (не мгновенная привязка!).

    Раньше привязка была мгновенной: родитель вводил никнейм и сразу
    видел прогресс — без всякого согласия ребёнка (приватность).
    Теперь создаётся ParentChildLink со статусом pending, а решение
    (принять / отклонить / заблокировать) принимает сам ученик.
    """
    _require_role('parent')
    nickname = (request.form.get('child_nickname', '') or '').strip()
    if not nickname:
        flash('Введите никнейм ребёнка', 'error')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    child = User.query.filter_by(nickname=nickname).first()
    if child is None:
        flash('Ребёнок с таким никнеймом не найден в системе', 'error')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    if child.id == current_user.id:
        flash('Нельзя привязать самого себя', 'error')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    child_role = getattr(child, 'role', 'student') or 'student'
    if child_role in ('teacher', 'parent'):
        flash('Привязать можно только аккаунт ученика', 'error')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    link = ParentChildLink.query.filter_by(
        parent_id=current_user.id, child_id=child.id
    ).first()

    if link is not None:
        if link.status == 'accepted':
            flash(f'{nickname} уже привязан к вашему аккаунту', 'info')
            return redirect(url_for('parent_teacher.parent_dashboard'))
        if link.status == 'pending':
            flash(f'Запрос для {nickname} уже отправлен и ждёт ответа ребёнка', 'info')
            return redirect(url_for('parent_teacher.parent_dashboard'))
        if link.status == 'blocked':
            flash(f'{nickname} запретил запросы на привязку от вашего аккаунта', 'error')
            return redirect(url_for('parent_teacher.parent_dashboard'))
        # rejected — разовый отказ: родитель вправе отправить запрос повторно
        link.status = 'pending'
        link.created_at = datetime.utcnow()
        db.session.commit()
        flash(f'Запрос на привязку повторно отправлен ученику {nickname}', 'success')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    link = ParentChildLink(
        parent_id=current_user.id, child_id=child.id, status='pending',
    )
    db.session.add(link)
    db.session.commit()
    flash(
        f'Запрос на привязку отправлен ученику {nickname}. '
        f'Прогресс станет виден после того, как ребёнок примет запрос.',
        'success',
    )
    return redirect(url_for('parent_teacher.parent_dashboard'))


@parent_teacher_bp.route('/parent-link/<int:link_id>/respond', methods=['POST'])
@login_required
def parent_link_respond(link_id: int):
    """Ответ ребёнка на запрос привязки: accept / reject / block.

    * accept — принять: родитель получает доступ к прогрессу ребёнка;
    * reject — отклонить разово (родитель может повторить запрос);
    * block  — заблокировать: запросы от этого родителя больше не приходят.
    """
    link = ParentChildLink.query.get(link_id)
    if link is None:
        abort(404)
    # Отвечать может только сам ребёнок, которому адресован запрос.
    if link.child_id != current_user.id:
        abort(403)

    action = (request.form.get('action', '') or '').strip()
    if action not in ('accept', 'reject', 'block'):
        flash('Некорректное действие', 'error')
        return redirect(request.form.get('next') or '/profile')

    if link.status not in ('pending',):
        flash('Запрос уже обработан', 'info')
        return redirect(request.form.get('next') or '/profile')

    if action == 'accept':
        link.accept()
        # Легаси-совместимость: legacy-проверки доступа (student_detail)
        # читают User.child_email (никнейм привязанного ребёнка).
        parent_user = User.query.get(link.parent_id)
        if parent_user is not None and not getattr(parent_user, 'child_email', None):
            parent_user.child_email = current_user.nickname
        flash('Запрос принят. Родитель теперь видит ваш прогресс.', 'success')
    elif action == 'reject':
        link.reject()
        flash('Запрос отклонён. Родитель сможет отправить его повторно.', 'info')
    else:  # block
        link.block()
        flash('Запросы от этого аккаунта заблокированы.', 'info')

    db.session.commit()
    return redirect(request.form.get('next') or '/profile')
