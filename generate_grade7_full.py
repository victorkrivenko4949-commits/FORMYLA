#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полная генерация 1050 олимпиадных задач для 7 класса.
30 параллельных воркеров. Resume mode.

Распределение:
- Уровень 1: 15 задач на тему
- Уровень 2: 20 задач на тему
- Уровень 3: 25 задач на тему
- Уровень 4: 20 задач на тему
- Уровень 5: 15 задач на тему
- Уровень 6: 8 задач на тему
- Уровень 7: 2 задачи на тему
Итого: 105 задач × 10 тем = 1050
"""

import asyncio
import aiohttp
import json
import os
import sys
import re
import time
from dotenv import load_dotenv

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT = "grade7_olympiad_RAW.jsonl"
MAX_WORKERS = 30
LOCK = asyncio.Lock()
stats = {"ok": 0, "fail": 0, "fallback": 0}

# 10 тем × распределение по уровням
TOPICS = [
    ("algebra_expressions", "Алгебраические тождества и преобразования"),
    ("linear_equations", "Линейные уравнения и системы"),
    ("functions", "Функции и графики"),
    ("geometry_basics", "Начала геометрии"),
    ("triangles", "Треугольники"),
    ("proofs_geometry", "Геометрические доказательства"),
    ("combinatorics_7", "Комбинаторика"),
    ("number_theory_7", "Теория чисел"),
    ("logic_invariants", "Логика и инварианты"),
    ("inequalities_7", "Неравенства"),
]

# Количество задач на каждый уровень
LEVEL_COUNTS = {1: 15, 2: 20, 3: 25, 4: 20, 5: 15, 6: 8, 7: 2}

CALIBRATION = """
ПРИМЕРЫ ХОРОШИХ ОЛИМПИАДНЫХ ЗАДАЧ (эталон стиля):

Уровень 1: "Сумма трёх натуральных чисел равна 10. Может ли их произведение быть равно 36?"

Уровень 3: "Число N — трёхзначное, кратно 7. Если переставить его цифры в обратном порядке, получится число, кратное 9. Найдите наименьшее такое N."

Уровень 5: "В клетчатом квадрате 7×7 закрашены некоторые клетки так, что в каждой строке и каждом столбце закрашено ровно 3 клетки. Докажите, что число закрашенных клеток чётно тогда и только тогда, когда главная диагональ пересекает чётное число закрашенных клеток."

Уровень 7: "Дано натуральное n >= 2. На доске написаны числа 1, 2, ..., n. За один ход разрешается стереть два числа a и b и записать вместо них число ab + a + b. Какое число может остаться на доске после n-1 ходов?"

ЗАПРЕЩЕНО:
- "Реши уравнение 2x + 5 = 11" — школа
- "Найди площадь треугольника с основанием 10 и высотой 4" — механика
- "Раскрой скобки (a+b)²" — упражнение из учебника
"""


def get_prompt(topic_id: str, topic_name: str, level: int, task_num: int) -> str:
    return f"""Ты — составитель олимпиадных задач по математике для российской платформы FORMYLA.
Генерируй задачи для 7 класса в стиле Всероссийской олимпиады школьников (ВсОШ).

УРОВНИ СЛОЖНОСТИ:
- 1: чуть выше школьной программы, простая идея
- 2-3: муниципальный этап ВсОШ
- 4-5: региональный этап ВсОШ
- 6-7: заключительный этап ВсОШ

ТЕМА: {topic_name} (id: {topic_id})
УРОВЕНЬ: {level}/7
НОМЕР ЗАДАЧИ: {task_num} (генерируй УНИКАЛЬНУЮ задачу, не повторяй предыдущие)

{CALIBRATION}

СТИЛЬ: Олимпиадный, НЕ школьный. Требует идеи, не шаблона.

ТРЕБОВАНИЯ К LaTeX:
- Используй \\\\text{{...}}, \\\\frac{{...}}{{...}}, \\\\cdot — двойной слэш!
- Формулы в \\\\( ... \\\\) для inline

ФОРМАТ (СТРОГО JSON, без markdown):
{{
  "statement": "Условие задачи на русском",
  "answer": "Краткий ответ или 'доказательство'",
  "solution": "Полное олимпиадное решение",
  "level": {level},
  "topic": "{topic_id}",
  "idea_tag": "ключевая идея"
}}"""


def fix_latex(text: str) -> str:
    for c in ['overline', 'sqrt', 'frac', 'geq', 'leq', 'neq', 'cdot',
              'times', 'text', 'left', 'right', 'ldots', 'pmod', 'binom',
              'sum', 'prod', 'int', 'lim', 'infty', 'equiv', 'approx',
              'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda', 'mu',
              'pi', 'sigma', 'phi', 'omega']:
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
        result = json.loads(fix_latex(c))
        stats["fallback"] += 1
        return result
    except Exception:
        pass
    try:
        m = re.search(r'\{.*\}', c, re.DOTALL)
        if m:
            result = json.loads(re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', m.group()))
            stats["fallback"] += 1
            return result
    except Exception:
        pass
    raise ValueError(f"Parse failed: {raw[:200]}")


def load_existing() -> set:
    existing = set()
    if not os.path.exists(OUTPUT):
        return existing
    with open(OUTPUT, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                t = json.loads(line)
                existing.add((t['topic'], t['level'], t.get('task_num', 0)))
            except Exception:
                pass
    return existing


async def gen_one(session, topic_id, topic_name, level, task_num, sem):
    async with sem:
        prompt = get_prompt(topic_id, topic_name, level, task_num)
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Сгенерируй олимпиадную задачу. Верни только JSON."}
            ],
            "temperature": 0.95,
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
                        "task_num": task_num,
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
                        total = stats["ok"] + stats["fail"]
                        print(f"[OK] {stats['ok']}/1050 | {topic_name[:25]} L{level} #{task_num} | Fallback: {stats['fallback']}")
                    return True
            except Exception as e:
                if attempt == 2:
                    async with LOCK:
                        stats["fail"] += 1
                        print(f"[ERR] {topic_name[:25]} L{level} #{task_num}: {str(e)[:60]}")
                    return False
                await asyncio.sleep(2 ** attempt)
        return False


async def main():
    if not API_KEY:
        print("[ERROR] No API key!")
        return

    existing = load_existing()
    already_done = len(existing)

    # Строим список всех задач
    all_tasks = []
    for topic_id, topic_name in TOPICS:
        for level, count in LEVEL_COUNTS.items():
            for task_num in range(1, count + 1):
                key = (topic_id, level, task_num)
                if key not in existing:
                    all_tasks.append((topic_id, topic_name, level, task_num))

    total_remaining = len(all_tasks)
    total_all = sum(LEVEL_COUNTS.values()) * len(TOPICS)

    print(f"\n{'='*70}")
    print(f">>> ГЕНЕРАЦИЯ 1050 ОЛИМПИАДНЫХ ЗАДАЧ ДЛЯ 7 КЛАССА (30 воркеров)")
    print(f"{'='*70}")
    print(f"[*] Всего задач: {total_all}")
    print(f"[*] Уже готово: {already_done}")
    print(f"[*] Осталось: {total_remaining}")
    print(f"[*] Файл: {OUTPUT}")
    print(f"{'='*70}\n")

    if total_remaining == 0:
        print("[DONE] All tasks already generated!")
        return

    sem = asyncio.Semaphore(MAX_WORKERS)
    start = time.time()
    conn = aiohttp.TCPConnector(limit=50, limit_per_host=30)
    async with aiohttp.ClientSession(connector=conn) as session:
        coros = [gen_one(session, tid, tname, lvl, num, sem)
                 for tid, tname, lvl, num in all_tasks]
        await asyncio.gather(*coros)

    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f">>> ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"[OK] Success: {stats['ok']}")
    print(f"[FAIL] Failed: {stats['fail']}")
    print(f"[FALLBACK] Regex fixes: {stats['fallback']}")
    print(f"[TIME] Elapsed: {elapsed/60:.1f} min")
    print(f"[TOTAL] In file: {stats['ok'] + already_done}/{total_all}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
