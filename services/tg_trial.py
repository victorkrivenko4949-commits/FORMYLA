# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK (05.11.2026) — неделя Premium за подписку на Telegram-канал.

Поток для пользователя (без входа через Telegram):
  1. «Перейти в канал» — ЛИЧНАЯ ссылка-приглашение (createChatInviteLink).
     Вступил по ней → бот видит апдейт chat_member и узнаёт Telegram id.
  2. Вернулся на сайт → проверка запускается сама (или кнопка «Проверить подписку»).
     Сервер забирает апдейты бота (getUpdates), находит Telegram id и
     спрашивает getChatMember(канал, id). Подписан → ровно 7 дней Premium.
  Уже был подписан (по ссылке вступить нельзя) → «Подтвердить через бота»:
     t.me/<бот>?start=<token>, бот узнаёт id из /start.

Правила:
  • одна неделя на аккаунт и одна на Telegram-аккаунт (таблица tg_trial_grants);
  • если идёт пробный день — неделя его заменяет (срок = сейчас + 7 дней);
  • уже есть оплаченный Premium — +7 дней сразу после текущего срока;
  • родитель/учитель — как с пробным днём: только в аккаунте ребёнка;
  • после выдачи отписка доступ не отзывает (честная акция, без «ловушек»).

Важно для работы: бот TELEGRAM_BOT_TOKEN должен быть АДМИНИСТРАТОРОМ канала,
иначе Telegram не отдаёт статус подписчика (ответ «member list is inaccessible»).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import db

log = logging.getLogger(__name__)

TRIAL_WEEK_DAYS = 7          # ровно неделя — не настраивается через env намеренно
TRIAL_WEEK_PLAN = 'premium_intense'
_MEMBER_STATUSES = {'creator', 'administrator', 'member'}


def channel_username() -> str:
    """@username канала без «@». По умолчанию — официальный канал FORMYLA."""
    raw = (os.environ.get('TG_TRIAL_CHANNEL') or 'FormylaMaths').strip()
    return raw.lstrip('@')


def channel_url() -> str:
    return f'https://t.me/{channel_username()}'


def _bot_token() -> str:
    return (os.environ.get('TELEGRAM_BOT_TOKEN') or '').strip()


def telegram_api_base() -> str:
    """Адрес Bot API. С российского сервера api.telegram.org недоступен —
    тогда TELEGRAM_API_BASE указывает на прокси (Cloudflare Worker),
    который пересылает запросы /bot<token>/… как есть."""
    return (os.environ.get('TELEGRAM_API_BASE') or 'https://api.telegram.org').strip().rstrip('/')


class TgTrialError(Exception):
    """Ошибка с понятным пользователю текстом и кодом для фронтенда."""

    def __init__(self, code: str, message: str, http: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http = http


# ───────────────────────── Bot API ─────────────────────────

def check_membership(telegram_id: str) -> bool:
    """True, если telegram_id подписан на канал. Ошибки конфигурации → TgTrialError."""
    token = _bot_token()
    if not token:
        log.error('[tg_trial] TELEGRAM_BOT_TOKEN не задан')
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)
    try:
        resp = requests.get(
            f'{telegram_api_base()}/bot{token}/getChatMember',
            params={'chat_id': '@' + channel_username(), 'user_id': telegram_id},
            timeout=5,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — сеть/JSON
        log.warning('[tg_trial] getChatMember network error: %r', exc)
        raise TgTrialError('network', 'Telegram не ответил. Нажми «Проверить» ещё раз через пару секунд.', 503)

    if not data.get('ok'):
        desc = str(data.get('description') or '')
        # «user not found» — пользователь ни разу не заходил в канал → не подписан.
        if 'user not found' in desc.lower() or 'participant_id_invalid' in desc.lower():
            return False
        log.error('[tg_trial] getChatMember failed: %s (бот должен быть админом канала)', desc)
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)

    member = data.get('result') or {}
    status = member.get('status')
    if status in _MEMBER_STATUSES:
        return True
    # restricted — участник с ограничениями, подписка есть, если is_member
    return status == 'restricted' and bool(member.get('is_member'))


def _bot_call(method: str, payload: dict, timeout: float = 6) -> dict:
    """POST в Bot API. Возвращает result или бросает TgTrialError('network')."""
    token = _bot_token()
    if not token:
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)
    try:
        resp = requests.post(f'{telegram_api_base()}/bot{token}/{method}', json=payload, timeout=timeout)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning('[tg_trial] %s network error: %r', method, exc)
        raise TgTrialError('network', 'Telegram не ответил. Нажми «Проверить» ещё раз через пару секунд.', 503)
    if not data.get('ok'):
        log.error('[tg_trial] %s failed: %s', method, data.get('description'))
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)
    return data.get('result')


def bot_username() -> str:
    return (os.environ.get('TELEGRAM_BOT_USERNAME') or '').strip().lstrip('@')


# ───────────────────── Личная ссылка в канал ─────────────────────
#
# Чтобы не просить «войти через Telegram» (виджет telegram.org в РФ часто не
# открывается), каждому даём ЛИЧНУЮ ссылку-приглашение в канал. Вступил по ней —
# бот получает апдейт chat_member с этой ссылкой и узнаёт его Telegram id.
# Уже подписанным (по ссылке вступить нельзя) — запасной путь через бота:
# t.me/<бот>?start=<token> → апдейт message «/start <token>».

def get_links(user) -> dict:
    """Личная ссылка в канал + ссылка на бота. Создаёт ссылку при первом вызове."""
    import secrets
    from models_tg_trial import TgTrialLink

    row = db.session.get(TgTrialLink, user.id)
    if row is None:
        row = TgTrialLink(user_id=user.id, start_token='fw' + secrets.token_urlsafe(12).replace('-', 'x').replace('_', 'y'))
        db.session.add(row)
        db.session.commit()
    if not row.invite_link:
        res = _bot_call('createChatInviteLink', {
            'chat_id': '@' + channel_username(),
            'name': f'FORMYLA неделя #{user.id}'[:32],
        })
        row.invite_link = (res or {}).get('invite_link')
        db.session.commit()
    bot = bot_username()
    return {
        'invite_link': row.invite_link or channel_url(),
        'bot_link': f'https://t.me/{bot}?start={row.start_token}' if bot else '',
    }


def _member_status_ok(member: dict) -> bool:
    st = (member or {}).get('status')
    return st in _MEMBER_STATUSES or (st == 'restricted' and bool((member or {}).get('is_member')))


def sync_updates() -> int:
    """Забрать новые апдейты бота и сопоставить Telegram id со ссылками.

    Идемпотентно: несколько воркеров могут вызвать одновременно — повторная
    обработка того же апдейта ничего не ломает. Возвращает число сопоставлений.
    """
    from models_tg_trial import TgBotCursor, TgTrialLink

    cur = db.session.get(TgBotCursor, 1)
    offset = int(cur.offset) if cur else 0
    updates = _bot_call('getUpdates', {
        'offset': offset, 'timeout': 0, 'limit': 100,
        'allowed_updates': ['chat_member', 'message'],
    }, timeout=8) or []
    matched = 0
    replies = []
    channel = channel_username().lower()
    for upd in updates:
        tg_id, row = None, None
        cm = upd.get('chat_member')
        msg = upd.get('message')
        if cm and str((cm.get('chat') or {}).get('username') or '').lower() == channel:
            link = ((cm.get('invite_link') or {}).get('invite_link') or '')
            if link and _member_status_ok(cm.get('new_chat_member')):
                row = TgTrialLink.query.filter_by(invite_link=link).first()
                tg_id = str(((cm.get('new_chat_member') or {}).get('user') or {}).get('id') or '')
        elif msg and str(msg.get('text') or '').startswith('/start'):
            parts = str(msg['text']).split(maxsplit=1)
            token = parts[1].strip() if len(parts) > 1 else ''
            tg_id = str((msg.get('from') or {}).get('id') or '')
            if token:
                row = TgTrialLink.query.filter_by(start_token=token).first()
            replies.append((msg.get('chat') or {}).get('id'))
        if row is not None and tg_id:
            row.telegram_id = tg_id
            row.matched_at = _now()
            matched += 1
    if updates:
        new_offset = max(int(u.get('update_id', 0)) for u in updates) + 1
        if cur is None:
            db.session.add(TgBotCursor(id=1, offset=new_offset, updated_at=_now()))
        elif new_offset > int(cur.offset):
            cur.offset = new_offset
            cur.updated_at = _now()
    try:
        db.session.commit()
    except IntegrityError:   # другой воркер успел создать курсор — не страшно
        db.session.rollback()
    for chat_id in replies:
        if not chat_id:
            continue
        try:
            _bot_call('sendMessage', {
                'chat_id': chat_id,
                'text': '✅ Готово! Вернись на сайт FORMYLA и нажми «Проверить подписку».\n'
                        f'Если ещё не подписан — вот канал: https://t.me/{channel_username()}',
                'disable_web_page_preview': True,
            }, timeout=4)
        except TgTrialError:
            pass
    return matched


def _telegram_for(user) -> str:
    """Telegram id пользователя: из личной ссылки/бота, иначе привязанный к аккаунту."""
    from models_tg_trial import TgTrialLink

    row = db.session.get(TgTrialLink, user.id)
    if row is not None and not row.telegram_id:
        try:
            sync_updates()
        except TgTrialError as e:
            if not getattr(user, 'telegram_id', None):
                raise
            log.warning('[tg_trial] sync_updates failed: %s', e.code)
        db.session.refresh(row)
    if row is not None and row.telegram_id:
        return str(row.telegram_id)
    return str(getattr(user, 'telegram_id', '') or '').strip()


# ───────────────────────── Состояние ─────────────────────────

def _now() -> datetime:
    return datetime.utcnow()


def _role_blocked(user) -> bool:
    return (getattr(user, 'role', 'student') or 'student') in ('parent', 'teacher')


def _premium_kind(user) -> str:
    """Какой Premium сейчас у пользователя — ОДНИМ запросом.

    'real'  — оплаченный / бета / пилотный (акция не нужна);
    'trial' — идёт пробный день (неделя его заменит);
    'none'  — Premium нет.
    """
    try:
        from services.pilot import is_pilot_user
        if is_pilot_user(user):
            return 'real'
    except Exception:  # noqa: BLE001
        pass
    try:
        # Сортировка по is_trial: настоящая подписка (0) важнее пробной (1).
        row = db.session.execute(text(
            "SELECT COALESCE(CAST(is_trial AS INTEGER),0) FROM subscriptions "
            "WHERE user_id = :u AND status = 'active' AND plan LIKE 'premium%' "
            "AND (expires_at IS NULL OR expires_at > :now) "
            "ORDER BY COALESCE(CAST(is_trial AS INTEGER),0) ASC LIMIT 1"
        ), {'u': user.id, 'now': _now().isoformat(sep=' ')}).first()
    except Exception:  # noqa: BLE001
        return 'none'
    if row is None:
        return 'none'
    return 'trial' if int(row[0]) == 1 else 'real'


def _grant_for(user_id: int):
    from models_tg_trial import TgTrialGrant
    return TgTrialGrant.query.filter_by(user_id=user_id).first()


_G_KEY = '_tg_trial_state'


def _drop_cache() -> None:
    try:
        from flask import g
        g.pop(_G_KEY, None)
    except Exception:  # noqa: BLE001 — вне запроса кэша нет
        pass


def get_state(user) -> dict:
    """Состояние для UI. Считается один раз за запрос (flask.g): шаблон base.html
    и страница /subscribe спрашивают его оба, в БД это 2 запроса, не 4."""
    try:
        from flask import g
        cached = g.get(_G_KEY)
        if cached is not None and cached[0] == getattr(user, 'id', None):
            return cached[1]
        state = _compute_state(user)
        setattr(g, _G_KEY, (getattr(user, 'id', None), state))
        return state
    except Exception:  # noqa: BLE001 — вне контекста запроса
        return _compute_state(user)


def _compute_state(user) -> dict:
    """Что показать пользователю. state:
       hidden     — гость/аноним/родитель/учитель: ничего не показываем;
       premium    — уже есть настоящий Premium;
       active     — неделя идёт (expires_at);
       used       — неделя уже была;
       available  — можно получить (tg_linked — привязан ли Telegram).
    """
    base = {'channel': channel_username(), 'channel_url': channel_url(), 'days': TRIAL_WEEK_DAYS}
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'is_guest', False):
        return {**base, 'state': 'hidden'}
    if _role_blocked(user) or not _bot_token():
        return {**base, 'state': 'hidden'}
    try:
        grant = _grant_for(user.id)
    except Exception:  # noqa: BLE001 — таблицы ещё нет и т.п.
        return {**base, 'state': 'hidden'}
    if grant is not None:
        if grant.expires_at > _now():
            return {**base, 'state': 'active', 'expires_at': grant.expires_at.isoformat(sep=' ')}
        return {**base, 'state': 'used'}
    # Акция доступна ВСЕМ ученикам: у кого уже есть Premium — +7 дней к сроку.
    kind = _premium_kind(user)
    trial_day = kind == 'trial'
    return {**base, 'state': 'available', 'has_premium': kind == 'real',
            'tg_linked': bool(getattr(user, 'telegram_id', None)),
            'tg_username': getattr(user, 'telegram_username', None) or '',
            'trial_day_active': trial_day}


# ───────────────────────── Выдача ─────────────────────────

def link_telegram(user, payload: dict) -> None:
    """Привязать Telegram к аккаунту по подписанному payload Login Widget."""
    from models import User
    from routes.telegram_auth import verify_telegram_payload

    clean = {k: str(v) for k, v in (payload or {}).items() if v is not None}
    if not verify_telegram_payload(clean):
        raise TgTrialError('tg_auth', 'Не удалось подтвердить Telegram. Попробуй войти ещё раз.', 400)
    tg_id = clean.get('id', '').strip()
    if not tg_id:
        raise TgTrialError('tg_auth', 'Telegram не передал id. Попробуй ещё раз.', 400)
    existing = User.query.filter_by(telegram_id=tg_id).first()
    if existing is not None and existing.id != user.id:
        raise TgTrialError('tg_taken', 'Этот Telegram уже привязан к другому аккаунту FORMYLA.', 409)
    user.telegram_id = tg_id
    user.telegram_username = (clean.get('username') or '').strip() or None
    db.session.commit()
    _drop_cache()


def _parse_dt(v):
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ').split('+')[0])
    except ValueError:
        return None


def _week_period(user, now):
    """(начало, конец, тариф, создавать_ли_подписку) для выдачи недели.

    Нет Premium / пробный день → неделя «Работяги» с этого момента.
    Есть оплаченный Premium → +7 дней сразу после текущего срока, тот же тариф
    (activate_premium с будущим началом не сокращает оплаченный период).
    Бессрочный доступ → подписку не трогаем, только фиксируем выдачу.
    """
    week = timedelta(days=TRIAL_WEEK_DAYS)
    if _premium_kind(user) != 'real':
        return now, now + week, TRIAL_WEEK_PLAN, True
    try:
        rows = db.session.execute(text(
            "SELECT plan, expires_at FROM subscriptions "
            "WHERE user_id = :u AND status = 'active' AND plan LIKE 'premium%' "
            "AND COALESCE(CAST(is_trial AS INTEGER),0) = 0 "
            "AND (expires_at IS NULL OR expires_at > :now)"
        ), {'u': user.id, 'now': now.isoformat(sep=' ')}).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    if any(r[1] is None for r in rows):
        return now, now + week, TRIAL_WEEK_PLAN, False
    if rows:
        plan, end = max(((r[0], _parse_dt(r[1])) for r in rows), key=lambda x: x[1] or now)
        if end and end > now:
            from services.subscription import PLAN_LIMITS
            plan = plan if plan in PLAN_LIMITS else TRIAL_WEEK_PLAN
            return end, end + week, plan, True
    # пилот/админ без строки подписки — обычная неделя с этого момента
    return now, now + week, TRIAL_WEEK_PLAN, True


def _remember_telegram(user, tg_id: str) -> None:
    """Привязать найденный Telegram к аккаунту, если он ничей (для входа и уведомлений)."""
    from models import User
    try:
        if getattr(user, 'telegram_id', None):
            return
        if User.query.filter_by(telegram_id=tg_id).first() is not None:
            return
        user.telegram_id = tg_id
        db.session.commit()
    except Exception as e:  # noqa: BLE001 — привязка не обязательна для выдачи
        log.warning('[tg_trial] remember telegram failed: %r', e)
        db.session.rollback()


def claim_week(user, tg_auth: Optional[dict] = None) -> dict:
    """Проверить подписку и выдать неделю. Возвращает {'expires_at': iso}."""
    from models_tg_trial import TgTrialGrant

    state = get_state(user)
    st = state['state']
    if st == 'hidden':
        if _role_blocked(user):
            raise TgTrialError('role', 'Неделя Premium оформляется в аккаунте ребёнка.', 403)
        raise TgTrialError('auth', 'Войди в аккаунт, чтобы получить неделю.', 403)
    if st == 'active':
        raise TgTrialError('already_active', 'Неделя Premium уже активна.', 409)
    if st == 'used':
        raise TgTrialError('used', 'Неделя за подписку уже была получена на этом аккаунте.', 409)

    if tg_auth:
        link_telegram(user, tg_auth)
    tg_id = _telegram_for(user)
    if not tg_id:
        raise TgTrialError('not_member',
                           'Пока не видим подписку. Нажми «Перейти в канал», подпишись и вернись сюда. '
                           'Если ты уже был подписан — нажми «Подтвердить через бота».', 400)
    _remember_telegram(user, tg_id)

    if TgTrialGrant.query.filter_by(telegram_id=tg_id).first() is not None:
        raise TgTrialError('tg_used', 'С этого Telegram неделя уже была получена на другом аккаунте.', 409)

    if not check_membership(tg_id):
        raise TgTrialError('not_member',
                           f'Пока не видим подписку на @{channel_username()}. '
                           'Подпишись на канал и нажми «Проверить» ещё раз.', 400)

    now = _now()
    starts, expires, plan, activate = _week_period(user, now)
    try:
        db.session.add(TgTrialGrant(user_id=user.id, telegram_id=tg_id,
                                    channel=channel_username(), granted_at=now, expires_at=expires))
        db.session.flush()   # уникальность: двойной клик / гонка → IntegrityError
    except IntegrityError:
        db.session.rollback()
        raise TgTrialError('used', 'Неделя за подписку уже получена.', 409)

    from services.subscription import get_subscription_service
    # activate_premium сам гасит текущий пробный день (superseded) и коммитит.
    if activate:
        get_subscription_service().activate_premium(
            user_id=user.id, plan=plan, is_beta=True, is_trial=True,
            starts_at=starts, expires_at=expires,
        )
    db.session.commit()
    _drop_cache()
    log.info('[tg_trial] user=%s tg=%s week granted until %s', user.id, tg_id, expires)
    # Сразу после выдачи сайт заставит выбрать 6 дней занятий (гейт /schedule):
    # говорим фронтенду, чтобы вёл туда сам, а не ждал редиректа посреди страницы.
    needs_schedule = True
    try:
        from services.schedule_days import days_for_plan, required_days_count
        needs_schedule = days_for_plan(user.id, plan) is None
        days_required = required_days_count(plan) or 6
    except Exception:  # noqa: BLE001
        days_required = 6
    return {'expires_at': expires.isoformat(sep=' '),
            'needs_schedule': needs_schedule, 'days_required': days_required}
