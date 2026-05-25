# -*- coding: utf-8 -*-
"""Шаг 1: сгенерировать ~100 новых тем секретов через DeepSeek.

Берёт текущие 23 темы из secrets_dump.json, передаёт их DeepSeek
в качестве уже занятых, просит вернуть строгий JSON-массив из 100
новых уникальных тем в том же формате (topic, title, difficulty_level).

Выход: scripts/_new_secret_titles.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

# Allow importing from project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if sys.platform == 'win32':
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    except Exception:
        pass

from ai.deepseek_client import DeepSeekClient  # noqa: E402

EXISTING_PATH = os.path.join(ROOT, 'secrets_dump.json')
OUT_PATH = os.path.join(ROOT, 'scripts', '_new_secret_titles.json')
TARGET_COUNT = 100


def load_existing() -> list:
    if not os.path.exists(EXISTING_PATH):
        return []
    with open(EXISTING_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_prompt(existing: list) -> str:
    """Промпт для DeepSeek: вернуть 100 новых тем строгим JSON-массивом."""
    occupied_lines = [
        f'  - [{s.get("difficulty_level", "?")}] {s.get("topic")} :: {s.get("title")}'
        for s in existing
    ]
    occupied = '\n'.join(occupied_lines)
    return f'''Ты — методист олимпиадной математики. На сайте FORMYLA есть раздел "Секреты" — каталог теоретических заметок для подготовки к ВсОШ.

УЖЕ ЕСТЬ {len(existing)} тем (их брать НЕЛЬЗЯ, нужны НОВЫЕ):
{occupied}

Существующие 6 категорий (используй ТОЛЬКО их в поле "topic"):
  - "Теория чисел"
  - "Комбинаторика"
  - "Алгебра"
  - "Геометрия"
  - "Логика"
  - "Графы"

Сложности (поле "difficulty_level"): 1 (базовая, 5–7 класс), 2 (средняя, 7–9 класс), 3 (продвинутая, 9–11 класс).

ЗАДАЧА: Сгенерируй РОВНО {TARGET_COUNT} НОВЫХ тем (не пересекающихся с уже существующими), которые будут полезны школьникам и олимпиадникам. Хорошие примеры классических методов и сюжетов:
  - "Возвратные последовательности и их характеристические уравнения"
  - "Метод математической индукции: усиление утверждения"
  - "Симметрические многочлены и формулы Ньютона"
  - "Геометрия Лобачевского для олимпиадника" (если уместно)
  - "Преобразование Эйлера для подсчёта"
  - "Лемма о 5 кругах"
  - "Лемма Холла о паросочетаниях"
  и т.п.

Распределяй темы примерно равномерно по 6 категориям (16–18 тем на категорию).
Среди сложностей: 1 ≈ 20%, 2 ≈ 50%, 3 ≈ 30%.

ВЫХОДНОЙ ФОРМАТ — СТРОГО валидный JSON-массив длины {TARGET_COUNT} без какого-либо текста до или после. Каждый элемент:
{{
  "topic": "<одна из 6 категорий>",
  "title": "<уникальное название темы, до 80 символов>",
  "difficulty_level": <1, 2 или 3>
}}

Не добавляй "```json" или поясняющий текст. Только JSON-массив.'''


def call_deepseek(prompt: str, client: DeepSeekClient) -> str:
    """Вызов DeepSeek с увеличенным max_tokens (нам нужно ~10KB JSON)."""
    payload = {
        "model": client.model,
        "messages": [
            {"role": "system", "content": "You output ONLY valid JSON. No prose, no markdown fences."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 8000,
    }
    import requests
    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }
    for attempt in range(client.max_retries + 1):
        try:
            r = requests.post(client.base_url, json=payload, headers=headers, timeout=180)
            if r.status_code != 200:
                print(f'[attempt {attempt+1}] HTTP {r.status_code}: {r.text[:200]}')
                time.sleep(2 * (attempt + 1))
                continue
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            print(f'[attempt {attempt+1}] error: {e}')
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("DeepSeek failed after retries")


def parse_titles(raw: str) -> list:
    """Извлекает JSON-массив из ответа модели (с попыткой убрать ```json)."""
    text = raw.strip()
    # Убираем optional fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    # Ищем первый '[' и последний ']'
    s = text.find('[')
    e = text.rfind(']')
    if s == -1 or e == -1:
        raise ValueError(f'No JSON array found in response. First 300 chars: {text[:300]}')
    snippet = text[s:e + 1]
    try:
        arr = json.loads(snippet)
    except json.JSONDecodeError as e:
        raise ValueError(f'JSON decode error: {e}\nSnippet head: {snippet[:300]}')
    if not isinstance(arr, list):
        raise ValueError(f'Expected list, got {type(arr).__name__}')
    return arr


def validate(items: list, existing_titles: set) -> list:
    """Отфильтровать невалидные/дубликаты, оставить только корректные."""
    allowed_topics = {"Теория чисел", "Комбинаторика", "Алгебра", "Геометрия", "Логика", "Графы"}
    good = []
    seen_titles = set(existing_titles)
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        topic = (it.get('topic') or '').strip()
        title = (it.get('title') or '').strip()
        dl = it.get('difficulty_level')
        if topic not in allowed_topics:
            print(f'  skip #{i}: bad topic={topic!r}')
            continue
        if not title or len(title) > 200:
            print(f'  skip #{i}: bad title')
            continue
        if title.lower() in seen_titles:
            print(f'  skip #{i}: dup title={title!r}')
            continue
        if not isinstance(dl, int) or dl < 1 or dl > 3:
            print(f'  skip #{i}: bad difficulty={dl!r}')
            continue
        seen_titles.add(title.lower())
        good.append({"topic": topic, "title": title, "difficulty_level": dl})
    return good


def main() -> int:
    existing = load_existing()
    print(f'Existing secrets: {len(existing)}')
    existing_titles = {(s.get('title') or '').strip().lower() for s in existing}

    client = DeepSeekClient()
    print(f'Using model: {client.model} ({client.base_url})')

    prompt = build_prompt(existing)
    print(f'Prompt size: {len(prompt)} chars')
    print('Calling DeepSeek (this may take 30-90 sec)...')

    raw = call_deepseek(prompt, client)
    print(f'Response: {len(raw)} chars')
    # Сохраняем сырой ответ для дебага
    with open(os.path.join(ROOT, 'scripts', '_raw_titles_response.txt'), 'w', encoding='utf-8') as f:
        f.write(raw)

    try:
        items = parse_titles(raw)
    except ValueError as e:
        print(f'PARSE FAILED: {e}')
        return 2
    print(f'Parsed: {len(items)} items')

    good = validate(items, existing_titles)
    print(f'Valid after filter: {len(good)} items')

    # Counts by topic
    from collections import Counter
    by_topic = Counter(x['topic'] for x in good)
    by_diff = Counter(x['difficulty_level'] for x in good)
    print('By topic:', dict(by_topic))
    print('By difficulty:', dict(by_diff))

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(good, f, ensure_ascii=False, indent=2)
    print(f'Saved: {OUT_PATH}')
    return 0 if len(good) >= 80 else 1  # OK если хотя бы 80 из 100


if __name__ == '__main__':
    sys.exit(main())
