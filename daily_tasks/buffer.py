# -*- coding: utf-8 -*-
"""
daily_tasks/buffer.py -- Daily task buffer for 3-day-ahead stock.

Provides ``ensure_daily_buffer(user_id, days_ahead=3)`` that checks
DailyTaskSet existence for upcoming days and triggers generation for
missing ones using the existing pipeline in ``daily_tasks/services.py``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from models import db
from daily_tasks.models import DailyTaskSet, DailyTaskItem, DailyGenerationJob
from daily_tasks.services import (
    today_in_user_tz,
    generate_daily_set,
    AI_GENERATION_ENABLED,
)

logger = logging.getLogger(__name__)


def ensure_daily_buffer(
    user_id: int,
    days_ahead: int = 3,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensure DailyTaskSet records exist for the next ``days_ahead`` days.

    For each day from today to today+days_ahead-1:
    - If a ready/generating set exists  -> ``already_exists``
    - If a failed set exists            -> delete it and recreate
    - If no set exists                  -> create and launch pipeline
    - If the pipeline cannot generate   -> ``empty_pool`` with reason

    Idempotent: second call for the same user+date range does NOT create
    duplicate records.  Uniqueness is enforced by the DB-level constraint
    ``_daily_set_user_date_uc`` on (user_id, target_date) at
    [`daily_tasks/models.py`](daily_tasks/models.py:46-48).

    Parameters
    ----------
    user_id : int
        User ID.
    days_ahead : int
        Number of days ahead to fill (default 3: today, +1, +2).
    profile : dict or None
        Optional pre-built profile.  If None, the pipeline builds its own.

    Returns
    -------
    dict
        {
            "status": "ok" | "partial" | "empty_pool",
            "days": {
                "<iso-date>": {
                    "status": "created" | "already_exists" | "empty_pool" | "error",
                    "daily_set_id": int or None,
                    "reason": str or None,
                },
                ...
            },
            "pipeline_calls": int,
        }
    """
    if not AI_GENERATION_ENABLED:
        logger.info("ensure_daily_buffer: AI-генерация отключена, пропускаем user=%d", user_id)
        return {"status": "disabled", "days": {}, "pipeline_calls": 0}

    today = today_in_user_tz()
    days_result: Dict[str, Dict[str, Any]] = {}
    pipeline_calls = 0
    any_created = False
    any_empty = False

    for offset in range(days_ahead):
        target = today + timedelta(days=offset)
        key = target.isoformat()

        # -- 1. Check existing set ---------------------------------------
        existing = DailyTaskSet.query.filter_by(
            user_id=user_id,
            target_date=target,
        ).first()

        if existing and existing.status in ("ready", "generating"):
            days_result[key] = {
                "status": "already_exists",
                "daily_set_id": existing.id,
                "reason": f"Set #{existing.id} status={existing.status}",
            }
            logger.debug(
                "Buffer day=%s user=%d: already exists set=#%d status=%s",
                key, user_id, existing.id, existing.status,
            )
            continue

        if existing and existing.status == "failed":
            logger.info(
                "Buffer day=%s user=%d: deleting failed set #%d",
                key, user_id, existing.id,
            )
            db.session.delete(existing)
            db.session.flush()

        # -- 2. Try to generate via existing pipeline --------------------
        try:
            result = generate_daily_set(
                user_id=user_id,
                target_date=target,
                triggered_by="buffer",
                profile=profile,
            )
            pipeline_calls += 1

            if result.get("status") == "empty_pool":
                days_result[key] = {
                    "status": "empty_pool",
                    "daily_set_id": None,
                    "reason": result.get("reason", "No tasks available"),
                }
                any_empty = True
                logger.warning(
                    "Buffer day=%s user=%d: empty_pool -- %s",
                    key, user_id, result.get("reason", ""),
                )
            elif result.get("status") == "error":
                days_result[key] = {
                    "status": "error",
                    "daily_set_id": None,
                    "reason": result.get("message", "Unknown error"),
                }
                logger.error(
                    "Buffer day=%s user=%d: error -- %s",
                    key, user_id, result.get("message", ""),
                )
            else:
                days_result[key] = {
                    "status": "created",
                    "daily_set_id": result.get("daily_set_id"),
                    "reason": f"Set #{result.get('daily_set_id')} generating",
                }
                any_created = True
                logger.info(
                    "Buffer day=%s user=%d: created set=#%s",
                    key, user_id, result.get("daily_set_id"),
                )
        except Exception as exc:
            days_result[key] = {
                "status": "error",
                "daily_set_id": None,
                "reason": str(exc),
            }
            logger.exception(
                "Buffer day=%s user=%d: exception -- %s",
                key, user_id, exc,
            )

    # -- 3. Determine overall status ------------------------------------
    if not any_created and not any_empty:
        overall = "ok"  # all already_exists
    elif any_empty and not any_created:
        overall = "empty_pool"
    else:
        overall = "partial"

    return {
        "status": overall,
        "days": days_result,
        "pipeline_calls": pipeline_calls,
    }
