# -*- coding: utf-8 -*-
"""
Миграция задач на новую структуру подтем
Старые подтемы → Новые английские ключи
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

# Маппинг старых подтем на новые ключи
SUBTOPIC_MAPPING = {
    # Алгебра
    "Уравнения": "equations",
    "Системы уравнений": "equations",
    "Неравенства": "inequalities",
    "Последовательности": "other_algebra",
    "Функции": "other_algebra",
    "Текстовые задачи": "text_problems",
    "Разное": "other_algebra",  # Для алгебры
    
    # Геометрия
    "Треугольники": "triangles",
    "Окружности": "circles",
    "Площади": "basics",
    "Четырёхугольники": "basics",
    "Координатная геометрия": "other_geometry",
    
    # Комбинаторика
    "Подсчёт и перебор": "dirichlet_and_graphs",
    "Принцип Дирихле": "dirichlet_and_graphs",
    "Графы и раскраски": "dirichlet_and_graphs",
    "Игры и стратегии": "games",
    
    # Теория чисел
    "Делимость": "divisibility",
    "Остатки": "divisibility",
    "Простые числа": "primes_and_equations",
    "Диофантовы уравнения": "primes_and_equations",
    
    # Движение
    "Равномерное движение": "movement_all",
    "Движение навстречу и вдогонку": "movement_all",
    "Движение по воде и эскалаторы": "movement_all",
    
    # Рыцари и лжецы
    "Классические задачи": "logic_all",
    "Задачи с условиями": "logic_all",
    "Задачи на острове": "logic_all",
}

# Маппинг для "Разное" в зависимости от раздела
RAZNOYE_MAPPING = {
    "algebra": "other_algebra",
    "geometry": "other_geometry",
    "combinatorics": "other_combinatorics",
    "number_theory": "other_number_theory",
    "movement": "movement_all",
    "knights_liars": "logic_all",
    "other": "other_algebra"
}

print("="*70)
print("Миграция задач на новую структуру подтем")
print("="*70)

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_new_structure.bak")
print("✓ Бэкап: problems.py.before_new_structure.bak")

# Мигрируем подтемы
print("\n🔄 Миграция подтем...")
migrated_count = 0
unmapped_count = 0

for problem in PROBLEMS_DB:
    old_subtopic = problem.get('subtopic', 'Разное')
    subject = problem.get('subject', 'other')
    
    # Пробуем найти в маппинге
    if old_subtopic in SUBTOPIC_MAPPING:
        new_subtopic = SUBTOPIC_MAPPING[old_subtopic]
        problem['subtopic'] = new_subtopic
        migrated_count += 1
    elif old_subtopic == "Разное":
        # Для "Разное" используем маппинг по разделу
        new_subtopic = RAZNOYE_MAPPING.get(subject, "other_algebra")
        problem['subtopic'] = new_subtopic
        migrated_count += 1
    else:
        # Неизвестная подтема - отправляем в "other"
        new_subtopic = RAZNOYE_MAPPING.get(subject, "other_algebra")
        problem['subtopic'] = new_subtopic
        unmapped_count += 1

print(f"✓ Мигрировано: {migrated_count} задач")
if unmapped_count > 0:
    print(f"⚠️  Неизвестных подтем: {unmapped_count} (отправлены в 'other')")

# Статистика
from collections import Counter
new_subtopics = Counter(p['subtopic'] for p in PROBLEMS_DB)

print("\n📊 Новое распределение по подтемам:")
for subtopic, count in new_subtopics.most_common():
    print(f"  {subtopic}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# Новая структура подтем с английскими ключами\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ МИГРАЦИЯ ЗАВЕРШЕНА!")
print("="*70)
print(f"\nВсе {len(PROBLEMS_DB)} задач мигрированы на новую структуру")
print("Перезапустите Flask приложение!")
