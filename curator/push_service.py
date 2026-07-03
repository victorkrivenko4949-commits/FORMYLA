# -*- coding: utf-8 -*-
"""
push_service.py — Отправка push-уведомлений от Куратора.

Позволяет куратору (AI-наставнику) самостоятельно писать ученику
мотивационные и дисциплинирующие сообщения, которые приходят
как push-уведомления на телефон.

Использование:
    from curator.push_service import check_and_notify_user
    check_and_notify_user(user_id=123)

Интегрировано с:
    - daily_tasks (DailyTaskSet / DailyTaskItem) — проверка задач дня
    - curator/progress.py (ProgressLog, generate_ai_advice) — профиль и советы
    - app.py _send_push_notification — отправка push через Web Push API
"""

import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# ─── Заголовки уведомлений ────────────────────────────────────────────────────

_CURATOR_TITLE = '🧑‍🏫 Куратор Formyla'

# ─── Публичные функции ────────────────────────────────────────────────────────


def send_curator_push(user_id: int, title: str, body: str, url: str = '/daily_tasks') -> bool:
    """Отправить push-уведомление от имени Куратора.

    Args:
        user_id: ID получателя.
        title: Заголовок (по умолчанию — '🧑‍🏫 Куратор Formyla').
        body: Текст сообщения.
        url: Ссылка при клике.

    Returns:
        True если отправлено, False если VAPID не настроен или нет подписок.
    """
    try:
        # Ленивый импорт — чтобы избежать циклических зависимостей
        import sys

        # Получаем функцию _send_push_notification из app
        # Используем __import__ для доступа к модулю верхнего уровня
        app_module = sys.modules.get('app')
        if app_module is None:
            logger.warning("[push_service] app module not loaded — cannot send push")
            return False

        send_fn = getattr(app_module, '_send_push_notification', None)
        if send_fn is None:
            logger.warning("[push_service] _send_push_notification not found in app")
            return False

        send_fn(user_id=user_id, title=title, body=body, url=url)
        logger.info(f"[push_service] ✓ Push sent to user #{user_id}: {title} — {body[:60]}")
        return True
    except Exception as e:
        logger.error(f"[push_service] Failed to send push to user #{user_id}: {e}")
        return False


def check_and_notify_user(
    user_id: int,
    force: bool = False,
) -> dict:
    """Проверить прогресс ученика за сегодня и отправить push-уведомление.

    Куратор сам оценивает, сколько задач решено, и пишет
    персонализированное сообщение: хвалит, мотивирует или
    мягко дисциплинирует.

    Args:
        user_id: ID пользователя.
        force: если True — отправить уведомление даже если всё решено.

    Returns:
        dict с полями:
            - sent: bool — было ли отправлено уведомление
            - message: str — текст сообщения (или причина пропуска)
            - stats: dict — статистика за сегодня
    """
    logger.info(f"[push_service] Checking curator status for user #{user_id}")

    # ── 1. Статистика за сегодня ──────────────────────────────────────────
    stats = _get_today_stats(user_id)
    logger.info(f"[push_service] Today stats for #{user_id}: {stats}")

    # ── 2. Проверка на застревание (нет активности несколько дней) ────────
    stuck_info = _check_stuck(user_id)
    days_inactive = stuck_info.get('days_inactive', 0)

    # ── 3. Генерация сообщения от куратора ────────────────────────────────
    message = _generate_curator_message(stats, stuck_info)

    if not message:
        logger.info(f"[push_service] No message needed for user #{user_id}")
        return {
            'sent': False,
            'message': 'Нет необходимости в уведомлении',
            'stats': stats,
        }

    # ── 4. Решаем: отправлять или нет ─────────────────────────────────────
    should_send = force

    if not should_send:
        # Отправляем, если:
        # 1. Есть задачи и не все решены (дисциплина)
        # 2. Несколько дней без активности (застревание)
        # 3. Всё решено — только если есть хорошая серия (похвала)
        if stats.get('has_tasks', False) and not stats.get('all_solved', False):
            should_send = True
        elif days_inactive >= 3:
            should_send = True
        elif stats.get('all_solved', False) and stats.get('solved', 0) >= 3:
            should_send = True

    if not should_send:
        logger.info(f"[push_service] Skip — conditions not met for user #{user_id}")
        return {
            'sent': False,
            'message': 'Условия для отправки не выполнены',
            'stats': stats,
        }

    # ── 5. Отправляем push ────────────────────────────────────────────────
    url = '/daily_tasks'
    # Если ученик застрял — ведём на страницу куратора
    if days_inactive >= 3:
        url = '/profile'

    title = _CURATOR_TITLE
    sent = send_curator_push(user_id=user_id, title=title, body=message, url=url)

    # ── 6. Сохраняем сообщение в ProgressLog (AI-совет) ───────────────────
    if sent:
        _save_curator_message_to_log(user_id, message, stats)

    return {
        'sent': sent,
        'message': message,
        'stats': stats,
    }


# ─── Внутренние функции ────────────────────────────────────────────────────────


def _get_today_stats(user_id: int) -> dict:
    """Собрать статистику по задачам дня для пользователя.

    Returns:
        dict с полями:
            - has_tasks: bool — есть ли задачи на сегодня
            - total: int — всего задач
            - solved: int — решено правильно
            - attempted: int — всего попыток (даже неверных)
            - all_solved: bool — все ли задачи решены
            - accuracy: float — точность (0-100)
            - pending: int — сколько осталось неотвеченных
    """
    result = {
        'has_tasks': False,
        'total': 0,
        'solved': 0,
        'attempted': 0,
        'all_solved': False,
        'accuracy': 0.0,
        'pending': 0,
    }

    try:
        from daily_tasks.models import DailyTaskSet, DailyTaskItem

        today = date.today()
        daily_set = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=today, status='ready'
        ).first()

        if not daily_set:
            return result

        items = DailyTaskItem.query.filter_by(daily_set_id=daily_set.id).all()
        if not items:
            return result

        total = len(items)
        answered = [i for i in items if i.is_correct is not None]
        correct = [i for i in answered if i.is_correct is True]
        wrong = [i for i in answered if i.is_correct is False]
        pending = total - len(answered)

        result['has_tasks'] = True
        result['total'] = total
        result['solved'] = len(correct)
        result['attempted'] = len(answered)
        result['pending'] = pending
        result['all_solved'] = pending == 0
        result['accuracy'] = round(len(correct) / max(len(answered), 1) * 100, 1)

    except ImportError:
        logger.warning("[push_service] daily_tasks.models not available")
    except Exception as e:
        logger.error(f"[push_service] Error getting today's stats: {e}")

    return result


def _check_stuck(user_id: int) -> dict:
    """Проверить, нет ли застревания (длительного отсутствия активности).

    Использует уже существующую функцию detect_stuck из curator.progress,
    а также проверяет последнюю дату в ProgressLog.

    Returns:
        dict с полями:
            - is_stuck: bool
            - days_inactive: int — сколько дней без активности
            - last_active: str или None
    """
    result = {
        'is_stuck': False,
        'days_inactive': 0,
        'last_active': None,
    }

    try:
        from curator.progress import detect_stuck
        stuck = detect_stuck(user_id)
        result['is_stuck'] = stuck.get('is_stuck', False)

        if result['is_stuck']:
            result['days_inactive'] = stuck.get('days_since_progress', 3)
    except Exception as e:
        logger.error(f"[push_service] detect_stuck failed: {e}")

    # Дополнительно: проверим ProgressLog напрямую
    if not result['is_stuck']:
        try:
            from curator.models import ProgressLog
            last_log = (
                ProgressLog.query
                .filter_by(user_id=user_id, log_type='daily')
                .order_by(ProgressLog.log_date.desc())
                .first()
            )
            if last_log:
                delta = (date.today() - last_log.log_date).days
                result['days_inactive'] = delta
                result['last_active'] = last_log.log_date.isoformat()
                if delta >= 3:
                    result['is_stuck'] = True
        except Exception as e:
            logger.error(f"[push_service] ProgressLog check failed: {e}")

    return result


def _generate_curator_message(stats: dict, stuck: dict) -> str:
    """Сгенерировать сообщение от куратора на основе статистики.

    Приоритет:
    1. Застревание (нет активности 3+ дней) — жёсткое сообщение
    2. Есть задачи, но ничего не решено — дисциплина
    3. Решено частично — мотивация
    4. Всё решено — похвала

    Сначала пробует AI, при недоступности — fallback-шаблоны.
    """
    days_inactive = stuck.get('days_inactive', 0)

    # ── Сценарий 1: Застревание ───────────────────────────────────────────
    if days_inactive >= 7:
        return (
            f'Ты не занимаешься уже {days_inactive} дней. '
            'Так дело не пойдет — надо держать дисциплину! '
            'Начни с одной задачи прямо сейчас.'
        )
    if days_inactive >= 3:
        return (
            f'Ты не решал задачи уже {days_inactive} дня. '
            'Не забывай про математику! '
            'Попробуй решить хотя бы пару задач сегодня.'
        )

    # ── Сценарий 2: Нет задач на сегодня ───────────────────────────────────
    if not stats.get('has_tasks', False):
        return ''

    total = stats['total']
    solved = stats['solved']
    pending = stats['pending']

    # ── Сценарий 3: Ничего не решено ──────────────────────────────────────
    if solved == 0 and pending == total:
        return (
            f'Сегодня ты не решил ни одной задачи из {total}. '
            'Попробуй завтра больше — результат зависит от твоих усилий!'
        )

    # ── Сценарий 4: Решено частично ───────────────────────────────────────
    if pending > 0 and solved < total:
        unsolved = total - solved
        if solved == 0:
            return (
                f'Сегодня ты не решил ни одной задачи. '
                'Так дело не пойдет — надо держать дисциплину! '
                f'У тебя осталось {unsolved} нерешённых задач.'
            )
        else:
            return (
                f'Сегодня ты решил {solved} из {total} задач. '
                f'Попробуй завтра решить больше — ты справишься!'
            )

    # ── Сценарий 5: Решено, но были ошибки ────────────────────────────────
    if stats.get('attempted', 0) > solved:
        accuracy = stats.get('accuracy', 0)
        if accuracy < 50:
            return (
                f'Ты решил все {total} задач, но точность всего {accuracy}%. '
                'Попробуй быть внимательнее — перепроверяй свои ответы!'
            )
        return (
            f'Ты решил все {total} задач с точностью {accuracy}%. '
            'Хороший результат, но есть куда расти!'
        )

    # ── Сценарий 6: Всё решено правильно ──────────────────────────────────
    if solved == total:
        if solved >= 5:
            return (
                f'Отличная работа! Ты решил все {total} задач сегодня. '
                'Так держать — ты на верном пути к победе!'
            )
        return (
            f'Молодец! Все {total} задач сегодня решены. '
            'Продолжай в том же духе!'
        )

    return ''


def _save_curator_message_to_log(user_id: int, message: str, stats: dict) -> None:
    """Сохранить сообщение куратора в ProgressLog как AI-совет.

    Args:
        user_id: ID пользователя.
        message: Текст сообщения.
        stats: Статистика за сегодня (для контекста).
    """
    try:
        from curator.models import ProgressLog
        from models import db

        today = date.today()

        # Ищем существующий лог за сегодня
        log = ProgressLog.query.filter_by(
            user_id=user_id,
            log_date=today,
            log_type='daily',
        ).first()

        if log:
            # Обновляем AI-совет (не затираем предыдущий, а дополняем)
            existing = log.ai_advice or ''
            if message not in existing:
                log.ai_advice = (existing + '\n---\n' + message).strip()
        else:
            # Создаём новый лог
            log = ProgressLog(
                user_id=user_id,
                log_date=today,
                log_type='daily',
                tasks_solved=stats.get('solved', 0),
                tasks_total=stats.get('total', 0),
                accuracy_pct=stats.get('accuracy'),
                ai_advice=message,
            )
            db.session.add(log)

        db.session.commit()
        logger.info(f"[push_service] ✓ Curator message saved to ProgressLog for user #{user_id}")
    except Exception as e:
        logger.error(f"[push_service] Failed to save message to log: {e}")
        db.session.rollback() if hasattr(db, 'session') else None
