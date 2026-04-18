#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ТЕСТОВЫЙ ПРОГОН (DRY RUN) - AI-парсер для исправления математических опечаток
Обрабатывает только 10 задач с потенциальными ошибками для демонстрации
"""
import asyncio
import aiohttp
import sqlite3
import os
import sys
import re
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

DB_PATH = 'instance/formyla.db'
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'

# УЛУЧШЕННЫЙ ПРОМПТ с фокусом на индексы vs степени
MATH_FIX_PROMPT = """Ты — строгий математический редактор синтаксиса LaTeX.
Твоя задача: исправить опечатки с индексами и степенями ВНУТРИ тегов LaTeX.

ТИПИЧНЫЕ ОШИБКИ, которые нужно искать:

1. Квадраты и кубы после скобок:
   - (a+b)2 должно стать (a+b)^2
   - (x-y)3 должно стать (x-y)^3
   - (2n+1)2 должно стать (2n+1)^2

2. Степени переменных в уравнениях/многочленах:
   - x2 + y2 = z2 должно стать x^2 + y^2 = z^2
   - a3 + b3 должно стать a^3 + b^3
   - НО: 2^n уже правильно, не меняй!

3. Индексы переменных в последовательностях:
   - Если видишь перечисление типа a1, a2, a3, ..., an → это индексы: a_1, a_2, a_3, ..., a_n
   - Если видишь x1 + x2 + ... + xn → это индексы: x_1 + x_2 + ... + x_n
   - Если видишь S = a1 + a2 → это индексы: S = a_1 + a_2

4. Единицы измерения:
   - см2, м2, км2 → см^2, м^2, км^2
   - м3, см3 → м^3, см^3

5. Синтаксис корней и дробей:
   - \\sqrt x → \\sqrt{{x}}
   - \\sqrtx → \\sqrt{{x}}

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
- НЕ меняй ни одного слова обычного русского текста вне LaTeX-тегов
- НЕ меняй смысл задачи или решения
- РАЗЛИЧАЙ индексы (элементы последовательности) и степени (возведение в степень)
- Если сомневаешься - НЕ меняй
- Верни ТОЛЬКО исправленный текст, без комментариев

Текст для исправления:
{{text}}"""


async def fix_text_via_ai(session, text):
    """Отправить текст в DeepSeek API для исправления"""
    if not text or not text.strip():
        return text
    
    try:
        payload = {
            'model': 'deepseek-chat',
            'messages': [
                {
                    'role': 'user',
                    'content': MATH_FIX_PROMPT.replace('{{text}}', text)
                }
            ],
            'temperature': 0.1,
            'max_tokens': 4000
        }
        
        async with session.post(
            DEEPSEEK_API_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status == 200:
                data = await response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    fixed_text = data['choices'][0]['message']['content'].strip()
                    # Убираем markdown блоки если AI их добавил
                    fixed_text = re.sub(r'^```.*?\n', '', fixed_text)
                    fixed_text = re.sub(r'\n```$', '', fixed_text)
                    return fixed_text
                else:
                    print(f"❌ Unexpected response: {data}")
                    return text
            else:
                error_text = await response.text()
                print(f"❌ API Error {response.status}: {error_text[:200]}")
                return text
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {str(e)[:100]}")
        return text


async def test_dry_run():
    """Тестовый прогон на 10 задачах"""
    print("=" * 80)
    print("🧪 ТЕСТОВЫЙ ПРОГОН (DRY RUN) - AI-парсер математических опечаток")
    print("=" * 80)
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 База данных: {DB_PATH}")
    print("=" * 80)
    
    if not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден в .env файле!")
        return
    
    # Подключение к БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Найти задачи с потенциальными ошибками
    cursor.execute('SELECT id, class_level, topic, task_text, solution FROM adaptive_tasks')
    records = cursor.fetchall()
    
    patterns = {
        'скобка_число': r'\)[2-9]',
        'переменная_число': r'[a-z][0-9]',
    }
    
    tasks_to_test = []
    for record_id, class_level, topic, task_text, solution in records:
        combined_text = (task_text or '') + ' ' + (solution or '')
        if not combined_text.strip():
            continue
        
        has_error = False
        for pattern in patterns.values():
            if re.search(pattern, combined_text):
                has_error = True
                break
        
        if has_error:
            tasks_to_test.append({
                'id': record_id,
                'class_level': class_level,
                'topic': topic,
                'task_text': task_text,
                'solution': solution
            })
        
        if len(tasks_to_test) >= 10:
            break
    
    print(f"\n✅ Выбрано {len(tasks_to_test)} задач для тестирования\n")
    
    # Создаем сессию
    async with aiohttp.ClientSession(
        headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        }
    ) as session:
        
        for i, task in enumerate(tasks_to_test, 1):
            print(f"\n{'='*80}")
            print(f"ЗАДАЧА #{i} (ID: {task['id']})")
            print(f"Класс: {task['class_level']}, Тема: {task['topic']}")
            print(f"{'='*80}")
            
            # Обработка task_text
            if task['task_text']:
                print(f"\n📝 БЫЛО (task_text):")
                print(task['task_text'][:400])
                
                fixed_task = await fix_text_via_ai(session, task['task_text'])
                
                if fixed_task != task['task_text']:
                    print(f"\n✨ СТАЛО (task_text):")
                    print(fixed_task[:400])
                    print(f"\n🔍 ИЗМЕНЕНИЯ НАЙДЕНЫ!")
                else:
                    print(f"\n✅ Изменений не требуется")
            
            # Обработка solution
            if task['solution']:
                print(f"\n📚 БЫЛО (solution):")
                print(task['solution'][:400])
                
                fixed_solution = await fix_text_via_ai(session, task['solution'])
                
                if fixed_solution != task['solution']:
                    print(f"\n✨ СТАЛО (solution):")
                    print(fixed_solution[:400])
                    print(f"\n🔍 ИЗМЕНЕНИЯ НАЙДЕНЫ!")
                else:
                    print(f"\n✅ Изменений не требуется")
            
            # Задержка между запросами
            if i < len(tasks_to_test):
                await asyncio.sleep(2)
    
    conn.close()
    
    print(f"\n{'='*80}")
    print("✅ ТЕСТОВЫЙ ПРОГОН ЗАВЕРШЕН")
    print("📊 Проверьте результаты выше")
    print("💡 Если AI правильно различает индексы и степени - можно запускать на всей базе")
    print(f"{'='*80}")


if __name__ == '__main__':
    asyncio.run(test_dry_run())
