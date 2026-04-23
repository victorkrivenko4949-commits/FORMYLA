#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генерация 5 задач по Логике для 6 класса (30 воркеров)"""

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
OUTPUT = "grade6_logic5.jsonl"
LOCK = asyncio.Lock()
stats = {"ok": 0, "fail": 0}

TASKS = [
    ("Логика (рыцари и лжецы, логические таблицы)", 1, 101),
    ("Логика (рыцари и лжецы, логические таблицы)", 2, 102),
    ("Логика (рыцари и лжецы, логические таблицы)", 3, 103),
    ("Логика (рыцари и лжецы, логические таблицы)", 4, 104),
    ("Логика (рыцари и лжецы, логические таблицы)", 5, 105),
    ("Логика (рыцари и лжецы, логические таблицы)", 6, 106),
    ("Логика (рыцари и лжецы, логические таблицы)", 7, 107),
]


def fix_latex(text):
    for c in ['overline', 'sqrt', 'frac', 'geq', 'leq', 'neq', 'cdot',
              'times', 'text', 'left', 'right', 'ldots', 'pmod', 'binom']:
        text = re.sub(r'(?<!\\)\\(' + c + r')(?![a-zA-Z])', r'\\\\\1', text)
    return text


def parse_json(raw):
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
    raise ValueError(f"Parse failed: {raw[:100]}")


def get_prompt(topic, level):
    return f"""Ты составитель олимпиадных задач для 6 класса.
Придумай ОДНУ оригинальную задачу.

ТЕМА: {topic}
ОПИСАНИЕ: Задачи на логику: рыцари всегда говорят правду, лжецы всегда лгут. Логические таблицы истинности. Логические выводы.
СЛОЖНОСТЬ: {level} из 7

ВАЖНО ДЛЯ JSON:
- Используй $ ... $ для inline формул
- Все LaTeX команды внутри $ $ должны иметь ДВОЙНОЙ слеш: \\\\frac, \\\\sqrt

ФОРМАТ (строго JSON без markdown):
{{
  "question": "Текст задачи",
  "answer": "Краткий ответ",
  "explanation": "Пошаговое решение"
}}"""


async def gen_one(session, topic, level, num, sem):
    async with sem:
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": get_prompt(topic, level)},
                {"role": "user", "content": "Сгенерируй задачу. Верни только JSON."}
            ],
            "temperature": 0.9,
            "max_tokens": 1500
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
                    if not all(k in tj for k in ["question", "answer", "explanation"]):
                        raise ValueError("Missing fields")
                    task = {"grade": 6, "topic": topic, "level": level,
                            "task_number": num, "question": tj["question"],
                            "answer": tj["answer"], "explanation": tj["explanation"]}
                    async with LOCK:
                        with open(OUTPUT, "a", encoding="utf-8") as f:
                            json.dump(task, f, ensure_ascii=False)
                            f.write("\n")
                        stats["ok"] += 1
                        print(f"[OK] {stats['ok']} | {topic[:25]} L{level} #{num}")
                    return True
            except Exception as e:
                if attempt == 2:
                    async with LOCK:
                        stats["fail"] += 1
                        print(f"[ERR] L{level} #{num}: {str(e)[:60]}")
                    return False
                await asyncio.sleep(2 ** attempt)
        return False


async def main():
    if not API_KEY:
        print("[ERROR] No API key!")
        return
    print(f"\n>>> Генерация {len(TASKS)} задач по Логике (30 воркеров)\n")
    sem = asyncio.Semaphore(30)
    conn = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=conn) as session:
        coros = [gen_one(session, t, l, n, sem) for t, l, n in TASKS]
        await asyncio.gather(*coros)
    print(f"\n[DONE] OK: {stats['ok']}, FAIL: {stats['fail']}")


if __name__ == "__main__":
    asyncio.run(main())
