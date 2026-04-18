"""
Точная обертка: оборачивает ТОЛЬКО уравнения/выражения, не трогая обычный текст
"""
import re
from problems import PROBLEMS_DB

def wrap_equations_only(text):
    """Обернуть только уравнения и математические выражения"""
    if not text or '\\(' in text:
        return text
    
    # Ищем уравнения и выражения с помощью точных паттернов
    # Паттерн 1: выражение с = (уравнение)
    # Паттерн 2: выражение с > или < (неравенство)
    # Паттерн 3: выражение со степенями и операторами
    
    # Находим все математические выражения
    # Паттерн: последовательность из букв, цифр, операторов, скобок
    # которая содержит хотя бы один оператор (=, +, -, *, /, ^)
    
    # Ищем выражения типа: x^2 + 3x - 5 = 0
    pattern = r'([a-zA-Z][a-zA-Z0-9()\s+\-*/^]*[=<>≤≥][a-zA-Z0-9()\s+\-*/^]*)'
    
    def replace_expr(match):
        expr = match.group(0).strip()
        # Исправляем сложные степени: ^(...) → ^{...}
        expr = re.sub(r'\^(\([^)]+\))', lambda m: '^{' + m.group(1)[1:-1] + '}', expr)
        return f'\\( {expr} \\)'
    
    result = re.sub(pattern, replace_expr, text)
    
    return result

print("="*80)
print("TOCHNAJA KONVERTATSIJA (tolko uravnenija)")
print("="*80)

converted = 0
examples = []

for problem in PROBLEMS_DB:
    original = problem.get('text', '')
    
    # Пропускаем, если уже правильно обернуто
    # Проверяем: если есть \( и русский текст ВНЕ \(, то это правильно
    if '\\(' in original and not original.startswith('\\('):
        continue
    
    # Если весь текст в одной формуле - исправляем
    if original.startswith('\\(') and original.endswith('\\)'):
        # Убираем обертку и переделываем
        original = original[3:-3].strip()
    
    converted_text = wrap_equations_only(original)
    
    if converted_text != original:
        problem['text'] = converted_text
        converted += 1
        
        if len(examples) < 3:
            examples.append({
                'id': problem.get('id'),
                'grade': problem.get('grade'),
                'level': problem.get('difficulty')
            })

print(f"[STATS] Konvertirovano: {converted}")

if examples:
    print("\n[PRIMERY konvertirovannyh zadach]:")
    for ex in examples:
        print(f"  ID={ex['id']}, Klass={ex['grade']}, Uroven={ex['level']}")

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(PROBLEMS_DB))

print("\n[SAVE] Sohraneno v problems.py")
print("="*80)
