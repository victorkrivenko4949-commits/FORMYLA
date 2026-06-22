# -*- coding: utf-8 -*-
"""
Step 1 пайплайна «Задачи дня» — планировщик (Claude Sonnet 4.6).

Отправляет профиль ученика в планировщика, получает 10 спецификаций задач
(spec'ов) и валидирует их структурно через `validate_gemini_plan()`.

При сбое (HTTP 402 баланс, 429 rate-limit, 5xx, JSON-parse, validation)
**бросает** ``GeminiPlanError`` с классифицированной категорией и человеко-
читаемым сообщением. Это критично: оркестратор и UI получают РЕАЛЬНУЮ
причину сбоя, а не обобщённое "вернул 0 specs".
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any, Dict, List, Optional

from pipeline.openrouter_client import OpenRouterClient, OpenRouterError, TokenUsage
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE
from services.taxonomy_grade6 import get_all_subtopics as get_grade6_subtopics
from services.topic_taxonomy import get_all_subtopics_for_grade
from daily_tasks.anti_repeat import get_recent_tasks_history, format_history_for_prompt

from .validators import (
    GeminiPlanValidation,
    extract_json_safe,
    validate_gemini_plan,
)
from .slot_planner import (
    PlannedSlot,
    check_slots_match_windows,
    plan_slots,
    topic_to_window_summary,
)

logger = logging.getLogger(__name__)

# ── модель ────────────────────────────────────────────────────────────────
# Step 1 PLAN: Claude Sonnet 4.5 — base-модель без reasoning. Reasoning-
# флагманы (gpt-5.5-pro, gemini-3.1-pro) на стриминге 4-5 минут регулярно
# роняют соединение через нестабильный интернет. Sonnet 4.5 уже в проде
_GEMINI_MODEL = "anthropic/claude-sonnet-4.6"


# ──────────────────────────────────────────────────────────────────────
# Классифицированная ошибка планировщика
# ──────────────────────────────────────────────────────────────────────


class GeminiPlanError(Exception):
    """Step 1 PLAN failed with a known, classified reason.

    Оркестратор ловит это исключение и пишет ``str(self)`` в
    ``PipelineResult.error`` и далее в ``DailyGenerationJob.error_message``
    + ``DailyTaskSet.reason_summary``, чтобы UI показал *настоящую* причину
    (HTTP-код, parse-error, validation-issue) — а не обобщённое
    "Gemini вернул 0 specs".
    """

    def __init__(
        self,
        message: str,
        category: str = "unknown",
        status_code: int = 0,
        body_snippet: str = "",
    ):
        super().__init__(message)
        # 'http_402' | 'http_429' | 'http_4xx' | 'http_5xx' |
        # 'network'  | 'parse'    | 'validate' | 'unknown'
        self.category = category
        self.status_code = status_code
        self.body_snippet = body_snippet


def _classify_openrouter_error(exc: OpenRouterError) -> str:
    """Map HTTP status from OpenRouterError to short human category."""
    code = getattr(exc, "status_code", 0) or 0
    if code == 402:
        return "http_402"          # payment required (balance / credit limit)
    if code == 429:
        return "http_429"          # rate limit
    if 400 <= code < 500:
        return f"http_{code}"
    if 500 <= code < 600:
        return f"http_{code}"
    return "network"


# ── helpers ───────────────────────────────────────────────────────────────


def _build_topics_reference(class_level: int) -> Dict[str, Any]:
    """Построить `TOPICS_REFERENCE` — словарь «тема → подтемы» для класса.

    Используемые источники в зависимости от класса:

    *   5 класс — `services/topic_taxonomy.py` (фильтр по grade=5)
    *   6 класс — `services/taxonomy_grade6.py` (специализированный справочник)
    *   7–11    — `services/adaptive_topics_registry.py` (7 тем на класс)
    """
    if class_level == 6:
        raw = get_grade6_subtopics()  # [(topic, key, label), ...]
        ref: Dict[str, Any] = {}
        for topic, key, label in raw:
            ref.setdefault(topic, []).append({"key": key, "label": label})
        return ref

    if class_level <= 5:
        raw = get_all_subtopics_for_grade(class_level)  # [(topic, subtopic), ...]
        ref: Dict[str, Any] = {}
        for topic, subtopic in raw:
            ref.setdefault(topic, []).append(subtopic)
        return ref

    # 7–11 классы — ADAPTIVE_TOPICS_BY_GRADE
    topics = ADAPTIVE_TOPICS_BY_GRADE.get(class_level, [])
    return {t["db_topic"]: [] for t in topics}


def _load_prompt() -> str:
    """Загрузить содержимое `prompts/gemini_plan.md`."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "gemini_plan.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_prompt(
    profile: Dict[str, Any],
    topics_ref: Dict[str, Any],
    planned_slots: List[PlannedSlot],
) -> str:
    """Подставить переменные в prompt-шаблон.

    PR per-topic difficulty matching: дополнительно передаём в промпт
    SLOT_PLAN — список из 10 заранее заполненных слотов с topic+
    difficulty_level. LLM ОБЯЗАНА сохранить эти поля без изменений
    и только обогатить spec текстовыми полями (archetype, must_use,
    reason_for_student и т.д.).
    """
    prompt = _load_prompt()
    slot_alloc = profile.get("slot_allocation") or {
        "measured": 10,
        "calibration": 0,
    }
    completeness = float(profile.get("profile_completeness", 1.0) or 1.0)

    # Текстовая сводка «тема → окно сложности» для подсказки LLM
    summary = topic_to_window_summary(planned_slots)
    window_lines: List[str] = []
    for topic, rec in summary.items():
        cal = " (КАЛИБРОВКА)" if rec["is_calibration"] else ""
        score = ""
        if rec.get("test_total"):
            score = f", тест {rec['test_correct']}/{rec['test_total']}"
        window_lines.append(
            f"  • {topic}{cal}{score} → "
            f"target=L{rec['target_level']}, окно [L{rec['window'][0]}, L{rec['window'][1]}], "
            f"запланированные уровни: {rec['levels']}"
        )
    topic_window_summary = "\n".join(window_lines) if window_lines else "(нет данных)"
    
    # Anti-repeat across cycles: история ранее выданных задач по темам дня.
    recent_history = get_recent_tasks_history(profile.get("user_id"))
    planned_topics: List[str] = []
    for s in planned_slots:
        if s.topic and s.topic not in planned_topics:
            planned_topics.append(s.topic)
    history_blocks: List[str] = []
    for _topic in planned_topics:
        history_blocks.append(
            f"Тема <<{_topic}>>:\n" + format_history_for_prompt(recent_history, _topic)
        )
    recent_tasks_for_topic = "\n\n".join(history_blocks) if history_blocks else "(нет данных)"

    # Полный план слотов как JSON — LLM должна сохранить эти поля 1:1
    slot_plan_json = json.dumps(
        [s.to_spec_seed() for s in planned_slots],
        ensure_ascii=False, indent=2,
    )

    return prompt.format(
        weak_topics=json.dumps(profile["weak_topics"], ensure_ascii=False, indent=2),
        strong_topics=json.dumps(profile["strong_topics"], ensure_ascii=False, indent=2),
        class_level=profile["class_level"],
        class_expected_level=profile["class_expected_level"],
        TOPICS_REFERENCE=json.dumps(topics_ref, ensure_ascii=False, indent=2),
        slot_allocation=json.dumps(slot_alloc, ensure_ascii=False),
        profile_completeness=f"{completeness:.2f}",
        SLOT_PLAN=slot_plan_json,
        TOPIC_WINDOW_SUMMARY=topic_window_summary,
        RECENT_TASKS_FOR_TOPIC=recent_tasks_for_topic,
    )


# ── основная функция ─────────────────────────────────────────────────────


async def generate_gemini_plan(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Сгенерировать 10 спецификаций задач через планировщика.

    Параметры
    ---------
    profile : dict
        Результат `build_profile(user_id)` — содержит ``weak_topics``,
        ``strong_topics``, ``class_level``, ``class_expected_level`` и пр.

    Возвращает
    ----------
    list[dict]
        10 валидированных spec'ов (каждый — словарь с ключами ``position``,
        ``slot_kind``, ``subject``, ``topic``, ``subtopic``,
        ``difficulty_level``, …).

    Raises
    ------
    GeminiPlanError
        При сбое OpenRouter, парсинга JSON или валидации структуры.
        ``str(exc)`` содержит человекочитаемое объяснение (включая HTTP-код).
    """
    class_level = profile["class_level"]
    topics_ref = _build_topics_reference(class_level)

    # ── PER-TOPIC DIFFICULTY MATCHING ────────────────────────────────
    # Детерминированно строим план 10 слотов ДО вызова LLM:
    # каждый слот уже знает topic + difficulty_level (из окна темы).
    planned_slots = plan_slots(profile)
    if len(planned_slots) != 10:
        raise GeminiPlanError(
            f"slot_planner вернул {len(planned_slots)} слотов вместо 10 — "
            "проверь профиль (weak_topics/strong_topics/calibration пусты?)",
            category="validate",
        )

    formatted_prompt = _format_prompt(profile, topics_ref, planned_slots)

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": formatted_prompt},
    ]

    # ── вызов планировщика через OpenRouter ──────────────────────────
    raw_response: str
    usage: TokenUsage

    try:
        async with OpenRouterClient() as client:
            raw_response, usage = await client.chat(
                model=_GEMINI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=16384,
            )
    except OpenRouterError as exc:
        # Classified HTTP / API error — propagate with status_code & snippet
        category = _classify_openrouter_error(exc)
        body_snippet = (getattr(exc, "body", "") or "")[:300]
        logger.exception(
            "Step 1 PLAN — OpenRouter call to %s failed: status=%s category=%s body=%s",
            _GEMINI_MODEL, exc.status_code, category, body_snippet,
        )
        if category == "http_402":
            human = (
                "Закончился баланс OpenRouter (HTTP 402). "
                "Пополни счёт на openrouter.ai/credits и попробуй снова."
            )
        elif category == "http_429":
            human = (
                "Слишком много запросов к OpenRouter (HTTP 429). "
                "Подожди минуту и повтори."
            )
        elif category.startswith("http_5"):
            human = (
                f"Временный сбой OpenRouter ({exc.status_code}). "
                "Повтори через минуту."
            )
        elif category.startswith("http_4"):
            human = (
                f"Ошибка запроса к OpenRouter ({exc.status_code}). "
                "Проверь конфигурацию."
            )
        else:
            human = f"Сбой связи с OpenRouter: {exc}"
        raise GeminiPlanError(
            human, category=category,
            status_code=exc.status_code, body_snippet=body_snippet,
        ) from exc
    except Exception as exc:
        # Network / timeout / asyncio.CancelledError / etc.
        logger.exception(
            "Step 1 PLAN — call to %s crashed: %s",
            _GEMINI_MODEL, exc,
        )
        raise GeminiPlanError(
            f"Сбой при вызове планировщика: {type(exc).__name__}: {exc}",
            category="network",
        ) from exc

    logger.info(
        "Gemini plan — токены: %d in / %d out, стоимость: $%.6f",
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
    )

    logger.info(
        "Gemini plan — raw response длина: %d символов",
        len(raw_response) if raw_response else 0,
    )

    # DEBUG: dump raw response to file for inspection
    try:
        with open("_gemini_last_response.txt", "w", encoding="utf-8") as _f:
            _f.write(raw_response or "(EMPTY)")
    except Exception:
        pass

    # ── валидация ────────────────────────────────────────────────────
    validation: GeminiPlanValidation = validate_gemini_plan(raw_response)

    if not validation.valid:
        err_summary = "; ".join(validation.all_errors[:5]) or "validation failed"
        logger.error(
            "Gemini plan — ошибки валидации (%d): %s",
            len(validation.all_errors), err_summary,
        )
        tail = raw_response[-800:] if raw_response else "(EMPTY)"
        logger.error("Gemini raw response END (last 800 chars): %s", tail)
        raise GeminiPlanError(
            f"Ответ модели не прошёл валидацию: {err_summary}",
            category="validate",
            body_snippet=tail[:300],
        )

    # ── парсинг JSON ─────────────────────────────────────────────────
    parsed: Optional[Dict[str, Any]] = extract_json_safe(raw_response)
    if parsed is None or "specs" not in parsed:
        raise GeminiPlanError(
            "Не удалось извлечь JSON со spec'ами из ответа модели",
            category="parse",
            body_snippet=(raw_response or "")[-300:],
        )

    specs: List[Dict[str, Any]] = parsed["specs"]
    if not isinstance(specs, list) or len(specs) != 10:
        raise GeminiPlanError(
            f"Модель вернула {len(specs) if isinstance(specs, list) else 'не-list'} spec'ов вместо 10",
            category="validate",
        )

    # ── PER-TOPIC DIFFICULTY MATCHING: enforcing the plan ────────────
    # LLM могла «креативно» поменять topic / difficulty_level. Источник
    # истины — planned_slots. Перезаписываем критичные поля и логируем,
    # если что-то расходилось. Текстовые поля (archetype, must_use,
    # reason_for_student, ...) оставляем как пришли от LLM.
    by_pos = {s.position: s for s in planned_slots}
    mismatches_before = check_slots_match_windows(specs, planned_slots)
    if mismatches_before:
        logger.warning(
            "Step 1 PLAN: %d slot(s) had difficulty OUT of topic window — "
            "rewriting from slot_planner: %s",
            len(mismatches_before), mismatches_before,
        )

    enforced_specs: List[Dict[str, Any]] = []
    for spec in specs:
        pos = spec.get("position")
        planned = by_pos.get(pos)
        if planned is None:
            # LLM выдала чужой position — пропускаем, потом отловит validation
            enforced_specs.append(spec)
            continue
        merged = dict(spec)
        # Жёстко берём topic / subject / difficulty / level_window из плана:
        merged["topic"] = planned.topic
        merged["subject"] = planned.subject
        merged["topic_key"] = planned.topic_key
        merged["slot_kind"] = planned.slot_kind
        merged["difficulty_level"] = planned.difficulty_level
        merged["target_level"] = planned.target_level
        merged["level_window"] = list(planned.level_window)
        merged["is_calibration"] = planned.is_calibration
        merged["measured"] = planned.measured
        # weakness_score legacy для DailyTaskItem
        if planned.pct is not None:
            merged.setdefault("weakness_score", round(100.0 - planned.pct, 2))
        enforced_specs.append(merged)

    # Re-check after enforcement (sanity).
    mismatches_after = check_slots_match_windows(enforced_specs, planned_slots)
    if mismatches_after:
        logger.error(
            "Step 1 PLAN: mismatches REMAIN after enforcement: %s",
            mismatches_after,
        )

    # ── лог-сводка: тема → уровни (для аудита) ───────────────────────
    enforced_summary: Dict[str, List[int]] = {}
    for spec in enforced_specs:
        enforced_summary.setdefault(spec.get("topic") or "?", []).append(
            spec.get("difficulty_level")
        )
    plan_summary = topic_to_window_summary(planned_slots)
    for topic, levels in enforced_summary.items():
        rec = plan_summary.get(topic, {})
        score = ""
        if rec.get("test_total"):
            score = f" {rec['test_correct']}/{rec['test_total']}"
        logger.info(
            "Step 1 plan match: %s%s window=%s levels=%s",
            topic, score, rec.get("window"), levels,
        )

    logger.info(
        "Gemini plan — OK: %d specs, cost=$%.4f, enforced=%d slots",
        len(enforced_specs), usage.cost_usd, len(enforced_specs),
    )
    return enforced_specs
