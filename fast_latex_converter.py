"""
Быстрая конвертация математических выражений в LaTeX
"""
import re
from problems import PROBLEMS_DB

def convert_to_latex(text):
    """Конвертировать текст в LaTeX"""
    if not text or '\\(' in text:
        return text
    
    # Ищем математические выражения (уравнения, неравенства)
    # Паттерн: текст с переменными, числами, операторами =, >, <, +, -, *, /, ^
    
    # Если есть уравнение или выражение после двоеточия
    if ':' in text:
        parts = text.split(':', 1)
        if len(parts) == 2:
            prefix = parts[0]
            math_part = parts[1].strip()
            
            # Проверяем, есть ли математика
            if any(char in math_part for char in ['^', '=', '+', '-', '*', '/', 'x', 'y', 'z', 'a', 'b']):
                # Оборачиваем в LaTeX
                # Заменяем сложные степени: ^(...) на ^{...}
                math_part = re.sub(r'\^(\([^)]+\))', r'^{\1}', math_part)
                # Убираем лишние скобки: ^{(выражение)} → ^{выражение}
                math_part = re.sub(r'\^\{(\([^)]+\))\}', r'^{\1}', math_part)
                
                return f'{prefix}: \\( {math_part} \\)'
    
    # Если нет двоеточия, но есть математика в конце предложения
    # Ищем паттерн: "текст уравнение."
    match = re.search(r'([a-z]+.*?)([x-z^0-9+\-*/=<>()]+\s*[=<>]\s*[x-z^0-9+\-*/()]+\.?)$', text, re.IGNORECASE)
    if match:
        prefix = match.group(1)
        math_part = match.group(2).strip()
        # Заменяем сложные степени
        math_part = re.sub(r'\^(\([^)]+\))', r'^{\1}', math_part)
        return f'{prefix}\\( {math_part} \\)'
    
    return text

print("="*80)
print("BYSTRAJA KONVERTATSIJA V LATEX")
print("="*80)

converted = 0
examples = []

for problem in PROBLEMS_DB:
    original = problem.get('text', '')
    converted_text = convert_to_latex(original)
    
    if converted_text != original:
        problem['text'] = converted_text
        converted += 1
        
        if len(examples) < 3:
            examples.append({
                'id': problem.get('id'),
                'original': original[:80],
                'converted': converted_text[:80]
            })

print(f"[STATS] Konvertirovano: {converted} zadach")

print("\n[PRIMERY]:")
for ex in examples:
    print(f"\nID {ex['id']}:")
    print(f"  DO:    {ex['original']}...")
    print(f"  POSLE: {ex['converted']}...")

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(PROBLEMS_DB))

print(f"\n[SAVE] Sohraneno v problems.py")
print("="*80)
