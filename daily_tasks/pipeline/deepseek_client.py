# -*- coding: utf-8 -*-
"""Async DeepSeek API client with OpenRouterClient-compatible interface.

Replaces OpenRouterClient in the daily_tasks pipeline — calls the official
DeepSeek API (api.deepseek.com) directly, no OpenRouter proxy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.deepseek.com/v1/chat/completions"

# Pricing per 1M tokens (DeepSeek official pricing, 2026-08)
# deepseek-v4-pro maps to deepseek-chat pricing.
_PRICING: Dict[str, Tuple[float, float]] = {
    "deepseek-v4-pro": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}
_DEFAULT_PRICING = (0.27, 1.10)


class TokenUsage:
    """Token usage and cost — same shape as OpenRouter's TokenUsage."""
    __slots__ = ("input_tokens", "output_tokens", "cost_usd")

    def __init__(self, input_tokens: int = 0, output_tokens: int = 0,
                 cost_usd: float = 0.0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd

    def __repr__(self) -> str:
        return (f"TokenUsage(in={self.input_tokens}, out={self.output_tokens}, "
                f"cost=${self.cost_usd:.6f})")


def make_token_usage(input_tokens: int = 0, output_tokens: int = 0,
                     cost_usd: float = 0.0) -> TokenUsage:
    return TokenUsage(input_tokens, output_tokens, cost_usd)


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    ip, op = _PRICING.get(model, _DEFAULT_PRICING)
    return in_tok / 1_000_000 * ip + out_tok / 1_000_000 * op


import threading
# Глобальный семафор — ограничение одновременных API-вызовов
# Используем threading.Semaphore (не asyncio!) — он не привязан к event loop
# и работает в фоновых потоках (conveyor worker, enqueue_daily_generation)
_GLOBAL_SEMAPHORE = threading.BoundedSemaphore(5)


class DeepSeekClient:
    """Async client for official DeepSeek API.

    Interface matches OpenRouterClient: ``chat`` and ``async_chat`` methods,
    ``TokenUsage`` returns.  Works as a context manager for connection reuse.
    """

    def __init__(self) -> None:
        # Load .env explicitly — this module may be imported before app.py runs load_dotenv()
        try:
            from dotenv import load_dotenv as _ld
            _ld(override=True)
        except Exception:
            pass
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self._model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
        if not self._api_key:
            logger.warning("DeepSeekClient: DEEPSEEK_API_KEY not set")
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "DeepSeekClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _ensure_session(self) -> None:
        if self._session is None:
            raise RuntimeError("DeepSeekClient used outside async context manager")

    @staticmethod
    def _strip_deepseek_prefix(model: str) -> str:
        """Remove 'deepseek/' prefix from OpenRouter-style model IDs."""
        return model.removeprefix("deepseek/")

    async def chat(self, model: str, messages: List[Dict[str, str]],
                   temperature: float = 0.3, max_tokens: int = 4096,
                   response_format: Optional[Dict[str, str]] = None,
                   thinking: bool = False,
                   **kwargs: Any) -> Tuple[str, TokenUsage]:
        """Sync-compatible async chat.  Same signature as OpenRouterClient.chat."""
        return await self.async_chat(model, messages, temperature, max_tokens,
                                      response_format, thinking=thinking, **kwargs)

    async def async_chat(self, model: str, messages: List[Dict[str, str]],
                         temperature: float = 0.3, max_tokens: int = 4096,
                         response_format: Optional[Dict[str, str]] = None,
                         thinking: bool = False,
                         **kwargs: Any) -> Tuple[str, TokenUsage]:
        """Call DeepSeek API and return (text, TokenUsage)."""
        # Глобальный семафор — только 5 одновременных API-вызовов
        # Используем threading.Semaphore (не asyncio) — работает из любого потока
        _GLOBAL_SEMAPHORE.acquire()
        try:
            return await self._async_chat_impl(model, messages, temperature,
                                                max_tokens, response_format,
                                                thinking=thinking, **kwargs)
        finally:
            _GLOBAL_SEMAPHORE.release()

    async def _async_chat_impl(self, model: str, messages: List[Dict[str, str]],
                                temperature: float, max_tokens: int,
                                response_format: Optional[Dict[str, str]],
                                thinking: bool = False,
                                **kwargs: Any) -> Tuple[str, TokenUsage]:
        """Реализация вызова API (вызывается после захвата семафора)."""
        self._ensure_session()
        assert self._session is not None

        # Use configured model, strip OpenRouter prefix if present
        ds_model = self._model

        payload: Dict[str, Any] = {
            "model": ds_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if thinking:
            payload["thinking"] = {"type": "enabled"}
        if response_format is not None:
            payload["response_format"] = response_format

        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                _t0 = time.time()
                async with self._session.post(_BASE_URL, json=payload) as resp:
                    body = await resp.text()
                _dt = time.time() - _t0

                if resp.status != 200:
                    snippet = body[:300]
                    logger.warning("DeepSeek HTTP %s (%.1fs): %s", resp.status, _dt, snippet)
                    if resp.status == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    if resp.status >= 500:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    raise RuntimeError(f"DeepSeek API HTTP {resp.status}: {snippet}")

                data = json.loads(body)
                choices = data.get("choices", [])
                if not choices:
                    raise ValueError("DeepSeek returned empty choices")

                msg = choices[0].get("message", {})
                content = msg.get("content", "") or ""
                usage_data = data.get("usage", {})
                in_tok = usage_data.get("prompt_tokens", 0)
                out_tok = usage_data.get("completion_tokens", 0)
                cost_usd = _cost(ds_model, in_tok, out_tok)
                logger.info(
                    "DeepSeek %s OK in %.1fs — in=%d out=%d cost=$%.4f",
                    ds_model, _dt, in_tok, out_tok, cost_usd,
                )
                return content, TokenUsage(input_tokens=in_tok, output_tokens=out_tok,
                                           cost_usd=cost_usd)

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError,
                    ValueError, json.JSONDecodeError) as exc:
                last_err = exc
                logger.warning("DeepSeek attempt %d/3 error: %s", attempt + 1, exc)
                await asyncio.sleep(2 * (attempt + 1))

        raise RuntimeError(f"DeepSeek API failed after 3 attempts: {last_err}")
