# -*- coding: utf-8 -*-
"""Цепочка распознавания фото решений (задачи дня / срезы).

Порядок: DeepSeek vision -> Gemini через OdiRouter -> Tesseract -> Novita.
OpenRouter в цепочке не участвует. Сеть не трогаем: движки подменяются.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services import solution_ocr as so  # noqa: E402

# 1×1 PNG — содержимое не важно, движки подменены.
_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
_TEXT = "x^2 - 5x + 6 = 0, D = 25 - 24 = 1, x = 2, x = 3"


@pytest.fixture()
def engines(monkeypatch):
    """Подменяет все движки; возвращает журнал вызовов и словарь ответов."""
    calls = []
    answers = {"deepseek": None, "gemini": None, "tesseract": None, "novita": None}

    def make(name):
        def _fn(*_a, **_k):
            calls.append(name)
            return answers[name]
        return _fn

    def _openrouter(*_a, **_k):
        calls.append("openrouter")
        return "OPENROUTER MUST NOT BE USED"

    monkeypatch.setattr(so, "_ocr_deepseek_vision", make("deepseek"))
    monkeypatch.setattr(so, "_ocr_gemini_vision", make("gemini"))
    monkeypatch.setattr(so, "_ocr_tesseract", make("tesseract"))
    monkeypatch.setattr(so, "_ocr_novita_vision", make("novita"))
    monkeypatch.setattr(so, "_ocr_openrouter_gemini", _openrouter)
    return calls, answers


def test_deepseek_is_primary(engines):
    calls, answers = engines
    answers["deepseek"] = _TEXT
    res = so.ocr_solution_images([_PNG], "Решите уравнение")
    assert calls == ["deepseek"]
    assert res["engine"] == "deepseek_vision"
    assert "x = 2" in res["text"]
    assert res["low_confidence"] is False


def test_fallback_goes_to_odirouter_gemini_not_openrouter(engines):
    calls, answers = engines
    answers["gemini"] = _TEXT
    res = so.ocr_solution_images([_PNG])
    assert calls == ["deepseek", "gemini"]
    assert "openrouter" not in calls
    assert res["engine"] == "gemini_vision"


def test_full_fallback_order(engines):
    calls, answers = engines
    answers["novita"] = _TEXT
    res = so.ocr_solution_images([_PNG])
    assert calls == ["deepseek", "gemini", "tesseract", "novita"]
    assert res["engine"] == "novita_vision"


def test_tesseract_result_is_never_trusted(engines):
    calls, answers = engines
    answers["tesseract"] = "x2 - 5Х + @ = 0 Da 292а 4 Oreeti v= Zk = 3 и ещё текст"
    res = so.ocr_solution_images([_PNG])
    assert res["engine"] == "tesseract"
    assert res["low_confidence"] is True


def test_all_engines_fail(engines):
    calls, _ = engines
    res = so.ocr_solution_images([_PNG])
    assert "openrouter" not in calls
    assert res["engine"] == "none"
    assert res["text"] == ""
    assert res["low_confidence"] is True


def test_each_photo_recognized_separately(engines):
    calls, answers = engines
    answers["deepseek"] = _TEXT
    res = so.ocr_solution_images([_PNG, _PNG, _PNG])
    assert calls == ["deepseek"] * 3
    assert res["parts"] == 3


def test_no_photos_calls_nothing(engines):
    calls, _ = engines
    res = so.ocr_solution_images([])
    assert calls == []
    assert res["parts"] == 0


# ── Куда реально уходят запросы ─────────────────────────────────────────


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_deepseek_vision_calls_deepseek_api(monkeypatch):
    import requests
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, model=json["model"], auth=headers["Authorization"])
        return _Resp(_TEXT)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.delenv("DEEPSEEK_VISION_MODEL", raising=False)
    monkeypatch.setattr(requests, "post", _post)
    assert so._ocr_deepseek_vision(_PNG, "") == _TEXT
    assert seen["url"].startswith("https://api.deepseek.com/")
    assert seen["model"] == "deepseek-v4-flash-vision-exp"
    assert seen["auth"] == "Bearer ds-test"


def test_gemini_vision_calls_odirouter(monkeypatch):
    import requests
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, model=json["model"], auth=headers["Authorization"])
        return _Resp(_TEXT)

    monkeypatch.setenv("GEMINI_API_KEY", "odi-test")
    monkeypatch.delenv("GEMINI_API_BASE", raising=False)
    monkeypatch.delenv("GEMINI_VISION_MODEL", raising=False)
    monkeypatch.setattr(requests, "post", _post)
    assert so._ocr_gemini_vision(_PNG, "") == _TEXT
    assert seen["url"] == "https://api.odirouter.ai/v1/chat/completions"
    assert "openrouter" not in seen["url"]
    assert seen["model"].startswith("gemini-")
    assert seen["auth"] == "Bearer odi-test"


def test_engines_skip_without_keys(monkeypatch):
    import requests

    def _boom(*_a, **_k):
        raise AssertionError("без ключа запроса быть не должно")

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(requests, "post", _boom)
    assert so._ocr_deepseek_vision(_PNG, "") is None
    assert so._ocr_gemini_vision(_PNG, "") is None
