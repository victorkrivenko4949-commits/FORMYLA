# -*- coding: utf-8 -*-
"""
Поднять ВСЕ уровни сложности на +6
Чтобы освободить уровни 1-6 для новых простых задач
"""
import sys
import os
import codecs
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

print("="*70)
print("Повышение ВСЕХ уровней сложности на +6")
print("="*70)
print("\nЦель: Освободить уровни 1-6 для новых простых задач")
print("Текущие задачи (олимпиадные) → уровни 7-10")

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_shift_all.bak")
print("✓ Бэкап: problems.py.before_shift_all.bak")

# Изменяем уровни
print("\n🔄 Повышение уровней...")
for problem in PROBLEMS_DB:
    old_diff = problem.get('difficulty', 1)
    new_diff = min(old_diff + 6, 10)  # Максимум 10
    problem['difficulty'] = new_diff

# Статистика
from collections import Counter
new_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)

print("\nНовое распределение:")
for level in range(1, 11):
    count = new_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# Уровни сложности: олимпиадные задачи (7-10)\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nУровни 1-6: {sum(new_dist.get(i, 0) for i in range(1, 7))} задач (готово для новых)")
print(f"Уровни 7-10: {sum(new_dist.get(i, 0) for i in range(7, 11))} задач (олимпиадные)")
