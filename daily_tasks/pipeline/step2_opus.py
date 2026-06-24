# -*- coding: utf-8 -*-
"""
Step 2 pipeline 'Daily tasks' - parallel task generator.

Prinimaet 10 specifikacij ot Step 1, dlya KAZHDOJ nezavisimo vyzyvaet LLM
cherez asyncio.Semaphore. Kazhdyj vorker obrabatyvaet svoyu speku nezavisimo:
upavshij vorker ne valit ostalnyh, a vozvrashchaet sintetic zaglushku s
pravilnoj position - na Step 3 ee pometyat needs_fix, na Step 4 vosstanovyat.

KLYUCH (2026-06-24):
* response_format json_object - DeepSeek lyubit oborachivat otvet v markdown,
  iz-za chego extract_json_safe padал i my poluchali GEN_FAILED. JSON-rezhim
  ubiraet bolshinstvo etih sboev (sm. api-docs.deepseek.com json_mode).
* max_tokens po urovnyu: L6-L8 (olimpiadnye) trebuyut dlinnogo resheniya,
  4096 obrezalo JSON -> nevalidnyj otvet.
* model routing po difficulty_level vynesen v _model_for_level - tochka,
  gde finalno reshaem kakaya model na kakoj uroven.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any, Dict, List, Optional, Tuple

from pipeline.openrouter_client import OpenRouterClient, TokenUsage
from .validators import (
    OpusGenerationValidation,
    extract_json_safe,
    validate_opus_generation,
)

logger = logging.getLogger(__name__)

def _coerce_tasks_list(parsed: Any) -> List[Dict[str, Any]]:
    # Heuristicheski izvlekaem spisok zadach iz raznyh form otveta modeli.
    if isinstance(parsed, list):
        return [t for t in parsed if isinstance(t, dict)]
    if not isinstance(parsed, dict):
        return []
    # 1) Standartnyj klyuch "tasks".
    _t = parsed.get("tasks")
    if isinstance(_t, list) and _t:
        return [t for t in _t if isinstance(t, dict)]
    # 2) Inogda model kladet zadachi pod inymi klyuchami.
    for _alt_key in ("task", "items", "data", "result", "results"):
        _alt = parsed.get(_alt_key)
        if isinstance(_alt, list) and _alt:
            return [t for t in _alt if isinstance(t, dict)]
        if isinstance(_alt, dict):
            return [_alt]
    # 3) Esli sam parsed pohozh na odnu zadachu - obernem v spisok.
    if parsed.get("task_text") or parsed.get("correct_answer"):
        return [parsed]
    return []      

# == modeli i routing ==
# Step 2 GENERATE. Vse urovni poka na DeepSeek v3.1 (deshevo/bezlimit).
# Razdelenie EASY/HARD ostavleno yavnym, chtoby finalno podstavit silnuyu
# reasoning-model na olimpiadnye L6-L8 (DeepSeek v3.1 base slab na AIME ~40%,
# reasoning-modeli daet ~80% i 97% MATH-500 - sm. sravnenie R1 vs V3).
_GEN_MODEL_EASY = "deepseek/deepseek-chat-v3.1"
_GEN_MODEL_HARD = "deepseek/deepseek-r1"
_GEN_HARD_THRESHOLD = 4
_OPUS_MODEL = _GEN_MODEL_HARD  # alias dlya sovmestimosti s logami

# Parallelizm. Bylo 10 (vrazrez s docstring '5 potokov' i risk 429 ot
# OpenRouter). Vozvrashchaem 5 - stabilnee, 10 spec -> ~2 na vorker.
_PARALLEL_WORKERS = 5

# JSON-rezhim: zastavlyaet model vernut chistyj JSON-objekt bez markdown.
_JSON_RESPONSE_FORMAT = {"type": "json_object"}


def _model_for_level(difficulty_level: Any) -> str:
    """Vybor modeli po urovnyu slozhnosti (8-ballnaya shkala).

    Edinaya tochka resheniya 'kakaya model na kakoj uroven'. Seychas obe
    vetki - DeepSeek v3.1; pri finalnom reshenii dostatochno pomenyat
    _GEN_MODEL_HARD na reasoning-model (naprimer deepseek/deepseek-r1).
    """
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    return _GEN_MODEL_HARD if lvl >= _GEN_HARD_THRESHOLD else _GEN_MODEL_EASY


def _max_tokens_for_level(difficulty_level: Any) -> int:
    """Bolshe tokenov dlya slozhnyh urovnej - inache JSV obrezaetsya."""
    try:
        lvl = int(difficulty_level or 1)
    except (TypeError, ValueError):
        lvl = 1
    if lvl >= _GEN_HARD_THRESHOLD:
        return 8192
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
    """Podstavit ODNU specifikaciyu v prompt-shablon.

    Prompt ozhidaet {\"specs\": [...]} na vhode i {\"tasks\": [...]} na vyhode.
    Zdes podsovyvaem massiv dliny 1.
    """
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
        "task_text": (
            f"[GEN_FAILED] Ne udalos sgenerirovat zadachu dlya pozicii {pos}. "
            f"Prichina: {reason}"
        ),
        "correct_answer": "-",
        "solution": "-",
        "hints": ["Budet sgenerirovano na shage ispravleniya."],
        "_generation_failed": True,
        "_failure_reason": reason,
    }


async def _generate_one_spec(
    client: OpenRouterClient,
    semaphore: asyncio.Semaphore,
    spec: Dict[str, Any],
) -> Tuple[Dict[str, Any], float]:
    """Sgenerirovat odnu zadachu pod odnu speku.

    Vozvrashchaet (task_dict, cost_usd). Pri LYUBOJ oshibke - sintetic
    zaglushka s _generation_failed=True i cost=0, chtoby ostalnye vorkery
    spokojno dorabotali.
    """
    import time as _time_mod
    pos = spec.get("position")
    lvl = spec.get("difficulty_level")
    model = _model_for_level(lvl)
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
            raw, usage = await client.chat(
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
    # Retry do 3 raz pri nevalidnom JSON, peredavaya plohoj otvet modeli obratno.
    _MAX_JSON_RETRIES = 3
    parsed = extract_json_safe(raw)
    _retry_cost = usage.cost_usd
    for _retry_attempt in range(_MAX_JSON_RETRIES):
        if parsed is not None and isinstance(parsed, dict):
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
                    "Tvoj predydushchij otvet ne yavlyaetsya validnym JSON. "
                    "Verni TOLKO korrektnyj JSON-objekt vida "
                    '{"tasks": [{ ... }]} bez kakih-libo poyasnenij, '
                    "markdown-blokov ili lishnego teksta."
                ),
            },
        ]
        try:
            async with semaphore:
                raw, _retry_usage = await client.chat(
                    model=model,
                    messages=retry_messages,
                    temperature=0.3,
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

    if parsed is None or not isinstance(parsed, dict):
        logger.error(
            "Step 2 GENERATE - pos=%s - ne smogli rasparsit JSON posle %d popytok",
            pos, _MAX_JSON_RETRIES,
        )
        return _synthesize_fallback_task(spec, "invalid_json"), _retry_cost

    usage_cost = _retry_cost
    tasks_list = _coerce_tasks_list(parsed)
    if not isinstance(tasks_list, list) or len(tasks_list) == 0:
        logger.error(
            "Step 2 GENERATE - pos=%s - otsutstvuet/pustoj 'tasks' v otvete",
            pos,
        )
        return _synthesize_fallback_task(spec, "no_tasks_key"), usage_cost

    task = tasks_list[0]
    if not isinstance(task, dict):
        logger.error("Step 2 GENERATE - pos=%s - task ne slovar", pos)
        return _synthesize_fallback_task(spec, "task_not_dict"), usage_cost

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
async def generate_opus_tasks(specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sgenerirovat 10 zadach parallelno (semaphore=_PARALLEL_WORKERS).

    Vozvrashchaet 10 zadach (po odnoj na speku, otsortirovany po position).
    Sbojnye pozicii - fallback-zaglushki s _generation_failed=True; obshchij
    spisok vsegda dliny 10, chtoby validate_opus_generation ne valilsya.
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

    async with OpenRouterClient() as client:
        coros = [_generate_one_spec(client, semaphore, spec) for spec in specs]
        results = await asyncio.gather(*coros, return_exceptions=False)

    tasks: List[Dict[str, Any]] = []
    total_cost = 0.0
    failed_positions: List[Any] = []
    for task, cost in results:
        tasks.append(task)
        total_cost += cost
        if task.get("_generation_failed"):
            failed_positions.append(task.get("position"))

    tasks.sort(key=lambda t: t.get("position") or 0)
    logger.info(
        "Step 2 GENERATE - DONE: %d zadach (failed=%d at positions %s), total_cost=$%.4f",
        len(tasks), len(failed_positions), failed_positions, total_cost,
    )

    pseudo_raw = json.dumps({"tasks": tasks}, ensure_ascii=False)
    validation: OpusGenerationValidation = validate_opus_generation(pseudo_raw)
    if not validation.valid:
        valid_entries = sum(1 for e in validation.entries if e.valid)
        if valid_entries >= 5:
            logger.warning(
                "Step 2 GENERATE - chastichnaya validaciya: %d/10 ok, %d oshibok. "
                "Propuskaem dalshe - Step 3 pometit sbojnye, Step 4 ispravit.",
                valid_entries, len(validation.all_errors),
            )
        else:
            logger.error(
                "Step 2 GENERATE - kriticheskaya oshibka: tolko %d/10 zadach proshli "
                "validaciyu. Oshibki: %s",
                valid_entries,
                "; ".join(validation.all_errors[:5]),
            )
            return []

    return tasks
