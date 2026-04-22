"""
Тестовый скрипт для проверки функции compare_math_answers
"""

from utils.math_answer_utils import compare_math_answers

# Тестовые кейсы
test_cases = [
    # (user_input, db_answer, expected_result, description)
    ("7", "7", True, "Точное совпадение"),
    ("7", "x=7", True, "Пользователь без префикса, БД с префиксом"),
    ("x=7", "7", True, "Пользователь с префиксом, БД без префикса"),
    ("x=7", "x = 7", True, "Разные пробелы в префиксе"),
    ("7", "$7$", True, "БД с LaTeX"),
    ("$7$", "7", True, "Пользователь с LaTeX"),
    ("7", "Ответ: 7", True, "БД с префиксом 'Ответ:'"),
    ("Ответ: 7", "7", True, "Пользователь с префиксом 'Ответ:'"),
    ("0,5", "0.5", True, "Запятая vs точка"),
    ("0.5", "0,5", True, "Точка vs запятая"),
    (" 7 ", "7", True, "Пробелы по краям"),
    ("005", "5", True, "Ведущие нули"),
    ("y=10", "10", True, "Другая переменная"),
    ("Answer: 42", "42", True, "Английский префикс"),
    ("15", "15.0", False, "Разные представления числа"),
    ("abc", "def", False, "Разные строки"),
]

print("=" * 70)
print("ТЕСТИРОВАНИЕ ФУНКЦИИ compare_math_answers")
print("=" * 70)

passed = 0
failed = 0

for user_input, db_answer, expected, description in test_cases:
    result = compare_math_answers(user_input, db_answer)
    status = "[OK]" if result == expected else "[FAIL]"
    
    if result == expected:
        passed += 1
    else:
        failed += 1
    
    print(f"\n{status} {description}")
    print(f"  User: '{user_input}' | DB: '{db_answer}'")
    print(f"  Expected: {expected}, Got: {result}")

print("\n" + "=" * 70)
print(f"ИТОГО: Пройдено {passed}/{len(test_cases)}, Провалено {failed}/{len(test_cases)}")
print("=" * 70)
