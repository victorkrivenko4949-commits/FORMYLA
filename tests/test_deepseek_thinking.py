# -*- coding: utf-8 -*-
"""
T-THINKING: политика рассуждения DeepSeekClient (26.10.2026).

Проверяем исходящий payload:
  * thinking=True  -> {"thinking": {"type": "enabled"}}
  * thinking=False -> {"thinking": {"type": "disabled"}}  (явное выключение)
  * thinking=None / не передан -> параметра нет в payload (как раньше)
"""
import asyncio
import json

from daily_tasks.pipeline.deepseek_client import DeepSeekClient

_MESSAGES = [{"role": "user", "content": "hi"}]


class _FakeResp:
    status = 200

    async def text(self):
        return json.dumps({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })


class _FakeSession:
    def __init__(self):
        self.payloads = []

    def post(self, url, json=None):
        self.payloads.append(json)

        class _CM:
            async def __aenter__(self):
                return _FakeResp()

            async def __aexit__(self, *args):
                return False

        return _CM()


def _run(thinking):
    session = _FakeSession()
    client = DeepSeekClient()
    client._session = session

    async def _go():
        return await client._async_chat_impl(
            "deepseek-v4-pro", _MESSAGES, 0.5, 100, None, thinking=thinking)

    text, _usage = asyncio.run(_go())
    assert text == "ok"
    return session.payloads[0]


def test_thinking_enabled_payload():
    payload = _run(True)
    assert payload["thinking"] == {"type": "enabled"}


def test_thinking_disabled_explicit():
    # явное выключение: у reasoning-моделей рассуждение может быть
    # включено по умолчанию — отсутствие параметра его не гарантирует
    payload = _run(False)
    assert payload["thinking"] == {"type": "disabled"}


def test_thinking_default_omitted():
    # не передали — параметра нет в payload (обратная совместимость
    # со всеми существующими вызовами пайплайна)
    payload = _run(None)
    assert "thinking" not in payload
