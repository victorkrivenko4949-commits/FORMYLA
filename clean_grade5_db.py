"""
Скрипт очистки базы олимпиадных задач для 5 класса
Исправляет юникод, удаляет дубликаты, сокращает длинные ответы
"""

import asyncio
import aiohttp
import json
import os
import re
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"

INPUT_FILE = "grade5_olympiad_COMPLETE.jsonl"
OUTPUT_FILE = "grade5_olympiad_PERFECT.jsonl"

# Маппинг юникод-символов на LaTeX
UNICODE_TO_LATEX = {
    '×': r'$\times$',
    '÷': r'$\div$',
    '≈': r'$\approx$',
    '≤': r'$\leq$',
    '≥': r'$\geq$',
    '≠': r'$\neq$',
    '°': r'$^\circ$',
    '²': r'$^2$',
    '³': r'$^3$',
    '½': r'$\frac{1}{2}$',
    '¼': r'$\frac{1}{4}$',
    '¾': r'$\frac{3}{4}$',
    '√': r'$\sqrt{}$',
    '∞': r'$\infty$',
    '⌈': r'$\lceil$',
    '⌉': r'$\rceil$',
    '⌊': r'$\lfloor$',
    '⌋': r'$\rfloor$',
}


def fix_unicode_to_latex(text: str) -> str:
    """Заменяет юникод-символы на LaTeX"""
    for unicode_char, latex in UNICODE_TO_LATEX.items():
        text = text.replace(unicode_char, latex)
    
    # Замена слов
    text = text.replace('градусов', r'$^\circ$')
    text = text.replace('кв. см', r'$\text{см}^2$')
    text = text.replace('кв.см', r'$\text{см}^2$')
    text = text.replace('куб. см', r'$\text{см}^3$')
    text = text.replace('куб.см', r'$\text{см}^3$')
    
    return text


async def shorten_answer(session: aiohttp.ClientSession, question: str, long_answer: str) -> str:
    """Сокращает длинный ответ через API"""
    try:
        prompt = f"""Тебе дано условие задачи и её длинный ответ. 
Вытащи из этого текста ТОЛЬКО финальный краткий ответ (число, слово или короткое выражение в LaTeX). 
Не пиши никаких пояснений. Если ответов несколько, перечисли через запятую.

Задача: {question[:500]}

Длинный ответ: {long_answer[:1000]}

Верни ТОЛЬКО краткий ответ без дополнительного текста:"""

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 100
        }
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        async with session.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                result = await response.json()
                short_answer = result["choices"][0]["message"]["content"].strip()
                # Очистка от возможных markdown блоков
                short_answer = short_answer.replace('```', '').strip()
                return short_answer if len(short_answer) < 200 else long_answer[:50]
            else:
                return long_answer[:50]
                
    except Exception as e:
        print(f"[WARN] Ошибка сокращения ответа: {str(e)[:50]}")
        return long_answer[:50]


async def clean_database():
    """Основная функция очистки"""
    print("="*70)
    print("ОЧИСТКА БАЗЫ ОЛИМПИАДНЫХ ЗАДАЧ")
    print("="*70)
    
    # Читаем задачи
    tasks = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            tasks.append(json.loads(line))
    
    print(f"Загружено задач: {len(tasks)}\n")
    
    # ШАГ 1: Фикс юникода
    print("[1] Исправление юникод-символов...")
    unicode_fixed = 0
    for task in tasks:
        original_q = task['question']
        original_e = task['explanation']
        
        task['question'] = fix_unicode_to_latex(task['question'])
        task['answer'] = fix_unicode_to_latex(task['answer'])
        task['explanation'] = fix_unicode_to_latex(task['explanation'])
        
        if task['question'] != original_q or task['explanation'] != original_e:
            unicode_fixed += 1
    
    print(f"Исправлено задач: {unicode_fixed}")
    
    # ШАГ 2: Удаление дубликатов
    print("\n[2] Удаление дубликатов...")
    seen_questions = set()
    unique_tasks = []
    duplicates_removed = 0
    
    for task in tasks:
        q = task['question']
        if q not in seen_questions:
            seen_questions.add(q)
            unique_tasks.append(task)
        else:
            duplicates_removed += 1
    
    print(f"Удалено дубликатов: {duplicates_removed}")
    print(f"Осталось уникальных задач: {len(unique_tasks)}")
    
    tasks = unique_tasks
    
    # ШАГ 3: Сокращение длинных ответов
    print("\n[3] Сокращение длинных ответов...")
    long_answers = [task for task in tasks if len(task['answer']) > 50]
    print(f"Задач с длинным ответом: {len(long_answers)}")
    
    if long_answers:
        print("Отправка запросов к API для сокращения...")
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(10)
            
            async def process_task(task):
                async with semaphore:
                    short = await shorten_answer(session, task['question'], task['answer'])
                    task['answer'] = short
                    return task
            
            # Обрабатываем только задачи с длинными ответами
            tasks_to_fix = []
            tasks_ok = []
            
            for task in tasks:
                if len(task['answer']) > 50:
                    tasks_to_fix.append(task)
                else:
                    tasks_ok.append(task)
            
            print(f"Обрабатываем {len(tasks_to_fix)} задач...")
            fixed_tasks = await asyncio.gather(*[process_task(t) for t in tasks_to_fix])
            
            tasks = tasks_ok + fixed_tasks
            print(f"Ответы сокращены!")
    
    # Сохранение
    print(f"\n[4] Сохранение в {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for task in tasks:
            json.dump(task, f, ensure_ascii=False)
            f.write('\n')
    
    print("\n" + "="*70)
    print("ОЧИСТКА ЗАВЕРШЕНА!")
    print("="*70)
    print(f"Итоговый файл: {OUTPUT_FILE}")
    print(f"Задач в файле: {len(tasks)}")
    print(f"Исправлено юникода: {unicode_fixed}")
    print(f"Удалено дубликатов: {duplicates_removed}")
    print(f"Сокращено ответов: {len(long_answers)}")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(clean_database())
