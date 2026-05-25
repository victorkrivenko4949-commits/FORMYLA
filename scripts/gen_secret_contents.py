# -*- coding: utf-8 -*-
"""Шаг 2: для каждой темы из _new_secret_titles.json сгенерировать
полный markdown-конспект через DeepSeek по структуре эталона.

Структура контента (как у первого эталона):
  ## 1. Введение
  ## 2. Базовый пример
  ## 3. Олимпиадная задача

Логика:
  - идём по списку тем последовательно (DeepSeek ~30 сек/тема)
  - валидируем: ≥3 H2 заголовка, ≥1500 символов, есть формула \( \) или $...$
  - при неудаче — до 2-х перегенераций
  - результаты сохраняем потоково в out_path (resumable)

Выход: scripts/_new_secrets_with_content.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if sys.platform == 'win32':
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    except Exception:
        pass

from ai.deepseek_client import DeepSeekClient  # noqa: E402

TITLES_PATH = os.path.join(ROOT, 'scripts', '_new_secret_titles.json')
OUT_PATH = os.path.join(ROOT, 'scripts', '_new_secrets_with_content.json')
MAX_RETRIES_PER_ITEM = 2
MIN_CONTENT_LEN = 1500
REQUIRED_HEADINGS = 3


def build_prompt(topic: str, title: str, difficulty: int) -> str:
    return f'''Ты — методист олимпиадной математики ВсОШ. Напиши подробную теоретическую заметку для раздела "Секреты" сайта FORMYLA.

Тема: {topic}
Название: {title}
Сложность: {difficulty}/3  (1=базовая, 2=средняя, 3=продвинутая)

ОБЯЗАТЕЛЬНАЯ структура (markdown, ровно 3 раздела H2):
# {title} — короткое подзаголовок-фраза

## 1. Введение
Объясни суть метода/теоремы простыми словами. Дай формальное определение или формулировку. Используй формулы в LaTeX: одиночные \\( ... \\) для inline, двойные $$ ... $$ для display.

## 2. Базовый пример
Разберём простую обучающую задачу. Покажи применение шаг за шагом. Дай пояснения.

## 3. Олимпиадная задача
Бери задачу из олимпиад (ВсОШ, Турнир городов, Курчатов). Сформулируй условие. Дай ПОЛНОЕ решение с обоснованием.

ТРЕБОВАНИЯ:
- Объём: 2500–6000 символов markdown
- Минимум 3–5 формул в LaTeX
- Никаких ```markdown ``` обёрток в начале/конце — выводи прямо markdown
- Без англоязычных вставок (всё на русском)
- Без "Источник:", "Автор:" и т.п. в конце
- Используй жирный (**...**), курсив (*...*), bullet-списки (-) где уместно
- Формулы НЕ внутри $$, а \\( ... \\) (inline) или $$ ... $$ на отдельной строке
- Не используй \\frac в простых случаях, лучше пиши a/b или (a+b)/c, чтобы лучше рендерилось KaTeX'ом

Выводи ТОЛЬКО markdown, без преамбулы.'''


def validate_content(content: str) -> tuple:
    """Возвращает (is_valid, reason)."""
    if not content or len(content) < MIN_CONTENT_LEN:
        return False, f'too short ({len(content) if content else 0} chars)'
    # Должно быть >= 3 H2 заголовка с цифрами
    h2s = re.findall(r'^##\s+\d+\.', content, flags=re.M)
    if len(h2s) < REQUIRED_HEADINGS:
        return False, f'only {len(h2s)} H2 sections'
    # Должна быть хотя бы одна формула LaTeX
    has_latex = bool(
        re.search(r'\\\(.+?\\\)', content, flags=re.S)
        or re.search(r'\$\$.+?\$\$', content, flags=re.S)
        or re.search(r'\$[^$\n]{2,40}\$', content)
    )
    if not has_latex:
        return False, 'no LaTeX formulas detected'
    return True, 'OK'


def call_deepseek(prompt: str, client: DeepSeekClient) -> str:
    import requests
    payload = {
        "model": client.model,
        "messages": [
            {"role": "system", "content": "You are a math olympiad methodist writing detailed markdown notes."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 4000,
    }
    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }
    r = requests.post(client.base_url, json=payload, headers=headers, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    return r.json()["choices"][0]["message"]["content"].strip()


def clean_content(content: str) -> str:
    """Убираем markdown-fences ```markdown ... ``` если модель добавила."""
    content = content.strip()
    content = re.sub(r'^```(?:markdown)?\s*\n', '', content)
    content = re.sub(r'\n```\s*$', '', content)
    return content.strip()


def load_existing_progress() -> list:
    """Сохранённый промежуточный результат — для resume."""
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_progress(items: list) -> None:
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def main() -> int:
    if not os.path.exists(TITLES_PATH):
        print(f'ERROR: titles file not found: {TITLES_PATH}')
        print('Run gen_secret_titles.py first.')
        return 2

    with open(TITLES_PATH, 'r', encoding='utf-8') as f:
        titles = json.load(f)
    print(f'Total titles to process: {len(titles)}')

    done = load_existing_progress()
    done_titles = {(x.get('title') or '').strip().lower() for x in done}
    print(f'Already done: {len(done)} (resuming)')

    client = DeepSeekClient()
    print(f'Using: {client.model}')

    failed = []
    for i, t in enumerate(titles, 1):
        title = t['title']
        topic = t['topic']
        diff = t['difficulty_level']

        if title.strip().lower() in done_titles:
            print(f'[{i:>3}/{len(titles)}] SKIP (already done): {title}')
            continue

        print(f'[{i:>3}/{len(titles)}] {topic} :: {title} (diff={diff})')
        prompt = build_prompt(topic, title, diff)

        content = None
        last_err = ''
        for attempt in range(MAX_RETRIES_PER_ITEM + 1):
            try:
                raw = call_deepseek(prompt, client)
                content = clean_content(raw)
                ok, reason = validate_content(content)
                if ok:
                    break
                last_err = reason
                print(f'    [retry {attempt+1}] invalid: {reason}; len={len(content)}')
                time.sleep(1)
            except Exception as e:
                last_err = str(e)
                print(f'    [retry {attempt+1}] error: {e}')
                time.sleep(3 * (attempt + 1))

        if not content or not validate_content(content)[0]:
            print(f'    FAIL after retries ({last_err})')
            failed.append({**t, 'reason': last_err})
            # сохраняем заглушку — позже можно регенерить
            done.append({
                'topic': topic,
                'title': title,
                'difficulty_level': diff,
                'content': '',
                '__error': last_err,
            })
            save_progress(done)
            continue

        done.append({
            'topic': topic,
            'title': title,
            'difficulty_level': diff,
            'content': content,
        })
        save_progress(done)
        print(f'    OK ({len(content)} chars)')

        # Пауза, чтобы не упереться в rate-limit
        time.sleep(0.5)

    print('\n' + '=' * 60)
    print(f'Done: {len(done)} / {len(titles)}')
    print(f'Failed: {len(failed)}')
    if failed:
        print('Failed titles:')
        for fl in failed:
            print(f'  - {fl["title"]}: {fl["reason"]}')

    return 0 if len(failed) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
