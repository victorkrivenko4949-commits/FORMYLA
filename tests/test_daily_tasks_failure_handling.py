# -*- coding: utf-8 -*-
"""End-to-end test of failure handling in /daily_tasks generation.

Simulates the OpenRouter HTTP 402 (credit limit) scenario that produced
"empty block, no error" in production. Verifies:

1. Pipeline propagates the REAL error (not generic "Gemini вернул 0 specs").
2. _persist_pipeline_result does NOT create zombie items with task_text=''.
3. DailyGenerationJob.error_message contains the classified error.
4. Failed sets don't count toward the 1-per-day regenerate limit.

Run: pytest tests/test_daily_tasks_failure_handling.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Ensure project root in sys.path BEFORE app imports.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@pytest.fixture()
def app_ctx():
    """Yield an app context for DB operations."""
    from app import app
    with app.app_context():
        yield app


@pytest.fixture()
def clean_today_set(app_ctx):
    """Ensure a test user (id=1) exists and wipe today's set/items/jobs.

    Tests run against the project's live SQLite DB (formyla.db) but CI may
    boot with an empty users table. We bootstrap user_id=1 so that
    ``dev_login`` succeeds (it calls ``User.query.get(1)``).
    """
    from models import db, User
    from daily_tasks.models import (
        DailyTaskSet, DailyTaskItem, DailyGenerationJob,
    )

    # ── ensure user_id=1 exists (required by dev_login + FK on daily_task_sets.user_id)
    user = User.query.get(1)
    if not user:
        user = User(id=1, email="test_user_1@formyla.local", name="TestUser")
        db.session.add(user)
        db.session.commit()

    today = date.today()
    DailyGenerationJob.query.filter_by(target_date=today).delete()
    set_ids = [
        s.id for s in DailyTaskSet.query.filter_by(target_date=today).all()
    ]
    if set_ids:
        DailyTaskItem.query.filter(
            DailyTaskItem.daily_set_id.in_(set_ids)
        ).delete(synchronize_session=False)
        DailyTaskSet.query.filter(
            DailyTaskSet.id.in_(set_ids)
        ).delete(synchronize_session=False)
    db.session.commit()
    yield
    # cleanup also after
    DailyGenerationJob.query.filter_by(target_date=today).delete()
    set_ids = [
        s.id for s in DailyTaskSet.query.filter_by(target_date=today).all()
    ]
    if set_ids:
        DailyTaskItem.query.filter(
            DailyTaskItem.daily_set_id.in_(set_ids)
        ).delete(synchronize_session=False)
        DailyTaskSet.query.filter(
            DailyTaskSet.id.in_(set_ids)
        ).delete(synchronize_session=False)
    db.session.commit()


# ──────────────────────────────────────────────────────────────────────


def test_classify_openrouter_402():
    """Sanity: 402 → 'http_402', 503 → 'http_503', 0 → 'network'."""
    from daily_tasks.pipeline.step1_gemini import _classify_openrouter_error
    from pipeline.openrouter_client import OpenRouterError
    assert _classify_openrouter_error(OpenRouterError("", status_code=402)) == "http_402"
    assert _classify_openrouter_error(OpenRouterError("", status_code=429)) == "http_429"
    assert _classify_openrouter_error(OpenRouterError("", status_code=503)) == "http_503"
    assert _classify_openrouter_error(OpenRouterError("", status_code=0)) == "network"


def test_gemini_plan_raises_classified_error_on_402():
    """When OpenRouter returns 402, step1 raises GeminiPlanError with
    category='http_402' and a human-readable message."""
    from daily_tasks.pipeline.step1_gemini import (
        generate_gemini_plan, GeminiPlanError,
    )
    from pipeline.openrouter_client import OpenRouterError

    profile = {
        "user_id": 1, "class_level": 9, "class_expected_level": 4,
        "weak_topics": [{"topic": "T1", "subject": "algebra"}],
        "strong_topics": [], "subject": "algebra",
    }

    fake_chat = AsyncMock(side_effect=OpenRouterError(
        "OpenRouter returned 402", status_code=402,
        body='{"error":{"message":"insufficient credits"}}',
    ))

    with patch("daily_tasks.pipeline.step1_gemini.OpenRouterClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.chat = fake_chat
        with pytest.raises(GeminiPlanError) as exc_info:
            asyncio.run(generate_gemini_plan(profile))

    err = exc_info.value
    assert err.category == "http_402"
    assert err.status_code == 402
    assert "402" in str(err) or "баланс" in str(err).lower()


def test_orchestrator_propagates_http_402_into_result_error():
    """run_daily_generation_pipeline catches GeminiPlanError and writes
    the classified human-readable message into result.error."""
    from daily_tasks.pipeline.orchestrator import (
        run_daily_generation_pipeline, PipelineResult,
    )
    from daily_tasks.pipeline.step1_gemini import GeminiPlanError

    profile = {
        "user_id": 1, "class_level": 9, "class_expected_level": 4,
        "weak_topics": [{"topic": "T1", "subject": "algebra"}],
        "strong_topics": [], "subject": "algebra",
    }

    err = GeminiPlanError(
        "Закончился баланс OpenRouter (HTTP 402). "
        "Пополни счёт на openrouter.ai/credits и попробуй снова.",
        category="http_402", status_code=402,
    )
    with patch(
        "daily_tasks.pipeline.orchestrator.generate_gemini_plan",
        new=AsyncMock(side_effect=err),
    ):
        result: PipelineResult = asyncio.run(run_daily_generation_pipeline(profile))

    assert result.success is False
    assert result.status == "failed"
    assert result.error is not None
    assert "402" in result.error or "баланс" in result.error.lower()
    # The OLD bug returned generic "Gemini вернул 0 specs". Must NOT appear.
    assert "вернул 0 specs" not in result.error
    assert "вернул 0 задач" not in result.error  # also not the new generic


def test_persist_does_not_create_zombie_items_on_failure(
    app_ctx, clean_today_set,
):
    """When pipeline returns status='failed', _persist_pipeline_result
    must NOT insert 10 empty DailyTaskItem rows with task_text=''."""
    from models import db
    from daily_tasks.models import (
        DailyTaskSet, DailyTaskItem, DailyGenerationJob,
    )
    from daily_tasks.pipeline.orchestrator import PipelineResult
    from daily_tasks.services import _persist_pipeline_result

    today = date.today()
    daily_set = DailyTaskSet(
        user_id=1, target_date=today, status="generating",
        triggered_by="test",
    )
    db.session.add(daily_set)
    db.session.flush()
    job = DailyGenerationJob(
        user_id=1, target_date=today, daily_set_id=daily_set.id,
        state="running",
    )
    db.session.add(job)
    db.session.commit()
    set_id = daily_set.id

    failure = PipelineResult(
        success=False, status="failed",
        error="Закончился баланс OpenRouter (HTTP 402). Пополни счёт.",
    )

    profile = {
        "user_id": 1, "class_level": 9, "class_expected_level": 4,
        "weak_topics": [], "strong_topics": [],
    }
    _persist_pipeline_result(
        daily_set_id=set_id, job_id=job.id,
        result=failure, profile=profile,
    )
    db.session.expire_all()

    items = DailyTaskItem.query.filter_by(daily_set_id=set_id).all()
    assert len(items) == 0, (
        f"Expected 0 items on failure, got {len(items)} "
        f"(task_texts: {[repr(it.task_text)[:30] for it in items]})"
    )
    s = DailyTaskSet.query.get(set_id)
    assert s.status == "failed"
    assert s.reason_summary and "402" in s.reason_summary


def test_regenerate_allows_retry_after_failed_set(app_ctx, clean_today_set):
    """Failed-сет НЕ должен срабатывать как «уже сгенерировано сегодня».

    Воспроизводит сценарий: пользователь нажал «Сгенерировать», получил
    ошибку 402 → status='failed'. Раньше следующий клик на «Повторить»
    давал 429 «Перегенерация доступна 1 раз в день». Теперь — пускает.

    Использует ``date.today()`` — это нормально потому что и фикстура,
    и endpoint (после TZ-фикса 543c510) читают одну и ту же дату через
    ``today_in_user_tz()`` (UTC+3 МСК) при стандартном времени сервера,
    либо обе даты сходятся при отсутствии TZ-фикса. Расхождение
    возможно только в полуночное окно UTC vs МСК, что не покрывается
    этим юнит-тестом (для этого есть отдельный live-сценарий).
    """
    from models import db
    from daily_tasks.models import DailyTaskSet
    from daily_tasks.services import today_in_user_tz
    from app import app

    # Используем ту же функцию, что и endpoint, чтобы фикстурные данные
    # совпадали с тем, что ищет /daily_tasks/regenerate.
    today = today_in_user_tz()

    # Имитируем уже существующий failed-сет от предыдущей попытки
    failed_set = DailyTaskSet(
        user_id=1, target_date=today, status="failed",
        triggered_by="manual",
    )
    db.session.add(failed_set)
    db.session.commit()

    with app.test_client() as c:
        # dev_login требует user_id=1 в БД — это гарантирует фикстура
        # clean_today_set. Проверяем что вход прошёл (302 redirect = success).
        login_rv = c.get('/dev_login')
        assert login_rv.status_code in (302, 200), (
            f"dev_login failed: {login_rv.status_code} {login_rv.get_data(as_text=True)[:200]}"
        )

        # Mock the heavy enqueue_daily_generation so we don't actually hit LLM
        with patch(
            "daily_tasks.routes.services.enqueue_daily_generation",
            return_value={
                "daily_set_id": 999, "job_id": 1, "status": "generating",
                "message": "ok",
            },
        ):
            rv = c.post('/daily_tasks/regenerate', json={})

    # Должно быть 202 Accepted, НЕ 429.
    assert rv.status_code == 202, (
        f"Got status {rv.status_code} body={rv.get_data(as_text=True)} — "
        "failed-сет ошибочно блокирует regenerate."
    )
