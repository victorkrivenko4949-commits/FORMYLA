"""
Умная обертка: оборачивает ТОЛЬКО математические выражения, не трогая русский текст
"""
import re
from problems import PROBLEMS_DB

def wrap_math_only(text):
    """Обернуть только математические выражения, оставив русский текст как есть"""
    if not text or '\\(' in text:
        return text
    
    # Ищем математические выражения: уравнения, неравенства, выражения
    # Паттерн: последовательность из переменных, чисел, операторов
    # Например: x^2 + 3x - 5 = 0
    
    # Регулярка для математического выражения:
    # - Начинается с переменной или числа или скобки
    # - Содержит операторы +, -, *, /, ^, =, <, >
    # - Заканчивается числом, переменной или скобкой
    
    # Паттерн: (переменная|число|скобка)(операторы и переменные)(=|<|>)(что-то)
    math_pattern = r'([a-zA-Z0-9()\s]+[+\-*/^=<>≤≥≠]+[a-zA-Z0-9()\s+\-*/^=<>≤≥≠]+)'
    
    def replace_math(match):
        expr = match.group(0).strip()
        # Исправляем сложные степени
        expr = re.sub(r'\^(\([^)]+\))', r'^{\1}', expr)
        return f'\\( {expr} \\)'
    
    # Заменяем математические выражения
    result = re.sub(math_pattern, replace_math, text)
    
    return result

print("="*80)
print("UMNAJA KONVERTATSIJA (tolko matematika)")
print("="*80)

converted = 0

for problem in PROBLEMS_DB:
    original = problem.get('text', '')
    
    # Пропускаем, если уже есть LaTeX
    if '\\(' in original:
        continue
    
    # Пропускаем, если нет математики
    if not any(char in original for char in ['^', '=']):
        continue
    
    converted_text = wrap_math_only(original)
    
    if converted_text != original:
        problem['text'] = converted_text
        converted += 1

print(f"[STATS] Konvertirovano: {converted}")

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(PROBLEMS_DB))

print("[SAVE] Sohraneno v problems.py")

# Проверяем результат
from problems import PROBLEMS_DB as NEW_DB
task = next((p for p in NEW_DB if 'x^4 + 4x^2 + 5' in p.get('text', '')), None)
if task:
    print("\n[CHECK] Primer zadachi:")
    print(task['text'][:200])

print("="*80)
