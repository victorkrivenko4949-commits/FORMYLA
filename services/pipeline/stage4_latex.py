# -*- coding: utf-8 -*-
"""
Stage 4: Оформление LaTeX через Gemini Flash (OpenRouter).
"""
import json
import logging
import re
from typing import List, Optional
from .types import RewrittenTask, ProcessedTask
from .prompts.stage4 import (
    STAGE4_SYSTEM, STAGE4_USER, build_previous_errors_block,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MIN_LATEX_SIZE = 30


class Stage4Error(Exception):
    """Ошибка этапа LaTeX-оформления."""
    pass


class Stage4Latex:
    """Форматирует задачу с правильным LaTeX через Gemini."""

    def __init__(self, gemini_client, model: str = "google/gemini-2.0-flash-001"):
        """
        Args:
            gemini_client: GeminiClient instance с методом
                           generate(prompt, system_prompt, temperature, max_tokens)
            model: модель Gemini (хранится для справки, модель задаётся в клиенте)
        """
        self.llm = gemini_client
        self.model = model

    def process(self, rewritten: RewrittenTask,
                previous_errors: Optional[List[str]] = None,
                previous_output: str = "") -> ProcessedTask:
        """
        Оформить LaTeX. Если переданы previous_errors —
        это ретрай от валидатора, передаём их в промпт.

        Args:
            rewritten: переписанная задача из Stage 2
            previous_errors: ошибки из предыдущей попытки Stage 5
            previous_output: предыдущий processed_text (для контекста)

        Returns:
            ProcessedTask с отформатированным текстом

        Raises:
            Stage4Error: если все попытки исчерпаны
        """
        previous_errors = previous_errors or []
        last_error = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                temperature = 0.2 + 0.1 * (attempt - 1)
                raw = self._call_llm(
                    rewritten, previous_errors,
                    previous_output, temperature=temperature,
                )
                parsed = self._parse_json(raw)
                processed = self._build_processed(rewritten, parsed)
                self._basic_sanity_check(processed)
                logger.info(f"Stage4 attempt {attempt} succeeded")
                return processed
            except Stage4Error as e:
                logger.warning(
                    f"Stage4 attempt {attempt}/{MAX_ATTEMPTS} failed: {e}"
                )
                last_error = e
                continue

        raise Stage4Error(
            f"Не удалось оформить LaTeX за {MAX_ATTEMPTS} попыток. "
            f"Последняя ошибка: {last_error}"
        )

    def _call_llm(self, rewritten: RewrittenTask,
                  previous_errors: List[str],
                  previous_output: str,
                  temperature: float) -> str:
        """Вызов Gemini API через GeminiClient."""
        errors_block = build_previous_errors_block(
            previous_errors, previous_output,
        )
        user_prompt = STAGE4_USER.format(
            rewritten_text=rewritten.rewritten_text,
            previous_errors_block=errors_block,
        )
        return self.llm.generate(
            prompt=user_prompt,
            system_prompt=STAGE4_SYSTEM,
            temperature=temperature,
        )

    def _parse_json(self, raw: str) -> dict:
        """Парсинг JSON из ответа LLM (с очисткой markdown-обёрток)."""
        cleaned = raw.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise Stage4Error(
                f"Невалидный JSON: {e}. Raw: {raw[:300]}"
            )

    def _build_processed(self, rewritten: RewrittenTask,
                         data: dict) -> ProcessedTask:
        """Создание ProcessedTask из распарсенного JSON."""
        try:
            return ProcessedTask(
                rewritten=rewritten,
                processed_text=data["processed_text"],
                formulas_count=int(data.get("formulas_count", 0)),
                notes=data.get("notes", ""),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise Stage4Error(f"Отсутствует/некорректно поле: {e}")

    def _basic_sanity_check(self, p: ProcessedTask):
        """
        Минимальные проверки ДО формального Stage 5.
        Здесь только то, что явно сломано и не даёт
        смысла передавать дальше.
        """
        text = p.processed_text

        if len(text) < MIN_LATEX_SIZE:
            raise Stage4Error(
                f"Текст слишком короткий: {len(text)} символов"
            )

        if text.count('$') % 2 != 0:
            raise Stage4Error("Непарное количество $")

        if '$$$' in text:
            raise Stage4Error("Найдено $$$ (скорее всего склейка)")
