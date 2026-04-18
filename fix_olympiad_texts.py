"""
Скрипт исправления текстов олимпиадных задач
Конвертирует сломанные тексты в правильный LaTeX
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olympiads import OLYMPIADS_DB
from ai.deepseek_client import DeepSeekClient
import json
import time

def fix_text_with_ai(client, broken_text):
    """Исправить сломанный текст используя AI"""
    
    system_prompt = r"""Ты - эксперт по LaTeX форматированию математических текстов.

Твоя задача: исправить сломанный текст олимпиадной задачи.

ЧТО НУЖНО ИСПРАВИТЬ:
1. Индексы: pn → \( p_n \), p1 → \( p_1 \), xi → \( x_i \)
2. Сложные индексы: pn+1 → \( p_{n+1} \), xi,j → \( x_{i,j} \)
3. Степени: p^2 → \( p^2 \), x^n → \( x^n \)
4. Уравнения: y = p2 x + q2 → \( y = p_2 x + q_2 \)
5. Дроби: a/b → \( \frac{a}{b} \)

ВАЖНО: Оборачивай ТОЛЬКО математические выражения, не трогай обычный русский текст!

В JSON используй ДВОЙНЫЕ слэши: "\\\\( p_n \\\\)"

Верни ТОЛЬКО JSON:
{
  "fixed_text": "Исправленный текст"
}"""
    
    user_prompt = f"""Исправь сломанный текст олимпиадной задачи:

{broken_text}

Восстанови индексы, степени и правильное форматирование LaTeX."""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2000
        )
        
        # Парсим
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        data = json.loads(response_text)
        return data.get('fixed_text', broken_text)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return broken_text

def main():
    print("="*80)
    print("ISPRAVLENIE TEKSTOV OLIMPIADNYH ZADACH")
    print("="*80)
    
    client = DeepSeekClient()
    
    # Ищем задачу про "Саша рисует"
    target_task = None
    target_combo = None
    
    for combo in OLYMPIADS_DB:
        for problem in combo.get('problems', []):
            text = problem.get('text', '')
            if 'Саша' in text and 'координатной плоскости' in text:
                target_task = problem
                target_combo = combo
                break
        if target_task:
            break
    
    if not target_task:
        print("[ERROR] Zadacha pro Sashu ne najdena")
        return
    
    print(f"[INFO] Najdena zadacha v combo ID={target_combo.get('id')}, problem #{target_task.get('num')}")
    print(f"\n[ORIGINAL TEXT]:")
    print(target_task['text'][:200])
    
    print(f"\n[FIXING] Otpravlyaem v AI...")
    fixed_text = fix_text_with_ai(client, target_task['text'])
    
    print(f"\n[FIXED TEXT]:")
    print(fixed_text[:200])
    
    # Обновляем
    target_task['text'] = fixed_text
    
    # Сохраняем
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza olimpiad s ispravlennymi tekstami\n\n')
        f.write('OLYMPIADS_DB = ')
        f.write(repr(OLYMPIADS_DB))
    
    print(f"\n[SAVE] Sohraneno v olympiads.py")
    print("="*80)

if __name__ == '__main__':
    main()
