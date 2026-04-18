#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Оборачивание математических выражений в LaTeX теги через DeepSeek API
ТОЛЬКО оборачивание, БЕЗ изменения содержимого!
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from problems import PROBLEMS_DB

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'

WRAP_PROMPT = """Ты редактор математических текстов. Твоя задача ТОЛЬКО обернуть математические формулы, числа и переменные в тексте в теги LaTeX \\\\( и \\\\).

ПРАВИЛА:
1. НЕ ИЗМЕНЯЙ СЛОВА. НЕ МЕНЯЙ СУТЬ. НЕ ДОБАВЛЯЙ НИЧЕГО. НЕ ИСПРАВЛЯЙ ОШИБКИ.
2. Оборачивай ТОЛЬКО математические выражения: переменные (x, y), числа в формулах, уравнения, неравенства.
3. НЕ оборачивай обычные числа в тексте (например, "5 задач", "2 часа").
4. Верни ТОЛЬКО исправленный текст, без пояснений и без маркдаун-блоков.

Примеры:
- "Реши уравнение x^2 = 4" → "Реши уравнение \\\\( x^2 = 4 \\\\)"
- "Найди x + y = 7" → "Найди \\\\( x + y = 7 \\\\)"
- "Решите 5 задач" → "Решите 5 задач" (НЕ меняем!)

Текст для обработки:
{text}"""

async def wrap_text_via_api(session, text):
    """Обернуть текст через DeepSeek API"""
    if not text or '\\(' in text:
        return text
    
    try:
        payload = {
            'model': 'deepseek-chat',
            'messages': [{'role': 'user', 'content': WRAP_PROMPT.format(text=text)}],
            'temperature': 0.1,
            'max_tokens': 2000
        }
        
        async with session.post(DEEPSEEK_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                data = await response.json()
                return data['choices'][0]['message']['content'].strip()
            else:
                print(f"❌ API Error {response.status}")
                return text
    except Exception as e:
        print(f"❌ Exception: {e}")
        return text

async def test_first_5():
    """Тест на первых 5 задачах"""
    print("=" * 80)
    print("ТЕСТ: Оборачивание через DeepSeek API (первые 5 задач)")
    print("=" * 80)
    
    test_tasks = PROBLEMS_DB[:5]
    
    print("\n📝 ДО обработки:")
    for i, task in enumerate(test_tasks):
        print(f"\nЗадача {i+1}:")
        print(f"  text: {task.get('text', '')}")
    
    # Обработка через API
    async with aiohttp.ClientSession(headers={
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }) as session:
        print("\n🔄 Обработка через DeepSeek API...")
        
        processed = []
        for i, task in enumerate(test_tasks):
            print(f"  Обработка задачи {i+1}/5...")
            new_text = await wrap_text_via_api(session, task.get('text', ''))
            new_answer = await wrap_text_via_api(session, task.get('answer', ''))
            
            processed.append({
                'original_text': task.get('text', ''),
                'new_text': new_text,
                'original_answer': task.get('answer', ''),
                'new_answer': new_answer
            })
    
    print("\n✅ ПОСЛЕ обработки:")
    for i, p in enumerate(processed):
        print(f"\nЗадача {i+1}:")
        print(f"  БЫЛО: {p['original_text']}")
        print(f"  СТАЛО: {p['new_text']}")
    
    print("\n" + "=" * 80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("Если результат хороший - запусти полную обработку!")
    print("=" * 80)

if __name__ == '__main__':
    asyncio.run(test_first_5())
