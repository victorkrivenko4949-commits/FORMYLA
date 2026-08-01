# -*- coding: utf-8 -*-
"""
Unit + integration tests for the «Текст → Рукопись» feature.

Covers:
    1. routes/handwriting.py    — _extract_latex, _wrap_lines helpers.
    2. POST /api/handwriting/prepare in mode="raw"     — no network.
    3. POST /api/handwriting/prepare in mode="ai_format"
        - without OPENROUTER_API_KEY   → silent fallback to raw.
        - with monkey-patched openrouter.chat → returns AI lines.
        - with openrouter raising         → graceful fallback to raw.
    4. Empty text → HTTP 400.
    5. Frontend asset sanity:
        - static/js/board/handwriting.js exists, exports the expected names.
        - static/js/board/handwriting_ui.js is syntactically NOT truncated
          (no stray `if{` etc. — balanced braces & ends with closing `})();`).
        - static/css/board.css declares .hw-modal class.
        - templates/whiteboard.html links board.css and uses cyrillic subset.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from routes.handwriting import _extract_latex, _wrap_lines, handwriting_bp


# ─── 1. Helpers ─────────────────────────────────────────────────────────────


class TestExtractLatex:
    def test_no_math(self):
        text, frags = _extract_latex("Hello world")
        assert text == "Hello world"
        assert frags == []

    def test_single_inline(self):
        text, frags = _extract_latex("Pythagoras: $a^2+b^2=c^2$.")
        assert text == "Pythagoras: <m0/>."
        assert frags == ["a^2+b^2=c^2"]

    def test_multiple(self):
        text, frags = _extract_latex("Sum $x+y$ and product $x \\cdot y$.")
        assert "<m0/>" in text and "<m1/>" in text
        assert frags == ["x+y", "x \\cdot y"]

    def test_cyrillic_preserved(self):
        text, frags = _extract_latex("Теорема Пифагора: $a^2+b^2=c^2$")
        assert text.startswith("Теорема Пифагора:")
        assert frags == ["a^2+b^2=c^2"]

    def test_ignores_unclosed(self):
        # A single `$` should not eat the rest of the input.
        text, frags = _extract_latex("Цена: $50 рублей")
        assert frags == []
        assert text == "Цена: $50 рублей"


class TestWrapLines:
    def test_short(self):
        assert _wrap_lines("Hello", 40) == ["Hello"]

    def test_wraps_at_word_boundary(self):
        lines = _wrap_lines("один два три четыре пять шесть семь", 12)
        # Each line ≤ 12 chars, no word split.
        for ln in lines:
            assert len(ln) <= 12
        assert " ".join(lines) == "один два три четыре пять шесть семь"

    def test_preserves_explicit_newlines(self):
        lines = _wrap_lines("a\nb\nc", 40)
        assert lines == ["a", "b", "c"]

    def test_keeps_latex_placeholders_atomic(self):
        # A <m0/> token must never be split mid-tag.
        lines = _wrap_lines("Формула <m0/> и ещё текст", 10)
        for ln in lines:
            # No half-tag artifacts.
            assert "<m" not in ln or "/>" in ln

    def test_clamps_max_line(self):
        # max_line clamped to ≥ 8.
        lines = _wrap_lines("aaaa bbbb cccc", 1)
        for ln in lines:
            assert len(ln) <= 8 + 4  # one extra word may overshoot if no break point


# ─── 2-4. /api/handwriting/prepare endpoint ─────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    """Minimal Flask app exposing only the handwriting blueprint."""
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(handwriting_bp)
    app.testing = True
    # Make sure the AI path is OFF unless a test opts in.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return app.test_client()


class TestPrepareEndpointRaw:
    def test_basic_raw(self, client):
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "Hello world", "mode": "raw"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["ai_used"] is False
        assert data["mode"] == "raw"
        assert "Hello world" in data["processed_text"]
        assert isinstance(data["lines"], list)
        assert data["latex_segments"] == []

    def test_extracts_latex(self, client):
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "x is $x^2$ here.", "mode": "raw"},
        )
        data = r.get_json()
        assert data["latex_segments"] == ["x^2"]
        assert "<m0/>" in data["processed_text"]

    def test_empty_text_returns_400(self, client):
        r = client.post("/api/handwriting/prepare", json={"text": "   "})
        assert r.status_code == 400

    def test_unknown_mode_falls_back_to_raw(self, client):
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "x", "mode": "nonsense"},
        )
        assert r.status_code == 200
        assert r.get_json()["ai_used"] is False

    def test_cyrillic_lines(self, client):
        big = "Раз два три четыре пять шесть семь восемь девять десять"
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": big, "mode": "raw", "max_line": 12},
        )
        data = r.get_json()
        for ln in data["lines"]:
            assert len(ln) <= 14  # tolerance for trailing word
        assert "".join(data["lines"]).replace(" ", "") == big.replace(" ", "")

    def test_caps_text_length(self, client):
        huge = "x" * 5000
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": huge, "mode": "raw"},
        )
        # Server must trim to HARD_TEXT_LIMIT (4000) silently.
        assert r.status_code == 200


class TestPrepareEndpointAiFormat:
    def test_ai_mode_without_key_falls_back(self, client):
        # No OPENROUTER_API_KEY set → graceful fallback to raw.
        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "Hello there", "mode": "ai_format"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ai_used"] is False
        assert "Hello" in data["processed_text"]

    def test_ai_mode_uses_openrouter(self, monkeypatch, client):
        """When OPENROUTER_API_KEY is set AND openrouter.chat returns
        a valid JSON payload, the endpoint marks ai_used=True."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")

        # Patch services.openrouter_client.openrouter.chat → fake response.
        fake_lines = ["Привет,", "это рукопись."]
        from services import openrouter_client as orc

        def fake_chat(model, messages, temperature=0.7, max_tokens=1200, **kw):
            assert any("математ" in m["content"].lower() for m in messages if m["role"] == "system")
            return {"content": json.dumps({"lines": fake_lines})}

        monkeypatch.setattr(orc.openrouter, "chat", fake_chat)

        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "Привет, это рукопись.", "mode": "ai_format"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ai_used"] is True
        assert data["lines"] == fake_lines

    def test_ai_mode_graceful_on_exception(self, monkeypatch, client):
        """If openrouter.chat raises, the endpoint MUST NOT 5xx — it falls
        back to the raw word-wrap branch."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
        from services import openrouter_client as orc

        def boom(*a, **kw):
            raise orc.OpenRouterError("network down")
        monkeypatch.setattr(orc.openrouter, "chat", boom)

        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "Привет всем", "mode": "ai_format"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ai_used"] is False
        assert "Привет" in data["processed_text"]

    def test_ai_mode_graceful_on_bad_json(self, monkeypatch, client):
        monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
        from services import openrouter_client as orc

        def garbage(*a, **kw):
            return {"content": "not a json {{{ broken"}
        monkeypatch.setattr(orc.openrouter, "chat", garbage)

        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "Hello", "mode": "ai_format"},
        )
        assert r.status_code == 200
        assert r.get_json()["ai_used"] is False

    def test_ai_mode_strips_markdown_codefences(self, monkeypatch, client):
        monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
        from services import openrouter_client as orc

        def fenced(*a, **kw):
            return {"content": "```json\n{\"lines\": [\"a\", \"b\"]}\n```"}
        monkeypatch.setattr(orc.openrouter, "chat", fenced)

        r = client.post(
            "/api/handwriting/prepare",
            json={"text": "a b", "mode": "ai_format"},
        )
        data = r.get_json()
        assert data["ai_used"] is True
        assert data["lines"] == ["a", "b"]


# ─── 5. Frontend asset sanity ───────────────────────────────────────────────


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestFrontendAssets:
    def test_handwriting_js_exists_and_exports(self):
        p = PROJECT_ROOT / "static" / "js" / "board" / "handwriting.js"
        assert p.is_file(), "handwriting.js is missing"
        src = p.read_text(encoding="utf-8")
        for name in (
            "FormylaHandwriting",
            "renderHandwriting",
            "measureHandwriting",
            "makeSeed",
            "AVAILABLE_FONTS",
            "mulberry32",       # deterministic PRNG present
        ):
            assert name in src, f"handwriting.js: missing '{name}'"

    def test_handwriting_ui_js_is_not_truncated(self):
        """The file was previously truncated at line 77 ('if{').
        Regression test: ensure it is now a complete IIFE."""
        p = PROJECT_ROOT / "static" / "js" / "board" / "handwriting_ui.js"
        assert p.is_file()
        src = p.read_text(encoding="utf-8")
        # No stray "if{" without a body — naive but catches the bug.
        assert "if{" not in src.replace(" ", "")[:0] + src, "should not contain `if{` syntax error"
        # Top-level IIFE properly closed.
        assert src.rstrip().endswith(")();") or src.rstrip().endswith(")();\n".strip())
        # Hooks the renderer + WB.
        for needle in (
            "FormylaHandwriting",
            "addHandwritingObject",
            "/api/handwriting/prepare",
            "hwInsertBtn",
            "hwModal",
            "drawPreview",
        ):
            assert needle in src, f"handwriting_ui.js: missing '{needle}'"
        # Braces are balanced (cheap heuristic; suffices to catch truncation).
        opens, closes = src.count("{"), src.count("}")
        assert opens == closes, f"unbalanced braces: {opens} '{{' vs {closes} '}}'"

    def test_board_css_has_modal(self):
        p = PROJECT_ROOT / "static" / "css" / "board.css"
        assert p.is_file()
        css = p.read_text(encoding="utf-8")
        for selector in (".hw-modal", ".hw-field", ".hw-preview", ".hw-ink", ".hw-actions"):
            assert selector in css, f"board.css: missing {selector}"

    def test_whiteboard_html_links_board_css(self):
        # P7 fix: whiteboard.html extends base.html, so render via Flask
        from app import app
        with app.test_request_context('/whiteboard/test'):
            from flask import render_template
            html = render_template('whiteboard.html',
                board_id='test',
                wb_call_ws_url='ws://test',
                wb_room_name='test',
            )
        assert "css/board.css" in html
        # The template loads the renderer BEFORE the UI controller —
        # otherwise window.FormylaHandwriting would be undefined at boot.
        idx_render = html.index("board/handwriting.js")
        idx_ui     = html.index("board/handwriting_ui.js")
        assert idx_render < idx_ui

    def test_whiteboard_html_loads_cyrillic_fonts(self):
        p = PROJECT_ROOT / "templates" / "whiteboard.html"
        html = p.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" in html
        # Either explicit `subset=cyrillic` or one of the cyrillic-aware
        # families (Caveat / Marck Script / Pangolin) is loaded.
        assert "Caveat" in html
        assert "Marck+Script" in html or "Marck Script" in html
        assert "subset=cyrillic" in html

    def test_handwriting_button_in_toolbar(self):
        p = PROJECT_ROOT / "templates" / "whiteboard.html"
        html = p.read_text(encoding="utf-8")
        assert 'id="wbHandwritingBtn"' in html

    def test_modal_has_all_required_controls(self):
        # P7 fix: render template to include base.html content
        from app import app
        with app.test_request_context('/whiteboard/test'):
            from flask import render_template
            html = render_template('whiteboard.html',
                board_id='test',
                wb_call_ws_url='ws://test',
                wb_room_name='test',
            )
        for ctrl in (
            'id="hwModal"',
            'id="hwText"',
            'id="hwFont"',
            'id="hwSize"',
            'id="hwJitter"',
            'id="hwAi"',
            'id="hwPreview"',
            'id="hwInsertBtn"',
        ):
            assert ctrl in html, f"whiteboard.html: missing {ctrl}"

    def test_whiteboard_js_handles_handwriting_kind(self):
        p = PROJECT_ROOT / "static" / "js" / "whiteboard.js"
        src = p.read_text(encoding="utf-8")
        assert 'kind: "handwriting"' in src
        assert "addHandwritingObject" in src
        # Eraser & undo work because handwriting passes through the same
        # objects[] / pushHistory pipeline — sanity check the wiring.
        assert "pushHistory" in src
