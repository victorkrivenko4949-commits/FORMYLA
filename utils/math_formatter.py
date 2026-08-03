#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Math Formatter - автоматическое форматирование математики в LaTeX
Оборачивает математические выражения в $ $ для рендеринга MathJax
"""

import re


def format_math_to_latex(text: str) -> str:
    """
    Автоматически оборачивает математические выражения в LaTeX формат.
    
    Args:
        text: Исходный текст с плоской математикой
        
    Returns:
        Текст с математикой, обернутой в $ $
    """
    if not text:
        return text
    
    # Если уже есть LaTeX-разметка, не трогаем
    if '$' in text and '\\' in text:
        return text
    
    # 1. Заменяем sqrt(...) на \sqrt{...}
    text = re.sub(r'sqrt\(([^)]+)\)', r'\\sqrt{\1}', text)
    
    # 2. Оборачиваем уравнения (содержат =, переменные и операторы)
    # Паттерн: выражение с переменными, числами, операторами и знаком равенства
    equation_pattern = r'([a-zA-Z0-9\s\+\-\*/\^()]+\s*=\s*[a-zA-Z0-9\s\+\-\*/\^()]+)'
    
    def wrap_equation(match):
        eq = match.group(1)
        # Проверяем, что это действительно математика (содержит переменные или операторы)
        if re.search(r'[a-zA-Z]\^|[a-zA-Z]\d|[+\-*/=]', eq):
            return f'${eq}$'
        return eq
    
    text = re.sub(equation_pattern, wrap_equation, text)
    
    # 3. Оборачиваем степени (x^2, a^n, 2^n и т.д.)
    # Паттерн: буква или число, затем ^, затем число или буква
    power_pattern = r'([a-zA-Z0-9]+)\^([a-zA-Z0-9]+)'
    
    def wrap_power(match):
        base = match.group(1)
        exp = match.group(2)
        # Если уже в долларах, не трогаем
        if match.start() > 0 and text[match.start()-1] == '$':
            return match.group(0)
        return f'${base}^{{{exp}}}$'
    
    text = re.sub(power_pattern, wrap_power, text)
    
    # 4. Оборачиваем дроби (a/b где a и b - переменные или простые выражения)
    fraction_pattern = r'([a-zA-Z0-9]+)/([a-zA-Z0-9]+)'
    
    def wrap_fraction(match):
        num = match.group(1)
        den = match.group(2)
        # Проверяем, что это математическая дробь (хотя бы одна переменная)
        if re.search(r'[a-zA-Z]', num + den):
            # Если уже в долларах, не трогаем
            if match.start() > 0 and text[match.start()-1] == '$':
                return match.group(0)
            return f'$\\frac{{{num}}}{{{den}}}$'
        return match.group(0)
    
    text = re.sub(fraction_pattern, wrap_fraction, text)
    
    # 5. Оборачиваем одиночные переменные с индексами (p_n, x_1, a_i)
    index_pattern = r'([a-zA-Z])_([a-zA-Z0-9]+)'
    
    def wrap_index(match):
        var = match.group(1)
        idx = match.group(2)
        # Если уже в долларах, не трогаем
        if match.start() > 0 and text[match.start()-1] == '$':
            return match.group(0)
        return f'${var}_{{{idx}}}$'
    
    text = re.sub(index_pattern, wrap_index, text)
    
    # 6. Оборачиваем корни (\sqrt{...})
    sqrt_pattern = r'\\sqrt\{([^}]+)\}'
    
    def wrap_sqrt(match):
        content = match.group(1)
        # Если уже в долларах, не трогаем
        if match.start() > 0 and text[match.start()-1] == '$':
            return match.group(0)
        return f'$\\sqrt{{{content}}}$'
    
    text = re.sub(sqrt_pattern, wrap_sqrt, text)
    
    # 7. Убираем двойные доллары (если случайно обернули дважды)
    text = re.sub(r'\$\$+', '$', text)
    text = re.sub(r'\$\s*\$', '', text)  # Убираем пустые $ $
    
    # 8. Объединяем соседние математические выражения
    # $a$ + $b$ -> $a + b$
    text = re.sub(r'\$\s*([+\-*/=])\s*\$', r' \1 ', text)
    text = re.sub(r'\$([^$]+)\$\s*\$([^$]+)\$', r'$\1 \2$', text)
    
    return text


def format_task_math(task: dict) -> dict:
    """
    Форматирует математику во всех полях задачи.
    
    Args:
        task: Словарь с полями text, answer, solution
        
    Returns:
        Задача с отформатированной математикой
    """
    formatted = task.copy()
    
    if 'text' in formatted:
        formatted['text'] = format_math_to_latex(formatted['text'])
    
    if 'solution' in formatted:
        formatted['solution'] = format_math_to_latex(formatted['solution'])
    
    if 'answer' in formatted:
        # Ответ обычно короткий, оборачиваем целиком если содержит математику
        answer = formatted['answer']
        if re.search(r'[a-zA-Z]\^|[a-zA-Z]/|sqrt|\\', answer):
            if not answer.startswith('$'):
                formatted['answer'] = f'${format_math_to_latex(answer)}$'
    
    return formatted


# Тестирование
if __name__ == "__main__":
    test_cases = [
        "Найдите корни уравнения x^2 - 5x + 6 = 0",
        "Вычислите sqrt(25) + sqrt(16)",
        "Дробь a/b равна 1/2",
        "Последовательность p_n определена как p_1 = 1",
        "Уравнение x^4 + (a-2)x^2 + (a^2 - 4a + 3) = 0",
        "Расстояние sqrt(2)/2 от точки",
        "Число 2^n + n^2 является квадратом"
    ]
    
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ФОРМАТИРОВАНИЯ МАТЕМАТИКИ")
    print("=" * 80)
    
    for i, test in enumerate(test_cases, 1):
        result = format_math_to_latex(test)
        print(f"\n{i}. ОРИГИНАЛ:")
        print(f"   {test}")
        print(f"   РЕЗУЛЬТАТ:")
        print(f"   {result}")
