# -*- coding: utf-8 -*-
"""
Pydantic-модели для валидации JSON-ответов от нейросетей.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ─── Generator output ─────────────────────────────────────────────────────────

class GeneratorOutput(BaseModel):
    """JSON-ответ от Generator."""
    statement: str = Field(..., description="Условие задачи в LaTeX")
    answer_type: str = Field(
        ...,
        description="Тип ответа: число|выражение|доказательство|пример+оценка|перечисление",
    )
    expected_answer_short: str = Field(..., description="Краткий ответ")
    key_ideas: List[str] = Field(default_factory=list, description="Ключевые идеи решения")
    techniques: List[str] = Field(default_factory=list, description="Используемые приёмы")
    estimated_steps: int = Field(..., ge=1, le=20, description="Оценка числа шагов")
    why_this_level: str = Field(..., description="Почему именно этот уровень")
    anti_pattern_check: str = Field(
        ..., description="Почему НЕ уровень N-1 и НЕ N+1"
    )

    @field_validator("answer_type")
    @classmethod
    def validate_answer_type(cls, v: str) -> str:
        # Канон из ТЗ + типичные синонимы для устойчивости к капризам LLM.
        # Нормализуем синонимы → канонический тип.
        v_norm = (v or "").strip().lower()
        synonyms = {
            "число": "число",
            "числовой": "число",
            "численный ответ": "число",
            "выражение": "выражение",
            "формула": "выражение",
            "доказательство": "доказательство",
            "докажите": "доказательство",
            "доказать": "доказательство",
            "пример+оценка": "пример+оценка",
            "пример + оценка": "пример+оценка",
            "оценка+пример": "пример+оценка",
            "перечисление": "перечисление",
            "множество": "перечисление",
            "интервал": "перечисление",
            "неравенство": "перечисление",
            "решение неравенства": "перечисление",
            "уравнение": "перечисление",
            "корни": "перечисление",
        }
        if v_norm in synonyms:
            return synonyms[v_norm]
        allowed = {"число", "выражение", "доказательство", "пример+оценка", "перечисление"}
        if v in allowed:
            return v
        raise ValueError(f"answer_type must be one of {allowed}, got '{v}'")


# ─── Validator output ─────────────────────────────────────────────────────────

class ValidatorIssue(BaseModel):
    """Одна проблема, найденная Validator."""
    type: str
    description: str
    severity: str = Field(..., description="blocker|major|minor")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"blocker", "major", "minor"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {allowed}, got '{v}'")
        return v


class ValidatorOutput(BaseModel):
    """JSON-ответ от Validator."""
    verdict: str = Field(..., description="PASS или FAIL")
    issues: List[ValidatorIssue] = Field(default_factory=list)
    fix_hint: str = Field(default="", description="Подсказка для исправления")

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        if v not in ("PASS", "FAIL"):
            raise ValueError(f"verdict must be PASS or FAIL, got '{v}'")
        return v


# ─── Calibrator output ────────────────────────────────────────────────────────

class CalibratorOutput(BaseModel):
    """JSON-ответ от Calibrator."""
    predicted_level: int = Field(..., ge=1, le=7)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    ideas_required: List[str] = Field(default_factory=list)
    verdict: str = Field(..., description="PASS или FAIL")
    suggested_level: int = Field(..., ge=1, le=7)
    fix_hint: str = Field(default="")

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        if v not in ("PASS", "FAIL"):
            raise ValueError(f"verdict must be PASS or FAIL, got '{v}'")
        return v


# ─── Pipeline result ──────────────────────────────────────────────────────────

class PipelineResult(BaseModel):
    """Итоговый результат одного прогона пайплайна."""
    success: bool
    task: Optional[GeneratorOutput] = None
    validator_result: Optional[ValidatorOutput] = None
    calibrator_result: Optional[CalibratorOutput] = None
    iterations: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    error: Optional[str] = None
    sent_to_review: bool = False
