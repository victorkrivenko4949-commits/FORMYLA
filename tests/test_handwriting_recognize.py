# -*- coding: utf-8 -*-
"""
Tests for POST /api/handwriting/recognize and the frontend OCR module
that drives it.

Strategy:
    * Backend: patch `services.openrouter_client.openrouter.chat` so we
      never hit the network. Verify the endpoint correctly threads
      `text` through on success, returns ok=False on auth/network
      failure (without 5xx'ing), and rejects bad input.
    * Frontend: static checks that handwriting_ocr.js, the template
      include, the toolbar toggle integration and the WB hooks are all
      in place — exactly the kind of "did I forget to register the
      module" regressions we had on the previous feature.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ───────────────────────── Backend endpoint ───────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Spin up the Flask app with login disabled so tests don't need a user."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    # Re-import the app fresh so env vars take effect.
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module           # noqa: E402
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


# 1×1 transparent PNG (smallest valid image, plenty for the contract test).
_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_recognize_rejects_missing_image(client):
    rv = client.post("/api/handwriting/recognize", json={})
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["ok"] is False


def test_recognize_rejects_oversized_image(client):
    # ~2 MB of base64 — over the configured 1.5 MB cap.
    huge = "A" * (2 * 1024 * 1024)
    rv = client.post("/api/handwriting/recognize", json={"image": huge})
    assert rv.status_code == 413
    assert rv.get_json()["ok"] is False


def test_recognize_happy_path_returns_text(client):
    """OpenRouter returns clean JSON → endpoint forwards the text."""
    fake = {
        "content": json.dumps({"text": "привет"}),
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "cost_usd": 0.0,
        "model": "google/gemini-flash-1.5",
    }
    with patch("services.openrouter_client.openrouter.chat", return_value=fake):
        rv = client.post("/api/handwriting/recognize",
                         json={"image": "data:image/png;base64," + _TINY_PNG})
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["ok"] is True
    assert body["text"] == "привет"
    assert body["font"] == "Caveat"


def test_recognize_strips_markdown_fences(client):
    """Defensively unwrap ```json … ``` even if the model misbehaves."""
    fake = {
        "content": "```json\n{\"text\": \"теорема Пифагора\"}\n```",
        "usage": {},
        "cost_usd": 0.0,
        "model": "x/y",
    }
    with patch("services.openrouter_client.openrouter.chat", return_value=fake):
        rv = client.post("/api/handwriting/recognize",
                         json={"image": "data:image/png;base64," + _TINY_PNG})
    body = rv.get_json()
    assert body["ok"] is True
    assert "Пифагора" in body["text"]


def test_recognize_handles_plain_text_response(client):
    """If the model ignored the JSON instruction, we still accept short replies."""
    fake = {"content": "x + 1 = 2", "usage": {}, "cost_usd": 0.0, "model": "x/y"}
    with patch("services.openrouter_client.openrouter.chat", return_value=fake):
        rv = client.post("/api/handwriting/recognize",
                         json={"image": "data:image/png;base64," + _TINY_PNG})
    body = rv.get_json()
    assert body["ok"] is True
    assert body["text"] == "x + 1 = 2"


def test_recognize_soft_fails_on_network_error(client):
    """A vision-call exception must NOT 5xx — UI keeps strokes intact."""
    from services.openrouter_client import OpenRouterError
    with patch("services.openrouter_client.openrouter.chat",
               side_effect=OpenRouterError("boom")):
        rv = client.post("/api/handwriting/recognize",
                         json={"image": "data:image/png;base64," + _TINY_PNG})
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["ok"] is False
    assert body["text"] == ""
    assert "boom" in (body.get("error") or "")


def test_recognize_returns_empty_text_when_model_sees_nothing(client):
    """`{"text": ""}` from the model is a valid 'no-op, keep strokes'."""
    fake = {"content": json.dumps({"text": ""}), "usage": {}, "cost_usd": 0, "model": "x/y"}
    with patch("services.openrouter_client.openrouter.chat", return_value=fake):
        rv = client.post("/api/handwriting/recognize",
                         json={"image": "data:image/png;base64," + _TINY_PNG})
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["ok"] is True
    assert body["text"] == ""


def test_recognize_works_with_raw_base64_no_dataurl(client):
    """Frontend may pass either a full dataURL or bare base64."""
    fake = {"content": "{\"text\": \"hi\"}", "usage": {}, "cost_usd": 0, "model": "x/y"}
    with patch("services.openrouter_client.openrouter.chat", return_value=fake) as m:
        rv = client.post("/api/handwriting/recognize", json={"image": _TINY_PNG})
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True
    # Sanity: ensure the model was called with an image_url block.
    call_kwargs = m.call_args.kwargs
    msgs = call_kwargs.get("messages") or []
    user_msg = next((m for m in msgs if m.get("role") == "user"), None)
    assert user_msg, "user message missing"
    blocks = user_msg["content"] if isinstance(user_msg["content"], list) else []
    types = [b.get("type") for b in blocks]
    assert "image_url" in types


# ─────────────────────── Frontend static checks ───────────────────────


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_JS = os.path.join(ROOT, "static", "js", "board", "handwriting_ocr.js")
WB_JS = os.path.join(ROOT, "static", "js", "whiteboard.js")
WB_HTML = os.path.join(ROOT, "templates", "whiteboard.html")
BOARD_CSS = os.path.join(ROOT, "static", "css", "board.css")


def test_ocr_module_file_exists_with_public_api():
    assert os.path.exists(OCR_JS)
    txt = open(OCR_JS, encoding="utf-8").read()
    for token in [
        "FormylaHWOcr",
        "startSelection",
        "cancelSelection",
        "/api/handwriting/recognize",
        "replacePenStrokesWithHandwriting",
        "wbOcrRecognizeBtn",
        "hwocr-lasso",
        "Claude Opus",
    ]:
        assert token in txt, f"handwriting_ocr.js missing reference: {token}"


def test_whiteboard_template_loads_handwriting_ocr_js():
    txt = open(WB_HTML, encoding="utf-8").read()
    assert "handwriting_ocr.js" in txt
    # MUST load AFTER whiteboard.js so WB is ready.
    wb_idx = txt.index("whiteboard.js")
    ocr_idx = txt.index("handwriting_ocr.js")
    assert wb_idx < ocr_idx, "handwriting_ocr.js must load after whiteboard.js"


def test_whiteboard_js_exposes_replace_and_listener_apis():
    txt = open(WB_JS, encoding="utf-8").read()
    for token in [
        "replacePenStrokesWithHandwriting",
        "setPenStrokeListener",
        "_onPenStrokeFinished",
    ]:
        assert token in txt, f"whiteboard.js missing API: {token}"


def test_board_css_has_ocr_button_styles():
    txt = open(BOARD_CSS, encoding="utf-8").read()
    assert ".hwocr-btn" in txt
    assert ".hwocr-spinner" in txt
    assert ".hwocr-toast" in txt
    assert ".hwocr-lasso-overlay" in txt
    assert ".hwocr-lasso-rect" in txt
    assert ".hwocr-hint" in txt


def test_whiteboard_js_exposes_screen_to_world_helpers():
    txt = open(WB_JS, encoding="utf-8").read()
    assert "screenToWorld:" in txt, "WB.screenToWorld not exposed"
    assert "getCanvasEl:" in txt, "WB.getCanvasEl not exposed"


# ────────────────── _delatex unit tests ───────────────────────────────


def test_delatex_strips_dollar_delimiters():
    from routes.handwriting import _delatex
    assert _delatex("$x+1$") == "x+1"
    assert _delatex("$$y=2$$") == "y=2"


def test_delatex_converts_sqrt_to_unicode():
    from routes.handwriting import _delatex
    assert _delatex(r"\sqrt{2x}") == "√2x"
    assert _delatex(r"$\sqrt{2x}$") == "√2x"


def test_delatex_converts_frac():
    from routes.handwriting import _delatex
    assert _delatex(r"\frac{a+1}{b}") == "(a+1)/(b)"


def test_delatex_converts_superscripts():
    from routes.handwriting import _delatex
    assert _delatex(r"x^{2}") == "x²"
    assert _delatex(r"x^2") == "x²"
    # The translator handles letters + digits + operators as superscripts
    # when each character has a unicode equivalent — that's better than
    # the original `x^(n+1)` fallback because it reads more naturally.
    assert _delatex(r"x^{n+1}") == "xⁿ⁺¹"


def test_delatex_converts_greek_letters():
    from routes.handwriting import _delatex
    assert _delatex(r"\alpha + \beta") == "α + β"
    # Note: `\pi r^2` keeps a space because LaTeX cmd boundaries always
    # produced one. That's intentional — readability over compactness.
    assert _delatex(r"$\pi r^2$") == "π r²"


def test_delatex_idempotent_on_plain_text():
    from routes.handwriting import _delatex
    plain = "привет, как дела? 42 + 1 = 43"
    assert _delatex(plain) == plain
    assert _delatex(_delatex(plain)) == plain


def test_delatex_strips_leftover_braces_and_backslashes():
    from routes.handwriting import _delatex
    assert "{" not in _delatex(r"\unknown{thing}")
    assert "}" not in _delatex(r"\unknown{thing}")
    assert "\\" not in _delatex(r"\unknown{thing}")
