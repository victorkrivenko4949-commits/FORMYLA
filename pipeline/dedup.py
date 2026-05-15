# -*- coding: utf-8 -*-
"""
Дедупликация задач через эмбеддинги.

Если косинусное сходство с любой существующей задачей > 0.92 → дубль.
Использует openai/text-embedding-3-small через OpenRouter.
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional, Sequence

import httpx

from pipeline.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
    EMBEDDING_MODEL,
    DEDUP_COSINE_THRESHOLD,
    MODEL_COSTS,
)

logger = logging.getLogger("pipeline.dedup")

_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


async def get_embedding(text: str, client: Optional[httpx.AsyncClient] = None) -> tuple[List[float], float]:
    """
    Получить эмбеддинг для текста через OpenRouter.

    Returns:
        (vector, cost_usd)
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY не задан")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }
    payload = {"model": EMBEDDING_MODEL, "input": text}

    owns = client is None
    if owns:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        resp = await client.post(_EMBEDDINGS_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        vec = data["data"][0]["embedding"]
        usage = data.get("usage", {})
        tokens = usage.get("prompt_tokens", 0)
        cost = tokens * MODEL_COSTS.get(EMBEDDING_MODEL, {"input": 0.02})["input"] / 1_000_000
        return vec, cost
    finally:
        if owns:
            await client.aclose()


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Косинусное сходство двух векторов."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def is_duplicate(
    candidate_embedding: Sequence[float],
    existing_embeddings: Sequence[Sequence[float]],
    threshold: float = DEDUP_COSINE_THRESHOLD,
) -> tuple[bool, float]:
    """
    Проверяет, является ли candidate дублем какой-либо из существующих задач.

    Returns:
        (is_dup, max_similarity)
    """
    if not existing_embeddings:
        return False, 0.0

    max_sim = max(
        cosine_similarity(candidate_embedding, e) for e in existing_embeddings
    )
    return max_sim >= threshold, max_sim
