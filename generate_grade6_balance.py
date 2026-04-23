#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Балансировщик задач для 6 класса.
Генерирует задачи только для дефицитных тем.
Использует 30 параллельных воркеров.
"""

import asyncio
import aiohttp
import json
import os
import sys
import time
import re
from dotenv import load_dotenv

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "grade6_balance_RAW.jsonl"
MAX_WORKERS = 30
LOCK = asyncio.Lock()

stats = {"success": 0, "failed": 0, "fallback": 0}

# Дефицит по темам (из анализа)
DEFICIT = {
    'Принцип Дирихле': 54,
    'Признаки делимости и остатки': 41,
    'Логика (рыцари и лжецы, логические таблицы)': 39,
    'Дроби, доли и пропорции': 32,
    'Геометрия (периметры и площади)': 6,
}

TOPIC_DESCRIPTIONS = {
    'Принцип Дирихле': 'Принцип Дирихле (принцип ящиков): если n+1 предмет разложить в n ящиков, то хотя бы в одном ящике окажется не менее 2 предметов. Геометрический и числовой Дирихле.',
    'Признаки делимости и остатки': 'Признаки делимости на 2, 3, 4, 5, 9, 11. Остатки от деления. Последние цифры степеней. Задачи на делимость.',
    'Логика (рыцари и лжецы, логические таблицы)': 'Задачи на логику: рыцари всегда говорят правду, лжецы всегда лгут. Логические таблицы истинности. Логические выводы.',
    'Дроби, доли и пропорции': 'Олимпиадные задачи на дроби, части, доли и пропорции. Текстовые задачи с дробями.',
    'Геометрия (периметры и площади)': 'Периметры и площади фигур, составленных из прямоугольников. Геометрия на клетчатой бумаге.',
}

DIFFICULTY_DESCRIPTIONS = {
    1: 'Базовая задача. Прямое применение одной идеи. 2-3 действия.',
    2: 'Школьный этап ВсОШ. Требует понимания олимпиадного метода.',
    3: 'Муниципальный этап ВсОШ. Комбинация базовых идей.',
    4: 'Сложный муниципальный. Несколько шагов рассуждений.',
    5: 'Математический праздник МГУ. Метод Оценка+Пример.',
    6: 'Региональный этап Эйлера. Глубокая логика.',
    7: 'Заключительный этап ВсОШ. Гениальные идеи.',
}


def fix_latex_escapes(text: str) -> str:
    latex_commands = [
        'overline', 'underline', 'sqrt', 'frac', 'dfrac',
        'sum', 'prod', 'int', 'lim', 'max', 'min',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'theta', 'lambda',
        'mu', 'pi', 'sigma', 'phi', 'omega',
        'geq', 'leq', 'neq', 'approx', 'equiv', 'cdot', 'times', 'div',
        'infty', 'partial', 'forall', 'exists', 'in', 'notin',
        'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow',
        'pmod', 'bmod', 'text', 'mathrm', 'mathbf', 'mathbb',
        'left', 'right', 'ldots', 'cdots', 'quad', 'qquad',
        'le', 'ge', 'ne', 'to', 'land', 'lor', 'lnot',
        'lceil', 'rceil', 'lfloor', 'rfloor', 'langle', 'rangle',
        'hat', 'tilde', 'bar', 'vec', 'dot', 'ddot',
        'binom', 'gcd', 'lcm', 'not', 'mid', 'pm', 'mp',
    ]
    for cmd in latex_commands:
        text = re.sub(r'(?<!\\)\\(' + cmd + r')(?![a-zA-Z])', r'\\\\\1', text)
    text = re.sub(r'(?<!\\)\\([\(\)\[\]])', r'\\\\\1', text)
    return text


def extract_json(raw: str) -> dict:
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    try:
        fixed = fix_latex_escapes(cleaned)
        result = json.loads(fixed)
        stats["fallback"] += 1
        return result
    except json.JSONDecodeError:
        pass

    try:
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            fixed = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_match.group())
            result = json.loads(fixed)
            stats["fallback"] += 1
            return result
    except Exception:
        pass

    try:
        q = re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        a = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        e = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        if q and a and e:
            stats["fallback"] += 1
            return {"question": q.group(1), "answer": a.group(1), "explanation": e.group(1)}
    except Exception:
        pass

    raise ValueError(f"JSON parse failed: {raw[:200]}")


def get_prompt(topic: str, level: int, task_num: int) -> str:
    desc = TOPIC_DESCRIPTIONS.get(topic, topic)
    level_desc = DIFFICULTY_DESCRIPTIONS.get(level, '')
    return f"""Ты составитель олимпиадных задач для 6 класса.
Придумай ОДНУ оригинальную задачу #{task_num}.

ТЕМА: {topic}
ОПИСАНИЕ: {desc}
СЛОЖНОСТЬ: {level} из 7 — {level_desc}

ВАЖНО ДЛЯ JSON:
- Используй $ ... $ для inline формул
- Используй $$ ... $$ для display формул
- Все LaTeX команды внутри $ $ должны иметь ДВОЙНОЙ слеш: \\\\overline, \\\\frac, \\\\sqrt

ФОРМАТ (строго JSON без markdown):
{{
  "question": "Текст задачи с формулами в $...$",
  "answer": "Краткий ответ без слова Ответ:",
  "explanation": "Пошаговое решение"
}}"""


def load_existing() -> set:
    existing = set()
    if not os.path.exists(OUTPUT_FILE):
        return existing
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                t = json.loads(line)
                existing.add((t['topic'], t['level'], t['task_number']))
            except Exception:
                pass
    return existing


async def generate_one(session: aiohttp.ClientSession, topic: str, level: int, task_num: int, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        prompt = get_prompt(topic, level, task_num)
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Сгенерируй задачу. Верни только JSON."}
            ],
            "temperature": 0.9,
            "max_tokens": 2000
        }
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        for attempt in range(3):
            try:
                async with session.post(API_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    task_json = extract_json(content)

                    if not all(k in task_json for k in ["question", "answer", "explanation"]):
                        raise ValueError("Missing fields")

                    ans = task_json["answer"]
                    for prefix in ["Ответ:", "ответ:", "Answer:"]:
                        if ans.lower().startswith(prefix.lower()):
                            ans = ans[len(prefix):].strip()
                    task_json["answer"] = ans

                    task = {
                        "grade": 6,
                        "topic": topic,
                        "level": level,
                        "task_number": task_num,
                        "question": task_json["question"],
                        "answer": task_json["answer"],
                        "explanation": task_json["explanation"],
                    }

                    async with LOCK:
                        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                            json.dump(task, f, ensure_ascii=False)
                            f.write("\n")
                        stats["success"] += 1
                        total = stats["success"] + stats["failed"]
                        print(f"[OK] {total} | {topic[:30]} L{level} #{task_num} | Fallback: {stats['fallback']}")

                    return True

            except Exception as e:
                if attempt == 2:
                    async with LOCK:
                        stats["failed"] += 1
                        print(f"[ERR] {topic[:30]} L{level} #{task_num}: {str(e)[:60]}")
                    return False
                await asyncio.sleep(2 ** attempt)

        return False


async def main():
    if not API_KEY:
        print("[ERROR] DEEPSEEK_API_KEY not found!")
        return

    existing = load_existing()

    # Строим список задач для генерации
    all_tasks = []
    for topic, deficit in DEFICIT.items():
        # Распределяем дефицит по уровням равномерно
        per_level = deficit // 7
        remainder = deficit % 7

        task_num = 1
        for level in range(1, 8):
            count = per_level + (1 if level <= remainder else 0)
            for i in range(count):
                key = (topic, level, task_num)
                if key not in existing:
                    all_tasks.append((topic, level, task_num))
                task_num += 1

    total_remaining = len(all_tasks)
    total_deficit = sum(DEFICIT.values())

    print(f"\n{'='*70}")
    print(f">>> БАЛАНСИРОВЩИК ЗАДАЧ 6 КЛАССА - 30 WORKERS")
    print(f"{'='*70}")
    print(f"[*] Дефицит: {total_deficit} задач")
    print(f"[*] Уже сгенерировано: {len(existing)}")
    print(f"[*] Осталось: {total_remaining}")
    print(f"[*] Workers: {MAX_WORKERS}")
    print(f"[*] Output: {OUTPUT_FILE}")
    print(f"\nПо темам:")
    for topic, deficit in sorted(DEFICIT.items(), key=lambda x: -x[1]):
        print(f"  - {topic}: +{deficit}")
    print(f"{'='*70}\n")

    if total_remaining == 0:
        print("[DONE] All deficit tasks already generated!")
        return

    semaphore = asyncio.Semaphore(MAX_WORKERS)
    start_time = time.time()

    connector = aiohttp.TCPConnector(limit=50, limit_per_host=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            generate_one(session, topic, level, task_num, semaphore)
            for topic, level, task_num in all_tasks
        ]
        await asyncio.gather(*tasks)

    elapsed = time.time() - start_time

    print(f"\n{'='*70}")
    print(f">>> ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"[OK] Success: {stats['success']}")
    print(f"[FAIL] Failed: {stats['failed']}")
    print(f"[FALLBACK] Regex fixes: {stats['fallback']}")
    print(f"[TIME] Elapsed: {elapsed/60:.1f} min")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
