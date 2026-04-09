import sys
sys.path.insert(0, ".")
from olympiads import OLYMPIADS_DB
from problem_images import IMAGE_MAP

# Ищем ту самую задачу про числа 2020 и 2021
target_combo = None
target_problem = None

for combo in OLYMPIADS_DB:
    for p in combo.get("problems", []):
        if "2020 число 2021" in p.get("text", "") or "Теслер" in p.get("text", ""):
            target_combo = combo
            target_problem = p
            break
    if target_combo:
        break

if target_combo and target_problem:
    print(f"НАЙДЕНА ЗАДАЧА:")
    print(f"Олимпиада: {target_combo.get('olympiad')} {target_combo.get('year')} {target_combo.get('grade')} класс")
    print(f"ID пробника: {target_combo.get('id')}")
    print(f"Номер задачи (num): {target_problem.get('num')}")
    
    # Смотрим, какая картинка к ней привязалась
    key = f"{target_combo.get('id')}_{target_problem.get('num')}"
    print(f"Привязанная картинка: {IMAGE_MAP.get(key, 'НЕТ КАРТИНКИ')}")
    
    # Смотрим все картинки для этого пробника
    print("\nВСЕ КАРТИНКИ ЭТОГО ПРОБНИКА:")
    for k, v in IMAGE_MAP.items():
        if k.startswith(f"{target_combo.get('id')}_"):
            print(f"  Ключ {k} -> {v}")
else:
    print("Задача не найдена в базе!")
