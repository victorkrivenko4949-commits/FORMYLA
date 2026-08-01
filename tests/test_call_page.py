# -*- coding: utf-8 -*-
"""Smoke-tests for the video-call lobby page.

Цель: гарантировать, что:
  * GET /call возвращает 200 (а не 404 — как было до фикса).
  * В ответе действительно отрендерен шаблон call.html (видны опорные тексты).
  * Blueprint /api/wb_call/* зарегистрирован и его endpoints не дают 404.

Со времени P13 /call стал @login_required — тесты теперь входят в аккаунт
перед обращением к странице.

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


def _ensure_user_1_and_login(client):
    """Создать user #1 в БД (если нет) и войти через сессию."""
    from app import app  # noqa: WPS433
    from models import db, User  # noqa: WPS433

    with app.app_context():
        u = db.session.get(User, 1)
        if u is None:
            u = User(
                id=1,
                email='test1@test.ru',
                name='Test User 1',
                preferred_grade=9,
                is_guest=False,
            )
            db.session.add(u)
            db.session.commit()
        else:
            # Пользователь уже существует — убедимся что не гость
            if u.is_guest:
                u.is_guest = False
                db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True


def test_call_page_returns_200(client):
    """GET /call должен отдавать 200 OK после входа (P13: @login_required)."""
    _ensure_user_1_and_login(client)

    resp = client.get("/call")
    assert resp.status_code == 200, (
        "GET /call вернул "
        + str(resp.status_code)
        + " — страница лобби видеозвонка должна быть 200 после входа."
    )


def test_call_page_renders_lobby(client):
    """В HTML должны быть опорные тексты страницы лобби."""
    _ensure_user_1_and_login(client)

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
