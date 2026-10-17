# -*- coding: utf-8 -*-
"""AB_V1 — когорта мягких лимитов. in_limits_cohort(user): user_id % 100 < PAYWALL_AB.

PAYWALL_AB=0  — лимиты ни у кого (контроль 100%)
PAYWALL_AB=50 — лимиты у половины (план на 1–11 ноября)
PAYWALL_AB=100 — у всех (после решения 11.11)
Когорта детерминированная: один и тот же пользователь всегда в одной группе.
"""
from __future__ import annotations

import os


def ab_percent() -> int:
    try:
        return max(0, min(100, int(os.environ.get('PAYWALL_AB', '0') or 0)))
    except ValueError:
        return 0


def cohort_of(user_id: int | None) -> int:
    """1 — в когорте лимитов, 0 — контроль."""
    if not user_id:
        return 0
    return 1 if (int(user_id) % 100) < ab_percent() else 0


def in_limits_cohort(user) -> bool:
    return cohort_of(getattr(user, 'id', None)) == 1
