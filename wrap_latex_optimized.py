#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Оптимизированное оборачивание LaTeX через DeepSeek API
30 параллельных запросов + промежуточное сохранение
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
SEMAPHORE_LIMIT = 30  # 30 параллельных запросов!
SAVE_EVERY = 200  # Сохранять каждые 200 задач

WRAP_PROMPT = """Оберни математические выражения в LaTeX теги \\\\( и \\\\).
НЕ МЕНЯЙ слова и смысл. Верни ТОЛЬКО обработанный текст.
Текст: {text}"""

class LaTeXWrapper:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self.session = None
        self.processed = 0
        self.total = len(PROBLEMS_DB)
        self.results = []
    
    async def wrap_text(self, text):
        # Преобразуем в строку, если это число
        if isinstance(text, (int, float)):
            text = str(text)
        if not text or not isinstance(text, str) or '\\(' in text:
            return text
        
        async with self.semaphore:
            try:
                payload = {
                    'model': 'deepseek-chat',
                    'messages': [{'role': 'user', 'content': WRAP_PROMPT.format(text=text)}],
                    'temperature': 0.1,
                    'max_tokens': 1500
                }
                
                async with self.session.post(DEEPSEEK_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content'].strip()
                    return text
            except:
                return text
    
    async def process_task(self, task, index):
        """Обработка одной задачи"""
        new_task = task.copy()
        new_task['text'] = await self.wrap_text(task.get('text', ''))
        if task.get('answer'):
            new_task['answer'] = await self.wrap_text(task.get('answer', ''))
        
        self.processed += 1
        if self.processed % 50 == 0:
            print(f"✅ Обработано: {self.processed}/{self.total} ({self.processed*100//self.total}%)")
        
        return new_task
    
    def save_results(self):
        """Сохранение результатов"""
        print(f"\n💾 Сохранение {len(self.results)} задач в problems.py...")
        with open('problems.py', 'w', encoding='utf-8') as f:
            f.write('# -*- coding: utf-8 -*-\n')
            f.write('PROBLEMS_DB = ')
            f.write(json.dumps(self.results, ensure_ascii=False, indent=2))
            f.write('\n')
        print(f"✅ Сохранено!")
    
    async def process_all(self):
        print("=" * 80)
        print(f"ОБОРАЧИВАНИЕ LaTeX: {self.total} задач")
        print(f"Параллельных запросов: {SEMAPHORE_LIMIT}")
        print("=" * 80)
        
        self.session = aiohttp.ClientSession(headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        })
        
        try:
            # Обрабатываем батчами по 200 задач
            for batch_start in range(0, self.total, SAVE_EVERY):
                batch_end = min(batch_start + SAVE_EVERY, self.total)
                batch = PROBLEMS_DB[batch_start:batch_end]
                
                print(f"\n🔄 Батч {batch_start}-{batch_end}...")
                
                # Обрабатываем батч параллельно
                tasks = [self.process_task(task, i) for i, task in enumerate(batch, start=batch_start)]
                batch_results = await asyncio.gather(*tasks)
                self.results.extend(batch_results)
                
                # Промежуточное сохранение
                self.save_results()
            
            print(f"\n✅ ГОТОВО! Обработано {self.processed} задач")
            
        finally:
            await self.session.close()

async def main():
    wrapper = LaTeXWrapper()
    await wrapper.process_all()

if __name__ == '__main__':
    asyncio.run(main())
