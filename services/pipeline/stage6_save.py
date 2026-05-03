# -*- coding: utf-8 -*-
"""
Stage 6: Сохранение задачи в БД.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List
from .types import ProcessedTask, PipelineResult

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0"


class Stage6Error(Exception):
    """Ошибка этапа сохранения."""
    pass


class Stage6Save:
    """Сохраняет задачу в таблицы OlympiadVariant / OlympiadTask."""

    def save_task(self, variant_id: str, position: int,
                  processed: ProcessedTask,
                  stages_log: List[dict]) -> PipelineResult:
        """
        Сохранить задачу в БД. Транзакционно.

        Вызывающий код должен быть в рамках app_context().
        Коммит делает вызывающий код (pipeline.generate_variant).

        Args:
            variant_id: UUID варианта
            position: позиция задачи (1..5)
            processed: финальная задача из Stage 4/5
            stages_log: лог всех этапов

        Returns:
            PipelineResult с task_id

        Raises:
            Stage6Error: при ошибке БД
        """
        from models import db, OlympiadTask

        rewritten = processed.rewritten
        found = rewritten.original

        try:
            task = OlympiadTask(
                variant_id=variant_id,
                position=position,
                text=processed.processed_text,
                original_text=found.original_text,
                solution=rewritten.solution if hasattr(rewritten, 'solution') else None,
                answer=rewritten.answer if hasattr(rewritten, 'answer') else None,
                topic=found.topic,
                source_year=found.year,
                source_problem=found.problem_number,
                author=found.author,
                pipeline_version=PIPELINE_VERSION,
                status='validated',
                validated_at=datetime.now(timezone.utc),
                validation_errors=None,
            )
            db.session.add(task)
            db.session.flush()  # получаем task.id без коммита

            result = PipelineResult(
                task_id=task.id,
                variant_id=variant_id,
                position=position,
                final_text=processed.processed_text,
                final_solution=rewritten.solution if hasattr(rewritten, 'solution') else "",
                final_answer=rewritten.answer if hasattr(rewritten, 'answer') else "",
                topic=found.topic,
                original_text=found.original_text,
                source_year=found.year,
                source_problem=found.problem_number,
                author=found.author,
                stages_log=stages_log,
                created_at=datetime.now(timezone.utc),
            )
            logger.info(
                f"Stage6: task saved id={task.id} "
                f"variant={variant_id} pos={position}"
            )
            return result
        except Exception as e:
            db.session.rollback()
            raise Stage6Error(f"Ошибка сохранения: {e}")

    def save_failed_task(self, variant_id: str, position: int,
                         processed_text: str,
                         errors: List[str],
                         stages_log: List[dict]):
        """
        Сохранить задачу со статусом 'failed' для дебага.

        Args:
            variant_id: UUID варианта
            position: позиция задачи
            processed_text: текст (может быть пустым)
            errors: список ошибок
            stages_log: лог этапов
        """
        from models import db, OlympiadTask

        try:
            task = OlympiadTask(
                variant_id=variant_id,
                position=position,
                text=processed_text or "(не сгенерирован)",
                original_text="",
                pipeline_version=PIPELINE_VERSION,
                status='failed',
                validation_errors=json.dumps(errors, ensure_ascii=False),
            )
            db.session.add(task)
            db.session.flush()
            logger.warning(
                f"Failed task saved id={task.id} errors={len(errors)}"
            )
        except Exception as e:
            logger.error(f"Could not save failed task: {e}")
            db.session.rollback()
