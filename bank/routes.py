"""Extracted legacy routes; URL, authentication and response contracts preserved."""
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from models import db, User, Mentorship

bp = Blueprint('bank', __name__)

@bp.route("/secrets")
@login_required
def secrets():
    """Главная страница раздела 'Секреты олимпиадной математики'"""
    from models import OlympiadSecret

    # Получаем выбранную категорию из параметров
    selected_topic = request.args.get('topic', 'all')

    # Получаем все уникальные категории
    topics = db.session.query(OlympiadSecret.topic).distinct().order_by(OlympiadSecret.topic).all()
    topics = [t[0] for t in topics]

    # Фильтруем статьи по категории
    if selected_topic == 'all':
        secrets_list = OlympiadSecret.query.order_by(OlympiadSecret.topic, OlympiadSecret.title).all()
    else:
        secrets_list = OlympiadSecret.query.filter_by(topic=selected_topic).order_by(OlympiadSecret.title).all()

    # Группируем статьи по категориям для отображения
    secrets_by_topic = {}
    for secret in secrets_list:
        if secret.topic not in secrets_by_topic:
            secrets_by_topic[secret.topic] = []
        secrets_by_topic[secret.topic].append(secret)

    return render_template('secrets.html',
        topics=topics,
        selected_topic=selected_topic,
        secrets_by_topic=secrets_by_topic,
        total_count=len(secrets_list)
    )


@bp.route("/secrets/<int:secret_id>")
def secret_detail(secret_id):
    """Страница отдельной статьи"""
    from models import OlympiadSecret

    secret = OlympiadSecret.query.get_or_404(secret_id)

    # Получаем похожие статьи из той же категории
    related_secrets = OlympiadSecret.query.filter(
        OlympiadSecret.topic == secret.topic,
        OlympiadSecret.id != secret.id
    ).limit(3).all()

    return render_template('secret_detail.html',
        secret=secret,
        related_secrets=related_secrets
    )


@bp.route("/api/secrets")
@login_required
def api_secrets():
    """API для получения списка секретов (для будущих фич)"""
    from models import OlympiadSecret

    topic = request.args.get('topic')
    difficulty = request.args.get('difficulty', type=int)

    query = OlympiadSecret.query

    if topic:
        query = query.filter_by(topic=topic)
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)

    secrets_list = query.all()

    return jsonify({
        'success': True,
        'count': len(secrets_list),
        'secrets': [{
            'id': s.id,
            'topic': s.topic,
            'title': s.title,
            'difficulty_level': s.difficulty_level,
            'preview': s.content[:200] + '...' if len(s.content) > 200 else s.content
        } for s in secrets_list]
    })


LEGACY_ENDPOINTS = ('secrets', 'secret_detail', 'api_secrets')
