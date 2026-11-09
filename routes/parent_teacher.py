# -*- coding: utf-8 -*-
"""
routes/parent_teacher.py — T10 parent / teacher blueprint.

Key flows (CONFIRM_LINK_V1):
* Родитель добавляет ребёнка по никнейму → создаётся ParentChildLink(pending).
* Учитель добавляет ученика в группу по никнейму → создаётся
  T10GroupMember(status='pending'). Раньше ученик добавлялся мгновенно —
  теперь он получает уведомление и сам подтверждает приглашение.
* Ученик подтверждает/отклоняет запросы: на странице /profile (формы),
  через модальное уведомление (AJAX-эндпоинты /api/link-requests/*).
* Статистика ученика доступна родителю и учителю только после подтверждения
  (accepted-связь / accepted-участие в группе) и если ученик не скрыл прогресс.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template,
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


def _safe_next(default: str = '/profile') -> str:
    """Внутренний redirect-таргет из формы next (защита от open redirect)."""
    nxt = (request.form.get('next') or '').strip() if request.form else ''
    if not nxt:
        nxt = (request.args.get('next') or '').strip()
    if not nxt or not nxt.startswith('/') or nxt.startswith('//'):
        return default
    return nxt


def _notify(uid: int, ntype: str, sender_id: int, data=None) -> None:
    """Создать уведомление (колокол) — как _make_notif в app.py."""
    try:
        from models import Notification
        n = Notification(
            user_id=uid,
            type=ntype,
            from_user_id=sender_id,
            data=json.dumps(data, ensure_ascii=False) if data else None,
        )
        db.session.add(n)
    except Exception:
        db.session.rollback()


def _display(user) -> str:
    """Отображаемое имя пользователя (никнейм или имя из email)."""
    if user is None:
        return '—'
    try:
        return user.display_name
    except Exception:
        return display_name_from_email(user.email)


def _week_avg_tasks(user: User, today: date) -> float:
    """Average number of answered daily tasks per day over the last 7 days."""
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


def _daily_task_stats(user_id: int) -> dict:
    """Полная статистика задач дня: за 7 дней и за всё время.

    * attempts — сколько задач ученик пытался решить (есть ответ);
    * correct — сколько решено верно (is_correct);
    * active_days — дней с хотя бы одной попыткой;
    * last_active — последняя дата с попыткой.
    """
    from daily_tasks.models import DailyTaskItem, DailyTaskSet

    today = date.today()
    week_start = today - timedelta(days=6)

    sets = DailyTaskSet.query.filter(DailyTaskSet.user_id == user_id).all()
    set_map = {s.id: s for s in sets}
    items = DailyTaskItem.query.filter(
        DailyTaskItem.daily_set_id.in_(set_map.keys()),
        DailyTaskItem.user_answer.isnot(None),
    ).all() if sets else []

    week_attempts = week_correct = 0
    life_attempts = life_correct = 0
    active_days = set()
    last_active = None
    for it in items:
        ds = set_map.get(it.daily_set_id)
        if not ds:
            continue
        active_days.add(ds.target_date)
        if last_active is None or ds.target_date > last_active:
            last_active = ds.target_date
        life_attempts += 1
        if it.is_correct:
            life_correct += 1
        if ds.target_date >= week_start:
            week_attempts += 1
            if it.is_correct:
                week_correct += 1

    accuracy = round(100.0 * life_correct / life_attempts, 1) if life_attempts else None
    return {
        'week_attempts': week_attempts,
        'week_correct': week_correct,
        'week_avg_attempts': round(week_attempts / 7.0, 2),
        'week_avg_correct': round(week_correct / 7.0, 2),
        'life_attempts': life_attempts,
        'life_correct': life_correct,
        'accuracy': accuracy,
        'active_days': len(active_days),
        'last_active': last_active,
    }


def _test_stats(user_id: int) -> dict:
    """Статистика адаптивных тестов: сколько пройдено, средний уровень, последний.

    ВАЖНО: у AdaptiveTestResult НЕТ поля status — фильтруем по completed_at
    (аналогично странице /profile), иначе except маскирует ошибку нулями.
    """
    from models import AdaptiveTestResult
    try:
        results = AdaptiveTestResult.query.filter(
            AdaptiveTestResult.user_id == user_id,
            AdaptiveTestResult.completed_at.isnot(None),
        ).order_by(AdaptiveTestResult.completed_at.desc()).all()
    except Exception:
        results = []
    if not results:
        return {'count': 0, 'avg_level': None, 'last_at': None}
    levels = [r.final_level for r in results if r.final_level is not None]
    avg_level = round(sum(levels) / len(levels), 2) if levels else None
    last = results[0]
    return {
        'count': len(results),
        'avg_level': avg_level,
        'last_at': last.completed_at,
    }


def _latest_mu_sigma(user_id: int) -> dict:
    """Return {anchor: {'mu': float, 'sigma': float}} for the latest snapshot.

    Если данных по ученику нет — все значения None (шаблон покажет «нет данных»).
    """
    anchors_order = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']
    has_state = False
    try:
        from models_curator import CuratorState
        state = CuratorState.query.filter_by(user_id=user_id).first()
        if state and state.level_by_section:
            has_state = True
            sections = json.loads(state.level_by_section) if isinstance(
                state.level_by_section, str) else state.level_by_section
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
    return {a: {'mu': None, 'sigma': None} for a in anchors_order}


def _premium_expires_str(value):
    """Дата окончания Premium в виде 'YYYY-MM-DD' (или None).

    PostgreSQL возвращает TIMESTAMP как datetime, SQLite — как строку.
    Шаблоны раньше резали строку срезом [:10] — с datetime это TypeError
    и ошибка 500 всего кабинета родителя. Нормализуем оба случая здесь.
    """
    if value is None:
        return None
    if hasattr(value, 'strftime'):  # datetime / date (PostgreSQL)
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]  # строка ISO (SQLite)


def _premium_brief(user_id: int):
    """Активный Premium пользователя (для кнопки покупки родителем/учителем).

    Возвращает {'plan': ..., 'expires_at': 'YYYY-MM-DD'} или None.
    Кэш-запросов нет — страниц с детьми/группами немного, запрос лёгкий.
    """
    try:
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user_id)
        if plan.get('is_premium'):
            return {
                'plan': plan.get('plan'),
                'expires_at': _premium_expires_str(plan.get('expires_at')),
            }
    except Exception:
        return None
    return None


def _student_row(s: User, today: date) -> dict:
    """Строка ученика для таблицы группы (только accepted, с учётом приватности)."""
    row = {
        'id': s.id,
        'name': _display(s),
        'premium': _premium_brief(s.id),
    }
    if getattr(s, 'share_progress', True) in (False, 0):
        row.update({
            'avg_tasks': None,
            'row_color': 'gray',
            'streak': None,
            'anchors': {},
            'progress_hidden': True,
        })
        return row
    row.update({
        'avg_tasks': _week_avg_tasks(s, today),
        'row_color': 'green',
        'streak': student_streak(s.id),
        'anchors': _latest_mu_sigma(s.id),
        'progress_hidden': False,
    })
    return row


# ---------------------------------------------------------------------------
# Teacher routes
# ---------------------------------------------------------------------------

@parent_teacher_bp.route('/teacher')
@login_required
def teacher_dashboard():
    _require_role('teacher')

    groups = T10Group.query.filter_by(teacher_id=current_user.id).all()

    group_stats = []
    today = date.today()
    for g in groups:
        all_members = T10GroupMember.query.filter_by(group_id=g.id).all()
        accepted_ids = [m.user_id for m in all_members if m.status == 'accepted']
        pending_members = [m for m in all_members if m.status == 'pending']

        students = User.query.filter(User.id.in_(accepted_ids)).all() if accepted_ids else []
        student_data = []
        group_total = 0.0
        shown = 0
        for s in students:
            avg = _week_avg_tasks(s, today)
            row = _student_row(s, today)
            if not row['progress_hidden']:
                # avg уже посчитан выше; для скрытого прогресса не считаем
                row['avg_tasks'] = avg
                group_total += avg
                shown += 1
                if avg < 4:
                    row['row_color'] = 'red'
            student_data.append(row)

        group_avg = round(group_total / shown, 2) if shown else 0.0
        group_stats.append({
            'group': g,
            'students': student_data,
            'group_avg': group_avg,
            'student_count': len(accepted_ids),
            'pending_count': len(pending_members),
        })

    from routes.seat_pay import seat_gate
    return render_template(
        'teacher/dashboard.html',
        group_stats=group_stats,
        seat=seat_gate(current_user.id, 'teacher'),
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
    accepted_ids = [m.user_id for m in members if m.status == 'accepted']
    pending_members = [m for m in members if m.status == 'pending']
    rejected_members = [m for m in members if m.status == 'rejected']

    students = User.query.filter(User.id.in_(accepted_ids)).all() if accepted_ids else []

    today = date.today()
    student_data = []
    group_total = 0.0
    shown = 0
    for s in students:
        row = _student_row(s, today)
        if not row['progress_hidden']:
            row['avg_tasks'] = _week_avg_tasks(s, today)
            group_total += row['avg_tasks']
            shown += 1
            if row['avg_tasks'] < 4:
                row['row_color'] = 'red'
        student_data.append(row)

    group_avg = round(group_total / shown, 2) if shown else 0.0

    def _pending_info(m):
        u = User.query.get(m.user_id)
        return {
            'id': m.id,
            'name': _display(u),
            'created_at': m.joined_at,
        }

    pending_data = [_pending_info(m) for m in pending_members]
    rejected_data = [_pending_info(m) for m in rejected_members]

    from routes.seat_pay import seat_gate
    return render_template(
        'teacher/group.html',
        group=g,
        students=student_data,
        group_avg=group_avg,
        pending_students=pending_data,
        rejected_students=rejected_data,
        seat=seat_gate(current_user.id, 'teacher'),
    )


@parent_teacher_bp.route('/teacher/group/<int:gid>/add-student', methods=['POST'])
@login_required
def teacher_group_add_student(gid: int):
    """Учитель вводит ник → ученику приходит запрос на подтверждение.

    Ученик НЕ добавляется мгновенно: создаётся T10GroupMember(status='pending'),
    ученик получает уведомление и решает сам. Статистика откроется учителю
    только после подтверждения.

    SEAT_SUBSCRIPTION_V1: добавление новых учеников — только с активной
    подпиской на места и в пределах лимита мест.
    """
    _require_role('teacher')
    g = T10Group.query.get(gid)
    if g is None or g.teacher_id != current_user.id:
        abort(404)

    from routes.seat_pay import seat_gate
    gate = seat_gate(current_user.id, 'teacher')
    if gate['sub'] is None:
        flash('Добавление учеников — по подписке. Как это работает — '
              'на странице «Как это будет работать».', 'error')
        return redirect('/demo')
    if not gate['can_add']:
        flash(f'Места закончились: {gate["used"]} из {gate["seats"]}. '
              'Расширить тариф можно в разделе «Тарифы».', 'error')
        return redirect('/tariffs/teacher')

    nickname = (request.form.get('nickname', '') or '').strip()
    if not nickname:
        flash('Введите никнейм ученика', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    student = User.query.filter_by(nickname=nickname).first()
    if student is None:
        flash(f'Ученик с никнеймом "{nickname}" не найден', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    if student.id == current_user.id:
        flash('Нельзя добавить самого себя', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    student_role = getattr(student, 'role', 'student') or 'student'
    if student_role in ('teacher', 'parent'):
        flash('Добавить в группу можно только аккаунт ученика', 'error')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    existing = T10GroupMember.query.filter_by(
        group_id=g.id, user_id=student.id
    ).first()
    if existing:
        if existing.status == 'accepted':
            flash(f'{nickname} уже в группе', 'info')
            return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))
        if existing.status == 'pending':
            flash(f'Запрос для {nickname} уже отправлен — ждём подтверждения ученика', 'info')
            return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))
        # rejected — учитель вправе отправить запрос повторно
        existing.status = 'pending'
        existing.joined_at = datetime.utcnow()
        existing.responded_at = None
        _notify(student.id, 'group_invite', current_user.id, {
            'group': g.name,
            'teacher': _display(current_user),
        })
        db.session.commit()
        flash(f'Повторный запрос отправлен ученику {nickname}', 'success')
        return redirect(url_for('parent_teacher.teacher_group_view', gid=gid))

    gm = T10GroupMember(
        group_id=g.id, user_id=student.id, role='student', status='pending',
    )
    db.session.add(gm)
    _notify(student.id, 'group_invite', current_user.id, {
        'group': g.name,
        'teacher': _display(current_user),
    })
    db.session.commit()
    flash(
        f'Запрос отправлен ученику {nickname}. Он появится в группе, '
        f'как только подтвердит приглашение.', 'success',
    )
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
# Student responses to teacher invitations
# ---------------------------------------------------------------------------

def _respond_teacher_invite(member: T10GroupMember, action: str) -> tuple[bool, str]:
    """Обработать ответ ученика на приглашение в группу. Возвращает (ok, message)."""
    if action == 'accept':
        member.accept()
        return True, 'Приглашение принято — вы в группе.'
    if action == 'reject':
        member.reject()
        return True, 'Приглашение отклонено.'
    return False, 'Некорректное действие'


@parent_teacher_bp.route('/teacher-link/<int:member_id>/respond', methods=['POST'])
@login_required
def teacher_link_respond(member_id: int):
    """Ответ ученика на приглашение учителя (форма с /profile)."""
    member = T10GroupMember.query.get(member_id)
    if member is None:
        abort(404)
    if member.user_id != current_user.id:
        abort(403)

    action = (request.form.get('action', '') or '').strip()
    if action not in ('accept', 'reject'):
        flash('Некорректное действие', 'error')
        return redirect(_safe_next())

    if member.status != 'pending':
        flash('Приглашение уже обработано', 'info')
        return redirect(_safe_next())

    ok, message = _respond_teacher_invite(member, action)
    if ok:
        db.session.commit()
        flash(message, 'success' if action == 'accept' else 'info')
    return redirect(_safe_next())


# ---------------------------------------------------------------------------
# Parent routes
# ---------------------------------------------------------------------------

@parent_teacher_bp.route('/parent')
@login_required
def parent_dashboard():
    _require_role('parent')

    # JOIN_CODE_V1: у родителя всегда есть код для подключения ребёнка
    invite_code = _ensure_parent_code(current_user)

    # Подтверждённые связи: показываем ВСЕХ привязанных детей (не только первого).
    links = ParentChildLink.query.filter_by(
        parent_id=current_user.id, status='accepted',
    ).order_by(ParentChildLink.responded_at.desc()).all()

    children = [User.query.get(l.child_id) for l in links]
    children = [c for c in children if c is not None]

    pending_links = ParentChildLink.query.filter_by(
        parent_id=current_user.id, status='pending',
    ).order_by(ParentChildLink.created_at.desc()).all()
    pending_children = [
        (User.query.get(p.child_id), p) for p in pending_links
    ]
    pending_children = [(c, p) for c, p in pending_children if c is not None]

    from routes.seat_pay import seat_gate
    seat = seat_gate(current_user.id, 'parent')

    if not children:
        # Привязанного ребёнка нет: форма добавления + статус pending-запросов.
        # Легаси-путь через User.child_email убран: без подтверждённой
        # учеником связи статистика не открывается (приватность).
        legacy_nick = getattr(current_user, 'child_email', None)
        return render_template(
            'parent/dashboard.html',
            invite_code=invite_code if seat['sub'] else None,
            children=[],
            pending_children=[
                {'nickname': c.nickname, 'created_at': p.created_at}
                for c, p in pending_children
            ],
            legacy_hint=bool(legacy_nick),
            seat=seat,
        )

    today = date.today()
    child_cards = []
    for child in children:
        card = {'id': child.id, 'name': _display(child), 'premium': _premium_brief(child.id)}
        if getattr(child, 'share_progress', True) in (False, 0):
            card['hidden'] = True
        else:
            card['hidden'] = False
            card['avg_tasks'] = _week_avg_tasks(child, today)
            card['streak'] = student_streak(child.id)
            card['anchors'] = _latest_mu_sigma(child.id)
        child_cards.append(card)

    return render_template(
        'parent/dashboard.html',
        invite_code=invite_code if (seat['sub'] or child_cards) else None,
        children=child_cards,
        pending_children=[
            {'nickname': c.nickname, 'created_at': p.created_at}
            for c, p in pending_children
        ],
        legacy_hint=False,
        seat=seat,
    )


# ---------------------------------------------------------------------------
# TARIFFS_SECTIONS_V1 (07.11.2026): отдельные тарифы для учителя и родителя.
# Покупка Premium — подарочно для ученика (PREMIUM_GIFT_V1, for_user=<id>):
# платит взрослый, Premium активируется ученику. Автопродление не
# подключается. Попап «Как работает подготовка» — на самих страницах
# (1 раз, ключ localStorage по роли).
# ---------------------------------------------------------------------------

def _tariff_students_for_teacher():
    """Все accepted-ученики всех групп учителя: [{id, name, group, premium}]."""
    rows = []
    groups = T10Group.query.filter_by(teacher_id=current_user.id).all()
    for g in groups:
        members = T10GroupMember.query.filter_by(
            group_id=g.id, status='accepted').all()
        for m in members:
            s = User.query.get(m.user_id)
            if s is None:
                continue
            rows.append({
                'id': s.id,
                'name': _display(s),
                'group': g.name,
                'premium': _premium_brief(s.id),
            })
    return rows


def _tariff_children_for_parent():
    """Все подтверждённые дети родителя: [{id, name, premium}]."""
    links = ParentChildLink.query.filter_by(
        parent_id=current_user.id, status='accepted').all()
    rows = []
    for l in links:
        c = User.query.get(l.child_id)
        if c is None:
            continue
        rows.append({
            'id': c.id,
            'name': _display(c),
            'premium': _premium_brief(c.id),
        })
    return rows


def _tariff_plans():
    """Тарифы для страниц учителя/родителя (общие планы Premium)."""
    from routes.premium_pay import PLAN_INFO
    return [
        {'key': k, 'icon': v['icon'], 'title': v['title'],
         'price_rub': v['price_rub'], 'tagline': v['tagline'],
         'features': v['features']}
        for k, v in PLAN_INFO.items()
    ]


@parent_teacher_bp.route('/tariffs/teacher')
@login_required
def teacher_tariffs():
    _require_role('teacher')
    from routes.seat_pay import SEAT_PLANS, seat_gate
    return render_template(
        'tariffs/teacher.html',
        students=_tariff_students_for_teacher(),
        plans=_tariff_plans(),
        seat_plans=[{'key': k, **v} for k, v in SEAT_PLANS.items()],
        seat=seat_gate(current_user.id, 'teacher'),
    )


@parent_teacher_bp.route('/tariffs/parent')
@login_required
def parent_tariffs():
    _require_role('parent')
    from routes.seat_pay import SEAT_PLANS, seat_gate
    return render_template(
        'tariffs/parent.html',
        children=_tariff_children_for_parent(),
        plans=_tariff_plans(),
        seat_plans=[{'key': k, **v} for k, v in SEAT_PLANS.items()],
        seat=seat_gate(current_user.id, 'parent'),
    )


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
    back_url = None

    # STUDENT_VIEW_FIX_V2: доступ только по подтверждённым связям.
    is_self = current_user.id == student.id

    if role == 'teacher':
        # Teacher must have this student as an ACCEPTED member of their group.
        member = T10GroupMember.query.join(T10Group).filter(
                T10GroupMember.user_id == sid,
                T10Group.teacher_id == current_user.id,
                T10GroupMember.status == 'accepted',
        ).first()
        if member is None:
            # Есть только pending-приглашение — статистика закрыта.
            pending_only = T10GroupMember.query.join(T10Group).filter(
                T10GroupMember.user_id == sid,
                T10Group.teacher_id == current_user.id,
                T10GroupMember.status == 'pending',
            ).first()
            if pending_only is not None:
                flash(
                    'Ученик ещё не подтвердил приглашение — статистика '
                    'станет доступна после подтверждения.', 'info',
                )
            abort(403)
        group = T10Group.query.get(member.group_id)
        if group is not None:
            back_url = url_for('parent_teacher.teacher_group_view', gid=group.id)
    elif role == 'parent':
        # Доступ только по подтверждённой связи ParentChildLink.
        # Легаси-путь через child_email (никнейм) убран: ученик может сменить
        # никнейм, а непросвещённое согласие нельзя подразумевать.
        _link = ParentChildLink.query.filter_by(
            parent_id=current_user.id, child_id=student.id, status='accepted',
        ).first()
        if _link is None:
            abort(403)
        back_url = url_for('parent_teacher.parent_dashboard')
    elif not is_self:
        abort(403)

    # share_progress: NULL/отсутствует трактуем как «разрешено» (default=True).
    if not is_self and getattr(student, 'share_progress', True) in (False, 0):
        abort(403)

    today = date.today()
    task_stats = _daily_task_stats(student.id)
    tests = _test_stats(student.id)

    grade = getattr(student, 'preferred_grade', None)
    try:
        grade = int(grade) if grade else 7
    except (TypeError, ValueError):
        grade = 7

    return render_template(
        'student/profile_detail.html',
        student=student,
        student_display=_display(student),
        avg_tasks=task_stats['week_avg_attempts'],
        task_stats=task_stats,
        tests=tests,
        user_stats={
            'total_solved': getattr(student, 'total_problems_solved', 0) or 0,
            'xp': getattr(student, 'experience_points', 0) or 0,
            'level': getattr(student, 'current_level', 1) or 1,
            'mock_exams': getattr(student, 'mock_exams_passed', 0) or 0,
            'highest_difficulty': getattr(student, 'highest_difficulty_solved', 0) or 0,
        },
        streak=student_streak(student.id),
        anchors=_latest_mu_sigma(student.id),
        section_radar=_section_radar(student.id),
        theme_radars=_theme_radars(student.id, grade),
        calendar_days=_month_calendar(student.id),
        back_url=back_url,
        # STATS_UX_V1 (09.11.2026): данные для понятной сводки и календаря.
        viewer_role=role if not is_self else 'self',
        calendar_offset=today.replace(day=1).weekday(),
        month_title=_MONTHS_RU[today.month - 1] + ' ' + str(today.year),
        days_since_active=((today - task_stats['last_active']).days
                           if task_stats.get('last_active') else None),
    )


_MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль',
              'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


# ---------------------------------------------------------------------------
# Profile actions (group join / share toggle)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# JOIN_CODE_V1: единая страница «Присоединиться по коду» (/join)
# ---------------------------------------------------------------------------

def _join_teacher_group_by_code(user, code: str) -> tuple[bool, str]:
    """Вступить в группу учителя по 6-символьному коду.

    Согласие ученика выражено самим действием ввода кода, поэтому участник
    создаётся сразу со статусом 'accepted' (pending/rejected — апгрейдятся).
    Возвращает (ok, message).
    """
    if len(code) != 6:
        return False, 'Неверный код: нужно ровно 6 символов'

    g = T10Group.query.filter_by(invite_code=code).first()
    if g is None:
        return False, 'Группа с таким кодом не найдена'

    existing = T10GroupMember.query.filter_by(
        group_id=g.id, user_id=user.id
    ).first()
    if existing:
        if existing.status == 'accepted':
            return False, f'Вы уже состоите в группе «{g.name}»'
        # pending (приглашение от учителя) или rejected — ввод кода = согласие
        existing.accept()
        db.session.commit()
        return True, f'Вы вступили в группу «{g.name}»'

    # SEAT_SUBSCRIPTION_V1: новый участник по коду занимает место учителя —
    # проверяем активную подписку и лимит (upgrade существующих не трогаем).
    from routes.seat_pay import seat_gate
    t_gate = seat_gate(g.teacher_id, 'teacher')
    if t_gate['sub'] is None:
        return False, ('У учителя пока нет активной подписки на группу — '
                       'попросите его оформить её на formyla.net')
    if not t_gate['can_add']:
        return False, 'У учителя закончились места в подписке'

    gm = T10GroupMember(
        group_id=g.id, user_id=user.id, role='student', status='accepted',
    )
    db.session.add(gm)
    # Уведомим учителя, что ученик пришёл по коду
    try:
        if g.teacher_id != user.id:
            _notify(g.teacher_id, 'group_join', user.id, {
                'group': g.name,
                'student': _display(user),
            })
    except Exception:
        pass
    db.session.commit()
    return True, f'Вы вступили в группу «{g.name}»'


def _link_parent_by_code(user, code: str) -> tuple[bool, str]:
    """Привязаться к родителю по его коду (users.parent_invite_code).

    Ввод кода = согласие ученика, поэтому связь создаётся сразу 'accepted'.
    Возвращает (ok, message).
    """
    parent = User.query.filter_by(parent_invite_code=code).first()
    if parent is None:
        return False, 'Родитель с таким кодом не найден'

    if parent.id == user.id:
        return False, 'Нельзя использовать свой собственный код'

    existing = ParentChildLink.query.filter_by(
        parent_id=parent.id, child_id=user.id
    ).first()
    if existing:
        if existing.status == 'accepted':
            return False, 'Вы уже привязаны к этому родителю'
        if existing.status == 'blocked':
            return False, 'Эта привязка заблокирована — обратитесь к родителю'
        # pending / rejected — ввод кода = согласие
        existing.accept()
        db.session.commit()
        return True, f'Вы привязаны к родителю {_display(parent)}'

    # SEAT_SUBSCRIPTION_V1: новая привязка занимает место родителя —
    # проверяем активную подписку и лимит (upgrade существующих не трогаем).
    from routes.seat_pay import seat_gate
    p_gate = seat_gate(parent.id, 'parent')
    if p_gate['sub'] is None:
        return False, ('У родителя пока нет активной подписки — попросите его '
                       'оформить её на formyla.net')
    if not p_gate['can_add']:
        return False, 'У родителя закончились места в подписке'

    link = ParentChildLink(
        parent_id=parent.id, child_id=user.id, status='accepted',
    )
    db.session.add(link)
    db.session.commit()
    return True, f'Вы привязаны к родителю {_display(parent)}'


def _ensure_parent_code(user) -> str:
    """Лениво выдать родителю код привязки (если ещё нет)."""
    if not user.parent_invite_code:
        from services.parent_teacher_helpers import generate_parent_invite_code
        user.parent_invite_code = generate_parent_invite_code()
        db.session.commit()
    return user.parent_invite_code


@parent_teacher_bp.route('/join', methods=['GET'])
@login_required
def join_by_code_page():
    """Страница «Присоединиться по коду» — из раздела «Прочее»."""
    if getattr(current_user, 'is_guest', False):
        flash('Гостевым аккаунтам нужно зарегистрироваться, чтобы присоединяться к группам', 'error')
        return redirect('/register')

    my_groups = [
        m.group for m in current_user.teacher_group_memberships
        if m.status == 'accepted'
    ] if hasattr(current_user, 'teacher_group_memberships') else []

    my_parents = [
        l.parent for l in current_user.parent_links
        if l.status == 'accepted'
    ] if hasattr(current_user, 'parent_links') else []

    return render_template(
        'join_group.html',
        my_groups=my_groups,
        my_parents=my_parents,
    )


@parent_teacher_bp.route('/join', methods=['POST'])
@login_required
def join_by_code_submit():
    """Обработка введённого кода: группа учителя ИЛИ код родителя."""
    if getattr(current_user, 'is_guest', False):
        flash('Гостевым аккаунтам нужно зарегистрироваться, чтобы присоединяться к группам', 'error')
        return redirect('/register')

    code = (request.form.get('invite_code', '') or '').strip().upper()
    if not code:
        flash('Введите код', 'error')
        return redirect(url_for('parent_teacher.join_by_code_page'))
    if len(code) != 6 or not code.isalnum():
        flash('Неверный формат кода: нужно 6 букв или цифр', 'error')
        return redirect(url_for('parent_teacher.join_by_code_page'))

    role = _user_role()
    if role in ('teacher', 'parent'):
        flash('Присоединяться по коду могут только ученические аккаунты', 'error')
        return redirect(url_for('parent_teacher.join_by_code_page'))

    # 1) Сначала проверяем группы учителей (легаси-приоритет).
    if T10Group.query.filter_by(invite_code=code).first():
        ok, msg = _join_teacher_group_by_code(current_user, code)
        flash(msg, 'success' if ok else 'info')
        return redirect(url_for('parent_teacher.join_by_code_page'))

    # 2) Затем — коды родителей.
    ok, msg = _link_parent_by_code(current_user, code)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('parent_teacher.join_by_code_page'))


@parent_teacher_bp.route('/profile/join-group', methods=['POST'])
@login_required
def profile_join_group():
    """Ученик сам вступает в группу по коду — согласие уже дано действием."""
    code = (request.form.get('invite_code', '') or '').strip().upper()
    ok, msg = _join_teacher_group_by_code(current_user, code)
    flash(msg, 'success' if ok else 'error')
    return redirect(_safe_next('/profile'))


@parent_teacher_bp.route('/parent/invite-code/regenerate', methods=['POST'])
@login_required
def parent_invite_code_regenerate():
    """JOIN_CODE_V1 — перевыпустить код привязки родителя (старый перестаёт работать)."""
    _require_role('parent')
    from services.parent_teacher_helpers import generate_parent_invite_code
    current_user.parent_invite_code = generate_parent_invite_code()
    db.session.commit()
    flash('Код обновлён — сообщите ребёнку новый код', 'success')
    return redirect(url_for('parent_teacher.parent_dashboard'))


@parent_teacher_bp.route('/profile/share', methods=['POST'])
@login_required
def profile_share_toggle():
    val = request.form.get('share_progress', '0')
    current_user.share_progress = (val == '1')
    db.session.commit()
    flash('Настройки доступа обновлены', 'success')
    return redirect(_safe_next('/profile'))


@parent_teacher_bp.route('/parent/bind-child', methods=['POST'])
@login_required
def parent_bind_child():
    """Отправить ребёнку ЗАПРОС на привязку (не мгновенная привязка!).

    Создаётся ParentChildLink со статусом pending, а решение
    (принять / отклонить / заблокировать) принимает сам ученик.

    SEAT_SUBSCRIPTION_V1: добавление детей — только с активной
    подпиской на места и в пределах лимита мест.
    """
    _require_role('parent')
    from routes.seat_pay import seat_gate
    gate = seat_gate(current_user.id, 'parent')
    if gate['sub'] is None:
        flash('Добавление ребёнка — по подписке. Как это работает — '
              'на странице «Как это будет работать».', 'error')
        return redirect('/demo')
    if not gate['can_add']:
        flash(f'Места закончились: {gate["used"]} из {gate["seats"]}. '
              'Расширить тариф можно в разделе «Тарифы».', 'error')
        return redirect('/tariffs/parent')

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
        _notify(child.id, 'parent_link_request', current_user.id, {
            'parent': _display(current_user),
        })
        db.session.commit()
        flash(f'Запрос на привязку повторно отправлен ученику {nickname}', 'success')
        return redirect(url_for('parent_teacher.parent_dashboard'))

    link = ParentChildLink(
        parent_id=current_user.id, child_id=child.id, status='pending',
    )
    db.session.add(link)
    _notify(child.id, 'parent_link_request', current_user.id, {
        'parent': _display(current_user),
    })
    db.session.commit()
    flash(
        f'Запрос на привязку отправлен ученику {nickname}. '
        f'Прогресс станет виден после того, как ребёнок примет запрос.',
        'success',
    )
    return redirect(url_for('parent_teacher.parent_dashboard'))


def _respond_parent_link(link: ParentChildLink, action: str) -> tuple[bool, str]:
    """Обработать ответ ребёнка на запрос привязки. Возвращает (ok, message)."""
    if action == 'accept':
        link.accept()
        # Легаси-совместимость: некоторые проверки читают User.child_email.
        parent_user = User.query.get(link.parent_id)
        if parent_user is not None and not getattr(parent_user, 'child_email', None):
            parent_user.child_email = current_user.nickname
        return True, 'Запрос принят. Родитель теперь видит ваш прогресс.'
    if action == 'reject':
        link.reject()
        return True, 'Запрос отклонён. Родитель сможет отправить его повторно.'
    if action == 'block':
        link.block()
        return True, 'Запросы от этого аккаунта заблокированы.'
    return False, 'Некорректное действие'


@parent_teacher_bp.route('/parent-link/<int:link_id>/respond', methods=['POST'])
@login_required
def parent_link_respond(link_id: int):
    """Ответ ребёнка на запрос привязки (форма с /profile)."""
    link = ParentChildLink.query.get(link_id)
    if link is None:
        abort(404)
    if link.child_id != current_user.id:
        abort(403)

    action = (request.form.get('action', '') or '').strip()
    if action not in ('accept', 'reject', 'block'):
        flash('Некорректное действие', 'error')
        return redirect(_safe_next())

    if link.status != 'pending':
        flash('Запрос уже обработан', 'info')
        return redirect(_safe_next())

    ok, message = _respond_parent_link(link, action)
    if ok:
        db.session.commit()
        flash(message, 'success' if action == 'accept' else 'info')
    return redirect(_safe_next())


# ---------------------------------------------------------------------------
# AJAX API для модального уведомления (как «Как тебе сайт?»)
# ---------------------------------------------------------------------------

def _pending_link_requests_for(user) -> list:
    """Все ожидающие ответа запросы для ученика: родители + учителя."""
    requests_out = []

    # Запросы от родителей
    try:
        links = ParentChildLink.query.filter_by(
            child_id=user.id, status='pending',
        ).order_by(ParentChildLink.created_at.desc()).all()
        for l in links:
            p = User.query.get(l.parent_id)
            requests_out.append({
                'kind': 'parent',
                'id': l.id,
                'name': _display(p),
                'nickname': (p.nickname if p else None),
                'created_at': (l.created_at.isoformat() if l.created_at else None),
                'text': 'хочет добавить тебя и видеть твою статистику',
            })
    except Exception:
        pass

    # Приглашения от учителей в группы
    try:
        invites = (
            T10GroupMember.query.join(T10Group, T10GroupMember.group_id == T10Group.id)
            .filter(T10GroupMember.user_id == user.id, T10GroupMember.status == 'pending')
            .order_by(T10GroupMember.joined_at.desc())
            .all()
        )
        for m in invites:
            g = T10Group.query.get(m.group_id)
            if not g:
                continue
            t = User.query.get(g.teacher_id)
            requests_out.append({
                'kind': 'teacher',
                'id': m.id,
                'name': _display(t),
                'nickname': (t.nickname if t else None),
                'group': g.name,
                'created_at': (m.joined_at.isoformat() if m.joined_at else None),
                'text': f'хочет добавить тебя в группу «{g.name}»',
            })
    except Exception:
        pass

    return requests_out


@parent_teacher_bp.route('/api/link-requests/pending')
@login_required
def api_link_requests_pending():
    """Есть ли у ученика ожидающие запросы (для модального уведомления)."""
    if getattr(current_user, 'is_guest', False):
        return jsonify({'pending': False, 'requests': []})
    reqs = _pending_link_requests_for(current_user)
    return jsonify({'pending': bool(reqs), 'requests': reqs})


@parent_teacher_bp.route('/api/link-requests/respond', methods=['POST'])
@login_required
def api_link_requests_respond():
    """Ответ ученика из модального уведомления: {kind, id, action}."""
    if getattr(current_user, 'is_guest', False):
        return jsonify({'ok': False, 'error': 'guest'}), 403

    payload = request.get_json(silent=True) or request.form or {}
    kind = str(payload.get('kind', '')).strip()
    action = str(payload.get('action', '')).strip()
    try:
        obj_id = int(payload.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'bad id'}), 400

    if kind not in ('parent', 'teacher') or action not in ('accept', 'reject'):
        return jsonify({'ok': False, 'error': 'bad request'}), 400

    if kind == 'parent':
        link = ParentChildLink.query.get(obj_id)
        if link is None or link.child_id != current_user.id:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        if link.status != 'pending':
            return jsonify({'ok': False, 'error': 'already handled'}), 409
        ok, message = _respond_parent_link(link, action)
    else:
        member = T10GroupMember.query.get(obj_id)
        if member is None or member.user_id != current_user.id:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        if member.status != 'pending':
            return jsonify({'ok': False, 'error': 'already handled'}), 409
        ok, message = _respond_teacher_invite(member, action)

    if not ok:
        return jsonify({'ok': False, 'error': message}), 400

    db.session.commit()
    # После ответа проверим, остались ли другие запросы.
    remaining = _pending_link_requests_for(current_user)
    return jsonify({
        'ok': True,
        'status': action,
        'message': message,
        'remaining': len(remaining),
    })
