#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
БЕЗОПАСНОЕ оборачивание LaTeX через DeepSeek API
Читает из problems.py -> Пишет в problems_latex_fixed.py
Сохраняет ВСЕ 2305 задач после каждого батча
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
SEMAPHORE_LIMIT = 30  # 30 параллельных запросов
BATCH_SIZE = 10  # Обрабатывать по 10 задач за раз
PROGRESS_FILE = 'latex_progress.txt'
OUTPUT_FILE = 'problems_latex_fixed.py'

WRAP_PROMPT = """Оберни все математические формулы, числа и переменные в теги LaTeX \\\\( и \\\\).
НЕ меняй слова и смысл! Верни ТОЛЬКО обработанный текст без пояснений.
Текст: {text}"""


class SafeLaTeXWrapper:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self.session = None
        # Читаем ВСЮ базу ОДИН РАЗ в начале
        from problems import PROBLEMS_DB
        self.all_tasks = [task.copy() for task in PROBLEMS_DB]  # Копируем чтобы не менять оригинал
        self.total = len(self.all_tasks)
        self.last_processed = self.load_progress()
        
        print(f"📊 Загружено задач: {self.total}")
        print(f"📍 Последняя обработанная: {self.last_processed}")
        print(f"⏭️  Осталось обработать: {self.total - self.last_processed}")
    
    def load_progress(self):
        """Загрузить индекс последней обработанной задачи"""
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                return int(f.read().strip())
        return 0
    
    def save_progress(self, index):
        """Сохранить прогресс"""
        with open(PROGRESS_FILE, 'w') as f:
            f.write(str(index))
    
    def save_all_tasks(self):
        """
        КРИТИЧЕСКИ ВАЖНО: Сохраняет ВСЕ задачи (все 2305) в новый файл
        Даже если обработано только 100 задач, файл будет содержать все 2305
        """
        print(f"💾 Сохранение ВСЕХ {len(self.all_tasks)} задач в {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('# -*- coding: utf-8 -*-\n')
            f.write(f'# Обработано задач: {self.last_processed}/{self.total}\n')
            f.write('PROBLEMS_DB = ')
            f.write(json.dumps(self.all_tasks, ensure_ascii=False, indent=2))
            f.write('\n')
        print(f"✅ Сохранено! Файл содержит {len(self.all_tasks)} задач")
    
    async def wrap_text(self, text):
        """Обернуть текст через DeepSeek API"""
        # Преобразуем в строку если число
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
                
                async with self.session.post(
                    DEEPSEEK_API_URL, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content'].strip()
                    return text
            except Exception as e:
                print(f"❌ Error: {e}")
                return text
    
    async def process_task(self, index):
        """Обработка одной задачи (обновляет self.all_tasks[index] на месте)"""
        task = self.all_tasks[index]
        
        # Обрабатываем text
        if task.get('text'):
            task['text'] = await self.wrap_text(task['text'])
        
        # Обрабатываем answer
        if task.get('answer'):
            task['answer'] = await self.wrap_text(task['answer'])
        
        # Обрабатываем solution если есть
        if task.get('solution'):
            task['solution'] = await self.wrap_text(task['solution'])
    
    async def process_all(self):
        print("=" * 80)
        print(f"БЕЗОПАСНОЕ ОБОРАЧИВАНИЕ LaTeX")
        print(f"Исходный файл: problems.py (READ ONLY)")
        print(f"Выходной файл: {OUTPUT_FILE}")
        print(f"Параллельных запросов: {SEMAPHORE_LIMIT}")
        print(f"Размер батча: {BATCH_SIZE}")
        print("=" * 80)
        
        if not DEEPSEEK_API_KEY:
            print("❌ DEEPSEEK_API_KEY не найден!")
            return
        
        self.session = aiohttp.ClientSession(headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        })
        
        try:
            # Обрабатываем батчами
            for batch_start in range(self.last_processed, self.total, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, self.total)
                
                print(f"\n🔄 Батч {batch_start}-{batch_end}...")
                
                # Обрабатываем батч параллельно
                tasks = [self.process_task(i) for i in range(batch_start, batch_end)]
                await asyncio.gather(*tasks)
                
                # Обновляем прогресс
                self.last_processed = batch_end
                self.save_progress(self.last_processed)
                
                # КРИТИЧЕСКИ ВАЖНО: Сохраняем ВСЕ задачи (все 2305), а не только батч!
                self.save_all_tasks()
                
                print(f"✅ Обработано: {self.last_processed}/{self.total} ({self.last_processed*100//self.total}%)")
            
            print(f"\n✅ ГОТОВО! Все {self.total} задач обработаны")
            print(f"📁 Результат сохранен в: {OUTPUT_FILE}")
            print(f"\n💡 Проверьте файл, затем скопируйте:")
            print(f"   copy {OUTPUT_FILE} problems.py")
            
        finally:
            await self.session.close()


async def main():
    wrapper = SafeLaTeXWrapper()
    await wrapper.process_all()


if __name__ == '__main__':
    asyncio.run(main())
