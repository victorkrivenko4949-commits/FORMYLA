"""Extracted legacy routes; URL, authentication and response contracts preserved."""
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required
from models import db, User, Mentorship, Friendship

bp = Blueprint('teacher', __name__)

@bp.route("/api/social/mentorship/request", methods=["POST"])
@login_required
def send_mentorship_request():
    """Отправить заявку учитель-ученик"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')

        if not student_id:
            return jsonify({'success': False, 'error': 'Student ID required'}), 400

        # Проверка существования пользователя
        student = User.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404

        # Создаем заявку (текущий пользователь = учитель)
        mentorship = Mentorship.create_mentorship_request(current_user.id, student_id)
        db.session.add(mentorship)
        db.session.commit()

        return jsonify({
            'success': True,
            'mentorship_id': mentorship.id,
            'status': mentorship.status
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/social/mentorship/respond", methods=["POST"])
@login_required
def respond_mentorship_request():
    """Принять или отклонить заявку учитель-ученик"""
    try:
        data = request.get_json()
        mentorship_id = data.get('mentorship_id')
        action = data.get('action')  # 'accept' or 'reject'

        if not mentorship_id or action not in ['accept', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid parameters'}), 400

        mentorship = Mentorship.query.get(mentorship_id)
        if not mentorship:
            return jsonify({'success': False, 'error': 'Mentorship not found'}), 404

        # Проверка прав (только ученик может принять/отклонить)
        if mentorship.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        if action == 'accept':
            mentorship.accept()
        else:
            mentorship.reject()

        db.session.commit()

        return jsonify({'success': True, 'status': mentorship.status})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/social/mentorship/students")
@login_required
def list_students():
    """Получить список учеников (для учителя)"""
    try:
        mentorships = Mentorship.query.filter_by(
            teacher_id=current_user.id,
            status='accepted'
        ).all()

        students = []
        for m in mentorships:
            student = User.query.get(m.student_id)
            if student:
                students.append({
                    'id': student.id,
                    'nickname': student.nickname,
                    'name': student.name,
                    'avatar_url': student.avatar_url
                })

        return jsonify({'success': True, 'students': students})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/social/mentorship/teachers")
@login_required
def list_teachers():
    """Получить список учителей (для ученика)"""
    try:
        mentorships = Mentorship.query.filter_by(
            student_id=current_user.id,
            status='accepted'
        ).all()

        teachers = []
        for m in mentorships:
            teacher = User.query.get(m.teacher_id)
            if teacher:
                teachers.append({
                    'id': teacher.id,
                    'nickname': teacher.nickname,
                    'name': teacher.name,
                    'avatar_url': teacher.avatar_url
                })

        return jsonify({'success': True, 'teachers': teachers})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


LEGACY_ENDPOINTS = ('send_mentorship_request', 'respond_mentorship_request', 'list_students', 'list_teachers')


@bp.route("/accept_request/<int:mentorship_id>", methods=["POST"])
@login_required
def accept_request(mentorship_id):
    """Принять заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)

    # Проверка прав (только ученик может принять)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))

    try:
        mentorship.accept()
        db.session.commit()
        teacher = User.query.get(mentorship.teacher_id)
        flash(f'Вы приняли заявку от @{teacher.nickname or teacher.email}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('profile'))


@bp.route("/reject_request/<int:mentorship_id>", methods=["POST"])
@login_required
def reject_request(mentorship_id):
    """Отклонить заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)

    # Проверка прав (только ученик может отклонить)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))

    try:
        mentorship.reject()
        db.session.commit()
        flash('Заявка отклонена', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('profile'))


@bp.route("/student/<int:student_id>")
@login_required
def student_profile(student_id):
    """Просмотр профиля друга — показывает ВСЮ информацию"""
    # Проверяем дружбу
    is_friend = Friendship.query.filter(
        db.or_(
            db.and_(Friendship.requester_id == current_user.id,
                    Friendship.addressee_id == student_id),
            db.and_(Friendship.requester_id == student_id,
                    Friendship.addressee_id == current_user.id),
        ),
        Friendship.status == 'accepted'
    ).first()

    if not is_friend:
        flash('Этот пользователь не в ваших друзьях', 'error')
        return redirect(url_for('profile'))

    friend = User.query.get_or_404(student_id)

    # Собираем полную статистику друга
    from models import AdaptiveTestResult, TopicMastery

    # Тесты
    all_tests = AdaptiveTestResult.query.filter_by(user_id=friend.id).order_by(
        AdaptiveTestResult.completed_at.desc()
    ).limit(10).all()

    # Мастерство по темам
    mastery_data = TopicMastery.query.filter_by(user_id=friend.id).all()

    return render_template('student_profile.html',
        student=friend,
        teacher=current_user,
        tests=all_tests,
        mastery=mastery_data
    )


LEGACY_ENDPOINTS += ('accept_request', 'reject_request', 'student_profile')
