# -*- coding: utf-8 -*-
"""services/push_broadcast.py — массовая Web Push рассылка всем подписчикам FORMYLA.

Использует уже существующую инфраструктуру:
  * models.PushSubscription (таблица push_subscriptions: endpoint, p256dh_key, auth_key)
  * static/sw.js — ждёт JSON {title, body, icon, badge, data:{url,type}}
  * env VAPID_PRIVATE_KEY / VAPID_CLAIM_EMAIL (уже объявлены в render.yaml)

Запуск:
  python scripts/push_daily.py                       # «Задачи дня ждут»
  python scripts/push_daily.py --title ... --body ... --url /daily_tasks

HTTP-роут (опционально): register(app) добавляет POST /api/push/broadcast,
защищённый заголовком Authorization: Bearer <PUSH_BROADCAST_SECRET>.
"""
import json
import logging
import os

from pywebpush import WebPushException, webpush

_log = logging.getLogger('formyla.push_broadcast')

DAILY_TITLE = 'FORMYLA: задачи дня ждут'
DAILY_BODY = 'Новые задачи уже на сайте. Реши их сегодня и не потеряй серию!'
DAILY_URL = '/daily_tasks'


def _vapid_settings():
    private_key = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
    if not private_key:
        raise RuntimeError('VAPID_PRIVATE_KEY не задан — push-рассылка невозможна')
    email = os.environ.get('VAPID_CLAIM_EMAIL', 'noreply@formyla.net').strip()
    if not email.startswith('mailto:'):
        email = 'mailto:' + email
    return private_key, {'sub': email}


def build_payload(title, body, url=DAILY_URL, kind='daily', icon='/static/logo.png'):
    return json.dumps({
        'title': title,
        'body': body,
        'icon': icon,
        'badge': icon,
        'tag': kind,
        'data': {'url': url, 'type': kind},
    }, ensure_ascii=False)


def broadcast(title, body, url=DAILY_URL, kind='daily', ttl=43200, dry_run=False):
    """Отправить уведомление всем подписчикам. Возвращает dict со статистикой.

    Протухшие подписки (404/410 от push-сервиса) удаляются из БД.
    Должно вызываться внутри app.app_context().
    """
    from models import PushSubscription, db

    private_key, claims = _vapid_settings()
    payload = build_payload(title, body, url=url, kind=kind)

    subs = PushSubscription.query.all()
    stats = {'total': len(subs), 'sent': 0, 'removed': 0, 'failed': 0}
    if dry_run:
        _log.info('push_broadcast dry-run: %s подписок', stats['total'])
        return stats

    for sub in subs:
        info = {
            'endpoint': sub.endpoint,
            'keys': {'p256dh': sub.p256dh_key, 'auth': sub.auth_key},
        }
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=dict(claims),
                ttl=ttl,
            )
            stats['sent'] += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 410):
                db.session.delete(sub)
                stats['removed'] += 1
            else:
                stats['failed'] += 1
                _log.warning('push fail (%s) %s: %s', status, sub.endpoint[:60], exc)
        except Exception as exc:  # noqa: BLE001
            stats['failed'] += 1
            _log.warning('push error %s: %s', sub.endpoint[:60], exc)

    if stats['removed']:
        db.session.commit()
    _log.info('push_broadcast: %s', stats)
    return stats


def broadcast_daily(dry_run=False):
    return broadcast(DAILY_TITLE, DAILY_BODY, url=DAILY_URL, kind='daily', dry_run=dry_run)


# ───────────────────────── HTTP-роут (опционально) ─────────────────────────

def register(app):
    """Подключить POST /api/push/broadcast к уже созданному Flask-приложению."""
    if app.config.get('_PUSH_BROADCAST_REGISTERED'):
        return
    from flask import Blueprint, jsonify, request

    bp = Blueprint('push_broadcast', __name__)

    @bp.post('/api/push/broadcast')
    def _broadcast_route():
        secret = os.environ.get('PUSH_BROADCAST_SECRET', '')
        auth = request.headers.get('Authorization', '')
        if not secret or auth != 'Bearer ' + secret:
            return jsonify({'ok': False, 'error': 'unauthorized'}), 401
        data = request.get_json(silent=True) or {}
        try:
            stats = broadcast(
                data.get('title') or DAILY_TITLE,
                data.get('body') or DAILY_BODY,
                url=data.get('url') or DAILY_URL,
                kind=data.get('kind') or 'daily',
                dry_run=bool(data.get('dry_run')),
            )
        except RuntimeError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 500
        return jsonify({'ok': True, **stats})

    app.register_blueprint(bp)
    app.config['_PUSH_BROADCAST_REGISTERED'] = True
