# -*- coding: utf-8 -*-
"""
OlympiadPipeline — оркестратор 6-этапного пайплайна генерации олимпиадных задач.
"""
from .stage1_find import Stage1Find
from .stage2_rewrite import Stage2Rewrite
from .stage3_uniqueness import Stage3Uniqueness
from .stage4_latex import Stage4Latex
from .stage5_validate import Stage5Validate
from .stage6_save import Stage6Save
from .types import PipelineResult, PipelineError


class OlympiadPipeline:
    """
    Оркестратор генерации олимпиадных задач.

    Этапы:
        1. Find      — поиск прототипа (DeepSeek)
        2. Rewrite   — переписывание (DeepSeek)
        3. Uniqueness — проверка уникальности (web search)
        4. LaTeX     — оформление (Gemini Flash)
        5. Validate  — валидация LaTeX (regex)
        6. Save      — сохранение в БД

    Retry логика:
        - Stage 2: до 3 попыток (если Stage 3 не прошёл)
        - Stage 4-5: до 3 попыток (ошибки Stage 5 передаются в Stage 4)
    """

    MAX_UNIQUENESS_ATTEMPTS = 3
    MAX_LATEX_ATTEMPTS = 3

    def __init__(self, deepseek_client, gemini_client):
        """
        Args:
            deepseek_client: DeepSeekClient для Stage 1, 2
            gemini_client: GeminiClient для Stage 4
        """
        self.s1 = Stage1Find(deepseek_client)
        self.s2 = Stage2Rewrite(deepseek_client)
        self.s3 = Stage3Uniqueness()
        self.s4 = Stage4Latex(gemini_client)
        self.s5 = Stage5Validate()
        self.s6 = Stage6Save()

    def generate_task(self, variant_id: str, position: int,
                      olympiad: str, stage: str,
                      grade: int,
                      olympiads_db: list = None) -> PipelineResult:
        """
        Генерирует одну задачу через 6-этапный пайплайн.

        Args:
            variant_id: UUID варианта
            position: позиция задачи (1..5)
            olympiad: slug олимпиады
            stage: этап олимпиады
            grade: класс (5-11)
            olympiads_db: база задач для few-shot

        Returns:
            PipelineResult с финальной задачей

        Raises:
            PipelineError: если все попытки исчерпаны
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Orchestrator будет реализован на шаге 7")

    def generate_variant(self, olympiad: str, stage: str,
                         grade: int, task_count: int = 5,
                         user_id: int = None,
                         olympiads_db: list = None) -> list:
        """
        Генерирует полный вариант из task_count задач.

        Args:
            olympiad: slug олимпиады
            stage: этап олимпиады
            grade: класс (5-11)
            task_count: количество задач (default 5)
            user_id: ID пользователя (optional)
            olympiads_db: база задач для few-shot

        Returns:
            list[PipelineResult] — список сгенерированных задач

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Orchestrator будет реализован на шаге 7")
