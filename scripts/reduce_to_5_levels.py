# -*- coding: utf-8 -*-
"""
Сокращение до 5 уровней сложности
Было: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
Стало: 1, 3, 5, 7, 9
"""
import sys
import os
import json
import shutil
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

# Маппинг старых уровней на новые
LEVEL_MAPPING = {
    1: 1,
    2: 1,
    3: 3,
    4: 3,
    5: 5,
    6: 5,
    7: 7,
    8: 7,
    9: 9,
    10: 9
}

print("="*70)
print("Сокращение до 5 уровней сложности")
print("="*70)
print("\nБыло: 10 уровней (1-10)")
print("Стало: 5 уровней (1, 3, 5, 7, 9)")

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_5levels.bak")
print("✓ Бэкап: problems.py.before_5levels.bak")

# Изменяем уровни
print("\n🔄 Изменение уровней...")
for problem in PROBLEMS_DB:
    old_level = problem.get('difficulty', 1)
    new_level = LEVEL_MAPPING.get(old_level, 1)
    problem['difficulty'] = new_level

# Статистика
from collections import Counter
level_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)

print("\nНовое распределение по уровням:")
for level in [1, 3, 5, 7, 9]:
    count = level_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# 5 уровней сложности: 1, 3, 5, 7, 9\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсе {len(PROBLEMS_DB)} задач теперь используют 5 уровней")
print("Обновите app.py: измените range(1, 11) на [1, 3, 5, 7, 9]")
