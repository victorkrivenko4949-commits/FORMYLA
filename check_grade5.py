# -*- coding: utf-8 -*-
import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
from collections import Counter

# Все задачи для 5 класса
grade5 = [p for p in PROBLEMS_DB if p['grade']==5]
diff_count = Counter(p['difficulty'] for p in grade5)

print(f"Всего задач для 5 класса: {len(grade5)}")
print("\nРаспределение по уровням сложности:")
total_check = 0
for level in range(1, 11):
    count = diff_count.get(level, 0)
    total_check += count
    status = "ЕСТЬ ЗАДАЧИ" if count > 0 else "ПУСТО"
    print(f"Уровень {level}: {count} задач - {status}")

print(f"\nПроверка суммы: {total_check} (должно быть {len(grade5)})")

# По разделам
print("\n" + "="*50)
print("Распределение по разделам для 5 класса:")
subjects = Counter(p['subject'] for p in grade5)
for subj, count in subjects.most_common():
    print(f"{subj}: {count} задач")
