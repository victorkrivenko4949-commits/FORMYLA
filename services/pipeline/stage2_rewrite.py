# -*- coding: utf-8 -*-
"""
Stage 2: Переписывание задачи через DeepSeek.
"""
from .types import FoundTask, RewrittenTask


class Stage2Rewrite:
    """Переписывает прототип задачи, сохраняя метод решения."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: DeepSeekClient instance
        """
        self.llm = llm_client

    def rewrite(self, found: FoundTask) -> RewrittenTask:
        """
        Переписывает задачу: меняет числа, контекст, формулировку.

        Args:
            found: прототип задачи из Stage 1

        Returns:
            RewrittenTask с переписанным текстом

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 2 будет реализован на шаге 3")
