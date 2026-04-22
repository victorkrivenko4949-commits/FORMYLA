"""
Утилиты для умного сравнения математических ответов.
Минимизирует ложноотрицательные срабатывания при проверке ответов студентов.
"""

import re


def compare_math_answers(user_answer, correct_answer):
    """
    Умная функция сравнения математических ответов с нормализацией.
    
    Нормализует оба ответа перед сравнением, чтобы минимизировать ложноотрицательные срабатывания.
    
    Примеры:
        compare_math_answers(" x = 5 ", "5") -> True
        compare_math_answers("0,5", "0.5") -> True
        compare_math_answers("Ответ: 42", "42") -> True
        compare_math_answers("$12$", "12") -> True
        compare_math_answers("10 км/ч", "10") -> True
    
    Args:
        user_answer (str): Ответ пользователя
        correct_answer (str): Правильный ответ из базы данных
    
    Returns:
        bool: True если ответы совпадают после нормализации, иначе False
    """
    if not user_answer or not correct_answer:
        return False
    
    # Нормализуем оба ответа
    user_normalized = normalize_answer(user_answer)
    correct_normalized = normalize_answer(correct_answer)
    
    # DEBUG: Логирование для отладки
    result = user_normalized == correct_normalized
    print("=" * 60)
    print("=== DEBUG COMPARE_MATH_ANSWERS ===")
    print(f"Оригинал юзера: '{user_answer}' (тип: {type(user_answer).__name__})")
    print(f"Оригинал из БД: '{correct_answer}' (тип: {type(correct_answer).__name__})")
    print(f"Нормализовано юзер: '{user_normalized}'")
    print(f"Нормализовано БД: '{correct_normalized}'")
    print(f"Результат сравнения: {result}")
    print("=" * 60)
    
    # Сравниваем нормализованные ответы
    return result


def normalize_answer(answer):
    """
    Нормализует математический ответ для сравнения.
    
    Шаги нормализации:
    1. Приведение к нижнему регистру
    2. Удаление всех пробелов
    3. Замена запятых на точки (для десятичных дробей)
    4. Удаление префиксов типа "x=", "y=", "ответ:", "answer:"
    5. Удаление LaTeX-разметки ($, \\text{}, и т.д.)
    6. Извлечение числа из строки с единицами измерения (если эталон - число)
    
    Args:
        answer (str): Исходный ответ
    
    Returns:
        str: Нормализованный ответ
    """
    if not answer:
        return ""
    
    # Преобразуем в строку и приводим к нижнему регистру
    result = str(answer).lower().strip()
    
    # Удаляем все пробелы
    result = result.replace(' ', '')
    
    # Заменяем запятые на точки (для десятичных дробей)
    result = result.replace(',', '.')
    
    # Удаляем LaTeX-разметку СНАЧАЛА
    result = result.replace('$', '')  # Удаляем знаки доллара
    result = result.replace('\\(', '')  # Удаляем \(
    result = result.replace('\\)', '')  # Удаляем \)
    result = result.replace('(', '')  # Удаляем обычные скобки
    result = result.replace(')', '')  # Удаляем обычные скобки
    result = re.sub(r'\\text\{([^}]*)\}', r'\1', result)  # \\text{...} -> ...
    result = re.sub(r'\\[a-z]+\{([^}]*)\}', r'\1', result)  # Другие LaTeX команды
    result = result.replace('\\', '')  # Удаляем оставшиеся обратные слэши
    
    # ПОТОМ удаляем префиксы "ответ:", "answer:", "ans:"
    result = re.sub(r'^(ответ|answer|ans)\s*:\s*', '', result, flags=re.IGNORECASE)
    
    # И наконец удаляем префиксы типа "x=", "y=", "a=", "b=" и т.д. (одна буква + знак равно)
    result = re.sub(r'^[a-z]=', '', result)
    
    # Если результат содержит только цифры, точку и знак минус, пытаемся извлечь число
    # Это помогает обработать случаи типа "10км/ч" -> "10"
    if re.search(r'\d', result):  # Если есть хотя бы одна цифра
        # Пытаемся извлечь число (целое или десятичное, возможно отрицательное)
        number_match = re.search(r'-?\d+\.?\d*', result)
        if number_match:
            extracted_number = number_match.group()
            # Если извлеченное число составляет значительную часть строки, используем его
            if len(extracted_number) >= len(result) * 0.5:
                result = extracted_number
    
    # Удаляем ведущие нули (кроме "0" и "0.xxx")
    if result and result != '0' and not result.startswith('0.'):
        result = result.lstrip('0') or '0'
    
    return result


# Тесты для проверки функции
if __name__ == "__main__":
    test_cases = [
        (" x = 5 ", "5", True),
        ("0,5", "0.5", True),
        ("Ответ: 42", "42", True),
        ("$12$", "12", True),
        ("10 км/ч", "10", True),
        ("  3.14  ", "3.14", True),
        ("y=7", "7", True),
        ("Answer: 100", "100", True),
        ("0.5", "0,5", True),
        ("005", "5", True),
        ("x=2", "y=2", True),  # Оба нормализуются в "2"
        ("15", "15.0", False),  # Разные представления числа
        ("abc", "def", False),
        ("", "5", False),
        ("5", "", False),
    ]
    
    print("Тестирование функции compare_math_answers:")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for user_ans, correct_ans, expected in test_cases:
        result = compare_math_answers(user_ans, correct_ans)
        status = "[OK]" if result == expected else "[FAIL]"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} compare_math_answers('{user_ans}', '{correct_ans}') = {result} (expected: {expected})")
        if result != expected:
            print(f"  Нормализованные: '{normalize_answer(user_ans)}' vs '{normalize_answer(correct_ans)}'")
    
    print("=" * 60)
    print(f"Пройдено: {passed}/{len(test_cases)}, Провалено: {failed}/{len(test_cases)}")
