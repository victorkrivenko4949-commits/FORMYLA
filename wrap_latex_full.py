#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ПОЛНАЯ обработка: Оборачивание всех 2205 задач через DeepSeek API
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
SEMAPHORE_LIMIT = 10  # Параллельных запросов

WRAP_PROMPT = """Ты редактор математических текстов. Твоя задача ТОЛЬКО обернуть математические формулы в теги LaTeX \\\\( и \\\\).

ПРАВИЛА:
1. НЕ ИЗМЕНЯЙ СЛОВА. НЕ МЕНЯЙ СУТЬ.
2. Оборачивай ТОЛЬКО математические выражения: переменные, уравнения, неравенства.
3. НЕ оборачивай обычные числа в тексте.
4. Верни ТОЛЬКО исправленный текст, без пояснений.

Текст: {text}"""

class LaTeXWrapper:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self.session = None
        self.processed = 0
        self.total = len(PROBLEMS_DB)
    
    async def wrap_text(self, text):
        if not text or '\\(' in text:
            return text
        
        async with self.semaphore:
            try:
                payload = {
                    'model': 'deepseek-chat',
                    'messages': [{'role': 'user', 'content': WRAP_PROMPT.format(text=text)}],
                    'temperature': 0.1,
                    'max_tokens': 2000
                }
                
                async with self.session.post(DEEPSEEK_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content'].strip()
                    return text
            except:
                return text
    
    async def process_all(self):
        print("=" * 80)
        print(f"ПОЛНАЯ ОБРАБОТКА: {self.total} задач")
        print("=" * 80)
        
        self.session = aiohttp.ClientSession(headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        })
        
        try:
            new_db = []
            for i, task in enumerate(PROBLEMS_DB):
                new_task = task.copy()
                new_task['text'] = await self.wrap_text(task.get('text', ''))
                if task.get('answer'):
                    new_task['answer'] = await self.wrap_text(task.get('answer', ''))
                
                new_db.append(new_task)
                self.processed += 1
                
                if self.processed % 100 == 0:
                    print(f"✅ Обработано: {self.processed}/{self.total}")
            
            # Сохранение
            print(f"\n💾 Сохранение в problems.py...")
            with open('problems.py', 'w', encoding='utf-8') as f:
                f.write('# -*- coding: utf-8 -*-\n')
                f.write('PROBLEMS_DB = ')
                f.write(json.dumps(new_db, ensure_ascii=False, indent=2))
                f.write('\n')
            
            print(f"✅ Готово! Обработано {self.processed} задач")
            
        finally:
            await self.session.close()

async def main():
    wrapper = LaTeXWrapper()
    await wrapper.process_all()

if __name__ == '__main__':
    asyncio.run(main())
