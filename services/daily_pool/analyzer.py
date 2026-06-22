# -*- coding: utf-8 -*-
"""
Analyzer service: analyzes a (olympiad, grade, round) combination.
Cached in olympiad_analysis table for 30 days.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from models import db
from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

from config.models import ANALYZER_MODEL as MODEL, ANALYZER_TEMPERATURE as TEMPERATURE
CACHE_DAYS = 30


def get_or_create_analysis(olympiad_slug: str, grade: int, round_key: str) -> dict:
    """
    Get cached analysis or create new one.
    Returns the analysis JSON dict.
    """
    # Check cache
    cached = db.session.execute(
        db.text("""
            SELECT analysis_json, expires_at FROM olympiad_analysis
            WHERE olympiad_slug = :slug AND grade = :grade AND round = :round
        """),
        {'slug': olympiad_slug, 'grade': grade, 'round': round_key}
    ).fetchone()

    if cached and cached[1]:
        expires = cached[1]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires > datetime.now(timezone.utc):
            logger.info(f"[Analyzer] Cache hit: {olympiad_slug}/{grade}/{round_key}")
            if isinstance(cached[0], str):
                return json.loads(cached[0])
            return cached[0]

    # Generate new analysis
    logger.info(f"[Analyzer] Generating: {olympiad_slug}/{grade}/{round_key}")
    analysis = _run_analysis(olympiad_slug, grade, round_key)
    return analysis


def _run_analysis(olympiad_slug: str, grade: int, round_key: str) -> dict:
    """Run the analyzer model on all archived problems for this combo."""
    # Get all problems for this combination
    rows = db.session.execute(
        db.text("""
            SELECT year, num, text, answer, solution
            FROM problems_archive
            WHERE olympiad_slug = :slug AND grade = :grade AND round = :round
            ORDER BY year, num
        """),
        {'slug': olympiad_slug, 'grade': grade, 'round': round_key}
    ).fetchall()

    if not rows:
        raise ValueError(f"No archive problems for {olympiad_slug}/{grade}/{round_key}")

    # Build tasks block
    tasks_block = ""
    for r in rows:
        year, num, text, answer, solution = r
        tasks_block += f"\n--- Год {year}, задача {num} ---\n"
        tasks_block += f"Условие: {text}\n"
        if answer:
            tasks_block += f"Ответ: {answer}\n"

    # Get olympiad title
    title_row = db.session.execute(
        db.text("SELECT DISTINCT olympiad_title FROM problems_archive WHERE olympiad_slug = :slug LIMIT 1"),
        {'slug': olympiad_slug}
    ).fetchone()
    olympiad_title = title_row[0] if title_row else olympiad_slug

    # Load prompt template
    prompt = _build_prompt(olympiad_title, grade, round_key, len(rows), tasks_block)

    # Call model
    result = openrouter.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты — эксперт-аналитик олимпиадной математики с 20-летним опытом подготовки сборных."},
            {"role": "user", "content": prompt}
        ],
        temperature=TEMPERATURE,
        max_tokens=4096,
    )

    # Parse JSON response
    content = result["content"]
    try:
        # Try to extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        analysis = json.loads(content.strip())
    except json.JSONDecodeError as e:
        logger.error(f"[Analyzer] Failed to parse JSON: {e}\nContent: {content[:200]}")
        raise

    # v2.3: enforce a hard 5-topic template for vsosh/9/regional
    # to guarantee diversity even if model returned duplicate themes.
    analysis = _enforce_predicted_variant_template(analysis, olympiad_slug, grade, round_key)

    # Save to cache
    expires_at = datetime.now(timezone.utc) + timedelta(days=CACHE_DAYS)
    analysis_json = json.dumps(analysis, ensure_ascii=False)

    # Upsert
    existing = db.session.execute(
        db.text("SELECT id FROM olympiad_analysis WHERE olympiad_slug=:s AND grade=:g AND round=:r"),
        {'s': olympiad_slug, 'g': grade, 'r': round_key}
    ).fetchone()

    if existing:
        db.session.execute(
            db.text("""
                UPDATE olympiad_analysis
                SET analysis_json=:json, model_used=:model, tokens_used=:tokens, cost_usd=:cost, expires_at=:exp
                WHERE id=:id
            """),
            {
                'json': analysis_json, 'model': MODEL,
                'tokens': result['usage'].get('total_tokens', 0),
                'cost': result['cost_usd'], 'exp': expires_at.isoformat(),
                'id': existing[0]
            }
        )
    else:
        db.session.execute(
            db.text("""
                INSERT INTO olympiad_analysis
                (olympiad_slug, grade, round, analysis_json, model_used, tokens_used, cost_usd, expires_at)
                VALUES (:slug, :grade, :round, :json, :model, :tokens, :cost, :exp)
            """),
            {
                'slug': olympiad_slug, 'grade': grade, 'round': round_key,
                'json': analysis_json, 'model': MODEL,
                'tokens': result['usage'].get('total_tokens', 0),
                'cost': result['cost_usd'], 'exp': expires_at.isoformat()
            }
        )

    db.session.commit()

    # Log cost
    openrouter.log_cost_to_db('analyze', MODEL, result['usage'], result['cost_usd'])
    logger.info(f"[Analyzer] Done: {olympiad_slug}/{grade}/{round_key} "
                f"({len(rows)} problems, ${result['cost_usd']:.4f})")

    return analysis


def _build_prompt(title, grade, round_key, count, tasks_block):
    """Build the analyzer prompt from template."""
    ROUND_NAMES = {
        'school': 'Школьный этап',
        'municipal': 'Муниципальный этап',
        'regional': 'Региональный этап',
        'final': 'Заключительный этап',
        'selection': 'Отборочный этап',
        'distance': 'Дистанционный этап',
        'spring_basic': 'Весенний тур (базовый)',
        'spring_hard': 'Весенний тур (сложный)',
        'autumn_basic': 'Осенний тур (базовый)',
        'autumn_hard': 'Осенний тур (сложный)',
    }
    round_title = ROUND_NAMES.get(round_key, round_key)

    return f"""ОЛИМПИАДА: {title}
КЛАСС: {grade}
ЭТАП: {round_title}
КОЛИЧЕСТВО ЗАДАЧ В АРХИВЕ: {count}

{'='*55}
АРХИВ ЗАДАЧ (все доступные за разные годы):
{'='*55}
{tasks_block}
{'='*55}
ЗАДАНИЕ: Проанализируй архив и верни JSON-профиль.
{'='*55}

Думай шаг за шагом:
1. Определи типичные ТЕМЫ (алгебра, геометрия, комбинаторика, теория чисел, логика)
2. Определи РАСПРЕДЕЛЕНИЕ тем по позициям
3. Определи СТИЛЬ формулировок
4. Определи типичные МЕТОДЫ РЕШЕНИЯ
5. Определи формат ОТВЕТОВ
6. Определи УРОВЕНЬ СЛОЖНОСТИ по позициям (1-10)
7. Определи УНИКАЛЬНЫЕ ЧЕРТЫ этой олимпиады

Верни ТОЛЬКО валидный JSON (без markdown-обёртки) со структурой:
{{
    "olympiad": "{title}",
    "grade": {grade},
    "round": "{round_key}",
    "total_problems_analyzed": {count},
    "themes_distribution": {{"алгебра": 0.25, "геометрия": 0.20, ...}},
    "position_profiles": [
        {{"position": 1, "typical_themes": ["..."], "difficulty": N, "answer_type": "...", "typical_methods": ["..."], "avg_solution_length": "..."}}
    ],
    "style_notes": {{"formality": "...", "language_features": ["..."], "unique_traits": ["..."]}},
    "forbidden_topics": ["..."],
    "predicted_variant": [
        {{"position": 1, "theme": "алгебра", "subtopic": "...", "idea": "...", "difficulty": N, "answer_type": "number|formula|set", "expected_techniques": ["..."]}}
    ]
}}

⛔ ЖЁСТКИЕ ПРАВИЛА для predicted_variant:
1. answer_type ОБЯЗАН быть один из: "number", "formula", "set" (множество значений / пары / список).
   ЗАПРЕЩЕНО: "proof", "proof_or_*", "*_or_proof", "construction", "find_all" (только если ответ — конкретное множество).
   Даже если в архиве задачи требуют доказательства — в predicted_variant давай только числовые/формульные ответы.
2. РАСПРЕДЕЛЕНИЕ ТЕМ определяется ТЕМОЙ ДНЯ (см. _HARDCODED_TEMPLATES). Для дня с доминирующей темой (например, теория чисел) большинство задач должны быть по этой теме с РАЗНЫМИ подтемами; остальные 1-2 позиции — для разнообразия.
3. Если архив содержит мало числовых задач — придумай аналогичные числовые формулировки для тех же тем.
"""


# v2.4: hardcoded predicted_variant templates for combos where we want
# a guaranteed THEME-OF-THE-DAY focus. Today (Day 1) is Theory of Numbers:
# the variant is dominated by number theory (3 of 5 positions) with distinct
# subtopics, plus geometry and logic/games for a touch of variety.
# Each theme is canonical; idea is a hint that the generator may rephrase.
# DOMINANT_THEME marks the canonical theme that is allowed to repeat.
DOMINANT_THEME = {
    ("vsosh", 9, "regional"): "теория чисел",
}

_HARDCODED_TEMPLATES = {
    ("vsosh", 9, "regional"): [
        {"position": 1, "theme": "теория чисел", "subtopic": "делимость/сравнения",
         "idea": "Сравнения по модулю / признаки делимости / АОКиРуффини",
         "difficulty": 6, "answer_type": "number",
         "expected_techniques": ["сравнения", "разложение на множители"]},
        {"position": 2, "theme": "теория чисел", "subtopic": "диофантовы уравнения",
         "idea": "Решение уравнений в целых числах / оценка + перебор остатков",
         "difficulty": 7, "answer_type": "set",
         "expected_techniques": ["оценка", "остатки по модулю"]},
        {"position": 3, "theme": "геометрия", "subtopic": "планиметрия",
         "idea": "Свойства окружностей / биссектрис / подобия",
         "difficulty": 7, "answer_type": "number",
         "expected_techniques": ["вписанная окружность", "степень точки"]},
        {"position": 4, "theme": "теория чисел", "subtopic": "простые числа/порядок элемента",
         "idea": "Квадратичные вычеты / порядок элемента / теорема Эйлера",
         "difficulty": 8, "answer_type": "number",
         "expected_techniques": ["теорема Эйлера", "порядок элемента"]},
        {"position": 5, "theme": "логика/игры/инварианты", "subtopic": "инвариант/полуинвариант",
         "idea": "Инвариант, экстремальный принцип или стратегия в игре (с теоретико-числовым сюжетом)",
         "difficulty": 8, "answer_type": "number",
         "expected_techniques": ["инвариант", "крайний случай"]},
    ],
}


def _enforce_predicted_variant_template(analysis: dict, slug: str, grade, round_key: str) -> dict:
    """Override predicted_variant with a hardcoded theme-of-the-day template
    for combos in _HARDCODED_TEMPLATES; otherwise return analysis unchanged.

    v2.4: the template may intentionally repeat a DOMINANT_THEME (e.g. number
    theory) across several positions. We expose the dominant theme on the
    analysis dict so the generator can relax its topic-duplicate guard.
    """
    key = (slug, int(grade), round_key)
    template = _HARDCODED_TEMPLATES.get(key)
    if not template:
        return analysis

    original = analysis.get("predicted_variant") or []
    themes = [(p.get("theme") or "").strip().lower() for p in original]
    logger.info(
        f"[Analyzer] {slug}/{grade}/{round_key}: applying v2.4 theme-of-the-day "
        f"template (was themes={themes})"
    )

    analysis["predicted_variant"] = list(template)

    # v2.4: tell downstream (generator) which theme is allowed to repeat today.
    dominant = DOMINANT_THEME.get(key)
    if dominant:
        analysis["dominant_theme"] = dominant

    # Wipe forbidden_topics that might collide with our canonical themes
    forbidden = analysis.get("forbidden_topics") or []
    canonical = {"алгебра", "геометрия", "теория чисел", "комбинаторика",
                 "логика", "игры", "инварианты", "логика/игры/инварианты"}
    cleaned = [t for t in forbidden if (t or "").strip().lower() not in canonical]
    if len(cleaned) != len(forbidden):
        analysis["forbidden_topics"] = cleaned

    return analysis
