# -*- coding: utf-8 -*-
"""
Stage 2: Переписывание задачи-прототипа через DeepSeek.
"""
import json
import logging
import re
from difflib import SequenceMatcher
from .types import FoundTask, RewrittenTask
from .prompts.stage2 import STAGE2_SYSTEM, STAGE2_USER

logger = logging.getLogger(__name__)

MIN_CHANGES = 3
MAX_SIMILARITY = 0.75  # если текст почти не изменился — отказ
MIN_SIMILARITY = 0.05  # если совсем другой — скорее всего галлюцинация
MAX_ATTEMPTS = 3


class Stage2Error(Exception):
    """Ошибка этапа переписывания."""
    pass


class Stage2Rewrite:
    """Переписывает прототип задачи, сохраняя метод решения."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: DeepSeekClient instance с методом
                        generate(prompt, system_prompt, temperature, max_tokens)
        """
        self.llm = llm_client

    def rewrite(self, found: FoundTask) -> RewrittenTask:
        """
        Переписывает задачу: меняет числа, контекст, формулировку.

        Делает до MAX_ATTEMPTS попыток с повышенной температурой.

        Args:
            found: прототип задачи из Stage 1

        Returns:
            RewrittenTask с переписанным текстом

        Raises:
            Stage2Error: если все попытки исчерпаны
        """
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                temperature = 0.7 + 0.1 * (attempt - 1)
                raw = self._call_llm(found, temperature=temperature)
                parsed = self._parse_json(raw)
                rewritten = self._build_rewritten(found, parsed)
                self._validate(rewritten, found)
                logger.info(f"Stage2 success on attempt {attempt}")
                return rewritten
            except Stage2Error as e:
                logger.warning(
                    f"Stage2 attempt {attempt}/{MAX_ATTEMPTS} failed: {e}"
                )
                last_error = e
                continue

        raise Stage2Error(
            f"Не удалось переписать за {MAX_ATTEMPTS} попыток. "
            f"Последняя ошибка: {last_error}"
        )

    def _call_llm(self, found: FoundTask, temperature: float) -> str:
        """Вызов DeepSeek API."""
        user_prompt = STAGE2_USER.format(
            olympiad=found.olympiad,
            year=found.year,
            grade=found.grade,
            topic=found.topic,
            difficulty=found.difficulty,
            original_text=found.original_text,
        )
        return self.llm.generate(
            prompt=user_prompt,
            system_prompt=STAGE2_SYSTEM,
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
            raise Stage2Error(
                f"Невалидный JSON: {e}. Сырой ответ: {raw[:300]}"
            )

    def _build_rewritten(self, found: FoundTask, data: dict) -> RewrittenTask:
        """Создание RewrittenTask из распарсенного JSON."""
        try:
            return RewrittenTask(
                original=found,
                rewritten_text=data["rewritten_text"],
                changes=list(data.get("changes", [])),
                method_preserved=data.get("method_preserved", ""),
                difficulty_same=bool(data.get("difficulty_same", True)),
            )
        except (KeyError, TypeError) as e:
            raise Stage2Error(f"Отсутствует/некорректно поле: {e}")

    def _validate(self, r: RewrittenTask, found: FoundTask):
        """Валидация переписанной задачи."""
        text = r.rewritten_text

        # Минимальная длина
        if len(text) < 30:
            raise Stage2Error(
                f"Текст слишком короткий: {len(text)} символов"
            )

        # LaTeX-утечки
        if '\\' in text:
            raise Stage2Error("LaTeX-утечка: обратный слэш в тексте")
        if '$' in text:
            raise Stage2Error("LaTeX-утечка: символ $ в тексте")

        # Минимум изменений
        if len(r.changes) < MIN_CHANGES:
            raise Stage2Error(
                f"Изменений {len(r.changes)} < {MIN_CHANGES}"
            )

        # Метод решения указан
        if not r.method_preserved:
            raise Stage2Error("Не указан сохранённый метод")

        # Сложность сохранена
        if not r.difficulty_same:
            raise Stage2Error(
                "Модель сообщила что сложность не сохранена"
            )

        # Проверка похожести на прототип
        similarity = SequenceMatcher(
            None, found.original_text.lower(), text.lower()
        ).ratio()
        if similarity > MAX_SIMILARITY:
            raise Stage2Error(
                f"Текст слишком похож на прототип: "
                f"similarity={similarity:.2f} > {MAX_SIMILARITY}"
            )
        if similarity < MIN_SIMILARITY:
            raise Stage2Error(
                f"Текст подозрительно не похож на прототип: "
                f"similarity={similarity:.2f} < {MIN_SIMILARITY}"
            )

        # Намёки на решение
        forbidden_hints = [
            'решение:', 'ответ:', 'заметим, что',
            'очевидно, что', 'используйте',
        ]
        lower = text.lower()
        for hint in forbidden_hints:
            if hint in lower:
                raise Stage2Error(
                    f"Намёк на решение в тексте: '{hint}'"
                )
