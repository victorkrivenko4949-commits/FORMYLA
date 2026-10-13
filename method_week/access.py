# -*- coding: utf-8 -*-
"""Кому показывать «Метод недели» и план куратора (тестовый период).

METHOD_WEEK_ALLOWED_USERS — список через запятую, по умолчанию «lavrik,victor»
(как PWA_ALLOWED_USERS в routes/pwa.py). Сравнение без учёта регистра по
nickname, username, telegram_username, name и локальной части e-mail.
Открыть всем: METHOD_WEEK_ALLOWED_USERS=*
"""
from __future__ import annotations

import os

DEFAULT_ALLOWED = 'lavrik,victor'


def allowed_users() -> set:
    raw = os.environ.get('METHOD_WEEK_ALLOWED_USERS', DEFAULT_ALLOWED)
    return {p.strip().lower() for p in raw.split(',') if p.strip()}


def user_allowed(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    allowed = allowed_users()
    if '*' in allowed:
        return True
    idents = set()
    for attr in ('nickname', 'username', 'telegram_username', 'name'):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            idents.add(v.strip().lower())
    email = getattr(user, 'email', None)
    if isinstance(email, str) and email.strip():
        idents.add(email.strip().lower())
        idents.add(email.strip().lower().split('@', 1)[0])
    return bool(idents & allowed)
