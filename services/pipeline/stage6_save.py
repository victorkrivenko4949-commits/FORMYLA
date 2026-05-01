# -*- coding: utf-8 -*-
"""
Stage 6: Сохранение задачи в БД.
"""
from typing import List
from .types import ProcessedTask, PipelineResult


class Stage6Save:
    """Сохраняет задачу в таблицы OlympiadVariant / OlympiadTask."""

    def save_task(self, variant_id: str, position: int,
                  processed: ProcessedTask,
                  stages_log: List[dict]) -> PipelineResult:
        """
        Сохраняет задачу в БД.

        Args:
            variant_id: UUID варианта
            position: позиция задачи (1..5)
            processed: финальная задача из Stage 4/5
            stages_log: лог всех этапов

        Returns:
            PipelineResult с task_id

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 6 будет реализован на шаге 7")
