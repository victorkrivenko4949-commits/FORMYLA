# -*- coding: utf-8 -*-
"""
Step 1 пайплайна «Задачи дня» — планировщик (Claude Sonnet 4.6).

Отправляет профиль ученика в планировщика, получает 10 спецификаций задач
(spec'ов) и валидирует их структурно через `validate_gemini_plan()`.

+ generate_gemini_thematic_plan — упрощённый планировщик для «Тематического дня».

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

from services.openrouter_client import OpenRouterClient, OpenRouterError, TokenUsage, make_token_usage
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
    plan_slots_for_subtopic,
    plan_slots,
    topic_to_window_summary,
)

logger = logging.getLogger(__name__)

# ── модель ────────────────────────────────────────────────────────────────
# Step 1 PLAN: Claude Sonnet 4.5 — base-модель без reasoning. Reasoning-
# флагманы (gpt-5.5-pro, gemini-3.1-pro) на стриминге 4-5 минут регулярно
# роняют соединение через нестабильный интернет. Sonnet 4.5 уже в проде
_GEMINI_MODEL = "deepseek/deepseek-chat-v3.1"  # vse etapy na DeepSeek (deshevo)

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


DIVERSITY_RULES = """
=== ПРАВИЛА РАЗНООБРАЗИЯ (2026-06-21) ===
1. Каждая из 10 задач имеет свою подтему + свой метод решения (из subtopic_hints и reason_hint).
2. Подтема и метод для задачи №1 определяются днём и классом из слота[0].
3. Задача №i получает подтему и метод строго из своего слота (subtopic_hints[i-1], reason_hint).
4. Сложность (difficulty_level) меняется ТОЛЬКО внутри level_window каждого слота.
5. ЗАПРЕЩЕНО менять topic, class_level (grade), difficulty_level.
6. ЗАПРЕЩЕНО повторять subtopic в нескольких задачах, если в каталоге достаточно подтем.
7. ЗАПРЕЩЕНО повторять method в нескольких задачах.
8. Используй subtopic_hints и reason_hint из SLOT_PLAN как единственные источники подтемы/метода.
""".strip()


def build_forbidden_block(
    used: List[Dict[str, Any]],
    recent_pool_tasks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Сформировать текст \"ЧТО ГЕНЕРИРОВАТЬ ЗАПРЕЩЕНО\" для промпта.

    Parameters
    ----------
    used : list[dict]
        Результат ``assign_diversity()`` — по 1 записи на слот с ключами
        position, topic, subtopic, method, level, note.
    recent_pool_tasks : list[dict], optional
        Недавние задачи из пула (чтобы не повторять их сюжеты/числа).

    Returns
    -------
    str
        Многострочный блок \"ЧТО ГЕНЕРИРОВАТЬ ЗАПРЕЩЕНО\".
    """
    lines: List[str] = []
    lines.append("=== ЧТО ГЕНЕРИРОВАТЬ ЗАПРЕЩЕНО ===")
    lines.append("")

    if not used:
        lines.append("(Нет данных о разнообразии — ограничений нет)")
        return "\n".join(lines)

    # По каждой занятой связке «подтема + метод»
    lines.append("Каждая задача закреплена за своей парой (подтема, метод):")
    for entry in used:
        pos = entry.get("position", "?")
        topic = entry.get("topic", "?")
        sub = entry.get("subtopic", "?")
        method = entry.get("method", "?")
        lvl = entry.get("level", "?")
        note = entry.get("note", "")
        note_str = f" ({note})" if note else ""
        lines.append(
            f"  #{pos}: topic=«{topic}» subtopic=«{sub}» method=«{method}» "
            f"level=L{lvl}{note_str}"
        )

    lines.append("")
    lines.append("ЖЁСТКИЕ ЗАПРЕТЫ:")
    lines.append("- НЕЛЬЗЯ менять topic / class_level / difficulty_level — они фиксированы.")
    lines.append("- НЕЛЬЗЯ использовать subtopic или method не из назначенного слота.")
    lines.append("- НЕЛЬЗЯ назначать одну и ту же подтему двум разным задачам.")
    lines.append("- НЕЛЬЗЯ назначать один и тот же метод двум разным задачам.")
    lines.append("- НЕЛЬЗЯ повторять сюжет/числа из недавних задач (см. ниже).")

    # Recent-pool запреты
    if recent_pool_tasks:
        lines.append("")
        lines.append("НЕДАВНИЕ ЗАДАЧИ (НЕ ПОВТОРЯТЬ СЮЖЕТЫ/ЧИСЛА):")
        for i, task in enumerate(recent_pool_tasks[:10], 1):
            snippet = str(task.get("task_text", task.get("title", "")))[:120]
            lines.append(f"  {i}. {snippet}")

    lines.append("")
    lines.append(
        "Нарушение любого из этих запретов приведёт к тому, что "
        "набор задач будет отклонён автоматической проверкой."
    )

    return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────


def _build_topics_reference(class_level: int) -> Dict[str, Any]:
    """Построить `TOPICS_REFERENCE` — словарь «тема -> подтемы» для класса.

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

    # Текстовая сводка «тема -> окно сложности» для подсказки LLM
    summary = topic_to_window_summary(planned_slots)
    window_lines: List[str] = []
    for topic, rec in summary.items():
        cal = " (КАЛИБРОВКА)" if rec["is_calibration"] else ""
        score = ""
        if rec.get("test_total"):
            score = f", тест {rec['test_correct']}/{rec['test_total']}"
        window_lines.append(
            f"  • {topic}{cal}{score} -> "
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

    prompt = prompt.format(
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

    # ── DIVERSITY BLOCK ───────────────────────────────────────────────
    prompt += "\n\n" + DIVERSITY_RULES + "\n\n" + build_forbidden_block(
        profile.get("_diversity_used", []),
        profile.get("_recent_pool_tasks", []),
    )
    return prompt


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

            # PER-TOPIC DIFFICULTY MATCHING
    _curator_sub = profile.get("curator_subtopic") or {}
    if _curator_sub.get("slug"):
        planned_slots = plan_slots_for_subtopic(
            profile,
            _curator_sub.get("day_topic") or {},
            _curator_sub.get("slug", ""),
            _curator_sub.get("name", ""),
            day_index=int(_curator_sub.get("day_index", 0) or 0),
        )
    else:
        planned_slots = plan_slots(profile)
    if not planned_slots:
        raise GeminiPlanError(
            f"slot_planner вернул 0 слотов — "
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

    # ── лог-сводка: тема -> уровни (для аудита) ───────────────────────
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


# ══════════════════════════════════════════════════════════════════════════
# Thematic day planner
# ══════════════════════════════════════════════════════════════════════════


def _build_thematic_slot_plan(subject: str) -> List[Dict[str, Any]]:
    """Построить простой план из 10 слотов с нарастающей сложностью.

    Для тематического дня нет данных адаптивных тестов, поэтому slot_kind
    для всех слотов — ``calibration``, а difficulty_level ступенчато растёт
    с 1 до 7 (первые 2 слота L1, затем L2, L3, и т.д.).
    """
    difficulty_map = [1, 1, 2, 2, 3, 3, 4, 5, 6, 7]
    slots: List[Dict[str, Any]] = []
    for pos in range(1, 11):
        slots.append({
            "position": pos,
            "slot_kind": "calibration",
            "subject": subject,
            "topic": "",
            "topic_key": "",
            "difficulty_level": difficulty_map[pos - 1],
            "target_level": 1,
            "level_window": [1, 8],
            "is_calibration": True,
            "measured": False,
            "pct": None,
            "test_correct": None,
            "test_total": None,
            "final_level": None,
            "subtopic_hints": [],
            "reason_hint": "",
        })
    return slots


def _load_thematic_prompt() -> str:
    """Загрузить содержимое ``prompts/gemini_thematic_plan.md``."""
    prompt_path = os.path.join(
        os.path.dirname(__file__), "prompts", "gemini_thematic_plan.md",
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_thematic_prompt(
    profile: Dict[str, Any],
    slot_plan: List[Dict[str, Any]],
) -> str:
    """Подставить переменные в thematic prompt-шаблон.

    Параметры
    ---------
    profile : dict
        Минимальный профиль от ``build_thematic_profile()`` — содержит
        ``class_level`` и ``subject_constraint``.
    slot_plan : list[dict]
        10 слотов с предопределёнными position / difficulty_level / subject.
    """
    prompt = _load_thematic_prompt()
    slot_plan_json = json.dumps(slot_plan, ensure_ascii=False, indent=2)
    return prompt.format(
        class_level=profile["class_level"],
        subject_constraint=profile["subject_constraint"],
        SLOT_PLAN=slot_plan_json,
    )


async def generate_gemini_thematic_plan(
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Сгенерировать 10 спецификаций для тематического дня.

    Упрощённая версия ``generate_gemini_plan()`` — без ссылок на
    адаптивные тесты, weak/strong topics, per-topic difficulty matching.

    Параметры
    ---------
    profile : dict
        Результат ``build_thematic_profile(user_id, subject)`` — содержит
        ``class_level``, ``subject_constraint``, ``class_expected_level``.

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
    """
    subject = profile["subject_constraint"]
    slot_plan = _build_thematic_slot_plan(subject)
    formatted_prompt = _format_thematic_prompt(profile, slot_plan)

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
        category = _classify_openrouter_error(exc)
        body_snippet = (getattr(exc, "body", "") or "")[:300]
        logger.exception(
            "Thematic PLAN — OpenRouter call to %s failed: status=%s category=%s body=%s",
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
        logger.exception(
            "Thematic PLAN — call to %s crashed: %s",
            _GEMINI_MODEL, exc,
        )
        raise GeminiPlanError(
            f"Сбой при вызове планировщика: {type(exc).__name__}: {exc}",
            category="network",
        ) from exc

    logger.info(
        "Thematic plan — токены: %d in / %d out, стоимость: $%.6f",
        usage.input_tokens, usage.output_tokens, usage.cost_usd,
    )
    logger.info(
        "Thematic plan — raw response длина: %d символов",
        len(raw_response) if raw_response else 0,
    )

    # DEBUG: dump raw response
    try:
        with open("_thematic_last_response.txt", "w", encoding="utf-8") as _f:
            _f.write(raw_response or "(EMPTY)")
    except Exception:
        pass

    # ── валидация ────────────────────────────────────────────────────
    validation: GeminiPlanValidation = validate_gemini_plan(raw_response)

    if not validation.valid:
        err_summary = "; ".join(validation.all_errors[:5]) or "validation failed"
        logger.error(
            "Thematic plan — ошибки валидации (%d): %s",
            len(validation.all_errors), err_summary,
        )
        tail = raw_response[-800:] if raw_response else "(EMPTY)"
        logger.error("Thematic raw response END (last 800 chars): %s", tail)
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

    # ── enforce slot_kind + subject + difficulty_level из плана ──────
    # (на случай, если LLM их изменила)
    by_pos = {s["position"]: s for s in slot_plan}
    enforced_specs: List[Dict[str, Any]] = []
    enforced_count = 0
    for spec in specs:
        pos = spec.get("position")
        planned = by_pos.get(pos)
        if planned is None:
            enforced_specs.append(spec)
            continue
        merged = dict(spec)
        merged["slot_kind"] = planned["slot_kind"]
        merged["subject"] = planned["subject"]
        merged["difficulty_level"] = planned["difficulty_level"]
        # topic / subtopic — оставляем как есть (LLM сгенерировала)
        enforced_specs.append(merged)
        enforced_count += 1

    logger.info(
        "Thematic plan — OK: %d specs, cost=$%.4f, enforced=%d slots",
        len(enforced_specs), usage.cost_usd, enforced_count,
    )
    return enforced_specs
