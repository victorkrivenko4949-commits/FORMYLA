# -*- coding: utf-8 -*-
"""
Конвертация уровней 1,3,5,7,9 в 1,2,3,4,5
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

# Маппинг
LEVEL_MAPPING = {
    1: 1,
    3: 2,
    5: 3,
    7: 4,
    9: 5
}

print("="*70)
print("Конвертация в уровни 1-5")
print("="*70)

# Бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_1to5.bak")
print("✓ Бэкап: problems.py.before_1to5.bak")

# Конвертируем
print("\n🔄 Конвертация уровней...")
for problem in PROBLEMS_DB:
    old_level = problem.get('difficulty', 1)
    new_level = LEVEL_MAPPING.get(old_level, 1)
    problem['difficulty'] = new_level

# Статистика
from collections import Counter
level_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)

print("\nНовое распределение:")
for level in range(1, 6):
    count = level_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# 5 уровней сложности: 1, 2, 3, 4, 5\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")
print("\n✅ ГОТОВО! Теперь уровни 1-5")
