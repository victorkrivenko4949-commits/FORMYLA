# -*- coding: utf-8 -*-
"""tests/test_llm_router.py — CH17 provider model resolver tests."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services import llm_router as router  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("NOVITA_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("FIGURE_BASE_MODEL", raising=False)
    monkeypatch.delenv("FIGURE_AUX_MODEL", raising=False)
    monkeypatch.delenv("FIGURE_REPAIR_MODEL", raising=False)
    monkeypatch.delenv("FIGURE_AUDIT_MODEL", raising=False)
    monkeypatch.delenv("FIGURE_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    router.clear_model_cache()
    yield
    router.clear_model_cache()


def _set_key(monkeypatch, provider, value="key"):
    monkeypatch.setenv(router.PROVIDER_API_KEY_ENV[provider], value)


# ── 1. REC-5: base теперь Gemini через OdiRouter ──
def test_resolve_base_novita(monkeypatch):
    _set_key(monkeypatch, "novita")
    logical = router.logical_model_for_role("base")
    # base переведён на gemini-3.7-flash (REC-5).
    assert logical == "gemini-3.7-flash"
    # у novita нет маппинга для gemini -> None.
    assert router.resolve_provider_model(logical, "novita") is None


# ── 2. REC-5: у deepseek нет маппинга для gemini ──
def test_resolve_base_deepseek(monkeypatch):
    _set_key(monkeypatch, "deepseek")
    logical = router.logical_model_for_role("base")
    assert router.resolve_provider_model(logical, "deepseek") is None
    # gemini резолвится только у odirouter, без префикса.
    assert router.resolve_provider_model(logical, "odirouter") == "gemini-3.7-flash"


# ── 3. модель с "/" не преобразуется повторно ──
def test_native_model_not_remapped(monkeypatch):
    _set_key(monkeypatch, "novita")
    _set_key(monkeypatch, "deepseek")
    assert router.resolve_provider_model("deepseek/deepseek-v4-pro", "novita") == "deepseek/deepseek-v4-pro"
    assert router.resolve_provider_model("deepseek-v4-pro", "novita") == "deepseek/deepseek-v4-pro"


# ── 4. провайдер без маппинга исключается из цепочки ──
def test_provider_without_mapping_excluded(monkeypatch):
    _set_key(monkeypatch, "novita")
    _set_key(monkeypatch, "deepseek")
    # логическая модель без маппинга для novita (нет в PROVIDER_MODEL_MAP)
    chain = router.build_provider_chain("some-unknown-model")
    providers = [c["provider"] for c in chain]
    assert "novita" not in providers  # нет маппинга -> не вызываем novita
    assert "deepseek" not in providers  # нет маппинга и для deepseek


# ── 5. 404 MODEL_NOT_FOUND не ретраится на том же провайдере ──
def test_model_not_found_marks_unavailable(monkeypatch):
    _set_key(monkeypatch, "novita")
    _set_key(monkeypatch, "deepseek")
    router.mark_model_unavailable("novita", "deepseek/deepseek-v4-flash")
    chain = router.build_provider_chain("deepseek-v4-flash")
    providers = [c["provider"] for c in chain]
    assert "novita" not in providers
    assert "deepseek" in providers


# ── 6. content пуст, reasoning_content есть -> JSON извлечён ──
def test_reasoning_content_fallback():
    body = {"choices": [{"message": {"content": "", "reasoning_content": '{"a":1}'}}]}
    text, lengths = router.extract_response_text(body)
    assert text == '{"a":1}'
    assert lengths["reasoning_content"] == 7


# ── 7. все поля пусты -> LLM_EMPTY_CONTENT ──
def test_empty_content_error(monkeypatch):
    _set_key(monkeypatch, "deepseek")

    import requests

    class _Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": ""}}], "usage": {}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(router.LLMError) as exc:
        router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}])
    assert exc.value.code == "LLM_EMPTY_CONTENT"


# ── 8. текст без JSON -> LLM_NO_JSON (в job.error через _extract_json) ──
def test_text_without_json_returns_no_json():
    from routes.figures_generator import _extract_json
    assert _extract_json("просто текст без скобок") is None


# ── 9. при полном отказе провайдеров job=failed, кредит возвращён ──
def test_no_provider_raises():
    with pytest.raises(router.LLMError) as exc:
        router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}])
    assert exc.value.code == "LLM_NO_PROVIDER"
    assert exc.value.retryable is False


# ── classify_status ──
def test_classify_status():
    assert router.classify_status(401, None) == "LLM_AUTH_ERROR"
    assert router.classify_status(404, {"reason": "MODEL_NOT_FOUND"}) == "LLM_MODEL_NOT_FOUND"
    assert router.classify_status(429, None) == "LLM_RATE_LIMIT"
    assert router.classify_status(500, None) == "LLM_SERVER_ERROR"
    assert router.classify_status(418, None) == "LLM_HTTP_ERROR"


# ── describe_roles не падает и возвращает роли ──
def test_describe_roles():
    rows = router.describe_roles()
    roles = {r["role"] for r in rows}
    assert {"base", "aux", "repair", "audit", "legacy_reasoner"} <= roles
