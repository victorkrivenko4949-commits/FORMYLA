# -*- coding: utf-8 -*-
"""Smoke-tests for the public video-call lobby page.

Цель: гарантировать, что:
  * GET /call возвращает 200 (а не 404 — как было до фикса).
  * В ответе действительно отрендерен шаблон call.html (видны опорные тексты).
  * Blueprint /api/wb_call/* зарегистрирован и его endpoints не дают 404.

Эти тесты — страховка от повторения регрессии «404 на /call»: если кто-то
снесёт роут или забудет templates/call.html, CI завалится здесь, а не в проде.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def client():
    from app import app  # noqa: WPS433 - intentional late import

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


def test_call_page_returns_200(client):
    """GET /call должен отдавать 200 OK (страница лобби видеозвонка)."""
    resp = client.get("/call")
    assert resp.status_code == 200, (
        "GET /call вернул "
        + str(resp.status_code)
        + " — публичная страница лобби видеозвонка должна быть 200."
    )


def test_call_page_renders_lobby(client):
    """В HTML должны быть опорные тексты страницы лобби."""
    resp = client.get("/call")
    body = resp.get_data(as_text=True)
    # Проверяем по нескольким независимым маркерам, чтобы тест не ломался
    # от мелкой косметической правки одной строки.
    markers = [
        "callLobby",          # id главной секции лобби
        "btnCreateRoom",      # id кнопки «создать комнату»
        "joinCodeInput",      # id поля ввода кода
        "/api/wb_call/",      # ссылка на backend-сигналинг
    ]
    missing = [m for m in markers if m not in body]
    assert not missing, "В /call отсутствуют ожидаемые маркеры: " + ", ".join(missing)


def test_wb_call_blueprint_is_registered(client):
    """API blueprint /api/wb_call/* должен существовать (не 404)."""
    # POST без тела — обычно отдаёт 400/415, но НЕ 404. Главное — endpoint найден.
    resp = client.post("/api/wb_call/join", json={})
    assert resp.status_code != 404, (
        "POST /api/wb_call/join вернул 404 — blueprint wb_call_bp не зарегистрирован."
    )
