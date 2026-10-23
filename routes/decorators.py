# -*- coding: utf-8 -*-
"""
Декораторы для защиты эндпоинтов по лимитам подписки.

Использование:
    from routes.decorators import require_feature

    @app.route('/api/check_adaptive_answer', methods=['POST'])
    @require_feature('task')
    def check_adaptive_answer(): ...

    @app.route('/api/tutor/send', methods=['POST'])
    @login_required
    @require_feature('ai_explanation')
    def tutor_send(): ...

Поведение:
  - Не авторизован -> 401 JSON
  - Лимит достигнут -> 403 JSON с данными для paywall
  - Всё ок -> выполняет эндпоинт, затем увеличивает счётчик
"""

import logging
import functools
from flask import jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)


def require_feature(feature: str):
    """
    Декоратор: проверяет лимит перед выполнением эндпоинта.

    Args:
        feature: 'task' | 'ai_explanation'

    При блокировке возвращает 403 JSON:
    {
        "error": "limit_reached",
        "feature": "ai_explanation",
        "current_plan": "free",
        "message": "...",
        "usage_today": 3,
        "limit": 3,
        "upgrade_url": "/subscribe",
        "upgrade_price": "390 руб/мес"
    }

    При отсутствии авторизации возвращает 401 JSON.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            # 1. Проверка авторизации
            if not current_user.is_authenticated:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Необходима авторизация',
                }), 401

            user_id = current_user.id

            # 2. Получаем сервис подписок
            try:
                from services.subscription import get_subscription_service
                sub_service = get_subscription_service()
            except Exception as e:
                # Если сервис недоступен — не блокируем (fail open)
                logger.error(f'[require_feature] SubscriptionService unavailable: {e}')
                return f(*args, **kwargs)

            # 3. Проверяем лимит
            try:
                can_use, error_msg = sub_service.can_use_feature(user_id, feature)
            except Exception as e:
                # При ошибке проверки — не блокируем (fail open)
                logger.error(f'[require_feature] can_use_feature error: {e}')
                return f(*args, **kwargs)

            if not can_use:
                # Получаем данные для paywall
                try:
                    plan_info = sub_service.get_user_plan(user_id)
                    usage = sub_service.get_today_usage(user_id)
                    limits = plan_info['limits']

                    if feature == 'task':
                        used = usage.get('tasks_completed', 0)
                        limit = limits.get('tasks_per_day')
                    elif feature == 'ai_explanation':
                        used = usage.get('ai_explanations_used', 0)
                        limit = limits.get('ai_explanations_per_day')
                    else:
                        used = 0
                        limit = None

                except Exception as e:
                    logger.error(f'[require_feature] Error getting usage data: {e}')
                    used = 0
                    limit = None
                    plan_info = {'plan': 'free'}

                return jsonify({
                    'error': 'limit_reached',
                    'feature': feature,
                    'current_plan': plan_info.get('plan', 'free'),
                    'message': error_msg,
                    'usage_today': used,
                    'limit': limit,
                    'upgrade_url': '/subscribe',
                    'upgrade_price': '390 руб/мес',
                }), 403

            # 4. Выполняем эндпоинт
            response = f(*args, **kwargs)

            # 5. Увеличиваем счётчик ПОСЛЕ успешного выполнения
            # Проверяем что ответ не является ошибкой (4xx/5xx)
            try:
                status_code = _get_status_code(response)
                if status_code < 400:
                    sub_service.increment_usage(user_id, feature)
            except Exception as e:
                # Не ломаем ответ если счётчик не обновился
                logger.warning(f'[require_feature] increment_usage failed: {e}')

            return response

        return wrapped
    return decorator


def _get_status_code(response) -> int:
    """Извлекает HTTP статус-код из Flask response."""
    try:
        if isinstance(response, tuple):
            # (response_obj, status_code) или (response_obj, status_code, headers)
            if len(response) >= 2 and isinstance(response[1], int):
                return response[1]
        # Объект Response
        if hasattr(response, 'status_code'):
            return response.status_code
    except Exception:
        pass
    return 200  # По умолчанию считаем успехом


def require_admin(f):
    """
    Декоратор: проверяет что пользователь является администратором.
    Администратор = первый пользователь (id=1) или email из ADMIN_EMAILS.

    Возвращает 403 если не администратор, 401 если не авторизован.
    """
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'unauthorized'}), 401

        # Проверка: id=1 (первый пользователь) или email администратора
        import os
        admin_emails = os.environ.get('ADMIN_EMAILS', '').split(',')
        admin_emails = [e.strip() for e in admin_emails if e.strip()]

        is_admin = (
            current_user.id == 1
            or (hasattr(current_user, 'email') and current_user.email in admin_emails)
        )

        if not is_admin:
            logger.warning(
                f'[require_admin] Unauthorized access attempt by user {current_user.id}'
            )
            return jsonify({'error': 'forbidden', 'message': 'Доступ запрещён'}), 403

        return f(*args, **kwargs)
    return wrapped
