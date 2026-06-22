# -*- coding: utf-8 -*-
"""
Generator service: creates a single olympiad problem using GPT-5.
"""
import json
import logging
import re
from datetime import date

from services.openrouter_client import openrouter
from services.daily_pool.json_utils import parse_json_with_latex as _parse_json_with_latex

logger = logging.getLogger(__name__)

from config.models import (
    GENERATOR_MODEL as MODEL,
    GENERATOR_TEMPERATURE as TEMPERATURE,
)
try:
    from config.models import GENERATOR_FALLBACKS as _FALLBACKS
except ImportError:
    _FALLBACKS = []

# v2.3: nominal topic vocabulary for diversity check.
# All variants of the same topic name → one canonical key.
TOPIC_NORMALIZE = {
    # number theory
    "теория чисел": "number_theory",
    "теория_чисел": "number_theory",
    "number theory": "number_theory",
    "number_theory": "number_theory",
    "теория чисел и алгебра": "number_theory",
    "арифметика": "number_theory",
    # geometry
    "геометрия": "geometry",
    "geometry": "geometry",
    "планиметрия": "geometry",
    "стереометрия": "geometry",
    # algebra
    "алгебра": "algebra",
    "algebra": "algebra",
    "уравнения": "algebra",
    "неравенства": "algebra",
    "функциональные уравнения": "algebra",
    # combinatorics
    "комбинаторика": "combinatorics",
    "combinatorics": "combinatorics",
    "графы": "combinatorics",
    # logic / games / invariants
    "логика": "logic_games",
    "logic": "logic_games",
    "игры": "logic_games",
    "инварианты": "logic_games",
    "logic_games": "logic_games",
    "логика/игры/инварианты": "logic_games",
}

PROOF_ANSWER_MARKERS = (
    "докажите", "докажем", "докажу", "покажем", "покажите", "доказано",
    "существует", "не существует", "верно", "неверно",
)


def _normalize_topic(t: str) -> str:
    if not t:
        return ""
    key = t.strip().lower()
    return TOPIC_NORMALIZE.get(key, key)


def _has_year_constants(text: str, current_year: int) -> bool:
    """Return True if text contains any of the year-spam constants."""
    if not text:
        return False
    candidates = {str(current_year), str(current_year - 1), str(current_year + 1),
                  "2025", "2026", "2027"}
    for c in candidates:
        # word-boundary match so "20262" won't trigger
        if re.search(r"(?<!\d)" + c + r"(?!\d)", text):
            return True
    return False


def _is_proof_answer(answer: str) -> bool:
    """Detect text-based proof answers."""
    if not answer:
        return True
    a = answer.strip().lower()
    if not a:
        return True
    # heuristic: contains proof marker words AND no digits/LaTeX expression
    has_marker = any(m in a for m in PROOF_ANSWER_MARKERS)
    has_concrete = bool(re.search(r"\d|\\(frac|sqrt|binom|pi|infty)|[+\-*/=]", answer))
    return has_marker and not has_concrete


def _has_dirty_latex(text: str) -> bool:
    """Detect broken LaTeX commands not preceded by their backslash."""
    if not text:
        return False
    patterns = [
        r"(?<![\\A-Za-z])rac\{",
        r"(?<![\\A-Za-z])inom\{",
        r"(?<![\\A-Za-z])qrt\{",
        r"(?<![\\A-Za-z])ight[\)\]\}\.]",
        r"(?<![\\A-Za-z])eft[\(\[\\]",
    ]
    return any(re.search(p, text) for p in patterns)


def validate_generated_problem(problem: dict, existing_in_variant: list,
                                current_year: int) -> None:
    """v2.3: programmatic post-parse validation.

    Raises ValueError with a stable error code prefix so the retry-guard can
    log structured reasons.
    """
    if not problem:
        raise ValueError("empty_problem")

    statement = problem.get("statement") or ""
    answer = problem.get("answer") or ""
    solution = problem.get("solution") or ""
    topic = problem.get("topic") or ""

    # D) length sanity
    if len(statement) < 50:
        raise ValueError(f"length_anomaly: statement too short ({len(statement)} chars)")
    if len(statement) > 2000:
        raise ValueError(f"length_anomaly: statement too long ({len(statement)} chars)")

    # E) latex dirty
    for field_name, field_val in (("statement", statement),
                                   ("solution", solution),
                                   ("answer", answer)):
        if _has_dirty_latex(field_val):
            raise ValueError(f"latex_dirty: broken LaTeX cmd in {field_name}")

    # C) proof-answer (FIX 3 backstop)
    if _is_proof_answer(answer):
        raise ValueError(f"proof_answer: answer looks like proof text: {answer[:80]!r}")

    # B) topic duplicate (normalized)
    if existing_in_variant:
        norm_topic = _normalize_topic(topic)
        if norm_topic:
            for ex in existing_in_variant:
                if _normalize_topic(ex.get("topic", "")) == norm_topic:
                    raise ValueError(f"topic_duplicate: '{topic}' (normalized '{norm_topic}') already used")

    # A) year-constant spam: only block if any prior problem already used such a constant
    if existing_in_variant and _has_year_constants(statement, current_year):
        for ex in existing_in_variant:
            ex_stmt = ex.get("statement", "") or ""
            if _has_year_constants(ex_stmt, current_year):
                raise ValueError(
                    "year_constant_already_used: another problem in this variant "
                    f"already uses {current_year}/2025/2026/2027 in statement"
                )


def _chat_with_fallback(messages: list, **kwargs):
    """v2.3: try GENERATOR_MODEL, fall back through GENERATOR_FALLBACKS on
    HTTP 4xx 'No endpoints found' / model-id errors. Other errors propagate."""
    chain = [MODEL] + list(_FALLBACKS)
    last_err = None
    for m in chain:
        try:
            res = openrouter.chat(model=m, messages=messages, **kwargs)
            res["_model_used"] = m
            if m != MODEL:
                logger.warning(f"[Generator] fallback model used: {m} (primary {MODEL} failed)")
            return res
        except Exception as e:
            msg = str(e)
            last_err = e
            # only fallback on model-id/availability problems, not on other errors
            if ("No endpoints found" in msg
                or "is not a valid model ID" in msg
                or "HTTP 404" in msg
                or "HTTP 400" in msg):
                logger.warning(f"[Generator] model {m} unavailable: {msg[:120]}; trying fallback")
                continue
            raise
    raise last_err if last_err else RuntimeError("Generator exhausted all fallbacks")


def generate_problem(analysis: dict, position: int, existing_in_variant: list = None,
                     recent_problems: list = None, variant_date: str = None) -> dict:
    """
    Generate a single problem for the given position.

    Args:
        analysis: Full analysis JSON from analyzer
        position: 1-5
        existing_in_variant: Problems already generated for this variant
        recent_problems: Last 5 problems on same topic for dedup

    Returns: dict with keys: statement, solution, answer, topic, difficulty, method, idea_summary
    Raises: ValueError if model returns reject or invalid JSON
    """
    predicted = analysis.get("predicted_variant", [])     dominant_theme = analysis.get("dominant_theme")
    if position > len(predicted):
        raise ValueError(f"Position {position} not in predicted_variant (len={len(predicted)})")

    spec = predicted[position - 1]
    style_notes = json.dumps(analysis.get("style_notes", {}), ensure_ascii=False)
    forbidden = ", ".join(analysis.get("forbidden_topics", []))

    # NEW (v2.1): override answer_type if analyzer suggested any proof-like value.
    # Old cached analyses may contain "proof", "proof_or_construction", "find_all" etc.
    raw_answer_type = (spec.get("answer_type") or "").lower()
    PROOF_TOKENS = ("proof", "construction", "find_all", "verify", "show", "prove")
    if any(tok in raw_answer_type for tok in PROOF_TOKENS):
        logger.warning(
            f"[Generator] pos={position}: override answer_type "
            f"'{raw_answer_type}' -> 'number_or_formula' (FIX 3 enforcement)"
        )
        effective_answer_type = "number_or_formula"
    else:
        effective_answer_type = raw_answer_type or "number"

    existing_text = ""
    if existing_in_variant:
        for i, p in enumerate(existing_in_variant, 1):
            existing_text += f"  {i}. [{p.get('topic','')}] {p.get('statement','')[:100]}...\n"

    recent_text = ""
    if recent_problems:
        for p in recent_problems[:5]:
            recent_text += f"  - {p[:120]}...\n"

    # NEW (generator v2): variant_date + current_year + forbidden topics from existing
    variant_date_str = variant_date or date.today().isoformat()
    try:
        current_year = int(variant_date_str[:4])
    except (ValueError, TypeError):
        current_year = date.today().year
    existing_topics = []
    if existing_in_variant:
        for p in existing_in_variant:
            t = (p.get("topic") or "").strip()
            if t and t not in existing_topics:
                existing_topics.append(t)
    forbidden_topics_str = ", ".join(existing_topics) if existing_topics else "нет"

    prompt = f"""ПРОФИЛЬ ОЛИМПИАДЫ:
  Олимпиада: {analysis.get('olympiad', '')}
  Класс: {analysis.get('grade', '')}
  Этап: {analysis.get('round', '')}
  Дата варианта: {variant_date_str} (текущий год = {current_year})

ЗАДАНИЕ: Создай задачу для ПОЗИЦИИ {position} из 5.

ТРЕБОВАНИЯ К ЭТОЙ ПОЗИЦИИ:
  Тема: {spec.get('theme') or spec.get('topic') or spec.get('subject') or ''}
  Подтема: {spec.get('subtopic', '')}
  Идея: {spec.get('idea', '')}
  Сложность: {spec.get('difficulty', 5)}/10
  Тип ответа: {effective_answer_type} (ОБЯЗАТЕЛЬНО число / формула / множество значений; НЕ доказательство!)
  Ожидаемые методы: {', '.join(spec.get('expected_techniques', []))}

СТИЛЬ ОЛИМПИАДЫ:
{style_notes}

ЗАПРЕЩЁННЫЕ ТЕМЫ (общие для олимпиады): {forbidden or 'нет'}

⛔ СТРОГО ЗАПРЕЩЕНО ГЕНЕРИРОВАТЬ ЗАДАЧУ ПО ТЕМАМ, УЖЕ ВЗЯТЫМ В ЭТОМ ВАРИАНТЕ: {forbidden_topics_str}
(Это не намёк — каждая тема варианта должна быть уникальной. 5 задач = 5 разных тем.)

ЗАДАЧИ, КОТОРЫЕ УЖЕ ЕСТЬ В ЭТОМ ВАРИАНТЕ (для контекста):
{existing_text or '  (пока нет)'}

ПОСЛЕДНИЕ ЗАДАЧИ НА ЭТУ ТЕМУ (не повторять идеи):
{recent_text or '  (нет данных)'}

═══════════════════════════════════════════════════
⛔ ЗАПРЕЩЁННЫЕ ТИПЫ ЗАДАЧ (автоматический reject):
═══════════════════════════════════════════════════
- Задачи на доказательство. Запрещённые глаголы: "Докажите", "Покажите", "Обоснуйте", "Установите", "Проверьте, что", "Верно ли", "Является ли", "Найдите и докажите".
- Задачи без конкретного числового или формульного ответа.
- Задачи, где ответ — текстовое обоснование ("Да", "Нет", "Существует").

Ответ (answer) ОБЯЗАН быть:
  ✅ Число (целое, дробь): "42", "\\(\\frac{{7}}{{3}}\\)"
  ✅ Выражение: "\\(2\\sqrt{{3}}\\)", "\\(60^\\circ\\)"
  ✅ Множество значений / пары: "1, 2, 5", "\\((45, 2)\\)"
  ❌ НЕ "Доказано", НЕ "Да/Нет", НЕ текстовое описание

═══════════════════════════════════════════════════
🎯 КАЛИБРОВКА СЛОЖНОСТИ
═══════════════════════════════════════════════════
Это РЕГИОНАЛЬНЫЙ этап ВСОШ для {analysis.get('grade', '?')} класса. Целевая сложность 6–8/10.
ЗАПРЕЩЕНО: тривиальные школьные задачи уровня "подставь в формулу корней", "примени теорему Виета в одну строчку".
Задача ДОЛЖНА требовать нетривиальной идеи, комбинации методов или аккуратного перебора случаев.

═══════════════════════════════════════════════════
📅 ГОД В УСЛОВИИ
═══════════════════════════════════════════════════
Если используешь число-год в условии (например, "найдите все натуральные x: x² - y! = N"), число N должно быть равно {current_year} или {current_year}±1. ЗАПРЕЩЕНО использовать 2023, 2024 в варианте {current_year} года.

═══════════════════════════════════════════════════
🔢 ОГРАНИЧЕНИЕ НА ПОВТОР СЮЖЕТНЫХ КОНСТАНТ (v2.2)
═══════════════════════════════════════════════════
Сюжетные числа-константы (год варианта {current_year}, {current_year}-1, {current_year}+1, а также любые "круглые" числа вида 2025, 2026, 2027) можно использовать МАКСИМУМ В ОДНОЙ задаче из 5 в варианте.
Если в списке "ЗАДАЧИ, КОТОРЫЕ УЖЕ ЕСТЬ В ЭТОМ ВАРИАНТЕ" уже встречается такая константа — ОБЯЗАН использовать в этой задаче ДРУГИЕ числа:
  • простые числа (47, 113, 257),
  • степени (2^k, 3^k),
  • комбинаторные константы (n!, C(n,k)),
  • произвольные натуральные числа, подходящие к идее задачи.

═══════════════════════════════════════════════════
🎨 СТРОГОЕ ПРАВИЛО РАЗНООБРАЗИЯ ТЕМ (v2.2)
═══════════════════════════════════════════════════
В одном варианте из 5 задач КАЖДАЯ тема встречается РОВНО ОДИН РАЗ.
Канонический набор тем варианта: алгебра, геометрия, теория чисел, комбинаторика, логика/игры/инварианты.
Если выше в блоке "СТРОГО ЗАПРЕЩЕНО ГЕНЕРИРОВАТЬ ЗАДАЧУ ПО ТЕМАМ, УЖЕ ВЗЯТЫМ В ЭТОМ ВАРИАНТЕ" уже указана твоя целевая тема — СМЕНИ тему на одну из НЕвзятых из канонического списка, при этом сохрани сложность и стилистику позиции.

═══════════════════════════════════════════════════
✏️ LaTeX (КРИТИЧНО — иначе KaTeX не отрендерит)
═══════════════════════════════════════════════════
- ВСЕГДА \\frac{{a}}{{b}}, НИКОГДА rac{{a}}{{b}} (без обратного слэша — баг!).
- ВСЕГДА \\sqrt, \\cdot, \\angle, \\pmod, \\equiv — все команды с обратным слэшем.
- Углы: \\(60^\\circ\\), НЕ "60°" (символ ° KaTeX не понимает).
- Inline-математика: \\( ... \\). Display-математика: \\[ ... \\].
- ЗАПРЕЩЕНО $...$, $$...$$.
- Каждый \\frac имеет ровно два {{}} после: \\frac{{числитель}}{{знаменатель}}.

═══════════════════════════════════════════════════
🔬 SELF-CHECK ПЕРЕД ВЫДАЧЕЙ JSON
═══════════════════════════════════════════════════
Прежде чем вернуть JSON, мысленно проверь:
1. Условие НЕ содержит логических противоречий.
   ⚠️ Пример бага: "точка C на ω₁, точка D на ω₂, отрезок CD касается обеих окружностей" — противоречие, потому что точка касания определяется однозначно, а не выбирается произвольно.
2. ВСЕ данные в условии используются в решении. Если параметр r₁, r₂ не влияет на ответ — это ошибка условия (либо нужно добавить условие, использующее их, либо убрать упоминание).
3. Ответ — конкретное число / формула / множество, не текст и не доказательство.
4. LaTeX: каждый \\frac, \\sqrt, \\angle, \\circ начинается с обратного слэша.
5. Сложность соответствует позиции и регион. этапу 9 класса (6-8/10).

Думай шаг за шагом:
1. Придумай ОРИГИНАЛЬНУЮ математическую идею (не из стандартного школьного набора).
2. Оберни её в условие в стиле этой олимпиады.
3. Реши задачу полностью.
4. Прогон self-check (5 пунктов выше).
5. Если хоть один пункт self-check провалился — переработай задачу или верни {{"status": "reject", "reason": "..."}}.

Верни ТОЛЬКО валидный JSON:
{{
  "statement": "Условие на русском с LaTeX через \\\\( \\\\) и \\\\[ \\\\]",
  "solution": "Полное решение",
  "answer": "Краткий ответ",
  "topic": "тема на русском",
  "difficulty": число 1-10,
  "method": "основной метод",
  "idea_summary": "краткое описание идеи"
}}

Если не можешь — верни: {{"status": "reject", "reason": "..."}}"""

    result = _chat_with_fallback(
        messages=[
            {"role": "system", "content": "Ты — составитель олимпиадных задач мирового уровня. LaTeX ТОЛЬКО через \\( \\) и \\[ \\]. Язык: русский."},
            {"role": "user", "content": prompt}
        ],
        temperature=TEMPERATURE,
        max_tokens=6144,
    )
    model_used = result.get("_model_used", MODEL)

    content = result["content"]
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        data = _parse_json_with_latex(content.strip())
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"[Generator] JSON parse error: {e}")
        raise ValueError(f"Generator returned invalid JSON: {content[:200]}")

    if data.get("status") == "reject":
        raise ValueError(f"Generator rejected: {data.get('reason', 'unknown')}")

    # Validate required fields
    required = ["statement", "solution", "answer"]
    for field in required:
        if not data.get(field):
            raise ValueError(f"Generator missing field: {field}")

    # NEW (generator v2 / v2.2): post-process LaTeX bugs in returned strings
    def _fix_latex(s):
        if not isinstance(s, str):
            return s
        before = s
        # rac{...} not preceded by '\\f' or alpha/backslash -> \\frac{...}
        s = re.sub(r'(?<![\\A-Za-z])rac\{', r'\\frac{', s)
        # v2.2: inom{...}{...} not preceded by '\\b' -> \\binom{...}{...}
        s = re.sub(r'(?<![\\A-Za-z])inom\{', r'\\binom{', s)
        # v2.2: qrt{...} not preceded by '\\s' -> \\sqrt{...}
        s = re.sub(r'(?<![\\A-Za-z])qrt\{', r'\\sqrt{', s)
        # v2.2: broken \\right (matches "ight)" "ight]" "ight}" "ight.") not preceded by '\\r'
        s = re.sub(r'(?<![\\A-Za-z])ight([\)\]\}\.])', r'\\right\1', s)
        # v2.2: broken \\left (matches "eft(" "eft[" "eft\\{") not preceded by '\\l'
        s = re.sub(r'(?<![\\A-Za-z])eft([\(\[\\])', r'\\left\1', s)
        # standalone degree symbol -> ^\\circ
        s = s.replace('°', '^\\circ')
        if s != before:
            logger.warning(f"[Generator] LaTeX post-fix applied (pos={position})")
        return s

    for k in ("statement", "solution", "answer"):
        if k in data:
            data[k] = _fix_latex(data[k])

    # Attach cost info
    data["_usage"] = result["usage"]
    data["_cost"] = result["cost_usd"]

    openrouter.log_cost_to_db('generate', model_used, result['usage'], result['cost_usd'])
    # v2.3: programmatic post-parse validation (raises ValueError -> retry-guard)
    validate_generated_problem(data, existing_in_variant or [], current_year, dominant_theme)
    logger.info(
        f"[Generator] pos={position} topic={data.get('topic','')} "
        f"model={model_used} ${result['cost_usd']:.4f}"
    )
    return data
