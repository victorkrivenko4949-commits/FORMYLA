"""
Умное исправление LaTeX в олимпиадных задачах через RegEx
Dry Run - показывает изменения без применения к базе
"""

import re
from olympiads import OLYMPIADS_DB

def fix_latex_subscripts_superscripts(text):
    """
    Умные замены индексов и степеней в LaTeX
    """
    if not text:
        return text
    
    original = text
    changes = []
    
    # 1. Площади: cm2, m2, km2 -> cm^2, m^2, km^2
    # Ищем внутри LaTeX блоков \( ... \)
    def fix_areas(match):
        latex_content = match.group(1)
        old_content = latex_content
        
        # Замены для площадей
        latex_content = re.sub(r'\b(см|м|км|cm|m|km)2\b', r'\1^2', latex_content)
        
        if old_content != latex_content:
            changes.append(('area', old_content, latex_content))
        
        return r'\(' + latex_content + r'\)'
    
    text = re.sub(r'\\\((.*?)\\\)', fix_areas, text)
    
    # 2. Объемы: cm3, m3, km3 -> cm^3, m^3, km^3
    def fix_volumes(match):
        latex_content = match.group(1)
        old_content = latex_content
        
        latex_content = re.sub(r'\b(см|м|км|cm|m|km)3\b', r'\1^3', latex_content)
        
        if old_content != latex_content:
            changes.append(('volume', old_content, latex_content))
        
        return r'\(' + latex_content + r'\)'
    
    text = re.sub(r'\\\((.*?)\\\)', fix_volumes, text)
    
    # 3. Индексы переменных: x1, x2, a1, b2 -> x_1, x_2, a_1, b_2
    # Только если переменная стоит перед математическим оператором или запятой
    def fix_subscripts(match):
        latex_content = match.group(1)
        old_content = latex_content
        
        # Переменные с цифрами перед операторами: x1 + x2 = -> x_1 + x_2 =
        latex_content = re.sub(
            r'\b([a-z])(\d)\s*([+\-=<>,])',
            r'\1_\2 \3',
            latex_content
        )
        
        # Переменные с цифрами в последовательностях: x1, x2, x3
        latex_content = re.sub(
            r'\b([a-z])(\d)\s*,',
            r'\1_\2,',
            latex_content
        )
        
        # Переменные с цифрами в конце выражения: ...x1)
        latex_content = re.sub(
            r'\b([a-z])(\d)\s*\)',
            r'\1_\2)',
            latex_content
        )
        
        if old_content != latex_content:
            changes.append(('subscript', old_content, latex_content))
        
        return r'\(' + latex_content + r'\)'
    
    text = re.sub(r'\\\((.*?)\\\)', fix_subscripts, text)
    
    # 4. Степени: x2, x3, x4 -> x^2, x^3, x^4 (только если НЕ в последовательности)
    # Это сложнее - нужно отличить x2 (индекс) от x2 (квадрат)
    # Эвристика: если после переменной с цифрой идет оператор умножения/деления, это степень
    def fix_powers(match):
        latex_content = match.group(1)
        old_content = latex_content
        
        # x2 * y или x2 / y -> x^2 * y
        latex_content = re.sub(
            r'\b([xyz])([234])\s*([*/])',
            r'\1^\2 \3',
            latex_content
        )
        
        # x2 в конце выражения (если нет запятой рядом)
        # Только для x, y, z и только степени 2, 3, 4
        latex_content = re.sub(
            r'\b([xyz])([234])(?!\d)(?!,)(?=\s*[\)+=\-<>])',
            r'\1^\2',
            latex_content
        )
        
        if old_content != latex_content:
            changes.append(('power', old_content, latex_content))
        
        return r'\(' + latex_content + r'\)'
    
    text = re.sub(r'\\\((.*?)\\\)', fix_powers, text)
    
    return text, changes


def main():
    """Dry Run - показываем изменения без применения"""
    
    print("\n" + "="*80)
    print("DRY RUN: ИСПРАВЛЕНИЕ LATEX В ОЛИМПИАДАХ")
    print("="*80 + "\n")
    
    print(f"Загружено {len(OLYMPIADS_DB)} олимпиад из olympiads.py\n")
    
    total_changes = 0
    problems_with_changes = 0
    total_problems = 0
    
    for olympiad in OLYMPIADS_DB:
        for problem in olympiad.get('problems', []):
            total_problems += 1
            problem_changes = []
            
            # Проверяем текст задачи
            if problem.get('text'):
                new_text, changes = fix_latex_subscripts_superscripts(problem['text'])
                if changes:
                    problem_changes.extend([('text', c) for c in changes])
            
            # Проверяем решение
            if problem.get('solution'):
                new_solution, changes = fix_latex_subscripts_superscripts(problem['solution'])
                if changes:
                    problem_changes.extend([('solution', c) for c in changes])
            
            # Если есть изменения, выводим
            if problem_changes:
                problems_with_changes += 1
                print(f"\n{'='*80}")
                print(f"ОЛИМПИАДА: {olympiad['olympiad_title']} {olympiad['year']}, Класс {olympiad['grade']}")
                print(f"Задача #{problem['num']}: {problem['text'][:60]}...")
                print(f"{'='*80}")
                
                for field, (change_type, old, new) in problem_changes:
                    total_changes += 1
                    print(f"\n[{change_type.upper()}] в поле '{field}':")
                    print(f"  БЫЛО:  {old[:100]}...")
                    print(f"  СТАЛО: {new[:100]}...")
    
    print(f"\n{'='*80}")
    print(f"ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*80}")
    print(f"Всего олимпиад: {len(OLYMPIADS_DB)}")
    print(f"Всего задач: {total_problems}")
    print(f"Задач с изменениями: {problems_with_changes}")
    print(f"Всего изменений: {total_changes}")
    print(f"{'='*80}\n")
    
    if total_changes > 0:
        print("[OK] Изменения найдены! Проверьте лог выше.")
        print("Если всё корректно, создам скрипт apply_olympiads_regex.py для применения.")
    else:
        print("[OK] Изменений не найдено. LaTeX в олимпиадах уже корректен!")


if __name__ == "__main__":
    main()
