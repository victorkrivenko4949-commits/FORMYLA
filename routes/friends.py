# -*- coding: utf-8 -*-
"""
Friendship routes for FORMYLA
Bidirectional friend system with request/accept/decline/remove
"""
from flask import Blueprint, jsonify, render_template, abort, request
from flask_login import login_required, current_user
from models import db, User, Friendship, Notification
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

friends_bp = Blueprint('friends', __name__)


def _create_notification(user_id, notif_type, sender_id, data=None):
    """Create a notification for a user."""
    notif = Notification(
        user_id=user_id,
        type=notif_type,
        from_user_id=sender_id,
        data=json.dumps(data) if data else None
    )
    db.session.add(notif)
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Notification error: {e}")
        db.session.rollback()


@friends_bp.route('/friends/request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    """Send a friend request."""
    if user_id == current_user.id:
        return jsonify({'error': 'Нельзя добавить себя в друзья'}), 400

    target = User.query.get_or_404(user_id)
    status = current_user.friendship_status_with(user_id)

    if status == 'friends':
        return jsonify({'error': 'Вы уже друзья'}), 409
    if status == 'pending_sent':
        return jsonify({'error': 'Запрос уже отправлен'}), 409
    if status == 'blocked':
        return jsonify({'error': 'Недоступно'}), 403

    # Mutual request — auto-accept
    if status == 'pending_received':
        existing = Friendship.query.filter_by(
            requester_id=user_id, addressee_id=current_user.id, status='pending'
        ).first()
        if existing:
            existing.accept()
            db.session.commit()
            current_user.experience_points = (current_user.experience_points or 0) + 10
            target.experience_points = (target.experience_points or 0) + 10
            db.session.commit()
            _create_notification(target.id, 'friend_accepted', current_user.id)
            return jsonify({'status': 'friends', 'message': 'Теперь вы друзья! +10 XP'})

    # Отправляем запрос в друзья — ожидает подтверждения (как ВКонтакте)
    f = Friendship(requester_id=current_user.id, addressee_id=user_id, status='pending')
    db.session.add(f)
    db.session.commit()

    _create_notification(target.id, 'friend_request', current_user.id, {
        'message': f'{current_user.nickname or current_user.name or current_user.email} хочет добавить вас в друзья'
    })

    name = target.nickname or target.name or target.email
    return jsonify({'status': 'pending', 'message': f'Запрос в друзья отправлен {name}'})


@friends_bp.route('/friends/accept/<int:request_id>', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    """Accept a friend request."""
    f = Friendship.query.get_or_404(request_id)
    if f.addressee_id != current_user.id:
        abort(403)
    if f.status != 'pending':
        return jsonify({'error': 'Запрос уже обработан'}), 409

    f.accept()
    db.session.commit()

    requester = User.query.get(f.requester_id)
    current_user.experience_points = (current_user.experience_points or 0) + 10
    if requester:
        requester.experience_points = (requester.experience_points or 0) + 10
    db.session.commit()

    _create_notification(f.requester_id, 'friend_accepted', current_user.id)

    name = requester.nickname or requester.name or requester.email if requester else ''
    return jsonify({'status': 'friends', 'message': f'{name} теперь ваш друг! +10 XP'})