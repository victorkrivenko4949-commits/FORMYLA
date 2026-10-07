# -*- coding: utf-8 -*-
"""Replace all 8-level references with 5-level in routes/prep.py and others."""

import re

def fix_file(path, replacements):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    
    count = 0
    for old, new in replacements:
        if old in txt:
            txt = txt.replace(old, new)
            count += 1
            print(f'  [OK] replaced: {old[:70]}')
        else:
            # try fuzzy match
            print(f'  [--] not found: {old[:70]}')
    
    if count:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(txt)
        print(f'  -> {count} changes written')
    else:
        print(f'  -> no changes')

def main():
    print('=== Migrating 8-level to 5-level ===\n')
    
    # --- routes/prep.py ---
    print('\n--- routes/prep.py ---')
    fix_file('routes/prep.py', [
        # 1. level_labels: remove 6,7,8
        ('level_labels = {1: \U0001f535 Начальный, 2: \U0001f7e2 Базовый, 3: \U0001f7e1 Средний,\n'
         '                        4: \U0001f7e0 Продвинутый, 5: \U0001f534 Высокий, 6: \U0001f48e Эксперт,\n'
         '                        7: \U0001f451 Мастер, 8: \U0001f3c6 Легенда}',
         'level_labels = {1: \U0001f535 Начальный, 2: \U0001f7e2 Базовый, 3: \U0001f7e1 Средний,\n'
         '                        4: \U0001f7e0 Продвинутый, 5: \U0001f534 Высокий}'),
        
        # 2. Задачи дня готовятся /8
        ("сложность {_level}/8).", "сложность {_level}/5)."),
        # 3. Уровень сложности: /8
        ("Уровень сложности: {_level}/8.", "Уровень сложности: {_level}/5."),
        # 4. Задачи придут вечером /8
        ("({_level}/8).\\n\\n", "({_level}/5).\\n\\n"),
        
        # 5-8. max(1, min(8 -> max(1, min(5  (4 occurrences)
        ("max(1, min(8,", "max(1, min(5,"),
        ("max_level = min(8,", "max_level = min(5,"),
        
        # 9. overall_level /8 -> /5
        ("(уровень {overall_level}/8)", "(уровень {overall_level}/5)"),
        
        # 10-12. "от 1 до 8" -> "от 1 до 5"
        ("Оцени сложность каждой задачи от 1 до 8", "Оцени сложность каждой задачи от 1 до 5"),
        ("оцените сложность задачи по шкале от 1 до 8", "оцените сложность задачи по шкале от 1 до 5"),
        ("Оцени сложность этой задачи от 1 до 8", "Оцени сложность этой задачи от 1 до 5"),
    ])
    
    # --- services/diagnostic_questionnaire.py ---
    print('\n--- services/diagnostic_questionnaire.py ---')
    fix_file('services/diagnostic_questionnaire.py', [
        ("max(1, min(8,", "max(1, min(5,"),
        ("/8)", "/5)"),
        ("(уровень {level}/8)", "(уровень {level}/5)"),
        # level_labels
        ("1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый',\n        "
         "3: '\U0001f7e1 Средний', 4: '\U0001f7e0 Продвинутый',\n        "
         "5: '\U0001f534 Высокий', 6: '\U0001f48e Эксперт',\n        "
         "7: '\U0001f451 Мастер', 8: '\U0001f3c6 Легенда',",
         "1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый',\n        "
         "3: '\U0001f7e1 Средний', 4: '\U0001f7e0 Продвинутый',\n        "
         "5: '\U0001f534 Высокий',"),
    ])

    print('\n=== Done ===')

if __name__ == '__main__':
    main()
