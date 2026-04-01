# -*- coding: utf-8 -*-
import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
from collections import Counter

# Проверка распределения по уровням сложности для Алгебры, 5 класс
algebra_5 = [p for p in PROBLEMS_DB if p['subject']=='algebra' and p['grade']==5]
diff_count = Counter(p['difficulty'] for p in algebra_5)

print(f"Всего задач по Алгебре для 5 класса: {len(algebra_5)}")
print("\nРаспределение по уровням сложности:")
for level in range(1, 11):
    count = diff_count.get(level, 0)
    status = "OK" if count > 0 else "EMPTY"
    print(f"Уровень {level}: {count} задач - {status}")

print("\n" + "="*50)
print("Общая статистика по всем задачам:")
all_diff = Counter(p['difficulty'] for p in PROBLEMS_DB)
for level in range(1, 11):
    count = all_diff.get(level, 0)
    print(f"Уровень {level}: {count} задач")
