#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Массовое исправление LaTeX-синтаксиса в базе данных олимпиад через DeepSeek API
Обрабатывает таблицы: olympiad_secrets (content) и adaptive_tasks (task_text, solution)
"""

import asyncio
import aiohttp
import sqlite3
import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Исправление кодировки для Windows консоли
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
DB_PATH = 'instance/formyla.db'
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
SEMAPHORE_LIMIT = 20  # Параллельных запросов
COMMIT_BATCH_SIZE = 50  # Коммит каждые N записей

# Промпт для API
LATEX_FIX_PROMPT = """Ты — технический редактор математических текстов. Внимательно проверь и исправь LaTeX-синтаксис в следующем тексте задачи/решения.

Особое внимание удели следующим частым ошибкам:
1. Логика степеней и индексов: исправь `x_2`, если по смыслу это "икс в квадрате" (`x^2`), и наоборот.
2. Синтаксис корней: `\\sqrt x` или `\\sqrtx` должно стать `\\sqrt{{x}}`.
3. Синтаксис дробей: проверь, что у `\\frac{{numerator}}{{denominator}}` закрыты все фигурные скобки.
4. Убедись, что все математические выражения корректно обернуты в двойные экранированные теги: \\\\( ... \\\\) для внутристрочных и \\\\[ ... \\\\] для блочных.

ТВОЕ ПРАВИЛО: НЕ меняй слова, числа или математический смысл. ИСПРАВЛЯЙ ТОЛЬКО ОШИБКИ РАЗМЕТКИ LaTeX.
Верни строго ТОЛЬКО исправленный текст, без маркдаун-блоков (```) и без пояснений.

Текст для исправления:
{text}"""


class LaTeXFixer:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        self.session = None
        self.stats = {
            'total_checked': 0,
            'total_fixed': 0,
            'olympiad_secrets_fixed': 0,
            'adaptive_tasks_fixed': 0,
            'errors': 0
        }
        
    async def init_session(self):
        """Инициализация aiohttp сессии"""
        self.session = aiohttp.ClientSession(
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
        )
    
    async def close_session(self):
        """Закрытие сессии"""
        if self.session:
            await self.session.close()
    
    async def fix_latex_via_api(self, text: str) -> str:
        """Отправить текст в DeepSeek API для исправления LaTeX"""
        if not text or not text.strip():
            return text
        
        async with self.semaphore:
            try:
                payload = {
                    'model': 'deepseek-chat',
                    'messages': [
                        {
                            'role': 'user',
                            'content': LATEX_FIX_PROMPT.format(text=text)
                        }
                    ],
                    'temperature': 0.1,  # Низкая температура для точности
                    'max_tokens': 4000
                }
                
                async with self.session.post(
                    DEEPSEEK_API_URL, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            if 'choices' in data and len(data['choices']) > 0:
                                if 'message' in data['choices'][0] and 'content' in data['choices'][0]['message']:
                                    fixed_text = data['choices'][0]['message']['content'].strip()
                                    return fixed_text
                                else:
                                    print(f"❌ Unexpected response structure: {data}")
                                    self.stats['errors'] += 1
                                    return text
                            else:
                                print(f"❌ No choices in response: {data}")
                                self.stats['errors'] += 1
                                return text
                        except Exception as json_error:
                            print(f"❌ JSON parsing error: {json_error}")
                            self.stats['errors'] += 1
                            return text
                    else:
                        error_text = await response.text()
                        print(f"❌ API Error {response.status}: {error_text[:200]}")
                        self.stats['errors'] += 1
                        return text  # Вернуть оригинал при ошибке
                        
            except asyncio.TimeoutError:
                print(f"❌ Timeout during API call")
                self.stats['errors'] += 1
                return text
            except Exception as e:
                print(f"❌ Exception during API call: {type(e).__name__}: {str(e)[:100]}")
                self.stats['errors'] += 1
                return text
    
    async def process_olympiad_secrets(self, conn):
        """Обработка таблицы olympiad_secrets"""
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, content FROM olympiad_secrets')
        records = cursor.fetchall()
        
        print(f"\n📚 Обработка olympiad_secrets: {len(records)} записей")
        
        tasks = []
        for record_id, title, content in records:
            tasks.append(self.process_olympiad_secret(conn, record_id, title, content))
        
        await asyncio.gather(*tasks)
    
    async def process_olympiad_secret(self, conn, record_id, title, original_content):
        """Обработка одной записи olympiad_secrets"""
        self.stats['total_checked'] += 1
        
        # Исправить через API
        fixed_content = await self.fix_latex_via_api(original_content)
        
        # Сравнить и обновить если изменилось
        if fixed_content != original_content:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE olympiad_secrets SET content = ? WHERE id = ?',
                (fixed_content, record_id)
            )
            self.stats['total_fixed'] += 1
            self.stats['olympiad_secrets_fixed'] += 1
            print(f"✅ [Olympiad Secret ID {record_id}] {title[:50]} - Исправлен синтаксис LaTeX")
            
            # Периодический коммит
            if self.stats['total_fixed'] % COMMIT_BATCH_SIZE == 0:
                conn.commit()
                print(f"💾 Коммит: {self.stats['total_fixed']} исправлений сохранено")
    
    async def process_adaptive_tasks(self, conn):
        """Обработка таблицы adaptive_tasks"""
        cursor = conn.cursor()
        cursor.execute('SELECT id, class_level, topic, task_text, solution FROM adaptive_tasks')
        records = cursor.fetchall()
        
        print(f"\n📝 Обработка adaptive_tasks: {len(records)} записей")
        
        tasks = []
        for record_id, class_level, topic, task_text, solution in records:
            tasks.append(self.process_adaptive_task(conn, record_id, class_level, topic, task_text, solution))
        
        await asyncio.gather(*tasks)
    
    async def process_adaptive_task(self, conn, record_id, class_level, topic, original_task_text, original_solution):
        """Обработка одной записи adaptive_tasks"""
        self.stats['total_checked'] += 1
        
        # Исправить task_text
        fixed_task_text = await self.fix_latex_via_api(original_task_text) if original_task_text else original_task_text
        
        # Исправить solution
        fixed_solution = await self.fix_latex_via_api(original_solution) if original_solution else original_solution
        
        # Проверить изменения
        task_changed = fixed_task_text != original_task_text
        solution_changed = fixed_solution != original_solution
        
        if task_changed or solution_changed:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE adaptive_tasks SET task_text = ?, solution = ? WHERE id = ?',
                (fixed_task_text, fixed_solution, record_id)
            )
            self.stats['total_fixed'] += 1
            self.stats['adaptive_tasks_fixed'] += 1
            
            changes = []
            if task_changed:
                changes.append('task_text')
            if solution_changed:
                changes.append('solution')
            
            print(f"✅ [Adaptive Task ID {record_id}] Class {class_level}, {topic[:30]} - Исправлено: {', '.join(changes)}")
            
            # Периодический коммит
            if self.stats['total_fixed'] % COMMIT_BATCH_SIZE == 0:
                conn.commit()
                print(f"💾 Коммит: {self.stats['total_fixed']} исправлений сохранено")
    
    async def run(self):
        """Главная функция запуска"""
        print("=" * 80)
        print("🚀 МАССОВОЕ ИСПРАВЛЕНИЕ LaTeX ЧЕРЕЗ DeepSeek API")
        print("=" * 80)
        print(f"📅 Время старта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔧 База данных: {DB_PATH}")
        print(f"⚡ Параллельных запросов: {SEMAPHORE_LIMIT}")
        print(f"💾 Коммит каждые: {COMMIT_BATCH_SIZE} записей")
        print("=" * 80)
        
        # Проверка API ключа
        if not DEEPSEEK_API_KEY:
            print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден в .env файле!")
            return
        
        # Подключение к БД
        conn = sqlite3.connect(DB_PATH)
        
        try:
            # Инициализация сессии
            await self.init_session()
            
            # Обработка olympiad_secrets
            await self.process_olympiad_secrets(conn)
            
            # Обработка adaptive_tasks
            await self.process_adaptive_tasks(conn)
            
            # Финальный коммит
            conn.commit()
            print("\n💾 Финальный коммит выполнен")
            
        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            print(traceback.format_exc())
            conn.rollback()
        finally:
            # Закрытие соединений
            await self.close_session()
            conn.close()
        
        # Статистика
        print("\n" + "=" * 80)
        print("📊 СТАТИСТИКА ОБРАБОТКИ")
        print("=" * 80)
        print(f"✅ Всего проверено записей: {self.stats['total_checked']}")
        print(f"🔧 Всего исправлено: {self.stats['total_fixed']}")
        print(f"   - olympiad_secrets: {self.stats['olympiad_secrets_fixed']}")
        print(f"   - adaptive_tasks: {self.stats['adaptive_tasks_fixed']}")
        print(f"❌ Ошибок API: {self.stats['errors']}")
        print(f"📅 Время завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)


async def main():
    """Точка входа"""
    fixer = LaTeXFixer()
    await fixer.run()


if __name__ == '__main__':
    asyncio.run(main())
