# -*- coding: utf-8 -*-
"""
Stage 1: Поиск реальной задачи-прототипа через DeepSeek.
"""
import json
import logging
import re
from .types import FoundTask
from .prompts.stage1 import STAGE1_SYSTEM, STAGE1_USER

logger = logging.getLogger(__name__)

VALID_STAGES = {"school", "municipal", "regional", "final", "correspondence"}
MIN_CONFIDENCE = 0.7
MIN_TEXT_LENGTH = 30
MAX_ATTEMPTS = 3


class Stage1Error(Exception):
    """Ошибка этапа поиска прототипа."""
    pass


class Stage1Find:
    """Находит подходящий прототип задачи из архива олимпиад."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: DeepSeekClient instance с методом generate(prompt, system_prompt, temperature, max_tokens)
        """
        self.llm = llm_client

    def find(self, olympiad: str, stage: str, grade: int,
             olympiads_db: list = None) -> FoundTask:
        """
        Найти реальную задачу-прототип.

        Делает до MAX_ATTEMPTS попыток; каждая попытка — отдельный
        вызов DeepSeek с повышенной температурой если предыдущая не подошла.

        Args:
            olympiad: slug олимпиады (e.g. 'ВсОШ')
            stage: этап (e.g. 'regional')
            grade: класс (5-11)
            olympiads_db: не используется в Stage 1 (для совместимости)

        Returns:
            FoundTask с данными прототипа

        Raises:
            Stage1Error: если все попытки исчерпаны
        """
        self._validate_inputs(olympiad, stage, grade)

        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                temperature = 0.3 + 0.2 * (attempt - 1)
                raw = self._call_llm(olympiad, stage, grade,
                                     temperature=temperature)
                parsed = self._parse_json(raw)
                found = self._build_found_task(parsed, olympiad, stage, grade)
                self._validate_found_task(found)
                logger.info(
                    f"Stage1 success on attempt {attempt}: "
                    f"{found.olympiad}/{found.year}/#{found.problem_number} "
                    f"confidence={found.confidence}"
                )
                return found
            except Stage1Error as e:
                logger.warning(f"Stage1 attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
                last_error = e
                continue

        raise Stage1Error(
            f"Не удалось найти задачу за {MAX_ATTEMPTS} попыток. "
            f"Последняя ошибка: {last_error}"
        )

    def _validate_inputs(self, olympiad: str, stage: str, grade: int):
        """Валидация входных параметров до вызова LLM."""
        if not olympiad or not isinstance(olympiad, str):
            raise Stage1Error("olympiad должен быть непустой строкой")
        if stage not in VALID_STAGES:
            raise Stage1Error(
                f"stage '{stage}' должен быть из {VALID_STAGES}"
            )
        if not isinstance(grade, int) or not 5 <= grade <= 11:
            raise Stage1Error("grade должен быть int в диапазоне 5..11")

    def _call_llm(self, olympiad: str, stage: str, grade: int,
                  temperature: float) -> str:
        """Вызов DeepSeek API."""
        user_prompt = STAGE1_USER.format(
            olympiad=olympiad,
            stage=stage,
            grade=grade,
        )
        return self.llm.generate(
            prompt=user_prompt,
            system_prompt=STAGE1_SYSTEM,
            temperature=temperature,
            max_tokens=1500,
        )

    def _parse_json(self, raw: str) -> dict:
        """Парсинг JSON из ответа LLM (с очисткой markdown-обёрток)."""
        cleaned = raw.strip()
        # Убираем ```json ... ``` обёртки
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise Stage1Error(
                f"Невалидный JSON: {e}. Сырой ответ: {raw[:300]}"
            )

    def _build_found_task(self, data: dict, olympiad: str,
                          stage: str, grade: int) -> FoundTask:
        """Создание FoundTask из распарсенного JSON."""
        try:
            return FoundTask(
                olympiad=data.get("olympiad", olympiad),
                year=int(data["year"]),
                stage=data.get("stage", stage),
                grade=int(data.get("grade", grade)),
                problem_number=int(data.get("problem_number", 0)),
                topic=data.get("topic", "unknown"),
                difficulty=data.get("difficulty", "medium"),
                original_text=data["original_text"],
                author=data.get("author"),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise Stage1Error(f"Отсутствует/некорректно поле: {e}")

    def _validate_found_task(self, f: FoundTask):
        """Валидация найденной задачи."""
        if f.confidence < MIN_CONFIDENCE:
            raise Stage1Error(
                f"Confidence {f.confidence} < {MIN_CONFIDENCE}"
            )
        if len(f.original_text) < MIN_TEXT_LENGTH:
            raise Stage1Error(
                f"Текст слишком короткий: {len(f.original_text)} символов "
                f"(минимум {MIN_TEXT_LENGTH})"
            )
        if '\\' in f.original_text:
            raise Stage1Error(
                "В тексте обнаружен обратный слэш (LaTeX-утечка)"
            )
        if '$' in f.original_text:
            raise Stage1Error(
                "В тексте обнаружен $ (LaTeX-утечка)"
            )
        if not 2015 <= f.year <= 2024:
            raise Stage1Error(
                f"Год {f.year} вне диапазона 2015..2024"
            )
