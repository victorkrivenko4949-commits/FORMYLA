# -*- coding: utf-8 -*-
"""Фото в обычном чате ИИ-тьютора (/api/tutor/send, check_solution=false).

Фото читается общей цепочкой services.solution_ocr (DeepSeek первым).
Надёжный текст уходит тьютору вместо фото; ненадёжный — вместе с фото.
Сеть не трогаем: движки распознавания и ответ тьютора подменены.
"""

import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
_KEEP = []
_GOOD ="x^2 - 5x + 6 = 0, D = 25 - 24 = 1, x_1 = 3, x_2 = 2. Ответ: 2; 3"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tutor.db'}")
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-only-tutor-photo-ocr")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    if "app" in sys.modules:
        del sys.modules["app"]
    # Импорт app (через миграции) подменяет sys.stdout на TextIOWrapper поверх
    # буфера pytest; при сборке мусора он закрывает этот буфер. Держим ссылку
    # и возвращаем исходные потоки.
    _out, _err = sys.stdout, sys.stderr
    import app as app_module
    _KEEP.extend([sys.stdout, sys.stderr])
    sys.stdout, sys.stderr = _out, _err
    from ai.deepseek_client import DeepSeekClient
    from models import db, User
    from services import solution_ocr as so

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    calls = []
    answers = {"deepseek": None, "gemini": None, "tesseract": None, "novita": None}

    def make(name):
        def _fn(*_a, **_k):
            calls.append(name)
            return answers[name]
        return _fn

    monkeypatch.setattr(so, "_ocr_deepseek_vision", make("deepseek"))
    monkeypatch.setattr(so, "_ocr_gemini_vision", make("gemini"))
    monkeypatch.setattr(so, "_ocr_tesseract", make("tesseract"))
    monkeypatch.setattr(so, "_ocr_novita_vision", make("novita"))
    monkeypatch.setattr(so, "_ocr_openrouter_gemini", make("openrouter"))

    sent = {}

    def _chat(self, user, message, history, agent_type="general", hint_mode=True, image_data=None):
        sent.update(message=message, image_data=image_data)
        return "ответ тьютора"

    monkeypatch.setattr(DeepSeekClient, "chat_with_tutor", _chat)

    with flask_app.app_context():
        db.create_all()
        u = User.query.filter_by(email="tutor-ocr@test.local").first()
        if not u:
            u = User(email="tutor-ocr@test.local", name="Тест")
            db.session.add(u)
            db.session.commit()
        uid = u.id
        # анкета пройдена — иначе before_request уводит на /intake/
        import json
        from models_curator import CuratorState
        if not CuratorState.query.filter_by(user_id=uid).first():
            db.session.add(CuratorState(
                user_id=uid, prep_state=json.dumps({"intake": {"completed": True}}),
            ))
            db.session.commit()

    client = flask_app.test_client()
    with client.session_transaction() as s:
        s["_user_id"] = str(uid)
        s["_fresh"] = True
    return client, calls, answers, sent


def _send(client, n_photos=1, message=""):
    data = {"message": message, "agent_type": "general", "hint_mode": "true", "check_solution": "false"}
    data["files"] = [(io.BytesIO(_PNG), f"p{i}.png", "image/png") for i in range(n_photos)]
    return client.post("/api/tutor/send", data=data, content_type="multipart/form-data")


def test_deepseek_text_replaces_photo(env):
    client, calls, answers, sent = env
    answers["deepseek"] = _GOOD
    rv = _send(client, message="помоги")
    assert rv.status_code == 200, rv.get_data(as_text=True)
    assert calls == ["deepseek"]
    assert "25 - 24" in sent["message"]
    assert "помоги" in sent["message"]
    assert sent["image_data"] is None


def test_all_photos_are_recognized(env):
    client, calls, answers, _ = env
    answers["deepseek"] = _GOOD
    rv = _send(client, n_photos=3)
    assert rv.status_code == 200
    assert calls == ["deepseek"] * 3


def test_tesseract_garbage_keeps_photo_attached(env):
    client, calls, answers, sent = env
    answers["tesseract"] = "x2 - 5Х + @ = 0 Da 292а 4 Oreeti v= Zk = 3 и ещё текст"
    rv = _send(client)
    assert rv.status_code == 200
    assert "openrouter" not in calls
    assert sent["image_data"]  # фото не выброшено — vision-модель сверит сама


def test_nothing_recognized_sends_photo_to_vision(env):
    client, calls, _, sent = env
    rv = _send(client)
    assert rv.status_code == 200
    assert calls == ["deepseek", "gemini", "tesseract", "novita"]
    assert sent["image_data"]
