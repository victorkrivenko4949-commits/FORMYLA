# -*- coding: utf-8 -*-
"""
Async HTTP-клиент для OpenRouter API.

Использует httpx (async) + tenacity (retry с exponential backoff).
Считает токены и стоимость для cost_log.
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
    MODEL_COSTS,
    RETRY_ATTEMPTS,
    RETRY_WAIT_MIN,
    RETRY_WAIT_MAX,
)

logger = logging.getLogger("pipeline.openrouter")


def _extract_first_json_object(text: str) -> Optional[str]:
    """
    Найти первый сбалансированный JSON-объект {...} в произвольной строке.

    Учитывает строковые литералы JSON ("...") и escape-последовательности,
    чтобы скобки внутри строк не сбивали баланс. Возвращает подстроку
    либо None, если ничего не нашлось.
    """
    start = text.find("{")
    if start < 0:
        return None
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
                return text[start:i + 1]
    return None


class OpenRouterError(Exception):
    """Ошибка при обращении к OpenRouter."""

    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TokenUsage:
    """Счётчик токенов и стоимости одного вызова."""

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
    Async-клиент для OpenRouter.

    Пример использования::

        async with OpenRouterClient() as client:
            text, usage = await client.chat(
                model="deepseek/deepseek-chat",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.8,
            )
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 90.0):
        # H-4 (2026-05-14): откат G-3 (timeout=180 для R1). R1 отключён,
        # для chat/sonnet 60 сек достаточно.
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise OpenRouterError(
                "OPENROUTER_API_KEY не задан. Добавьте в .env: OPENROUTER_API_KEY=sk-or-..."
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
        Отправить запрос к OpenRouter и получить текстовый ответ.

        Returns:
            (content_text, TokenUsage)
        """
        if self._client is None:
            raise OpenRouterError("Client not initialized. Use 'async with OpenRouterClient() as c:'")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        t0 = time.monotonic()
        resp = await self._client.post(
            OPENROUTER_BASE_URL,
            headers=self._headers(),
            json=payload,
        )
        latency = time.monotonic() - t0

        if resp.status_code != 200:
            body = resp.text
            logger.error("OpenRouter %s → %d: %s", model, resp.status_code, body[:500])
            raise OpenRouterError(
                f"OpenRouter returned {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )

        data = resp.json()

        # Извлекаем контент
        choices = data.get("choices", [])
        if not choices:
            raise OpenRouterError("OpenRouter вернул пустой choices", body=json.dumps(data))

        content = choices[0].get("message", {}).get("content", "")

        # H-5 (2026-05-29): retry на пустой ответ.
        # OpenRouter иногда возвращает HTTP 200 с content="" и 0 токенов.
        # Без этой проверки пустой ответ проходит как «успех» → validate_gemini_plan()
        # → [] → orchestrator падает с «Gemini вернул 0 specs (нужно 10)».
        # Кидаем retryable-исключение, чтобы @retry сделал повторную попытку.
        if not content.strip():
            completion_tokens = data.get("usage", {}).get("completion_tokens", 0)
            logger.warning(
                "%s — пустой ответ (HTTP 200, content='', completion_tokens=%d). "
                "Retry в рамках существующего механизма (%d попыток).",
                model, completion_tokens, RETRY_ATTEMPTS,
            )
            raise OpenRouterError(
                f"OpenRouter вернул пустой ответ (HTTP 200, 0 токенов) — попытка {model}",
                body=json.dumps(data),
            )

        # Извлекаем usage
        usage_raw = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_raw.get("prompt_tokens", 0),
            output_tokens=usage_raw.get("completion_tokens", 0),
            model=model,
            latency_s=latency,
        )

        logger.info(
            "✓ %s  in=%d out=%d  $%.4f  %.1fs",
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
        Как chat(), но парсит ответ как JSON.
        Снимает markdown-обёртку ```...``` и (M-2.1) извлекает первый
        сбалансированный {...} из прозаичного ответа Claude/Anthropic,
        который иногда «размышляет вслух» перед JSON.
        """
        content, usage = await self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        text = content.strip()

        # Снимаем markdown-обёртку если есть
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Попытка 1: парсим как есть
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            pass

        # M-2.1 (2026-05-14): fallback — извлечь первый сбалансированный {...}
        # с учётом строковых литералов и escape-символов. Это лечит ответы
        # Anthropic-моделей, которые часто пишут "Проверяю задачу...\n\n{...}".
        extracted = _extract_first_json_object(text)
        if extracted is not None:
            try:
                parsed = json.loads(extracted)
                logger.info(
                    "JSON extracted from prose response (%s, %d→%d chars)",
                    model, len(text), len(extracted),
                )
                return parsed, usage
            except json.JSONDecodeError:
                pass

        logger.error(
            "JSON parse error from %s (and fallback extraction failed)\nRaw: %s",
            model, text[:500],
        )
        raise OpenRouterError(f"Invalid JSON from {model}", body=text)
