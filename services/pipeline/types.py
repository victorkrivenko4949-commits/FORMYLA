# -*- coding: utf-8 -*-
"""
Dataclasses для передачи данных между этапами пайплайна.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class FoundTask:
    """Результат Stage 1 — найденный прототип задачи."""
    olympiad: str
    year: int
    stage: str
    grade: int
    problem_number: int
    topic: str
    difficulty: str
    original_text: str
    author: Optional[str] = None
    confidence: float = 0.0


@dataclass
class RewrittenTask:
    """Результат Stage 2 — переписанная задача."""
    original: FoundTask
    rewritten_text: str
    solution: str = ""
    answer: str = ""
    changes: List[str] = field(default_factory=list)
    method_preserved: str = ""
    difficulty_same: bool = True


@dataclass
class ProcessedTask:
    """Результат Stage 4 — задача с правильным LaTeX."""
    rewritten: RewrittenTask
    processed_text: str
    processed_solution: str = ""
    formulas_count: int = 0
    notes: str = ""


@dataclass
class ValidationResult:
    """Результат Stage 5 — валидация LaTeX."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Финальный результат одной задачи для сохранения."""
    task_id: int = 0
    variant_id: str = ""
    position: int = 0
    final_text: str = ""
    final_solution: str = ""
    final_answer: str = ""
    topic: str = ""
    original_text: str = ""
    source_year: int = 0
    source_problem: int = 0
    author: Optional[str] = None
    stages_log: List[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class PipelineError(Exception):
    """Базовая ошибка пайплайна."""
    def __init__(self, stage: str, message: str, attempts: int = 0):
        self.stage = stage
        self.attempts = attempts
        super().__init__(f"[{stage}] {message} (attempts={attempts})")
