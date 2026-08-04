# -*- coding: utf-8 -*-
"""
services/parent_teacher_helpers.py — T10 helpers: invite code, streak wrapper.

DO NOT duplicate display_name_from_email from services/user_helpers.py;
import it from there.  This module provides:

- generate_invite_code() — 6-char code without O,0,I,1
- student_streak(user_id) — wraps T8 streak_service, returns current_streak
"""
from __future__ import annotations

import random
import string
from typing import Optional

from models import db, T10Group
from services.streak_service import get_or_create_streak

# Characters allowed in invite codes — no O, 0, I, 1 to avoid confusion.
_INVITE_ALPHABET = ''.join(
    c for c in string.ascii_uppercase + string.digits
    if c not in ('O', '0', 'I', '1')
)


def generate_invite_code() -> str:
    """Generate a unique 6-character invite code.

    Checks uniqueness against the ``groups`` table and retries on collision.
    """
    for _ in range(20):  # safety cap
        code = ''.join(random.choices(_INVITE_ALPHABET, k=6))
        if not T10Group.query.filter_by(invite_code=code).first():
            return code
    raise RuntimeError('Failed to generate a unique invite code after 20 attempts')


def student_streak(user_id: int) -> int:
    """Return the current daily streak for *user_id*.

    Wraps ``get_or_create_streak`` from T8's ``services/streak_service.py``.
    Returns 0 when no streak record exists yet.
    """
    rec = get_or_create_streak(user_id)
    return rec.current_streak or 0
