#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ШАГ 2: Безопасная починка LaTeX через DeepSeek API
Только оборачивает формулы, не меняет структуру
"""

import sys
import codecs
import time

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB
from ai.deepseek_client import DeepSeekClient

SYSTEM_PROMPT = """Ты — эксперт по LaTeX. Оберни ВСЕ математические выражения, переменные, числа, уравнения и формулы в этом тексте в LaTeX-разметку. Используй \\\\( ... \\\\) для внутристрочных формул и \\\\[ ... \\\\] для выделенных строк.

ВАЖНО:
1. Обязательно используй ДВОЙНОЕ экранирование слешей: \\\\( и \\\\).
2. НЕ меняй сам текст, только добавь разметку.
3. Верни ТОЛЬКО исправленный текст, без пояснений и маркдаун-блоков."""

def needs_latex_fix(text):
    """Проверяет, нужно ли исправлять LaTeX"""
    if not isinstance(text, str) or not text:
        return False
    # Уже обернуто
    if '\\(' in text or '\\[' in text:
        return False
    # Есть математика
    math_indicators = ['=', '<=', '>=', '^', 'x', 'y', 'a', 'b', 'n']
    return any(ind in text for ind in math_indicators)

def fix_latex_with_ai(client, text):
    """Исправляет LaTeX через DeepSeek API"""
    if not needs_latex_fix(text):
        return text, False
    
    try:
        prompt = f"""Оберни ВСЕ математические выражения в LaTeX-разметку \\\\( ... \\\\). Не меняй текст — только добавь LaTeX-обёртку. Верни ТОЛЬКО исправленный текст.

Текст: {text}"""
        
        response = client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1500
        )
        
        fixed = response.strip()
        
        # Убираем возможные обёртки
        if fixed.startswith('"') and fixed.endswith('"'):
            fixed = fixed[1:-1]
        if fixed.startswith('Текст:'):
            fixed = fixed[6:].strip()
        
        return fixed, True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return text, False

def main():
    print("="*80)
    print("🔧 ШАГ 2: БЕЗОПАСНАЯ ПОЧИНКА LATEX ЧЕРЕЗ AI")
    print("="*80)
    
    client = DeepSeekClient()
    
    total = len(PROBLEMS_DB)
    fixed_count = 0
    save_every = 50
    
    print(f"\n📊 Всего задач: {total}")
    print(f"💾 Сохранение каждые {save_every} задач\n")
    
    for i, task in enumerate(PROBLEMS_DB):
        text = task.get('text', '')
        
        if needs_latex_fix(text):
            print(f"\r🔄 [{i+1}/{total}] Исправляем задачу {task.get('id')}...", end='', flush=True)
            
            new_text, modified = fix_latex_with_ai(client, text)
            
            if modified:
                task['text'] = new_text
                fixed_count += 1
            
            time.sleep(0.3)
        
        # Сохранение прогресса
        if (i + 1) % save_every == 0:
            print(f"\n💾 Сохранение прогресса... (исправлено {fixed_count})")
            with open('problems.py', 'w', encoding='utf-8') as f:
                f.write('# -*- coding: utf-8 -*-\n')
                f.write(f'# Baza zadach FORMYLA - {len(PROBLEMS_DB)} zadach\n\n')
                f.write('PROBLEMS_DB = ')
                f.write(repr(PROBLEMS_DB))
            print("✅ Прогресс сохранён!")
        
        if (i + 1) % 100 == 0:
            print(f"\n✓ Обработано {i + 1}/{total}, исправлено: {fixed_count}")
    
    # Финальное сохранение
    print(f"\n\n💾 Финальное сохранение...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write(f'# Baza zadach FORMYLA - {len(PROBLEMS_DB)} zadach\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print(f"\n{'='*80}")
    print(f"✅ ШАГ 2 ЗАВЕРШЁН!")
    print(f"📊 Всего задач: {total}")
    print(f"🔧 Исправлено: {fixed_count}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()
