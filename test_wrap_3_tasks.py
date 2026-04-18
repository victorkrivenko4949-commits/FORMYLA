#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ТЕСТ: Оборачивание 3 задач через DeepSeek API
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

WRAP_PROMPT = """Я передам тебе текст математической задачи. Твоя задача — ТОЛЬКО обернуть все математические выражения, числа, уравнения и переменные в теги LaTeX \\\\( и \\\\).

ПРАВИЛА:
1. НИ В КОЕМ СЛУЧАЕ не меняй слова, не решай задачу, не меняй смысл!
2. Оборачивай только математику.
3. Верни ТОЛЬКО обновленный текст, без каких-либо комментариев.

Текст: {text}"""

async def wrap_via_api(session, text):
    """Обернуть текст через DeepSeek API"""
    if not text:
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

async def main():
    print("=" * 80)
    print("ТЕСТ: Оборачивание 3 задач (Уравнения, 9 класс)")
    print("=" * 80)
    
    # Найдем 3 задачи: algebra, equations, grade 9
    test_tasks = [p for p in PROBLEMS_DB if p.get('subject') == 'algebra' and p.get('subtopic') == 'equations' and p.get('grade') == 9][:3]
    
    print(f"\n📝 Найдено задач для теста: {len(test_tasks)}")
    
    print("\n" + "=" * 80)
    print("ДО ОБРАБОТКИ:")
    print("=" * 80)
    for i, task in enumerate(test_tasks):
        print(f"\nЗадача {i+1}:")
        print(f"  ID: {task.get('id')}")
        print(f"  text: {task.get('text')}")
        print(f"  answer: {task.get('answer', 'N/A')}")
    
    # Обработка
    async with aiohttp.ClientSession(headers={
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }) as session:
        print("\n" + "=" * 80)
        print("🔄 ОБРАБОТКА ЧЕРЕЗ DeepSeek API...")
        print("=" * 80)
        
        processed = []
        for i, task in enumerate(test_tasks):
            print(f"  Обработка задачи {i+1}/3...")
            new_text = await wrap_via_api(session, task.get('text', ''))
            new_answer = await wrap_via_api(session, task.get('answer', ''))
            
            processed.append({
                'id': task.get('id'),
                'original_text': task.get('text', ''),
                'new_text': new_text,
                'original_answer': task.get('answer', ''),
                'new_answer': new_answer
            })
    
    print("\n" + "=" * 80)
    print("ПОСЛЕ ОБРАБОТКИ:")
    print("=" * 80)
    for i, p in enumerate(processed):
        print(f"\nЗадача {i+1} (ID: {p['id']}):")
        print(f"  БЫЛО (text): {p['original_text']}")
        print(f"  СТАЛО (text): {p['new_text']}")
        print(f"  БЫЛО (answer): {p['original_answer']}")
        print(f"  СТАЛО (answer): {p['new_answer']}")
    
    print("\n" + "=" * 80)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("=" * 80)
    print("\nЕсли результат хороший - запусти wrap_latex_full.py для всех 2205 задач!")

if __name__ == '__main__':
    asyncio.run(main())
