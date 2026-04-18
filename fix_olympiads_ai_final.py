#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ФИНАЛЬНЫЙ СКРИПТ - AI-парсер для исправления математических опечаток
Обрабатывает ВСЮ базу adaptive_tasks с сохранением прогресса
"""
import asyncio
import aiohttp
import sqlite3
import os
import sys
import re
import json
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

DB_PATH = 'instance/formyla.db'
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
PROGRESS_FILE = 'olympiads_fix_progress.json'
BATCH_SIZE = 10  # Обрабатывать по 10 задач
DELAY_BETWEEN_BATCHES = 2  # Секунд между батчами

# УЛУЧШЕННЫЙ ПРОМПТ
MATH_FIX_PROMPT = """Ты — строгий математический редактор синтаксиса LaTeX.
Твоя задача: исправить опечатки с индексами и степенями ВНУТРИ тегов LaTeX.

ТИПИЧНЫЕ ОШИБКИ:

1. Квадраты и кубы после скобок: 
   - (a+b)2 → (a+b)^2
   - (x-y)3 → (x-y)^3

2. Степени переменных в уравнениях:
   - x2 + y2 = z2 → x^2 + y^2 = z^2
   - a3 + b3 → a^3 + b^3

3. Индексы в последовательностях:
   - a1, a2, a3 → a_1, a_2, a_3
   - x1 + x2 + xn → x_1 + x_2 + x_n

4. Единицы измерения:
   - см2, м3 → см^2, м^3

5. Синтаксис корней:
   - \\sqrt x → \\sqrt{{x}}

ПРАВИЛА:
- НЕ меняй русский текст вне LaTeX
- НЕ меняй смысл
- РАЗЛИЧАЙ индексы и степени по контексту
- Если сомневаешься - НЕ меняй
- Верни ТОЛЬКО исправленный текст

Текст:
{{text}}"""


class MathFixer:
    def __init__(self):
        self.session = None
        self.stats = {
            'total_processed': 0,
            'total_fixed': 0,
            'errors': 0,
            'skipped': 0
        }
        self.progress = self.load_progress()
    
    def load_progress(self):
        """Загрузить прогресс из файла"""
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'processed_ids': [], 'last_batch': 0}
    
    def save_progress(self):
        """Сохранить прогресс"""
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)
    
    async def fix_text(self, text):
        """Исправить текст через API"""
        if not text or not text.strip():
            return text
        
        try:
            payload = {
                'model': 'deepseek-chat',
                'messages': [{
                    'role': 'user',
                    'content': MATH_FIX_PROMPT.replace('{{text}}', text)
                }],
                'temperature': 0.1,
                'max_tokens': 4000
            }
            
            async with self.session.post(
                DEEPSEEK_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'choices' in data and len(data['choices']) > 0:
                        fixed = data['choices'][0]['message']['content'].strip()
                        # Убираем markdown блоки
                        fixed = re.sub(r'^```.*?\n', '', fixed)
                        fixed = re.sub(r'\n```$', '', fixed)
                        return fixed
                    return text
                else:
                    self.stats['errors'] += 1
                    return text
        except Exception as e:
            print(f"❌ Error: {type(e).__name__}")
            self.stats['errors'] += 1
            return text
    
    async def process_batch(self, conn, batch):
        """Обработать батч задач"""
        for task in batch:
            task_id = task['id']
            
            # Пропустить если уже обработано
            if task_id in self.progress['processed_ids']:
                self.stats['skipped'] += 1
                continue
            
            # Исправить тексты
            fixed_task = await self.fix_text(task['task_text']) if task['task_text'] else task['task_text']
            fixed_solution = await self.fix_text(task['solution']) if task['solution'] else task['solution']
            
            # Проверить изменения
            task_changed = fixed_task != task['task_text']
            solution_changed = fixed_solution != task['solution']
            
            if task_changed or solution_changed:
                # Обновить в БД
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE adaptive_tasks SET task_text = ?, solution = ? WHERE id = ?',
                    (fixed_task, fixed_solution, task_id)
                )
                self.stats['total_fixed'] += 1
                
                changes = []
                if task_changed:
                    changes.append('task')
                if solution_changed:
                    changes.append('solution')
                
                print(f"✅ ID {task_id}: {', '.join(changes)} исправлено")
            
            self.stats['total_processed'] += 1
            self.progress['processed_ids'].append(task_id)
    
    async def run(self):
        """Главная функция"""
        print("=" * 80)
        print("🚀 МАССОВОЕ ИСПРАВЛЕНИЕ МАТЕМАТИЧЕСКИХ ОПЕЧАТОК")
        print("=" * 80)
        print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔧 База: {DB_PATH}")
        print(f"📦 Размер батча: {BATCH_SIZE}")
        print(f"⏱️  Задержка: {DELAY_BETWEEN_BATCHES}с")
        print("=" * 80)
        
        if not DEEPSEEK_API_KEY:
            print("❌ DEEPSEEK_API_KEY не найден!")
            return
        
        # Подключение к БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Получить задачи с потенциальными ошибками
        cursor.execute('SELECT id, class_level, topic, task_text, solution FROM adaptive_tasks')
        all_records = cursor.fetchall()
        
        patterns = {
            'скобка_число': r'\)[2-9]',
            'переменная_число': r'[a-z][0-9]',
        }
        
        tasks_to_process = []
        for record_id, class_level, topic, task_text, solution in all_records:
            combined = (task_text or '') + ' ' + (solution or '')
            if not combined.strip():
                continue
            
            has_error = False
            for pattern in patterns.values():
                if re.search(pattern, combined):
                    has_error = True
                    break
            
            if has_error:
                tasks_to_process.append({
                    'id': record_id,
                    'class_level': class_level,
                    'topic': topic,
                    'task_text': task_text,
                    'solution': solution
                })
        
        print(f"\n📊 Всего задач с потенциальными ошибками: {len(tasks_to_process)}")
        print(f"📊 Уже обработано: {len(self.progress['processed_ids'])}")
        print(f"📊 Осталось обработать: {len(tasks_to_process) - len(self.progress['processed_ids'])}\n")
        
        # Создать сессию
        self.session = aiohttp.ClientSession(
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
        )
        
        try:
            # Обработка батчами
            for i in range(0, len(tasks_to_process), BATCH_SIZE):
                batch = tasks_to_process[i:i+BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                
                print(f"\n{'='*80}")
                print(f"📦 БАТЧ {batch_num}/{(len(tasks_to_process)-1)//BATCH_SIZE + 1}")
                print(f"{'='*80}")
                
                await self.process_batch(conn, batch)
                
                # Сохранить прогресс
                self.progress['last_batch'] = batch_num
                self.save_progress()
                conn.commit()
                
                print(f"💾 Прогресс сохранен (батч {batch_num})")
                
                # Задержка между батчами
                if i + BATCH_SIZE < len(tasks_to_process):
                    await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Финальный коммит
            conn.commit()
            
        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            conn.rollback()
        finally:
            await self.session.close()
            conn.close()
        
        # Статистика
        print(f"\n{'='*80}")
        print("📊 СТАТИСТИКА")
        print(f"{'='*80}")
        print(f"✅ Обработано: {self.stats['total_processed']}")
        print(f"🔧 Исправлено: {self.stats['total_fixed']}")
        print(f"⏭️  Пропущено: {self.stats['skipped']}")
        print(f"❌ Ошибок API: {self.stats['errors']}")
        print(f"📅 Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")


if __name__ == '__main__':
    fixer = MathFixer()
    asyncio.run(fixer.run())
