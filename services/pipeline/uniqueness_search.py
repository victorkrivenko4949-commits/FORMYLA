# -*- coding: utf-8 -*-
"""
Абстракция над поисковиком для проверки уникальности задач.
Поддерживает Perplexity API (основной) и DuckDuckGo (fallback).
"""
import logging
from dataclasses import dataclass
from typing import List, Protocol
import requests

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Один результат поиска."""
    url: str
    title: str
    snippet: str


class SearchBackend(Protocol):
    """Протокол для поискового бэкенда."""
    def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        ...


class PerplexitySearchBackend:
    """Использует Perplexity Sonar API для поиска."""

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "sonar",
            "messages": [{
                "role": "user",
                "content": (
                    f"Найди точные совпадения фразы в интернете: {query}. "
                    f"Верни список URL с заголовками и отрывками."
                ),
            }],
            "return_citations": True,
            "return_related_questions": False,
        }
        try:
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            citations = data.get("citations", [])
            content = ""
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                content = choices[0].get("message", {}).get("content", "")
            return [
                SearchResult(url=url, title="", snippet=content[:200])
                for url in citations[:num_results]
            ]
        except requests.RequestException as e:
            logger.warning(f"Perplexity search failed: {e}")
            raise


class DuckDuckGoSearchBackend:
    """Fallback: поиск через duckduckgo-search."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num_results))
            return [
                SearchResult(
                    url=r.get("href", ""),
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                )
                for r in results
            ]
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            raise


class FallbackSearchBackend:
    """Primary → fallback если primary упал."""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        try:
            return self.primary.search(query, num_results)
        except Exception as e:
            logger.info(f"Primary search failed ({e}), using fallback")
            try:
                return self.fallback.search(query, num_results)
            except Exception as e2:
                logger.error(
                    f"Both backends failed: primary={e}, fallback={e2}"
                )
                return []  # пусто = не блокируем генерацию
