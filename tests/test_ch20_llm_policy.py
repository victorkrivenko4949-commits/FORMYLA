# -*- coding: utf-8 -*-
"""CH20 tests: role max_tokens, thinking policy, retry strategies, provider unreachable."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services import llm_router as router  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for env in ("FIGURE_BASE_MAX_TOKENS", "FIGURE_AUX_MAX_TOKENS",
                "FIGURE_AUDIT_MAX_TOKENS", "FIGURE_REPAIR_MAX_TOKENS",
                "FIGURE_BASE_THINKING", "FIGURE_AUX_THINKING",
                "FIGURE_AUDIT_THINKING", "FIGURE_REPAIR_THINKING",
                "NOVITA_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    router.clear_model_cache()
    yield
    router.clear_model_cache()


def _set_key(monkeypatch, provider, value="key"):
    monkeypatch.setenv(router.PROVIDER_API_KEY_ENV[provider], value)


# 1. max_tokens по роли + env override
def test_max_tokens_by_role_defaults():
    assert router.max_tokens_for_role("base") == 3000
    assert router.max_tokens_for_role("aux") == 3500
    assert router.max_tokens_for_role("audit") == 800
    assert router.max_tokens_for_role("repair") == 6000
    assert router.max_tokens_for_role("legacy_reasoner") == 4096


def test_max_tokens_env_override(monkeypatch):
    monkeypatch.setenv("FIGURE_BASE_MAX_TOKENS", "1234")
    assert router.max_tokens_for_role("base") == 1234


def test_max_tokens_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("FIGURE_BASE_MAX_TOKENS", "abc")
    assert router.max_tokens_for_role("base") == 3000


# 2. thinking disabled в payload для base/aux/audit
def test_thinking_disabled_for_planners():
    assert router.thinking_mode_for_role("base") == "disabled"
    assert router.thinking_mode_for_role("aux") == "disabled"
    assert router.thinking_mode_for_role("audit") == "disabled"


def test_thinking_enabled_for_repair():
    assert router.thinking_mode_for_role("repair") == "enabled"
    assert router.thinking_mode_for_role("legacy_reasoner") == "enabled"


def test_thinking_env_override(monkeypatch):
    monkeypatch.setenv("FIGURE_REPAIR_THINKING", "disabled")
    assert router.thinking_mode_for_role("repair") == "disabled"


def _make_resp(payload_capture, status=200, body=None, text=""):
    class _Resp:
        status_code = status
        text = text

        def json(self):
            return body if body is not None else {"choices": [{"message": {"content": '{"a":1}'}}], "usage": {}}

    return _Resp()


# 3. thinking disabled попадает в payload
def test_thinking_payload_included(monkeypatch):
    _set_key(monkeypatch, "deepseek")
    import requests
    captured = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, **kw):
        captured["payload"] = kw["json"]
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}],
                    role="base", thinking_mode="disabled")
    assert captured["payload"].get("thinking") == {"type": "disabled"}


# 4. 400 из-за thinking -> retry без параметра, не fatal
def test_thinking_400_retry_without_param(monkeypatch):
    _set_key(monkeypatch, "deepseek")
    import requests
    calls = []

    class _BadResp:
        status_code = 400
        text = '{"error": "unknown parameter: thinking"}'
        def json(self):
            return {"error": "unknown parameter: thinking"}

    class _OkResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, **kw):
        calls.append(kw["json"])
        if len(calls) == 1:
            return _BadResp()
        return _OkResp()

    monkeypatch.setattr(requests, "post", fake_post)
    result = router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}],
                             role="base", thinking_mode="disabled")
    assert result["content"] == '{"a":1}'
    assert len(calls) == 2
    assert "thinking" not in calls[1]  # retry без thinking


# 5. reasoning overflow -> LLM_REASONING_OVERFLOW -> retry disabled
def test_reasoning_overflow_retry_disabled(monkeypatch):
    _set_key(monkeypatch, "deepseek")
    import requests
    calls = []

    class _OverflowResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": "", "reasoning_content": "..."}, "finish_reason": "length"}], "usage": {}}

    class _OkResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, **kw):
        calls.append(kw["json"])
        if len(calls) == 1:
            return _OverflowResp()
        return _OkResp()

    monkeypatch.setattr(requests, "post", fake_post)
    result = router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}],
                             role="base", thinking_mode="enabled")
    assert result["content"] == '{"a":1}'
    # второй вызов должен быть с thinking disabled
    assert calls[1].get("thinking") == {"type": "disabled"}


# 6. disabled + length -> LLM_TRUNCATED -> retry x2
def test_truncated_retry_x2(monkeypatch):
    _set_key(monkeypatch, "deepseek")
    import requests
    calls = []

    class _TruncResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": ""}, "finish_reason": "length"}], "usage": {}}

    class _OkResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, **kw):
        calls.append(kw["json"])
        if len(calls) < 3:
            return _TruncResp()
        return _OkResp()

    monkeypatch.setattr(requests, "post", fake_post)
    result = router.call_llm("deepseek-v4-flash", [{"role": "user", "content": "x"}],
                             role="base", max_tokens=100, thinking_mode="disabled")
    assert result["content"] == '{"a":1}'
    # strategy 2: max_tokens * 2
    assert calls[2]["max_tokens"] == 200


# 7. REC-6: транспортные ошибки блокируют provider::model, а не весь провайдер
def test_transport_unreachable_switch(monkeypatch):
    _set_key(monkeypatch, "novita")
    _set_key(monkeypatch, "deepseek")
    import requests

    class _TransportError(Exception):
        pass

    def fake_post(url, **kw):
        raise _TransportError("connection refused")

    monkeypatch.setattr(requests, "post", fake_post)
    # Заставляем конкретную пару novita::deepseek/deepseek-v4-flash
    # недоступной после порога транспортных ошибок.
    threshold = router.PROVIDER_UNREACHABLE_THRESHOLD
    model_id = "deepseek/deepseek-v4-flash"
    for _ in range(threshold - 1):
        assert router.record_transport_error("novita", model_id) is False
    assert router.record_transport_error("novita", model_id) is True

    # novita исключается из цепочки ТОЛЬКО для этой модели; deepseek остаётся.
    chain = router.build_provider_chain("deepseek-v4-flash")
    providers = [c["provider"] for c in chain]
    assert "novita" not in providers
    assert "deepseek" in providers
    # flash не блокирует pro (granularity REC-6).
    assert not router.is_provider_model_unreachable("novita", "deepseek/deepseek-v4-pro")
