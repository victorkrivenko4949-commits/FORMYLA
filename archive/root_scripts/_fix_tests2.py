# -*- coding: utf-8 -*-
"""Fix 6 broken tests in test_task_bank.py to match 1..5 scale."""
with open('tests/test_task_bank.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. test_miss_wrong_level
content = content.replace(
    '"""get_tasks для уровня вне [4,8]',
    '"""get_tasks для уровня вне [1,5]',
)
content = content.replace(
    'tb.get_tasks(grade=6, level=3, day=1)',
    'tb.get_tasks(grade=6, level=6, day=1)',
)
content = content.replace(
    '"Уровень 3 не должен быть в банке"',
    '"Уровень 6 не должен быть в банке"',
)

# 2. test_bank_levels
content = content.replace(
    '"""BANK_LEVELS = (4,5,6,7,8)."""',
    '"""BANK_LEVELS = (1,2,3,4,5)."""',
)
content = content.replace(
    'assert tb.BANK_LEVELS == (4, 5, 6, 7, 8)',
    'assert tb.BANK_LEVELS == (1, 2, 3, 4, 5)',
)
content = content.replace(
    'assert tb.MIN_BANK_LEVEL == 4',
    'assert tb.MIN_BANK_LEVEL == 1',
)
content = content.replace(
    'assert tb.MAX_BANK_LEVEL == 8',
    'assert tb.MAX_BANK_LEVEL == 5',
)

# 3. test_average_5_and_8 -> 2_and_4
content = content.replace(
    'def test_average_5_and_8_rounds_to_6(self):',
    'def test_average_2_and_4_rounds_to_3(self):',
)
content = content.replace(
    '"""(5+8)/2 = 6.5',
    '"""(2+4)/2 = 3',
)
content = content.replace(
    '"target_level": 5, "calibration": False},',
    '"target_level": 2, "calibration": False},',
    1,  # first occurrence only
)
content = content.replace(
    '"target_level": 8, "calibration": False},',
    '"target_level": 4, "calibration": False},',
    1,
)
content = content.replace(
    '# round((5+8)/2) = round(6.5) = 6 (Python banker',
    '# round((2+4)/2) = round(3.0) = 3',
)
content = content.replace(
    'assert result == 6',
    'assert result == 3',
    1,
)

# 4. test_calibration_topics_ignored
content = content.replace(
    '"target_level": 8, "calibration": False},   # measured',
    '"target_level": 5, "calibration": False},   # measured',
)
content = content.replace(
    '# Среднее: (8+8)/2 = 8 -> level=8',
    '# Среднее: (5+5)/2 = 5 -> level=5',
)
content = content.replace(
    'assert tb.pick_bank_level(profile) == 8',
    'assert tb.pick_bank_level(profile) == 5',
)

# 5. test_no_measured_topics_uses_class_expected
content = content.replace(
    '"class_expected_level": 7,',
    '"class_expected_level": 4,',
    1,
)
content = content.replace(
    'assert tb.pick_bank_level(profile) == 7',
    'assert tb.pick_bank_level(profile) == 4',
    1,
)

# 6. test_custom_default
content = content.replace(
    'default_level=6) == 6',
    'default_level=3) == 3',
)

with open('tests/test_task_bank.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('All 6 fixes applied')
