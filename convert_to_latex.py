"""
Скрипт для автоматической конвертации математических выражений в LaTeX
"""
import re
from problems import PROBLEMS_DB

def wrap_math_expressions(text):
    """
    Оборачивает математические выражения в \( ... \)
    """
    if not text:
        return text
    
    # Паттерны для поиска математических выражений
    # 1. Выражения со степенями: x^2, (x+1)^2, etc.
    # 2. Уравнения и неравенства: x = 5, x > 3, etc.
    # 3. Дроби: x/y (будем конвертировать в \frac)
    
    # Если уже есть LaTeX разметка, не трогаем
    if '\\(' in text or '\\[' in text:
        return text
    
    # Ищем математические выражения (упрощенная эвристика)
    # Паттерн: выражения с переменными, числами, операторами
    # Например: x^2, (x+1)^2, x = 5, x + y = 10
    
    # Сначала найдем все выражения со степенями
    # Паттерн: что-то^что-то
    def replace_power(match):
        base = match.group(1)
        exponent = match.group(2)
        # Если степень сложная (содержит операторы), оборачиваем в {}
        if any(op in exponent for op in ['+', '-', '*', '/', '^']):
            return f'{base}^{{{exponent}}}'
        else:
            return f'{base}^{exponent}'
    
    # Заменяем степени на правильный формат
    # (выражение)^(выражение) -> (выражение)^{выражение}
    text = re.sub(r'\(([^)]+)\)\^(\([^)]+\))', replace_power, text)
    # x^число -> x^число (оставляем как есть)
    # x^(выражение) -> x^{выражение}
    text = re.sub(r'([a-zA-Z])\^(\([^)]+\))', replace_power, text)
    
    # Теперь оборачиваем математические выражения в \( \)
    # Ищем паттерны типа: уравнение с =, >, <, ≤, ≥
    # Или выражения с переменными и операторами
    
    # Простая эвристика: если в тексте есть математические символы,
    # оборачиваем всё выражение после двоеточия
    if ':' in text and any(char in text for char in ['^', '=', '>', '<', '+', '-', '*', '/']):
        # Разделяем на текст до двоеточия и математику после
        parts = text.split(':', 1)
        if len(parts) == 2:
            prefix = parts[0]
            math_part = parts[1].strip()
            # Оборачиваем математическую часть
            if not math_part.startswith('\\('):
                text = f'{prefix}: \\( {math_part} \\)'
    
    return text

def convert_all_tasks():
    """Конвертировать все задачи в LaTeX"""
    print("="*80)
    print("KONVERTATSIJA ZADACH V LATEX FORMAT")
    print("="*80)
    
    converted_count = 0
    
    for problem in PROBLEMS_DB:
        original_text = problem.get('text', '')
        
        # Пропускаем, если уже есть LaTeX
        if '\\(' in original_text:
            continue
        
        # Конвертируем
        new_text = wrap_math_expressions(original_text)
        
        if new_text != original_text:
            problem['text'] = new_text
            converted_count += 1
    
    print(f"\n[STATS] Konvertirovano zadach: {converted_count}")
    
    # Сохраняем
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print(f"[SAVE] Obnovlennyj fajl sohranen v problems.py")
    print("="*80)

if __name__ == '__main__':
    convert_all_tasks()
