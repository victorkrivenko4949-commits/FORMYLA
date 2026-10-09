# -*- coding: utf-8 -*-
"""Final fixes: remaining 8-level refs in routes/prep.py"""

path = 'routes/prep.py'
with open(path, 'r', encoding='utf-8') as f:
    txt = f.read()

changes = 0

# 1. Second level_labels in _submit_onboarding_results (7/8)
old_labels = '''        level_labels = {1: ' Начальный', 2: ' Базовый', 3: ' Средний',
                        4: ' Продвинутый', 5: ' Высокий', 6: ' Эксперт',
        7: ' Мастер', 8: ' Легенда'}'''
new_labels = '''        level_labels = {1: ' Начальный', 2: ' Базовый', 3: ' Средний',
                        4: ' Продвинутый', 5: ' Высокий'}'''
if old_labels in txt:
    txt = txt.replace(old_labels, new_labels)
    changes += 1
    print(f'[OK] Replaced second level_labels')
else:
    print(f'[--] Second level_labels not found')

# 2. * 8 in final_level calculations -> * 5
# In coach_onboarding_submit and _submit_onboarding_results
old_star8 = "topic_results[topic]['total']) * 8"
new_star5 = "topic_results[topic]['total']) * 5"
if old_star8 in txt:
    txt = txt.replace(old_star8, new_star5)
    changes += 1
    print(f'[OK] Replaced *8 with *5')
else:
    print(f'[--] * 8 pattern not found')

# 3. difficulty <= 8 -> <= 5
old_diff = 'if 1 <= difficulty <= 8:'
new_diff = 'if 1 <= difficulty <= 5:'
if old_diff in txt:
    txt = txt.replace(old_diff, new_diff)
    changes += 1
    print(f'[OK] Replaced difficulty <= 8')
else:
    print(f'[--] difficulty <= 8 not found')

# 4. Comment "адаптация уровня (шкала 1..8)" -> "1..5"
old_comment = 'Адаптация уровня (шкала 1..8):'
new_comment = 'Адаптация уровня (шкала 1..5):'
if old_comment in txt:
    txt = txt.replace(old_comment, new_comment)
    changes += 1
    print(f'[OK] Replaced comment 1..8')
else:
    print(f'[--] comment 1..8 not found')

# 5. Another "clamped 1..8" comment in coach_daily_submit
old_clamped = '(окно ±1, clamped 1..8)'
new_clamped = '(окно ±1, clamped 1..5)'
if old_clamped in txt:
    txt = txt.replace(old_clamped, new_clamped)
    changes += 1
    print(f'[OK] Replaced clamped comment')
else:
    print(f'[--] clamped comment not found')

if changes:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)
    print(f'\n===> {changes} changes saved to routes/prep.py')
else:
    print(f'\n===> No changes needed')
