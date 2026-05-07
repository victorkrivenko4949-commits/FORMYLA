# -*- coding: utf-8 -*-
"""
OpenRouter API Client with rate limiting, retry, and circuit breaker.

Usage:
    from services.openrouter_client import openrouter
    result = openrouter.chat("anthropic/claude-opus-4.1", messages=[...])
    embedding = openrouter.embed("text to embed")
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Model-specific rate limits (requests per minute)
DEFAULT_RPM = {
    "anthropic/claude-sonnet-4.5": 40,
    "anthropic/claude-opus-4.7": 15,
    "anthropic/claude-opus-4.1": 20,
    "deepseek/deepseek-chat": 60,
    "google/gemini-2.5-pro": 30,
    "openai/o4-mini": 30,
    "openai/text-embedding-3-large": 200,
    # Legacy (kept for compatibility)
    "openai/gpt-4o": 60,
    "openai/gpt-4o-mini": 100,
}

# Pricing per 1M tokens (input/output) for cost tracking.
# v2.5 hotfix: added opus-4.7 + gemini-2.5-pro because generator/arbiter calls
# were logging $0.0000 due to missing pricing entries.  Numbers below match
# OpenRouter list pricing as of 2026-05; if/when official anthropic opus-4.7
# pricing is published, replace the placeholder.
MODEL_PRICING = {
    "anthropic/claude-sonnet-4.5": (3.0, 15.0),
    "anthropic/claude-opus-4.7": (15.0, 75.0),   # placeholder; mirror opus-4.1 until verified
    "anthropic/claude-opus-4.1": (15.0, 75.0),
    "deepseek/deepseek-chat": (0.27, 1.10),
    "google/gemini-2.5-pro": (1.25, 5.0),
    "openai/o4-mini": (1.10, 4.40),
    "openai/text-embedding-3-large": (0.13, 0.0),
    # Legacy
    "openai/gpt-4o": (2.5, 10.0),
    "openai/gpt-4o-mini": (0.15, 0.6),
}
_PRICING_PLACEHOLDER_WARNED = set()

CIRCUIT_BREAKER_THRESHOLD = 10
CIRCUIT_BREAKER_PAUSE_SEC = 300
MAX_RETRIES = 5
BASE_RETRY_DELAY = 2.0


class RateLimiter:
    """Per-model token bucket rate limiter."""

    def __init__(self):
        self._timestamps = defaultdict(list)
        self._lock = Lock()

    def wait(self, model: str):
        rpm = DEFAULT_RPM.get(model, 30)
        window = 60.0

        with self._lock:
            now = time.time()
            # Clean old timestamps
            self._timestamps[model] = [
                t for t in self._timestamps[model] if now - t < window
            ]
            if len(self._timestamps[model]) >= rpm:
                sleep_time = window - (now - self._timestamps[model][0]) + 0.1
                logger.info(f"[RateLimit] {model}: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
            self._timestamps[model].append(time.time())


class CircuitBreaker:
    """Circuit breaker: pauses model after consecutive failures."""

    def __init__(self):
        self._failures = defaultdict(int)
        self._paused_until = {}
        self._lock = Lock()

    def check(self, model: str) -> bool:
        """Returns True if model is available."""
        with self._lock:
            if model in self._paused_until:
                if time.time() < self._paused_until[model]:
                    return False
                else:
                    del self._paused_until[model]
                    self._failures[model] = 0
            return True

    def record_success(self, model: str):
        with self._lock:
            self._failures[model] = 0

    def record_failure(self, model: str):
        with self._lock:
            self._failures[model] += 1
            if self._failures[model] >= CIRCUIT_BREAKER_THRESHOLD:
                pause_until = time.time() + CIRCUIT_BREAKER_PAUSE_SEC
                self._paused_until[model] = pause_until
                logger.error(
                    f"[CircuitBreaker] {model}: {CIRCUIT_BREAKER_THRESHOLD} consecutive "
                    f"failures, pausing for {CIRCUIT_BREAKER_PAUSE_SEC}s"
                )


class OpenRouterClient:
    """OpenRouter API client with rate limiting, retry, circuit breaker."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self.rate_limiter = RateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self._total_cost = 0.0
        self._lock = Lock()

    def chat(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict = None,
    ) -> dict:
        """
        Send chat completion request.

        Returns: {"content": str, "usage": {...}, "cost_usd": float}
        Raises: OpenRouterError on failure after retries.
        """
        if not self.circuit_breaker.check(model):
            raise CircuitBreakerOpen(f"Model {model} is paused (circuit breaker)")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        for attempt in range(MAX_RETRIES):
            self.rate_limiter.wait(model)

            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://formyla.com",
                            "X-Title": "FORMYLA Daily Pool",
                        },
                        json=payload,
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    self.circuit_breaker.record_success(model)
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    cost = self._calc_cost(model, usage)
                    return {
                        "content": content,
                        "usage": usage,
                        "cost_usd": cost,
                        "model": model,
                    }

                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 30))
                    logger.warning(f"[429] {model}: rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue

                elif resp.status_code >= 500:
                    self.circuit_breaker.record_failure(model)
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"[{resp.status_code}] {model}: server error, retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue

                else:
                    error_body = resp.text[:500]
                    raise OpenRouterError(f"HTTP {resp.status_code}: {error_body}")

            except httpx.TimeoutException:
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"[Timeout] {model}: attempt {attempt+1}, retry in {delay:.1f}s")
                time.sleep(delay)
                continue

            except httpx.ConnectError as e:
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"[ConnectError] {model}: {e}, retry in {delay:.1f}s")
                time.sleep(delay)
                continue

        raise OpenRouterError(f"Failed after {MAX_RETRIES} retries for {model}")

    def embed(self, text: str, model: str = "openai/text-embedding-3-large") -> list:
        """Get embedding vector for text. Returns list of floats (3072 dims)."""
        if not self.circuit_breaker.check(model):
            raise CircuitBreakerOpen(f"Model {model} is paused")

        self.rate_limiter.wait(model)

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "input": text},
            )

        if resp.status_code == 200:
            data = resp.json()
            self.circuit_breaker.record_success(model)
            usage = data.get("usage", {})
            self._calc_cost(model, usage)
            return data["data"][0]["embedding"]
        else:
            self.circuit_breaker.record_failure(model)
            raise OpenRouterError(f"Embed failed: HTTP {resp.status_code}")

    def _calc_cost(self, model: str, usage: dict) -> float:
        """Calculate cost in USD and track total."""
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        pricing = MODEL_PRICING.get(model, (0, 0))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000
        with self._lock:
            self._total_cost += cost
        return cost

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def log_cost_to_db(self, task_type: str, model: str, usage: dict,
                       cost: float, variant_id: int = None, problem_id: int = None):
        """Log API call cost to generation_costs table."""
        try:
            from models import db
            db.session.execute(
                db.text("""
                    INSERT INTO generation_costs
                        (task_type, model, input_tokens, output_tokens, cost_usd, variant_id, problem_id)
                    VALUES (:task_type, :model, :input, :output, :cost, :vid, :pid)
                """),
                {
                    'task_type': task_type,
                    'model': model,
                    'input': usage.get('prompt_tokens', 0),
                    'output': usage.get('completion_tokens', 0),
                    'cost': cost,
                    'vid': variant_id,
                    'pid': problem_id,
                }
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to log cost: {e}")


class OpenRouterError(Exception):
    pass


class CircuitBreakerOpen(OpenRouterError):
    pass


# Singleton instance
openrouter = OpenRouterClient()
