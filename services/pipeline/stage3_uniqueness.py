# -*- coding: utf-8 -*-
"""
Stage 3: Проверка уникальности задачи (без LLM).
"""
from .types import RewrittenTask


class Stage3Uniqueness:
    """Проверяет что задача не гуглится."""

    def __init__(self, search_backend: str = "duckduckgo"):
        """
        Args:
            search_backend: бэкенд для поиска ('duckduckgo' | 'perplexity')
        """
        self.backend = search_backend

    def is_unique(self, rewritten: RewrittenTask) -> bool:
        """
        Проверяет уникальность задачи через веб-поиск.

        Args:
            rewritten: переписанная задача из Stage 2

        Returns:
            True если задача уникальна (не найдена в интернете)

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 3 будет реализован на шаге 4")
