# -*- coding: utf-8 -*-
"""
Скрипт для повышения уровней сложности задач
Смещение: 1→7, 2→8, 3→9, 4→10, 5→10, 6→10
"""
import sys
import os
import codecs

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
import json
import shutil

# Маппинг уровней сложности
DIFFICULTY_SHIFT = {
    1: 7,
    2: 8,
    3: 9,
    4: 10,
    5: 10,
    6: 10,
    7: 10,
    8: 10,
    9: 10,
    10: 10
}

print("="*70)
print("Повышение уровней сложности задач")
print("="*70)
print("\nМаппинг:")
for old, new in DIFFICULTY_SHIFT.items():
    print(f"  Уровень {old} → Уровень {new}")

# Создаем бэкап
print("\n💾 Создание бэкапа problems.py...")
shutil.copy2("problems.py", "problems.py.before_shift.bak")
print("✓ Бэкап создан: problems.py.before_shift.bak")

# Изменяем уровни сложности
print("\n🔄 Изменение уровней сложности...")
changed_count = 0
for problem in PROBLEMS_DB:
    old_diff = problem.get('difficulty', 1)
    new_diff = DIFFICULTY_SHIFT.get(old_diff, old_diff)
    if old_diff != new_diff:
        problem['difficulty'] = new_diff
        changed_count += 1

print(f"✓ Изменено задач: {changed_count}")

# Статистика после изменения
from collections import Counter
new_distribution = Counter(p['difficulty'] for p in PROBLEMS_DB)
print("\nНовое распределение по уровням:")
for level in range(1, 11):
    count = new_distribution.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение в problems.py...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач из HuggingFace — {len(PROBLEMS_DB)} задач\n")
    f.write("# Уровни сложности повышены: 1→7, 2→8, 3→9, 4→10\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nТеперь в базе:")
print(f"  Уровни 1-6: {sum(new_distribution.get(i, 0) for i in range(1, 7))} задач (нужно заполнить)")
print(f"  Уровни 7-10: {sum(new_distribution.get(i, 0) for i in range(7, 11))} задач (заполнено)")
print(f"\nСледующий шаг: Загрузить датасеты для уровней 1-6")
