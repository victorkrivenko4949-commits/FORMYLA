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

from config.models import GENERATOR_MODEL as MODEL, GENERATOR_TEMPERATURE as TEMPERATURE


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
    predicted = analysis.get("predicted_variant", [])
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
  Тема: {spec.get('theme', '')}
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

    result = openrouter.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты — составитель олимпиадных задач мирового уровня. LaTeX ТОЛЬКО через \\( \\) и \\[ \\]. Язык: русский."},
            {"role": "user", "content": prompt}
        ],
        temperature=TEMPERATURE,
        max_tokens=6144,
    )

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

    # NEW (generator v2): post-process LaTeX bugs in returned strings
    def _fix_latex(s):
        if not isinstance(s, str):
            return s
        before = s
        # rac{...}{...}  not preceded by '\\f' or alpha/backslash -> \\frac
        s = re.sub(r'(?<![\\A-Za-z])rac\{', r'\\frac{', s)
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

    openrouter.log_cost_to_db('generate', MODEL, result['usage'], result['cost_usd'])
    logger.info(f"[Generator] pos={position} topic={data.get('topic','')} ${result['cost_usd']:.4f}")
    return data
