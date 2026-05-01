# -*- coding: utf-8 -*-
"""
Tests for uniqueness_search backends.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.pipeline.uniqueness_search import (
    SearchResult,
    FallbackSearchBackend,
    PerplexitySearchBackend,
)


class TestFallbackSearchBackend:
    """Тесты для FallbackSearchBackend."""

    def test_uses_primary_when_ok(self):
        """Если primary работает — используем его."""
        primary = MagicMock()
        primary.search.return_value = [SearchResult("url", "t", "s")]
        fallback = MagicMock()

        fb = FallbackSearchBackend(primary, fallback)
        result = fb.search("query")

        assert len(result) == 1
        primary.search.assert_called_once()
        fallback.search.assert_not_called()

    def test_falls_back_on_primary_error(self):
        """Если primary упал — используем fallback."""
        primary = MagicMock()
        primary.search.side_effect = Exception("rate limit")
        fallback = MagicMock()
        fallback.search.return_value = [SearchResult("url2", "", "")]

        fb = FallbackSearchBackend(primary, fallback)
        result = fb.search("query")

        assert result[0].url == "url2"
        fallback.search.assert_called_once()

    def test_returns_empty_if_both_fail(self):
        """Если оба упали — пустой список (не блокируем)."""
        primary = MagicMock()
        primary.search.side_effect = Exception("fail1")
        fallback = MagicMock()
        fallback.search.side_effect = Exception("fail2")

        fb = FallbackSearchBackend(primary, fallback)
        assert fb.search("query") == []


class TestPerplexitySearchBackend:
    """Тесты для PerplexitySearchBackend."""

    @patch('services.pipeline.uniqueness_search.requests.post')
    def test_returns_citations(self, mock_post):
        """Парсит citations из ответа Perplexity."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "citations": ["https://site1.com", "https://site2.com"],
            "choices": [{"message": {"content": "snippet text"}}],
        }
        mock_post.return_value = mock_resp

        b = PerplexitySearchBackend(api_key="test")
        results = b.search("query")

        assert len(results) == 2
        assert results[0].url == "https://site1.com"

    @patch('services.pipeline.uniqueness_search.requests.post')
    def test_raises_on_http_error(self, mock_post):
        """Ошибка сети → RequestException."""
        import requests as _r
        mock_post.side_effect = _r.ConnectionError("timeout")
        b = PerplexitySearchBackend(api_key="test")
        with pytest.raises(_r.RequestException):
            b.search("query")
