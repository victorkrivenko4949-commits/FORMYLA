# -*- coding: utf-8 -*-
"""
OlympiadPipeline — оркестратор 6-этапного пайплайна генерации олимпиадных задач.
"""
import logging
import uuid
from datetime import datetime, timezone
from .stage1_find import Stage1Find, Stage1Error
from .stage2_rewrite import Stage2Rewrite, Stage2Error
from .stage3_uniqueness import Stage3Uniqueness
from .stage4_latex import Stage4Latex, Stage4Error
from .stage5_validate import Stage5Validate
from .stage6_save import Stage6Save, Stage6Error
from .types import PipelineResult, PipelineError

logger = logging.getLogger(__name__)

MAX_UNIQUENESS_ATTEMPTS = 3
MAX_LATEX_ATTEMPTS = 3


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
        - Stage 2+3: до 3 попыток (если Stage 3 не прошёл -> новый rewrite)
        - Stage 4+5: до 3 попыток (ошибки Stage 5 передаются в Stage 4)
    """

    def __init__(self, deepseek_client, gemini_client,
                 search_backend=None):
        """
        Args:
            deepseek_client: DeepSeekClient для Stage 1, 2
            gemini_client: GeminiClient для Stage 4
            search_backend: SearchBackend для Stage 3 (optional)
        """
        self.s1 = Stage1Find(deepseek_client)
        self.s2 = Stage2Rewrite(deepseek_client)
        self.s3 = Stage3Uniqueness(search_backend)
        self.s4 = Stage4Latex(gemini_client)
        self.s5 = Stage5Validate()
        self.s6 = Stage6Save()

    def generate_variant(self, olympiad_slug: str, olympiad_title: str,
                         round_key: str, round_title: str,
                         grade: int, user_id: int = None,
                         num_tasks: int = 5) -> dict:
        """
        Генерирует полный вариант из num_tasks задач.

        Транзакционно: либо все задачи сохранены, либо откат.

        Args:
            olympiad_slug: slug олимпиады
            olympiad_title: название олимпиады
            round_key: ключ этапа
            round_title: название этапа
            grade: класс (5-11)
            user_id: ID пользователя (optional)
            num_tasks: количество задач (default 5)

        Returns:
            dict с variant_id и списком PipelineResult

        Raises:
            PipelineError: если генерация провалилась
        """
        from models import db, OlympiadVariant

        variant_id = str(uuid.uuid4())
        variant = OlympiadVariant(
            id=variant_id,
            olympiad_slug=olympiad_slug,
            olympiad_title=olympiad_title,
            round_key=round_key,
            round_title=round_title,
            grade=grade,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(variant)

        results = []
        try:
            for position in range(1, num_tasks + 1):
                logger.info(
                    f"=== Variant {variant_id} / "
                    f"Task {position}/{num_tasks} ==="
                )
                result = self.generate_task(
                    variant_id=variant_id,
                    position=position,
                    olympiad=olympiad_title,
                    stage=round_key,
                    grade=grade,
                )
                results.append(result)

            db.session.commit()
            logger.info(
                f"Variant {variant_id} committed with "
                f"{len(results)} tasks"
            )
            return {
                "variant_id": variant_id,
                "tasks": results,
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Variant {variant_id} failed: {e}")
            raise

    def generate_task(self, variant_id: str, position: int,
                      olympiad: str, stage: str,
                      grade: int,
                      olympiads_db: list = None) -> PipelineResult:
        """
        Генерирует одну задачу через 6-этапный пайплайн.

        Args:
            variant_id: UUID варианта
            position: позиция задачи (1..5)
            olympiad: название олимпиады
            stage: этап олимпиады
            grade: класс (5-11)
            olympiads_db: база задач для few-shot (не используется)

        Returns:
            PipelineResult с финальной задачей

        Raises:
            PipelineError: если все попытки исчерпаны
        """
        stages_log = []

        # ── Stage 1: Find ──
        try:
            found = self.s1.find(olympiad, stage, grade)
            stages_log.append({
                "stage": 1, "ok": True,
                "year": found.year,
                "problem": found.problem_number,
            })
        except Stage1Error as e:
            stages_log.append({
                "stage": 1, "ok": False, "error": str(e),
            })
            raise PipelineError("stage1", str(e))

        # ── Stage 2 + Stage 3 (петля уникальности) ──
        rewritten = None
        for attempt in range(1, MAX_UNIQUENESS_ATTEMPTS + 1):
            try:
                rewritten = self.s2.rewrite(found)
                stages_log.append({
                    "stage": 2, "attempt": attempt, "ok": True,
                })
            except Stage2Error as e:
                stages_log.append({
                    "stage": 2, "attempt": attempt,
                    "ok": False, "error": str(e),
                })
                if attempt == MAX_UNIQUENESS_ATTEMPTS:
                    raise PipelineError("stage2", str(e), attempt)
                continue

            if self.s3.is_unique(rewritten):
                stages_log.append({
                    "stage": 3, "attempt": attempt, "unique": True,
                })
                break

            stages_log.append({
                "stage": 3, "attempt": attempt, "unique": False,
            })
            logger.info(
                f"Task not unique on attempt {attempt}, retrying rewrite"
            )
        else:
            raise PipelineError(
                "stage3",
                "Не удалось сделать задачу уникальной",
                MAX_UNIQUENESS_ATTEMPTS,
            )

        # ── Stage 4 + Stage 5 (петля LaTeX) ──
        processed = None
        prev_errors = []
        prev_output = ""

        for attempt in range(1, MAX_LATEX_ATTEMPTS + 1):
            try:
                processed = self.s4.process(
                    rewritten,
                    previous_errors=prev_errors,
                    previous_output=prev_output,
                )
                stages_log.append({
                    "stage": 4, "attempt": attempt, "ok": True,
                })
            except Stage4Error as e:
                stages_log.append({
                    "stage": 4, "attempt": attempt,
                    "ok": False, "error": str(e),
                })
                if attempt == MAX_LATEX_ATTEMPTS:
                    raise PipelineError("stage4", str(e), attempt)
                continue

            validation = self.s5.validate(processed)
            if validation.is_valid:
                stages_log.append({
                    "stage": 5, "attempt": attempt, "valid": True,
                })
                break

            stages_log.append({
                "stage": 5, "attempt": attempt,
                "valid": False,
                "errors_count": len(validation.errors),
            })
            prev_errors = validation.errors
            prev_output = processed.processed_text
            logger.info(
                f"LaTeX invalid on attempt {attempt}, "
                f"{len(validation.errors)} errors, retrying"
            )
        else:
            raise PipelineError(
                "stage5",
                f"LaTeX невалиден после {MAX_LATEX_ATTEMPTS} попыток: "
                f"{prev_errors}",
                MAX_LATEX_ATTEMPTS,
            )

        # ── Stage 6: Save ──
        try:
            result = self.s6.save_task(
                variant_id, position, processed, stages_log,
            )
            stages_log.append({
                "stage": 6, "ok": True, "task_id": result.task_id,
            })
            return result
        except Stage6Error as e:
            stages_log.append({
                "stage": 6, "ok": False, "error": str(e),
            })
            raise PipelineError("stage6", str(e))
