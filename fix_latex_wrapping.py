"""
Исправление: убираем обертку с русского текста, оставляем только на уравнениях
"""
import re
from problems import PROBLEMS_DB

def fix_wrapping(text):
    """Исправить неправильную обертку"""
    if not text:
        return text
    
    # Если весь текст обернут в \( ... \), нужно исправить
    if text.startswith('\\(') and text.endswith('\\)'):
        # Убираем внешнюю обертку
        inner = text[3:-3].strip()
        
        # Ищем уравнение/выражение внутри текста
        # Паттерн: последовательность с переменными и операторами
        # Например: x^4 + 4x^2 + 5 = 0
        
        # Ищем выражение с = (уравнение)
        match = re.search(r'([a-zA-Z0-9()\s+\-*/^]+\s*=\s*[a-zA-Z0-9()\s+\-*/^]+)', inner)
        if match:
            equation = match.group(0).strip()
            # Исправляем сложные степени
            equation = re.sub(r'\^(\([^)]+\))', lambda m: '^{' + m.group(1)[1:-1] + '}', equation)
            
            # Заменяем уравнение на обернутое
            result = inner.replace(equation, f'\\( {equation} \\)')
            return result
    
    return text

print("="*80)
print("ISPRAVLENIE NEPRAVILNOJ OBERTKI")
print("="*80)

fixed = 0

for problem in PROBLEMS_DB:
    original = problem.get('text', '')
    
    # Ищем задачи, где весь текст в одной формуле
    if original.startswith('\\(') and original.endswith('\\)'):
        fixed_text = fix_wrapping(original)
        
        if fixed_text != original:
            problem['text'] = fixed_text
            fixed += 1

print(f"[STATS] Ispravleno: {fixed}")

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach s LaTeX\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(PROBLEMS_DB))

print("[SAVE] Sohraneno v problems.py")

# Проверяем
from problems import PROBLEMS_DB as NEW_DB
task = next((p for p in NEW_DB if p.get('id') == 2019), None)
if task:
    print("\n[CHECK] Zadacha ID=2019:")
    print(task['text'][:200])

print("="*80)
