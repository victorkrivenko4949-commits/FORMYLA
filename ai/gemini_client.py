# -*- coding: utf-8 -*-
"""
Gemini Flash client via OpenRouter API.
Lightweight wrapper for Stage 4 (LaTeX formatting).
"""
import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Client for Gemini Flash via OpenRouter.
    Uses the same OpenRouter API key as the existing generate_variant().
    """

    def __init__(self, api_key: Optional[str] = None,
                 model: str = "google/gemini-2.0-flash-001"):
        """
        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY env var.
            model: Gemini model identifier on OpenRouter.
        """
        self.api_key = api_key or os.environ.get('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not provided and not found in environment")

        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = model
        self.timeout = 90

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.3,
                 max_tokens: Optional[int] = None) -> str:
        """
        Generate text using Gemini Flash via OpenRouter.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (None = no limit, API default)

        Returns:
            Generated text

        Raises:
            RuntimeError: If API call fails
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                usage = data.get('usage') or {}
                logger.info(
                    "llm usage role=gemini provider=gemini model=%s in=%s out=%s reasoning=%s",
                    self.model,
                    usage.get('prompt_tokens'),
                    usage.get('completion_tokens'),
                    usage.get('reasoning_tokens'),
                )
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0].get('message', {}).get('content')
                    if content:
                        logger.info("[OK] Gemini request successful")
                        return content
                else:
                    logger.warning("llm usage missing choices provider=gemini model=%s", self.model)

            logger.error(f"Gemini API error: HTTP {response.status_code}: {response.text[:200]}")
            raise RuntimeError(f"Gemini API error: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            logger.error("Gemini API timeout")
            raise RuntimeError("Gemini API timeout")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Gemini connection error: {e}")
            raise RuntimeError(f"Gemini connection error: {e}")
