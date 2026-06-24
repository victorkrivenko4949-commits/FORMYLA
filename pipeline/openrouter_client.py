# -*- coding: utf-8 -*-
"""
Async HTTP-client for OpenRouter API.

Uses httpx (async) + tenacity (retry with exponential backoff).
Counts tokens and cost for cost_log.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from pipeline.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
DEEPSEEK_API_KEY,
DEEPSEEK_BASE_URL,
DEEPSEEK_DIRECT_MODELS,
    MODEL_COSTS,
    RETRY_ATTEMPTS,
    RETRY_WAIT_MIN,
    RETRY_WAIT_MAX,
)

logger = logging.getLogger("pipeline.openrouter")


def _resolve_route(model, openrouter_headers):
    """Vybrat endpoint dlya zaprosa: DeepSeek napryamuyu ili OpenRouter.

    Esli model est v DEEPSEEK_DIRECT_MODELS i zadan DEEPSEEK_API_KEY -
    shlem napryamuyu na api.deepseek.com (deshevle/bystree, bez OpenRouter-nacenki).
    Inache - fallback na OpenRouter (nichego ne lomaetsya, esli klyucha net).
    Vozvrashchaet (api_url, api_model, headers).
    """
    direct_name = DEEPSEEK_DIRECT_MODELS.get(model)
    if direct_name and DEEPSEEK_API_KEY:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        return DEEPSEEK_BASE_URL, direct_name, headers
    return OPENROUTER_BASE_URL, model, openrouter_headers



def _extract_all_json_objects(text: str) -> list:
    """Find ALL balanced JSON objects in a string, accounting for
    string literals and escapes. Returns list of matched JSON substrings,
    ordered by appearance.
    """
    results = []
    start = 0
    while True:
        start = text.find("{", start)
        if start < 0:
            break
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    results.append(text[start:i + 1])
                    start = i + 1
                    break
        else:
            start += 1
    return results


def _extract_longest_json_object(text: str) -> Optional[str]:
    """
    Find the LONGEST balanced JSON object in arbitrary text.

    Strategy:
      1. First, look for markdown code blocks with json tag.
         Extract all balanced JSON objects from within them
         and return the longest.
      2. If no code blocks, find ALL balanced objects in the full
         text and return the longest one.

    This handles Claude/Anthropic responses that wrap JSON in markdown
    code blocks or include multiple JSON fragments (thinking fragments
    followed by the actual response).
    """
    if not text:
        return None

    import re

    # Strategy 1: Look for ```json ... ``` code blocks
    json_block_pattern = re.compile(
        # pattern: triple-backtick optional json tag, content, triple-backtick
        r'```(?:json)?\s*\n(.*?)```', re.IGNORECASE | re.DOTALL
    )
    all_candidates = []

    for match in json_block_pattern.finditer(text):
        block_content = match.group(1).strip()
        objs = _extract_all_json_objects(block_content)
        all_candidates.extend(objs)

    # Also find objects in the raw text (outside code blocks)
    # First strip code blocks to avoid double-counting
    remaining = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    all_candidates.extend(_extract_all_json_objects(remaining))

    if not all_candidates:
        return None

    # Return the longest candidate
    longest = max(all_candidates, key=len)
    if longest:
        logger.info(
            "Longest JSON: %d candidates, picked %d chars",
            len(all_candidates), len(longest),
        )
    return longest


class OpenRouterError(Exception):
    """Error when calling OpenRouter."""

    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TokenUsage:
    """Token and cost counter for a single API call."""

    __slots__ = ("input_tokens", "output_tokens", "model", "cost_usd", "latency_s")

    def __init__(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
        latency_s: float = 0.0,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model
        self.latency_s = latency_s
        self.cost_usd = self._calc_cost()

    def _calc_cost(self) -> float:
        costs = MODEL_COSTS.get(self.model, {"input": 0.0, "output": 0.0})
        return (
            self.input_tokens * costs["input"] / 1_000_000
            + self.output_tokens * costs["output"] / 1_000_000
        )


class OpenRouterClient:
    """
    Async client for OpenRouter.

    Usage::

        async with OpenRouterClient() as client:
            text, usage = await client.chat(
                model="deepseek/deepseek-chat",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.8,
            )
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 90.0):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise OpenRouterError(
                "OPENROUTER_API_KEY not set. Add to .env: OPENROUTER_API_KEY=sk-or-..."
            )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "OpenRouterClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        }

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def chat(
        self,
        model: str,
        messages: list[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> tuple[str, TokenUsage]:
        """
        Send request to OpenRouter and get text response.

        Returns:
            (content_text, TokenUsage)
        """
        if self._client is None:
            raise OpenRouterError("Client not initialized. Use 'async with OpenRouterClient() as c:'")
            
        api_url, api_model, headers = _resolve_route(model, self._headers())
        payload: Dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        t0 = time.monotonic()
        resp = await self._client.post(
            api_url,
            headers=headers,
            json=payload,
                )
        latency = time.monotonic() - t0

        if resp.status_code != 200:
            body = resp.text
            logger.error("OpenRouter %s -> %d: %s", model, resp.status_code, body[:500])
            raise OpenRouterError(
                f"OpenRouter returned {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )

        data = resp.json()

        # Extract content
        choices = data.get("choices", [])
        if not choices:
            raise OpenRouterError("OpenRouter returned empty choices", body=json.dumps(data))

        content = choices[0].get("message", {}).get("content", "")

        # Retry on empty response
        if not content.strip():
            completion_tokens = data.get("usage", {}).get("completion_tokens", 0)
            logger.warning(
                "%s - empty response (HTTP 200, content='', completion_tokens=%d). "
                "Retry within existing mechanism (%d attempts).",
                model, completion_tokens, RETRY_ATTEMPTS,
            )
            raise OpenRouterError(
                f"OpenRouter returned empty response (HTTP 200, 0 tokens) - attempt {model}",
                body=json.dumps(data),
            )

        # Extract usage
        usage_raw = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_raw.get("prompt_tokens", 0),
            output_tokens=usage_raw.get("completion_tokens", 0),
            model=model,
            latency_s=latency,
        )

        logger.info(
            "[OK] %s  in=%d out=%d  $%.4f  %.1fs",
            model, usage.input_tokens, usage.output_tokens,
            usage.cost_usd, usage.latency_s,
        )

        return content, usage

    async def chat_json(
        self,
        model: str,
        messages: list[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 4096,
    ) -> tuple[Dict, TokenUsage]:
        """
        Like chat(), but parses response as JSON.
        Strips markdown wrapper and extracts the longest
        balanced JSON object from Claude/Anthropic responses
        that sometimes think out loud before JSON.

        Uses _extract_longest_json_object() to find the
        longest JSON (not the first), correctly handling
        multiple fragments in the response.
        """
        # Anthropic models via OpenRouter do NOT support
        # response_format=json_object - they return thinking
        # text instead of JSON. For other models, use native mode.
        json_format = None if model.startswith("anthropic/") else {"type": "json_object"}
        content, usage = await self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=json_format,
        )

        # Prefill compensation: if the last message was assistant "{" prefill,
        # the model's continuation won't include the opening brace.
        # Prepend it back to reconstruct valid JSON before any parsing.
        if messages and len(messages) > 0:
            last = messages[-1]
            if last.get("role") == "assistant" and last.get("content") == "{":
                if not content.startswith("{"):
                    content = "{" + content
                    logger.debug("Prefill: prepended '{' to response (%d chars)", len(content))

        text = content.strip()

        # Attempt 1: parse as-is
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            pass

        # Fallback: extract longest balanced JSON object
        # accounting for code blocks and multiple fragments
        extracted = _extract_longest_json_object(text)
        if extracted is not None:
            try:
                parsed = json.loads(extracted)
                logger.info(
                    "JSON extracted from prose response (%s, %d->%d chars)",
                    model, len(text), len(extracted),
                )
                return parsed, usage
            except json.JSONDecodeError:
                pass

        raise OpenRouterError(f"Invalid JSON from {model}", body=text)
