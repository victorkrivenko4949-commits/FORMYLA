#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI-BASED исправление LaTeX через DeepSeek API
Перегенерирует задачи с правильным LaTeX форматированием
"""

import sys
import codecs
import asyncio
import time

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB
from ai.deepseek_client import DeepSeekClient

SYSTEM_PROMPT = """Ты - эксперт по LaTeX форматированию математических текстов.

Твоя задача: обернуть ВСЕ математические выражения в LaTeX-разметку.

ПРАВИЛА:
1. Инлайновые формулы: \\( ... \\)
2. Блочные формулы: \\[ ... \\]
3. НЕ МЕНЯЙ текст задачи - только добавь LaTeX-обёртку
4. Оборачивай ЦЕЛЫЕ выражения, а не куски
5. Дроби: \\frac{a}{b}
6. Корни: \\sqrt{x}
7. Степени: x^2, x^{n+1}
8. Индексы: a_1, x_{n+1}

ВАЖНО: Верни ТОЛЬКО исправленный текст, без пояснений."""

def needs_fixing(text):
    """Проверяет, нужно ли исправлять текст"""
    if not isinstance(text, str):
        return False
    if not text:
        return False
    # Уже обернуто
    if '\\(' in text or '\\[' in text:
        return False
    # Есть математика
    math_indicators = ['=', '+', '-', '*', '/', '^', 'x', 'y', 'a', 'b', 'n']
    return any(ind in text.lower() for ind in math_indicators)

def fix_task_with_ai(client, text):
    """Исправляет текст через DeepSeek API"""
    if not needs_fixing(text):
        return text, False
    
    try:
        prompt = f"""Перепиши следующий текст задачи, обернув ВСЕ математические выражения в LaTeX-разметку \\( ... \\) для инлайновых формул и \\[ ... \\] для блочных. Не меняй текст — только добавь LaTeX-обёртку. Верни ТОЛЬКО исправленный текст, без пояснений.

Текст: {text}"""
        
        response = client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1000
        )
        
        # Очистка ответа
        fixed = response.strip()
        
        # Убираем возможные обёртки
        if fixed.startswith('"') and fixed.endswith('"'):
            fixed = fixed[1:-1]
        if fixed.startswith('Текст:'):
            fixed = fixed[6:].strip()
        
        # Экранируем слеши для Python
        fixed = fixed.replace('\\(', '\\\\(').replace('\\)', '\\\\)')
        fixed = fixed.replace('\\[', '\\\\[').replace('\\]', '\\\\]')
        
        return fixed, True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return text, False

def main():
    print("="*80)
    print("🤖 AI-BASED ИСПРАВЛЕНИЕ LATEX ЧЕРЕЗ DEEPSEEK")
    print("="*80)
    
    client = DeepSeekClient()
    
    total_tasks = len(PROBLEMS_DB)
    fixed_count = 0
    examples = []
    
    print(f"\n📊 Всего задач: {total_tasks}")
    print(f"🔄 Начинаем обработку через DeepSeek API...\n")
    
    for i, task in enumerate(PROBLEMS_DB):
        task_id = task.get('id', i)
        text = task.get('text', '')
        
        # Исправляем текст задачи
        if needs_fixing(text):
            print(f"\r🔄 [{i+1}/{total_tasks}] Обрабатываем задачу {task_id}...", end='', flush=True)
            
            new_text, modified = fix_task_with_ai(client, text)
            
            if modified:
                task['text'] = new_text
                fixed_count += 1
                
                # Сохраняем примеры
                if len(examples) < 5:
                    examples.append({
                        'id': task_id,
                        'before': text[:100],
                        'after': new_text[:100]
                    })
            
            # Пауза между запросами
            time.sleep(0.5)
        
        # Прогресс каждые 100 задач
        if (i + 1) % 100 == 0:
            print(f"\n✓ Обработано {i + 1}/{total_tasks} задач, исправлено: {fixed_count}")
    
    print(f"\n\n{'='*80}")
    print(f"✅ ОБРАБОТКА ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"📊 Всего задач: {total_tasks}")
    print(f"🔧 Исправлено: {fixed_count}")
    print(f"{'='*80}\n")
    
    # Показываем примеры
    if examples:
        print("📝 ПРИМЕРЫ ИСПРАВЛЕНИЙ:\n")
        for idx, ex in enumerate(examples, 1):
            print(f"[ПРИМЕР {idx}] ID: {ex['id']}")
            print(f"❌ ДО:  {ex['before']}")
            print(f"✅ ПОСЛЕ: {ex['after']}")
            print("-"*80 + "\n")
    
    # Сохраняем
    print("💾 Сохранение исправленной базы данных...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza zadach FORMYLA - 2205 zadach\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print("✅ Файл problems.py успешно обновлён!")
    print("="*80)

if __name__ == '__main__':
    main()
