# -*- coding: utf-8 -*-
"""
Stage 1: Поиск прототипа задачи через DeepSeek.
"""
from .types import FoundTask


class Stage1Find:
    """Находит подходящий прототип задачи из архива олимпиад."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: DeepSeekClient instance
        """
        self.llm = llm_client

    def find(self, olympiad: str, stage: str, grade: int,
             olympiads_db: list = None) -> FoundTask:
        """
        Ищет прототип задачи для заданной олимпиады/этапа/класса.

        Args:
            olympiad: slug олимпиады (e.g. 'vsosh')
            stage: этап (e.g. 'regional')
            grade: класс (5-11)
            olympiads_db: база задач для few-shot примеров

        Returns:
            FoundTask с данными прототипа

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 1 будет реализован на шаге 2")
