#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный генератор задач для 6 класса - 30 параллельных воркеров
Resume mode: продолжает с места остановки
"""

import asyncio
import aiohttp
import json
import os
import sys
import time
import re
from typing import Dict, Any, Set, Tuple
from dotenv import load_dotenv
from topics_grade6 import GRADE_6_TOPICS, DIFFICULTY_LEVELS, TASKS_PER_CELL

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "grade6_olympiad_RAW.jsonl"
MAX_WORKERS = 30
LOCK = asyncio.Lock()

# Статистика
stats = {"success": 0, "failed": 0, "fallback": 0}


def fix_latex_escapes(text: str) -> str:
    latex_commands = [
        'overline', 'underline', 'sqrt', 'frac', 'dfrac', 'cfrac',
        'sum', 'prod', 'int', 'lim', 'max', 'min',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'theta', 'lambda',
        'mu', 'pi', 'sigma', 'phi', 'omega', 'Omega', 'Sigma', 'Delta',
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


def extract_json_bulletproof(raw: str) -> Dict[str, Any]:
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fix LaTeX escapes
    try:
        fixed = fix_latex_escapes(cleaned)
        result = json.loads(fixed)
        stats["fallback"] += 1
        return result
    except json.JSONDecodeError:
        pass

    # Strategy 3: aggressive fix - double all single backslashes
    try:
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            fixed = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_str)
            result = json.loads(fixed)
            stats["fallback"] += 1
            return result
    except Exception:
        pass

    # Strategy 4: regex field extraction
    try:
        q = re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        a = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        e = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        if q and a and e:
            stats["fallback"] += 1
            return {"question": q.group(1), "answer": a.group(1), "explanation": e.group(1)}
    except Exception:
        pass

    raise ValueError(f"All JSON strategies failed. Response: {raw[:200]}")


def get_prompt(topic: Dict, level: int) -> str:
    return f"""Ты составитель олимпиадных задач для 6 класса.
Придумай ОДНУ оригинальную задачу.

ТЕМА: {topic['name']}
ОПИСАНИЕ: {topic['description']}
СЛОЖНОСТЬ: {level} из 7

ВАЖНО ДЛЯ JSON:
- Используй $ ... $ для inline формул
- Используй $$ ... $$ для display формул
- Для \\overline{{abc}} пиши: $\\\\overline{{abc}}$
- Для \\frac{{a}}{{b}} пиши: $\\\\frac{{a}}{{b}}$
- Все LaTeX команды внутри $ $ должны иметь ДВОЙНОЙ слеш: \\\\overline, \\\\frac, \\\\sqrt

ФОРМАТ (строго JSON без markdown):
{{
  "question": "Текст задачи с формулами в $...$",
  "answer": "Краткий ответ без слова Ответ:",
  "explanation": "Пошаговое решение"
}}"""


def load_existing() -> Set[Tuple]:
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


async def generate_one(session: aiohttp.ClientSession, topic: Dict, level: int, task_num: int, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        prompt = get_prompt(topic, level)
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
                    task_json = extract_json_bulletproof(content)

                    if not all(k in task_json for k in ["question", "answer", "explanation"]):
                        raise ValueError("Missing fields")

                    # Clean answer
                    ans = task_json["answer"]
                    for prefix in ["Ответ:", "ответ:", "Answer:"]:
                        if ans.lower().startswith(prefix.lower()):
                            ans = ans[len(prefix):].strip()
                    task_json["answer"] = ans

                    task = {
                        "grade": 6,
                        "topic": topic['name'],
                        "level": level,
                        "task_number": task_num,
                        "question": task_json["question"],
                        "answer": task_json["answer"],
                        "explanation": task_json["explanation"],
                        "keywords": topic['keywords']
                    }

                    async with LOCK:
                        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                            json.dump(task, f, ensure_ascii=False)
                            f.write("\n")
                        stats["success"] += 1
                        total = stats["success"] + stats["failed"]
                        print(f"[OK] {total} | {topic['name'][:25]} L{level} #{task_num} | Fallback: {stats['fallback']}")

                    return True

            except Exception as e:
                if attempt == 2:
                    async with LOCK:
                        stats["failed"] += 1
                        print(f"[ERR] {topic['name'][:25]} L{level} #{task_num}: {str(e)[:60]}")
                    return False
                await asyncio.sleep(2 ** attempt)

        return False


async def main():
    if not API_KEY:
        print("[ERROR] DEEPSEEK_API_KEY not found!")
        return

    # Load existing tasks
    existing = load_existing()
    already_done = len(existing)

    # Build task list
    all_tasks = []
    for topic in GRADE_6_TOPICS:
        for level in DIFFICULTY_LEVELS:
            for task_num in range(1, TASKS_PER_CELL + 1):
                key = (topic['name'], level, task_num)
                if key not in existing:
                    all_tasks.append((topic, level, task_num))

    total_remaining = len(all_tasks)
    total_all = len(GRADE_6_TOPICS) * len(DIFFICULTY_LEVELS) * TASKS_PER_CELL

    print(f"\n{'='*70}")
    print(f">>> ASYNC GENERATOR v1 - 30 WORKERS")
    print(f"{'='*70}")
    print(f"[*] Total tasks: {total_all}")
    print(f"[*] Already done: {already_done}")
    print(f"[*] Remaining: {total_remaining}")
    print(f"[*] Workers: {MAX_WORKERS}")
    print(f"[*] Output: {OUTPUT_FILE}")
    print(f"{'='*70}\n")

    if total_remaining == 0:
        print("[DONE] All tasks already generated!")
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
    total_done = stats["success"] + already_done

    print(f"\n{'='*70}")
    print(f">>> GENERATION COMPLETE!")
    print(f"[OK] Success: {stats['success']}")
    print(f"[FAIL] Failed: {stats['failed']}")
    print(f"[FALLBACK] Regex fixes: {stats['fallback']}")
    print(f"[TIME] Elapsed: {elapsed/60:.1f} min")
    print(f"[TOTAL] In file: {total_done}/{total_all}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
