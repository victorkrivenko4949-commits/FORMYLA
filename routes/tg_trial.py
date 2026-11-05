# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK — API «Неделя Premium за подписку на Telegram-канал».

  GET  /api/tg-trial/status  → {state, channel, channel_url, days, expires_at?, tg_linked?}
  GET  /api/tg-trial/link    → {ok, invite_link, bot_link}
  POST /api/tg-trial/claim   {tg_auth?: {...payload Telegram Login Widget}}
       → {ok, expires_at} | {error, code}

Логика — services/tg_trial.py.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models import db
from services.security import validate_csrf
from services import tg_trial

log = logging.getLogger(__name__)

tg_trial_bp = Blueprint('tg_trial', __name__, url_prefix='/api/tg-trial')


@tg_trial_bp.route('/status', methods=['GET'])
@login_required
def status():
    return jsonify(tg_trial.get_state(current_user))


@tg_trial_bp.route('/link', methods=['GET'])
@login_required
def link():
    """Личная ссылка в канал и ссылка на бота (создаются при первом открытии окна)."""
    if tg_trial.get_state(current_user).get('state') != 'available':
        return jsonify({'error': 'Неделя недоступна.', 'code': 'unavailable'}), 409
    try:
        return jsonify({'ok': True, **tg_trial.get_links(current_user)})
    except tg_trial.TgTrialError as e:
        return jsonify({'error': e.message, 'code': e.code}), e.http
    except Exception as e:  # noqa: BLE001
        log.exception('[tg_trial] link failed: %s', e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return jsonify({'error': 'server', 'code': 'server'}), 500


@tg_trial_bp.route('/claim', methods=['POST'])
@login_required
def claim():
    if not validate_csrf(request.headers.get('X-CSRF-Token', '')):
        return jsonify({'error': 'Обнови страницу и попробуй ещё раз.', 'code': 'csrf'}), 400
    data = request.get_json(silent=True) or {}
    tg_auth = data.get('tg_auth') if isinstance(data.get('tg_auth'), dict) else None
    try:
        result = tg_trial.claim_week(current_user, tg_auth=tg_auth)
        return jsonify({'ok': True, **result})
    except tg_trial.TgTrialError as e:
        return jsonify({'error': e.message, 'code': e.code}), e.http
    except Exception as e:  # noqa: BLE001
        log.exception('[tg_trial] claim failed: %s', e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return jsonify({'error': 'Не получилось выдать неделю. Попробуй ещё раз.', 'code': 'server'}), 500
