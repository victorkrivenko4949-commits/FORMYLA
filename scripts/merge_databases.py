# -*- coding: utf-8 -*-
"""
Объединение двух баз задач:
1. Олимпиадные задачи (уровень 10) - из problems.py
2. Простые задачи (уровни 1-6) - из data/simple_problems.jsonl
"""
import sys
import os
import json
import shutil
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Объединение баз данных задач")
print("="*70)

# Загружаем текущую базу (олимпиадные задачи)
print("\n📥 Загрузка олимпиадных задач из problems.py...")
from problems import PROBLEMS_DB as olympiad_problems
print(f"✓ Загружено: {len(olympiad_problems)} олимпиадных задач")

# Загружаем простые задачи
print("\n📥 Загрузка простых задач из data/simple_problems.jsonl...")
simple_problems = []

if not os.path.exists("data/simple_problems.jsonl"):
    print("❌ Файл data/simple_problems.jsonl не найден!")
    print("Запустите сначала scripts/import_simple_problems.py")
    sys.exit(1)

with open("data/simple_problems.jsonl", 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                problem = json.loads(line)
                simple_problems.append(problem)
            except:
                pass

print(f"✓ Загружено: {len(simple_problems)} простых задач")

# Объединяем
print("\n🔄 Объединение баз...")
all_problems = olympiad_problems + simple_problems

# Переназначаем ID
for i, problem in enumerate(all_problems, 1):
    problem['id'] = i

print(f"✓ Всего задач: {len(all_problems)}")

# Статистика
from collections import Counter

print("\n📊 Статистика по уровням сложности:")
diff_dist = Counter(p['difficulty'] for p in all_problems)
for level in range(1, 11):
    count = diff_dist.get(level, 0)
    status = "✓" if count > 0 else "✗"
    print(f"  Уровень {level}: {count} задач {status}")

print("\n📊 Статистика по разделам:")
subject_dist = Counter(p['subject'] for p in all_problems)
for subj, count in subject_dist.most_common():
    print(f"  {subj}: {count} задач")

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_merge.bak")
print("✓ Бэкап: problems.py.before_merge.bak")

# Сохраняем объединенную базу
print("\n💾 Сохранение объединенной базы в problems.py...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# Объединенная база задач — {len(all_problems)} задач\n")
    f.write("# Уровни 1-6: Простые школьные задачи\n")
    f.write("# Уровень 10: Олимпиадные задачи\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(all_problems, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

# Верификация
print("\n🔍 Верификация...")
import importlib.util
spec = importlib.util.spec_from_file_location("problems_test", "problems.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(f"✓ Успешно загружено {len(module.PROBLEMS_DB)} задач из нового файла")

print("\n" + "="*70)
print("✅ ОБЪЕДИНЕНИЕ ЗАВЕРШЕНО!")
print("="*70)
print(f"\nИтоговая база:")
print(f"  Всего задач: {len(all_problems)}")
print(f"  Уровни 1-6: {sum(diff_dist.get(i, 0) for i in range(1, 7))} задач (простые)")
print(f"  Уровни 7-9: {sum(diff_dist.get(i, 0) for i in range(7, 10))} задач")
print(f"  Уровень 10: {diff_dist.get(10, 0)} задач (олимпиадные)")
print(f"\nСледующий шаг: Перезапустите Flask приложение")
print("  python app.py")
