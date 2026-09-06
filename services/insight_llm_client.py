# -*- coding: utf-8 -*-
"""Клиент `insightLlmClient` — вызовы модели для «Банка неточностей».

Обёртка над `services.llm_router.call_llm` с явным параметром `effort`:

- effort="low"  — быстрый вызов (скрининг, подбор visibility из базы),
                  thinking выключен, малый max_tokens.
- effort="max"  — дорогой глубокий разбор (thinking включён, большой
                  max_tokens). Возвращает reasoning_tokens — обязательная
                  метрика для пост-валидации глубины рассуждения (раздел 6 ТЗ).

Все вызовы возвращают унифицированный dict:
    {
      "content": str,
      "reasoning_tokens": int,
      "prompt_tokens": int,
      "completion_tokens": int,
      "cost_usd": float,
      "model_id": str,
      "provider": str,
      "latency_ms": float,
    }
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Порог глубины рассуждения. Подбирается по факту (раздел 6 ТЗ); env-переменная
# позволяет откалибровать без деплоя кода.
AI_INSIGHT_MIN_REASONING_TOKENS = int(
    os.environ.get("AI_INSIGHT_MIN_REASONING_TOKENS", "300") or "300"
)

# Логическая модель для глубокого разбора (reasoning-модель).
INSIGHT_DEEP_MODEL = os.environ.get("INSIGHT_DEEP_MODEL", "deepseek-v4-pro")
# Логическая модель для дешёвых вызовов.
INSIGHT_LOW_MODEL = os.environ.get("INSIGHT_LOW_MODEL", "gemini-3.7-flash")


class InsightLlmError(Exception):
    """Неустранимая ошибка вызова модели."""


class InsightLlmClient:
    """Клиент вызовов модели для банка неточностей."""

    def __init__(self):
        self._deep_max_tokens = int(os.environ.get("INSIGHT_DEEP_MAX_TOKENS", "6000") or "6000")
        self._low_max_tokens = int(os.environ.get("INSIGHT_LOW_MAX_TOKENS", "1500") or "1500")

    def call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        effort: str = "low",
    ) -> Dict:
        """Выполнить вызов модели с явным effort.

        effort="low"  -> быстрый JSON-вызов без thinking.
        effort="max"  -> глубокий reasoning-вызов с thinking включён.
        """
        messages: List[dict] = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": user_prompt})
        return self.call_messages(messages=messages, effort=effort)

    def call_messages(
        self,
        *,
        messages: List[dict],
        effort: str = "low",
    ) -> Dict:
        """Вызов модели по полному списку сообщений (поддержка multi-turn).

        Для deepseek-v4-pro передаём thinking явно включённым (reasoning-канал),
        чтобы провайдер вернул reasoning_tokens в usage.
        """
        from services.llm_router import call_llm

        if effort == "max":
            model = INSIGHT_DEEP_MODEL
            max_tokens = self._deep_max_tokens
            # Роль insight_deep -> строго прямой DeepSeek API (deepseek_direct).
            role = "insight_deep"
            thinking_mode = "enabled"
        else:
            model = INSIGHT_LOW_MODEL
            max_tokens = self._low_max_tokens
            role = "base"
            thinking_mode = "disabled"

        try:
            result = call_llm(
                logical_model=model,
                messages=messages,
                max_tokens=max_tokens,
                role=role,
                thinking_mode=thinking_mode,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[insightLlm] call failed effort=%s", effort)
            raise InsightLlmError(str(exc)) from exc

        usage = result.get("usage") or {}
        return {
            "content": result.get("content") or "",
            "reasoning_tokens": int(result.get("reasoning_tokens") or 0),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "cost_usd": float(result.get("cost_usd") or 0.0),
            "model_id": result.get("model_id") or "",
            "provider": result.get("provider") or "",
            "latency_ms": result.get("latency_ms") or 0.0,
        }

    def call_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        effort: str = "low",
    ) -> Tuple[Dict, Dict]:
        """Вызвать модель и распарсить JSON. Возвращает (parsed, meta)."""
        meta = self.call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            effort=effort,
        )
        content = (meta.get("content") or "").strip()
        parsed = _parse_json(content)
        return parsed, meta


def _parse_json(raw: str) -> Dict:
    """Надёжно распарсить JSON из ответа модели (снимаем markdown-обёртку)."""
    if not raw:
        return {}
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)
        text = text[1] if len(text) > 1 else ""
        text = text.split("\n```")[0]
    # Отрезаем до первой '{' и после последней '}'.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else {}
    except (ValueError, TypeError):
        return {}


def reasoning_too_short(meta: Dict) -> bool:
    """True, если deep-прогон дал слишком мало reasoning-токенов.

    Означает, что процедура самопроверки задач (раздел 4.1 ТЗ) скорее всего
    не выполнялась.
    """
    return int(meta.get("reasoning_tokens") or 0) < AI_INSIGHT_MIN_REASONING_TOKENS


# Singleton (лениво, чтобы не тянуть llm_router при импорте).
_client: Optional[InsightLlmClient] = None


def get_insight_client() -> InsightLlmClient:
    global _client
    if _client is None:
        _client = InsightLlmClient()
    return _client
