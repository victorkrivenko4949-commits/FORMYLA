"""
Универсальный обертыватель математики в LaTeX
Оборачивает ВСЕ математические выражения в \\( ... \\)
"""
import re
from problems import PROBLEMS_DB

def wrap_all_math(text):
    """Обернуть все математические выражения в LaTeX"""
    if not text or '\\(' in text:
        return text
    
    # Стратегия: найти все математические выражения и обернуть их
    # Математическое выражение = содержит переменные (x, y, z, a, b, c) и операторы
    
    # Паттерн для поиска математических выражений:
    # - Уравнения: x^2 + 3x = 5
    # - Неравенства: x > 5
    # - Выражения: (x+1)^2
    # - Системы: x + y = 5
    
    # Простой подход: если в тексте есть переменные и операторы,
    # оборачиваем всё после последней точки или двоеточия
    
    # Ищем последнее предложение с математикой
    sentences = text.split('.')
    result_sentences = []
    
    for sentence in sentences:
        # Проверяем, есть ли математика
        has_math = any(char in sentence for char in ['^', '=', '+', '-', '*', '/']) and \
                   any(var in sentence.lower() for var in ['x', 'y', 'z', 'a', 'b', 'c'])
        
        if has_math and '\\(' not in sentence:
            # Ищем математическое выражение
            # Паттерн: после двоеточия или в конце предложения
            if ':' in sentence:
                parts = sentence.split(':', 1)
                prefix = parts[0]
                math_expr = parts[1].strip()
                sentence = f'{prefix}: \\( {math_expr} \\)'
            else:
                # Оборачиваем всё предложение
                sentence = f'\\( {sentence.strip()} \\)'
        
        result_sentences.append(sentence)
    
    result = '.'.join(result_sentences)
    
    # Исправляем сложные степени: ^(...) → ^{...}
    result = re.sub(r'\^(\([^)]+\))', r'^{\1}', result)
    
    return result

print("="*80)
print("UNIVERSALNAJA KONVERTATSIJA V LATEX")
print("="*80)

converted = 0
skipped = 0

for problem in PROBLEMS_DB:
    original = problem.get('text', '')
    
    # Пропускаем, если уже есть LaTeX
    if '\\(' in original:
        skipped += 1
        continue
    
    # Пропускаем, если нет математики
    if not any(char in original for char in ['^', '=', 'x', 'y']):
        continue
    
    converted_text = wrap_all_math(original)
    
    if converted_text != original:
        problem['text'] = converted_text
        converted += 1

print(f"[STATS] Konvertirovano: {converted}")
print(f"[STATS] Propusheno (uzhe s LaTeX): {skipped}")

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(PROBLEMS_DB))

print("[SAVE] Sohraneno v problems.py")
print("="*80)
