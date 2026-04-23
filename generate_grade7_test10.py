#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ТЕСТ: Генерация 10 олимпиадных задач для 7 класса.
Проверяем олимпиадность перед полной генерацией.
"""

import asyncio
import aiohttp
import json
import os
import sys
import re
from dotenv import load_dotenv

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT = "grade7_test10.jsonl"
LOCK = asyncio.Lock()
stats = {"ok": 0, "fail": 0}

# 10 тестовых задач: по одной на каждую тему, уровни 2-4
TEST_TASKS = [
    ("algebra_expressions", 3, "Алгебраические тождества и преобразования"),
    ("linear_equations", 2, "Линейные уравнения и системы"),
    ("functions", 3, "Функции и графики"),
    ("geometry_basics", 2, "Начала геометрии"),
    ("triangles", 3, "Треугольники"),
    ("proofs_geometry", 4, "Геометрические доказательства"),
    ("combinatorics_7", 3, "Комбинаторика"),
    ("number_theory_7", 3, "Теория чисел"),
    ("logic_invariants", 4, "Логика и инварианты"),
    ("inequalities_7", 3, "Неравенства"),
]

CALIBRATION_EXAMPLES = """
ПРИМЕРЫ ХОРОШИХ ОЛИМПИАДНЫХ ЗАДАЧ (используй как эталон стиля):

Уровень 1: "Сумма трёх натуральных чисел равна 10. Может ли их произведение быть равно 36?"

Уровень 3 (муниципальный): "Число N — трёхзначное, кратно 7. Если переставить его цифры в обратном порядке, получится число, кратное 9. Найдите наименьшее такое N."

Уровень 5 (региональный): "В клетчатом квадрате 7×7 закрашены некоторые клетки так, что в каждой строке и каждом столбце закрашено ровно 3 клетки. Докажите, что число закрашенных клеток чётно тогда и только тогда, когда главная диагональ пересекает чётное число закрашенных клеток."

Уровень 7 (заключительный): "Дано натуральное n >= 2. На доске написаны числа 1, 2, ..., n. За один ход разрешается стереть два числа a и b и записать вместо них число ab + a + b. Какое число может остаться на доске после n-1 ходов?"

ПРИМЕРЫ ПЛОХИХ ЗАДАЧ (НЕ ГЕНЕРИРОВАТЬ):
- "Реши уравнение 2x + 5 = 11" — это школа, не олимпиада
- "Найди площадь треугольника с основанием 10 и высотой 4" — механика
- "Раскрой скобки (a+b)²" — упражнение из учебника
"""


def get_system_prompt(topic_id: str, level: int, topic_name: str) -> str:
    return f"""Ты — составитель олимпиадных задач по математике для российской платформы FORMYLA.
Генерируй задачи для 7 класса в стиле Всероссийской олимпиады школьников (ВсОШ).

УРОВНИ СЛОЖНОСТИ:
- 1: чуть выше школьной программы, простая идея
- 2-3: муниципальный этап ВсОШ
- 4-5: региональный этап ВсОШ
- 6-7: заключительный этап ВсОШ

ТЕМА: {topic_name} (id: {topic_id})
УРОВЕНЬ: {level}/7

{CALIBRATION_EXAMPLES}

СТИЛЬ ЗАДАЧ:
- Олимпиадный, НЕ школьный
- Требуют идеи, не шаблонного применения формул
- Короткое условие, элегантное решение
- Подобные задачам из сборников Агаханова, Прасолова, архивам ВсОШ

ТРЕБОВАНИЯ К LaTeX В JSON:
- Используй \\\\text{{...}}, \\\\frac{{...}}{{...}}, \\\\cdot — двойной слэш!
- Никогда не писать ext{{...}}, rac{{...}}, cdot без слэша
- Формулы в \\\\( ... \\\\) для inline, \\\\[ ... \\\\] для display

ФОРМАТ ВЫДАЧИ (СТРОГО JSON, без markdown):
{{
  "statement": "Условие задачи на русском",
  "answer": "Краткий ответ или 'доказательство'",
  "solution": "Полное олимпиадное решение с обоснованием",
  "level": {level},
  "topic": "{topic_id}",
  "idea_tag": "ключевая идея решения"
}}"""


def fix_latex(text: str) -> str:
    for c in ['overline', 'sqrt', 'frac', 'geq', 'leq', 'neq', 'cdot',
              'times', 'text', 'left', 'right', 'ldots', 'pmod', 'binom',
              'sum', 'prod', 'int', 'lim', 'infty', 'equiv', 'approx']:
        text = re.sub(r'(?<!\\)\\(' + c + r')(?![a-zA-Z])', r'\\\\\1', text)
    return text


def parse_json(raw: str) -> dict:
    c = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    c = re.sub(r'\s*```\s*$', '', c, flags=re.MULTILINE).strip()
    try:
        return json.loads(c)
    except Exception:
        pass
    try:
        return json.loads(fix_latex(c))
    except Exception:
        pass
    try:
        m = re.search(r'\{.*\}', c, re.DOTALL)
        if m:
            return json.loads(re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', m.group()))
    except Exception:
        pass
    raise ValueError(f"Parse failed: {raw[:200]}")


async def gen_one(session, topic_id, level, topic_name, sem):
    async with sem:
        prompt = get_system_prompt(topic_id, level, topic_name)
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Сгенерируй одну олимпиадную задачу. Верни только JSON."}
            ],
            "temperature": 0.9,
            "max_tokens": 2000
        }
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                async with session.post(API_URL, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    tj = parse_json(content)
                    if not all(k in tj for k in ["statement", "answer", "solution"]):
                        raise ValueError("Missing fields")
                    task = {
                        "grade": 7,
                        "topic": topic_id,
                        "topic_name": topic_name,
                        "level": level,
                        "statement": tj["statement"],
                        "answer": tj["answer"],
                        "solution": tj["solution"],
                        "idea_tag": tj.get("idea_tag", "")
                    }
                    async with LOCK:
                        with open(OUTPUT, "a", encoding="utf-8") as f:
                            json.dump(task, f, ensure_ascii=False)
                            f.write("\n")
                        stats["ok"] += 1
                        print(f"[OK] {stats['ok']} | {topic_name[:30]} L{level}")
                        print(f"     Условие: {tj['statement'][:100]}...")
                        print(f"     Ответ: {tj['answer']}")
                        print(f"     Идея: {tj.get('idea_tag', 'N/A')}")
                        print()
                    return True
            except Exception as e:
                if attempt == 2:
                    async with LOCK:
                        stats["fail"] += 1
                        print(f"[ERR] {topic_name[:30]} L{level}: {str(e)[:60]}")
                    return False
                await asyncio.sleep(2 ** attempt)
        return False


async def main():
    if not API_KEY:
        print("[ERROR] No API key!")
        return
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)
    print(f"\n>>> ТЕСТ: Генерация 10 олимпиадных задач для 7 класса\n")
    sem = asyncio.Semaphore(10)
    conn = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=conn) as session:
        coros = [gen_one(session, tid, lvl, tname, sem) for tid, lvl, tname in TEST_TASKS]
        await asyncio.gather(*coros)
    print(f"\n[DONE] OK: {stats['ok']}, FAIL: {stats['fail']}")
    print(f"[FILE] {OUTPUT}")
    print("\n>>> ПРОВЕРЬ ОЛИМПИАДНОСТЬ ЗАДАЧ ВЫШЕ!")
    print(">>> Если все задачи олимпиадные — запускай полную генерацию.")


if __name__ == "__main__":
    asyncio.run(main())
