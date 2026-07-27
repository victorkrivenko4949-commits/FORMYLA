# -*- coding: utf-8 -*-
"""
Step 2: генерация задач через DeepSeek API (parallelopus).

Вход: 10 спецификаций от планировщика (Gemini).
Выход: 10 готовых задач с текстом, ответом, решением и подсказками.
Каждая задача генерируется отдельным вызовом модели параллельно.

Доступные модели (настраиваются в pipeline/config.py):
  - deepseek/deepseek-chat-v3.1 — для уровней 1..3 (быстро, ~3-4 сек)
  - deepseek/deepseek-r1 — для уровней 4..8 (медленно, ~40-110 сек)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from services.openrouter_client import OpenRouterClient, TokenUsage, make_token_usage

from .validators import (
    OpusGenerationValidation,
    extract_json_safe,
    validate_opus_generation,
)

logger = logging.getLogger(__name__)

# == kontseptualnye konstanty ==

_OPUS_MODEL = "deepseek/deepseek-chat-v3.1"
_PARALLEL_WORKERS = 5
_MAX_REGEN_ROUNDS = 3
_GEN_HARD_THRESHOLD = 4
_GEN_MODEL_EASY = "deepseek/deepseek-chat-v3.1"
_GEN_MODEL_HARD = "deepseek/deepseek-r1"
_JSON_RESPONSE_FORMAT = {"type": "json_object"}


# == helpers dlya modeli ==


def _model_for_level(difficulty_level: Any) -> str:
    """Vybor modeli po urovnyu slozhnosti (8-ballnaya shkala)."""
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    return _GEN_MODEL_HARD if lvl >= _GEN_HARD_THRESHOLD else _GEN_MODEL_EASY


def _max_tokens_for_level(difficulty_level: Any) -> int:
    """Bolshe tokenov dlya slozhnyh urovnej - inache JSON obrezaetsya.

    Uvelichen do 20000 dlya R1 (lvl >= 4), chtoby chain-of-thought
    ne zhirala ves limit i model ne vozvrashchala pustoj JSON.
    """
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    if lvl >= _GEN_HARD_THRESHOLD:
        return 20000
    if lvl >= 4:
        return 6144
    return 4096


# == helpers ==
def _load_prompt() -> str:
    """Zagruzit soderzhimoe prompts/opus_generate.md."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "opus_generate.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _format_prompt_for_single_spec(spec: Dict[str, Any]) -> str:
    """Podstavit ODNU specifikaciyu v prompt-shablon."""
    prompt = _load_prompt()
    specs_json = json.dumps(
        {"specs": [spec]},
        ensure_ascii=False,
        indent=2,
    )
    return prompt.replace('{ "specs": [...] }', specs_json)


def _synthesize_fallback_task(spec: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Sformirovat pustuyu zadachu-zaglushku s pravilnoj poziciej."""
    pos = spec.get("position")
    return {
        "position": pos,
        "_generation_failed": True,
        "_fail_reason": reason,
        "task_text": "",
        "correct_answer": "",
        "solution": "",
        "hints": [],
    }


# == audit vnutri generatora (proverka GEN_FAILED i temy) ==


def _tokenize(text: str) -> set:
    """Razbit tekst na mnozhestvo slov dlya sravneniya."""

    def _norm(w):
        return w.strip(".,!?;:()[]{}«»'\"-").lower()

    return {_norm(w) for w in text.split() if len(_norm(w)) > 2}


def _topic_keywords(spec: Dict[str, Any]) -> set:
    """Sobrat klyuchevye slova iz (sub)topic specifikacii."""
    kw = set()
    for field in ("topic", "subtopic", "subject", "domain"):
        val = spec.get(field)
        if val:
            kw.update(_tokenize(str(val)))
    return kw


def _audit_task(task: Optional[Dict[str, Any]], spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Prostaya proverka: ne GEN_FAILED i sootvetstvie teme."""
    if task is None:
        return False, "missing"
    if task.get("_generation_failed"):
        return False, task.get("_fail_reason", "generation_failed")
    task_text = task.get("task_text", "")
    if not task_text or len(task_text.strip()) < 20:
        return False, "too_short"
    # Proverka tematicheskogo sootvetstviya
    spec_kw = _topic_keywords(spec)
    if not spec_kw:
        return True, "ok"  # net klyuchevyh slov - ne mozhem proverit
    task_kw = _tokenize(task_text)
    intersection = spec_kw & task_kw
    if not intersection:
        logger.warning(
            "Step 2 AUDIT - pos=%s topic=%r subtopic=%r: "
            "net peresecheniya klyuchevyh slov s temoj (spec_kw=%s)",
            spec.get("position"),
            spec.get("topic"),
            spec.get("subtopic"),
            spec_kw,
        )
        return False, "off_topic"
    return True, "ok"


# == generaciya odnoj zadachi ==


async def _generate_one_spec(
    client: OpenRouterClient,
    semaphore: asyncio.Semaphore,
    spec: Dict[str, Any],
    force_model: Optional[str] = None,
) -> Tuple[Dict[str, Any], float]:
    """Sgenerirovat odnu zadachu pod odnu speku.

    Vozvrashchaet (task_dict, cost_usd). Pri LYUBOJ oshibke - sintetic zaglushka
    s _generation_failed=True, chtoby ostalnye vorkery dorabotali.
    """
    import time as _time_mod

    pos = spec.get("position")
    lvl = spec.get("difficulty_level")
    model = force_model if force_model is not None else _model_for_level(lvl)
    max_tokens = _max_tokens_for_level(lvl)
    formatted = _format_prompt_for_single_spec(spec)
    messages = [{"role": "user", "content": formatted}]
    topic_short = (spec.get("topic") or "?")[:30]
    subtopic_short = (spec.get("subtopic") or "?")[:30]

    async with semaphore:
        _t0 = _time_mod.time()
        logger.info(
            "Step 2 GENERATE [pos=%s] START - topic=%r subtopic=%r L%s model=%s max_tokens=%d",
            pos, topic_short, subtopic_short, lvl, model, max_tokens,
        )
        try:
            raw, usage = await client.async_chat(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                response_format=_JSON_RESPONSE_FORMAT,
            )
        except Exception as exc:
            _dt = _time_mod.time() - _t0
            logger.exception(
                "Step 2 GENERATE [pos=%s] FAIL after %.1fs - HTTP/network error: %s",
                pos, _dt, exc,
            )
            return _synthesize_fallback_task(spec, f"http_error: {exc}"), 0.0

    _dt = _time_mod.time() - _t0
    logger.info(
        "Step 2 GENERATE [pos=%s] HTTP-OK in %.1fs - in=%d out=%d cost=$%.4f",
        pos, _dt, usage.input_tokens, usage.output_tokens, usage.cost_usd,
    )

    # Parsim otvet - ozhidaem {"tasks": [ODNA zadacha]}.
    _MAX_JSON_RETRIES = 4
    parsed = extract_json_safe(raw)
    _retry_cost = usage.cost_usd
    for _retry_attempt in range(_MAX_JSON_RETRIES):
        if parsed is not None and isinstance(parsed, dict) and _coerce_tasks_list(parsed):
            break
        logger.warning(
            "Step 2 GENERATE - pos=%s - ne smogli rasparsit JSON (popytka %d/%d), "
            "povtoryaem s prosboj vernut korrektnyj JSON",
            pos, _retry_attempt + 1, _MAX_JSON_RETRIES,
        )
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Tvoj predydushchij otvet ne yavlyaetsya validnym JSON ili ne "
                    "soderzhit klyuch 'tasks'. Verni TOLKO korrektnyj JSON-objekt "
                    'vida {"tasks": [{"position": N, "task_text": "...", '
                    '"correct_answer": "...", "solution": "...", "hints": ["..."]}]} '
                    "bez kakih-libo poyasnenij, markdown-blokov ili lishnego teksta."
                ),
            },
        ]
        try:
            async with semaphore:
                raw, _retry_usage = await client.async_chat(
                    model=model,
                    messages=retry_messages,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    response_format=_JSON_RESPONSE_FORMAT,
                )
            _retry_cost += _retry_usage.cost_usd
            parsed = extract_json_safe(raw)
        except Exception as _retry_exc:
            logger.warning(
                "Step 2 GENERATE - pos=%s - retry %d HTTP error: %s",
                pos, _retry_attempt + 1, _retry_exc,
            )
            continue

    usage_cost = _retry_cost
    if parsed is None or not isinstance(parsed, dict):
        logger.error(
            "Step 2 GENERATE - pos=%s - ne smogli rasparsit JSON posle %d popytok",
            pos, _MAX_JSON_RETRIES,
        )
        return _synthesize_fallback_task(spec, "invalid_json"), usage_cost

    tasks_list = _coerce_tasks_list(parsed)
    if not isinstance(tasks_list, list) or len(tasks_list) == 0:
        logger.error(
            "Step 2 GENERATE - pos=%s - otsutstvuet/pustoj 'tasks' v otvete (no_tasks_key); "
            "syroj otvet: %r",
            pos, str(raw)[:300],
        )
        return _synthesize_fallback_task(spec, "no_tasks_key"), usage_cost

    task = tasks_list[0]
    if not isinstance(task, dict):
        logger.error("Step 2 GENERATE - pos=%s - task ne slovar", pos)
        return _synthesize_fallback_task(spec, "task_not_dict"), usage_cost

    # Normalizaciya: esli model polozhila tekst pod alt-klyuchi - perenosim.
    if not task.get("task_text"):
        for _alt in ("condition", "problem", "statement", "text"):
            if task.get(_alt):
                task["task_text"] = task[_alt]
                break
    if not task.get("correct_answer") and task.get("answer"):
        task["correct_answer"] = task["answer"]

    # Prinuditelno fiksiruem position na tu, chto v speke.
    task["position"] = pos

    text_preview = (task.get("task_text") or "")[:120].replace("\n", " ")
    answer_preview = str(task.get("correct_answer") or "")[:60]
    logger.info(
        "Step 2 GENERATE [pos=%s] OK - text=%r answer=%r",
        pos, text_preview, answer_preview,
    )
    return task, usage_cost


# == osnovnaya funkciya ==


def _coerce_tasks_list(parsed: Any) -> List[Dict[str, Any]]:
    """Bezopasno izvlech spisok zadach iz parsenogo JSON."""
    if not isinstance(parsed, dict):
        return []
    tasks = parsed.get("tasks")
    if isinstance(tasks, list):
        return tasks
    # poprobovat drugie klyuchi
    for key in ("task", "problems", "items", "data"):
        val = parsed.get(key)
        if isinstance(val, list):
            return val
    return []


async def generate_opus_tasks(
    specs: List[Dict[str, Any]],
    force_model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Sgenerirovat 10 zadach parallelno (semaphore=_PARALLEL_WORKERS).

    Vozvrashchaet 10 zadach (po odnoj na speku, otsortirovany po position).
    Posle generacii zapuskaetsya ETAP AUDITA (_audit_task): kazhdaya zadacha
    proveryaetsya na GEN_FAILED i tematicheskoe sootvetstvie. Sbojnye/off-topic
    pozicii peregeneriruyutsya po TEM ZHE usloviyam do _MAX_REGEN_ROUNDS raz.

    force_model: esli peredan, ispolzuetsya DLya VSEH urovnej (vmesto _model_for_level).
                Ispolzuetsya v rescue-pass dlya obhoda medlennogo R1.
    """
    if not specs:
        logger.error("Step 2 GENERATE - pustoj spisok spek, nechego generirovat")
        return []

    if len(specs) != 10:
        logger.warning(
            "Step 2 GENERATE - polucheno %d spek vmesto 10, vse ravno prodolzhaem",
            len(specs),
        )

    semaphore = asyncio.Semaphore(_PARALLEL_WORKERS)
    logger.info(
        "Step 2 GENERATE - zapusk %d vorkerov (semaphore=%d), model_hard=%s",
        len(specs), _PARALLEL_WORKERS, _OPUS_MODEL,
    )

    # Spec po position - chtoby peregenerirovat konkretnye pozicii po tem zhe usloviyam.
    spec_by_pos: Dict[Any, Dict[str, Any]] = {spec.get("position"): spec for spec in specs}
    total_cost = 0.0

    async with OpenRouterClient() as client:
        # --- Raund 0: pervichnaya generaciya vseh spek ---
        coros = [_generate_one_spec(client, semaphore, spec, force_model=force_model) for spec in specs]
        results = await asyncio.gather(*coros, return_exceptions=False)

        task_by_pos: Dict[Any, Dict[str, Any]] = {}
        for task, cost in results:
            total_cost += cost
            task_by_pos[task.get("position")] = task

        # --- ETAP AUDITA + peregeneraciya nedostayushchih ---
        for _round in range(1, _MAX_REGEN_ROUNDS + 1):
            bad_positions: List[Any] = []
            for pos, spec in spec_by_pos.items():
                task = task_by_pos.get(pos)
                ok, reason = _audit_task(task, spec) if task is not None else (False, "missing")
                if not ok:
                    bad_positions.append(pos)
                    logger.warning(
                        "Step 2 AUDIT - pos=%s ne proshla (prichina=%s), v ochered na peregeneraciyu",
                        pos, reason,
                    )

            if not bad_positions:
                logger.info("Step 2 AUDIT - vse zadachi proshli audit, peregeneraciya ne nuzhna")
                break

            logger.info(
                "Step 2 AUDIT - raund peregeneracii %d/%d: %d pozicij (%s)",
                _round, _MAX_REGEN_ROUNDS, len(bad_positions), bad_positions,
            )
            regen_specs = [spec_by_pos[p] for p in bad_positions]
            regen_coros = [_generate_one_spec(client, semaphore, s, force_model=force_model) for s in regen_specs]
            regen_results = await asyncio.gather(*regen_coros, return_exceptions=False)
            for task, cost in regen_results:
                total_cost += cost
                task_by_pos[task.get("position")] = task
        else:
            # Cikl ne prervan break-om: posle vseh raundov chast pozicij vse eshche plohaya.
            still_bad = [
                pos for pos, spec in spec_by_pos.items()
                if not _audit_task(task_by_pos.get(pos), spec)[0]
            ]
            if still_bad:
                logger.error(
                    "Step 2 AUDIT - posle %d raundov ostalis sbojnye pozicii: %s. "
                    "Otdaem chto est - Step 3 pometit, Step 4 ispravit.",
                    _MAX_REGEN_ROUNDS, still_bad,
                )

    # Sobiraem itogovyj spisok po position.
    tasks: List[Dict[str, Any]] = list(task_by_pos.values())
    tasks.sort(key=lambda t: t.get("position") or 0)

    failed_positions = [
        pos for pos, spec in spec_by_pos.items()
        if not _audit_task(task_by_pos.get(pos), spec)[0]
    ]
    logger.info(
        "Step 2 GENERATE - DONE: %d zadach (audit_failed=%d at positions %s), total_cost=$%.4f",
        len(tasks), len(failed_positions), failed_positions, total_cost,
    )

    pseudo_raw = json.dumps({"tasks": tasks}, ensure_ascii=False)
    validation: OpusGenerationValidation = validate_opus_generation(pseudo_raw)
    if not validation.valid:
        valid_entries = sum(1 for e in validation.entries if e.valid)
        # Porog snizhen do 3/10: dazhe chastichnyj nabor luchshe pustogo -
        # Step 3 pometit sbojnye, Step 4 ih ispravit. Pustoj spisok ronyal ves
        # pipeline (sm. incident 2026-06-25, pozicii 4/6/8/9).
        if valid_entries >= 3:
            logger.warning(
                "Step 2 GENERATE - chastichnaya validaciya: %d/10 ok, %d oshibok. "
                "Propuskaem dalshe - Step 3 pometit sbojnye, Step 4 ispravit.",
                valid_entries, len(validation.all_errors),
            )
        else:
            logger.error(
                "Step 2 GENERATE - kriticheskaya oshibka: tolko %d/10 zadach proshli "
                "validaciyu. Oshibki: %s. Vse ravno otdaem chastichnyj nabor na Step 3/4.",
                valid_entries, "; ".join(validation.all_errors[:5]),
            )
            # Ne vozvrashchaem [] - otdaem chto est, chtoby Step 4 dorabotal.
            return tasks

    return tasks
