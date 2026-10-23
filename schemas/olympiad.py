# -*- coding: utf-8 -*-
"""Pydantic v2 schemas for the «Olympiads» section (`/olympiads/*`).

Used by `scripts/import_olympiad.py` and the section routes to strictly
validate input JSON files before writing to the DB.

IMPORTANT: Do **not** import from `models_olympiad` here.  `models_olympiad`
itself imports `db` from `models`, and `models.py` does a late re-export
from `models_olympiad`.  Pulling the chain through this schema module
would cause a circular import on Render startup.  The literals below are
the single source of truth — `models_olympiad` re-imports THESE values
via duck-typing (see `tests/test_olympiad_schema.py`).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Enum-style literals.  MUST stay in sync with the matching tuples in
# `models_olympiad.py` (the test suite checks this — see test_olympiad_schema).
ProbnikTypeLiteral = Literal['topic', 'stage']
DifficultyLiteral = Literal['green', 'yellow', 'orange', 'red']
SectionLiteral = Literal['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
StageResultLiteral = Literal['participant', 'prize', 'winner']


class _Strict(BaseModel):
    """Base config: forbid unknown fields so JSON imports fail loudly."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


# ─────────────────────── TheoryBlock ───────────────────────

class TheoryBlockSchema(_Strict):
    """One theory block from `*_theory.json`."""

    method_code: str = Field(min_length=1, max_length=10)
    method_name: str = Field(min_length=1, max_length=200)
    section: Optional[SectionLiteral] = None

    definition_md: Optional[str] = None
    main_theorems_md: Optional[str] = None
    typical_techniques_md: Optional[str] = None
    triggers_md: Optional[str] = None
    worked_example_md: Optional[str] = None
    pitfalls_md: Optional[str] = None

    related_methods: List[str] = Field(default_factory=list)

    @field_validator('related_methods')
    @classmethod
    def _no_self_reference(cls, v, info):
        code = info.data.get('method_code')
        if code and code in v:
            raise ValueError("related_methods of %r contains itself" % code)
        return v


# ─────────────────────── Task ───────────────────────

class TaskSchema(_Strict):
    """One probnik task from `*_tasks.json`."""

    probnik_code: str = Field(min_length=1, max_length=50)
    number: str = Field(min_length=1, max_length=10)
    sort_order: int = Field(default=0, ge=0)

    difficulty: Optional[DifficultyLiteral] = None

    method_primary: str = Field(min_length=1, max_length=10)
    method_secondary: Optional[str] = Field(default=None, max_length=10)

    condition_md: str = Field(min_length=1)
    idea_md: str = Field(min_length=1)
    solution_md: str = Field(min_length=1)
    answer: Optional[str] = Field(default=None, max_length=500)

    source_prototype: Optional[str] = Field(default=None, max_length=500)
    estimated_minutes: Optional[int] = Field(default=None, ge=0, le=600)
    max_score: int = Field(default=7, ge=0, le=100)


# ─────────────────────── Probnik ───────────────────────

class ProbnikTheoryLinkSchema(_Strict):
    """Reference to a theory block for a topic probnik."""

    method_code: str = Field(min_length=1, max_length=10)
    order: int = Field(default=0, ge=0)


class ProbnikSchema(_Strict):
    """One probnik from `*_probniks.json`.

    For stage probniks (`type == 'stage'`) `duration_minutes` and
    `max_score` are required.  We use a `model_validator` because
    `field_validator` runs per field and cannot reliably enforce a
    "field-B required iff field-A == X" rule on optional defaults.
    """

    code: str = Field(min_length=1, max_length=50)
    type: ProbnikTypeLiteral
    number: int = Field(ge=1, le=99)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None

    competition: str = Field(default='ВсОШ',
                             min_length=1, max_length=50)
    grade: int = Field(default=9, ge=1, le=11)
    season_year: int = Field(default=2027, ge=2000, le=2100)

    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    max_score: Optional[int] = Field(default=None, ge=1, le=500)
    threshold_prize: Optional[int] = Field(default=None, ge=0, le=500)
    threshold_winner: Optional[int] = Field(default=None, ge=0, le=500)

    sort_order: int = Field(default=0, ge=0)
    is_published: bool = True

    theory: List[ProbnikTheoryLinkSchema] = Field(default_factory=list)

    @field_validator('threshold_winner')
    @classmethod
    def _winner_ge_prize(cls, v, info):
        if v is None:
            return v
        prize = info.data.get('threshold_prize')
        if prize is not None and v < prize:
            raise ValueError(
                "threshold_winner (%s) < threshold_prize (%s)" % (v, prize)
            )
        return v

    def model_post_init(self, __context):
        """Cross-field validation: stage probniks require timing/scoring fields.

        Called by Pydantic AFTER all field validators, when `self.type` and
        `self.duration_minutes` etc. are already populated. This is the
        cleanest way to express "if type='stage' then these fields cannot
        be None".
        """
        if self.type == 'stage':
            missing = []
            if self.duration_minutes is None:
                missing.append('duration_minutes')
            if self.max_score is None:
                missing.append('max_score')
            if missing:
                raise ValueError(
                    "stage probnik %r is missing required fields: %s"
                    % (self.code, ', '.join(missing))
                )


__all__ = [
    'TheoryBlockSchema',
    'TaskSchema',
    'ProbnikSchema',
    'ProbnikTheoryLinkSchema',
    'ProbnikTypeLiteral',
    'DifficultyLiteral',
    'SectionLiteral',
    'StageResultLiteral',
]
