"""
AI-конвертер математических выражений в LaTeX
Использует DeepSeek для умной конвертации
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems import PROBLEMS_DB
from ai.deepseek_client import DeepSeekClient
import json
import time

def convert_task_to_latex(client, task_text):
    """Конвертировать текст задачи в LaTeX используя AI"""
    
    system_prompt = r"""Ты - эксперт по LaTeX форматированию математических текстов.

Твоя задача: взять текст задачи и обернуть ВСЕ математические выражения в \( ... \).

ПРАВИЛА:
1. Все переменные, числа в формулах, уравнения - оборачивай в \( ... \)
2. Степени: x^2 → \( x^2 \), сложные степени: x^(a+b) → \( x^{a+b} \)
3. Дроби: a/b → \( \frac{a}{b} \)
4. Корни: sqrt(x) → \( \sqrt{x} \)
5. Умножение: * → \( \cdot \)

Верни ТОЛЬКО JSON:
{
  "converted_text": "Текст с LaTeX разметкой"
}"""
    
    user_prompt = f"""Конвертируй этот текст задачи в LaTeX:

{task_text}

Оберни ВСЕ математические выражения в \\( ... \\)"""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1000
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
        return data.get('converted_text', task_text)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return task_text

def main():
    print("="*80)
    print("AI KONVERTATSIJA V LATEX")
    print("="*80)
    
    client = DeepSeekClient()
    
    # Находим задачи без LaTeX
    tasks_to_convert = []
    for i, problem in enumerate(PROBLEMS_DB):
        text = problem.get('text', '')
        # Если нет LaTeX разметки и есть математические символы
        if '\\(' not in text and any(char in text for char in ['^', '=', '+', '-', '*', '/']):
            tasks_to_convert.append(i)
    
    print(f"[INFO] Najdeno zadach bez LaTeX: {len(tasks_to_convert)}")
    print(f"[INFO] Obrabotaem pervye 50 zadach...")
    
    converted = 0
    for idx in tasks_to_convert[:50]:  # Первые 50 для теста
        problem = PROBLEMS_DB[idx]
        original = problem['text']
        
        print(f"[{converted+1}/50] Konvertacija zadachi ID={problem.get('id')}...")
        
        converted_text = convert_task_to_latex(client, original)
        problem['text'] = converted_text
        converted += 1
        
        time.sleep(1)  # Задержка между запросами
    
    print(f"\n[STATS] Konvertirovano: {converted} zadach")
    
    # Сохраняем
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza zadach FORMYLA s LaTeX\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print("[SAVE] Sohraneno v problems.py")
    print("="*80)

if __name__ == '__main__':
    main()
