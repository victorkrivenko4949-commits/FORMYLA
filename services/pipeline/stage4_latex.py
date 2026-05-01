# -*- coding: utf-8 -*-
"""
Stage 4: Оформление LaTeX через Gemini Flash (OpenRouter).
"""
from typing import List, Optional
from .types import RewrittenTask, ProcessedTask


class Stage4Latex:
    """Форматирует задачу с правильным LaTeX через Gemini."""

    def __init__(self, gemini_client, model: str = "google/gemini-2.0-flash-001"):
        """
        Args:
            gemini_client: GeminiClient instance (OpenRouter wrapper)
            model: модель Gemini для использования
        """
        self.llm = gemini_client
        self.model = model

    def process(self, rewritten: RewrittenTask,
                previous_errors: Optional[List[str]] = None) -> ProcessedTask:
        """
        Форматирует задачу с правильным LaTeX.

        Args:
            rewritten: переписанная задача из Stage 2
            previous_errors: ошибки из предыдущей попытки Stage 5

        Returns:
            ProcessedTask с отформатированным текстом

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 4 будет реализован на шаге 5")
