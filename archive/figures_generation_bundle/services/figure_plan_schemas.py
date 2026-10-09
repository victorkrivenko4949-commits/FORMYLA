# -*- coding: utf-8 -*-
"""services/figure_plan_schemas.py — Pydantic-схемы двухслойного конвейера.

CH15: Разделяет «условие → JSON» на два независимых плана:

  * BaseFigurePlan — исходная конфигурация, только из условия (без решения);
  * AuxFigurePlan  — diff дополнительных построений, извлечённых из решения;
  * FigureAuditResult — результат LLM-аудита связи условие/чертёж/решение.

Pydantic используется как «мягкая» валидация структуры на уровне приложения.
Если pydantic недоступен — все функции деградируют в ручной JSON-разбор,
но основная семантическая проверка всегда выполняется в
:func:`services.figure_plan_validator.validate_condition_solution`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover - pydantic is a dependency
    _HAS_PYDANTIC = False


# ──────────────────────────────────────────────────────────────────────────
# Конструкции (переиспользуем контракт geometric_engine, но допускаем
# свободные поля — полная строгость в figure_plan_validator).
# ──────────────────────────────────────────────────────────────────────────

class SolutionEvidence(BaseModel):
    """Привязка aux-объекта к конкретному шагу решения."""
    step_no: Optional[int] = Field(default=None, ge=1)
    quote: Optional[str] = None


class Construction(BaseModel):
    """Одно построение. type/id обязательны, остальное — свободно."""
    model_config = ConfigDict(extra="allow")

    type: str
    id: str
    op: Optional[str] = None
    dashed: Optional[bool] = None
    style: Optional[str] = None
    purpose: Optional[str] = None
    solution_evidence: Optional[SolutionEvidence] = None
    # CH15.1: имя точки-результата для операций, создающих новую точку
    # (altitude/median/angle_bisector).  Обязательно по контракту aux-плана,
    # чтобы следующие операции могли на неё ссылаться.
    foot_id: Optional[str] = None
    # CH16: семантическая роль визуализации (enum), не произвольный цвет.
    visual_role: Optional[str] = None


class GivenMark(BaseModel):
    """Метка явно заданного свойства условия (CH15.1)."""
    model_config = ConfigDict(extra="allow")

    type: str
    # Общие поля для разных типов меток (по контракту given_marks).
    segments: Optional[List[Any]] = None
    count: Optional[int] = None
    vertex: Optional[str] = None
    ray1: Optional[str] = None
    ray2: Optional[str] = None
    text: Optional[str] = None
    point: Optional[str] = None
    p1: Optional[str] = None
    p2: Optional[str] = None
    p3: Optional[str] = None


if _HAS_PYDANTIC:

    class SolverTarget(BaseModel):
        """Цель задачи (искомый объект)."""
        kind: str                      # angle | length | ratio | area
        object: str                    # ADC | B | CH | ABC
        description: Optional[str] = None

    class SolverAnswer(BaseModel):
        """Ответ решателя."""
        value: Optional[float] = None
        unit: Optional[str] = None
        exact: Optional[str] = None
        is_numeric: bool = True

    class SolverStep(BaseModel):
        """Шаг решения."""
        no: int
        text: str

    class SolverAuxConstruction(BaseModel):
        """Одно доп. построение из решения (solver-v1)."""
        model_config = ConfigDict(extra="allow")
        op: str
        points: Optional[List[str]] = None
        from_point: Optional[str] = None
        to_line: Optional[List[str]] = None
        to_side: Optional[List[str]] = None
        vertex: Optional[str] = None
        rays: Optional[List[str]] = None
        segment: Optional[List[str]] = None
        point: Optional[str] = None
        circle: Optional[str] = None
        over_line: Optional[List[str]] = None
        line1: Optional[List[str]] = None
        line2: Optional[List[str]] = None
        center: Optional[str] = None
        through: Optional[str] = None
        beyond: Optional[str] = None
        id: Optional[str] = None
        foot_id: Optional[str] = None
        quote: Optional[str] = None
        step_no: Optional[int] = None
        purpose: Optional[str] = None

    class SolverResult(BaseModel):
        """Полный ответ решателя (solver-v1 контракт)."""
        model_config = ConfigDict(extra="forbid")
        solvable: bool = True
        target: Optional[SolverTarget] = None
        answer: Optional[SolverAnswer] = None
        steps: List[SolverStep] = Field(default_factory=list)
        aux_needed: bool = False
        aux_constructions: List[SolverAuxConstruction] = Field(default_factory=list)
        confidence: Optional[float] = None

    class BaseFigurePlan(BaseModel):
        """План исходного чертежа — только объекты, заданные условием."""
        model_config = ConfigDict(extra="allow")

        version: int = 2
        canvas: Optional[Dict[str, Any]] = None
        constructions: List[Construction] = Field(default_factory=list)
        labels: Optional[List[str]] = None
        given_facts: Optional[List[str]] = None
        given_marks: Optional[List[GivenMark]] = None
        assumptions: Optional[List[str]] = None
        aux: Optional[Dict[str, Any]] = None  # has_aux / reason / constructions

    class AuxFigurePlan(BaseModel):
        """Diff дополнительных построений, извлечённых из решения."""
        model_config = ConfigDict(extra="allow")

        has_aux: bool = False
        reason: Optional[str] = None
        constructions: List[Construction] = Field(default_factory=list)
        # CH27 FIX4: построения, которые решение требует, но список action
        # их не покрывает.  При steps=[] и непустом unsupported aux_status
        # должен быть AUX_UNSUPPORTED (а не AUX_NOT_NEEDED).
        unsupported: List[Dict[str, Any]] = Field(default_factory=list)

    class AuditIssue(BaseModel):
        code: str
        message: Optional[str] = None
        solution_step_no: Optional[int] = None

    class FigureAuditResult(BaseModel):
        model_config = ConfigDict(extra="allow")

        approved: bool
        issues: List[AuditIssue] = Field(default_factory=list)

else:  # pragma: no cover - fallback if pydantic missing
    BaseFigurePlan = dict  # type: ignore
    AuxFigurePlan = dict  # type: ignore
    FigureAuditResult = dict  # type: ignore
    AuditIssue = dict  # type: ignore
    SolverResult = dict  # type: ignore
    SolverTarget = dict  # type: ignore
    SolverAnswer = dict  # type: ignore
    SolverStep = dict  # type: ignore
    SolverAuxConstruction = dict  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# Публичные парсеры (soft parse → dict, никогда не кидают исключение наружу)
# ──────────────────────────────────────────────────────────────────────────

def parse_base_plan(raw) -> Optional[Dict[str, Any]]:
    """Разобрать JSON-ответ base_planner в dict (или None при ошибке)."""
    data = _loads(raw)
    if not isinstance(data, dict):
        return None
    if _HAS_PYDANTIC:
        try:
            return BaseFigurePlan.model_validate(data).model_dump()
        except ValidationError:
            # Возвращаем сырой dict — строгая проверка в figure_plan_validator.
            return data
    return data


def parse_aux_plan(raw) -> Optional[Dict[str, Any]]:
    """Разобрать JSON-ответ aux_planner в dict (или None при ошибке)."""
    data = _loads(raw)
    if not isinstance(data, dict):
        return None
    if _HAS_PYDANTIC:
        try:
            return AuxFigurePlan.model_validate(data).model_dump()
        except ValidationError:
            return data
    return data


def parse_audit_result(raw) -> Optional[Dict[str, Any]]:
    """Разобрать JSON-ответ figure_auditor в dict (или None при ошибке)."""
    data = _loads(raw)
    if not isinstance(data, dict):
        return None
    if _HAS_PYDANTIC:
        try:
            return FigureAuditResult.model_validate(data).model_dump()
        except ValidationError:
            return data
    return data


def parse_solver_result(raw) -> Optional[Dict[str, Any]]:
    """Разобрать JSON-ответ solver'а в dict (или None при ошибке)."""
    data = _loads(raw)
    if not isinstance(data, dict):
        return None
    if _HAS_PYDANTIC:
        try:
            return SolverResult.model_validate(data).model_dump()
        except ValidationError:
            return None
    return data


def _loads(raw) -> Any:
    """JSON-разбор строки или прозрачный пропуск dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
