import sys
import json
import copy

sys.path.insert(0, ".")

try:
    from olympiads_backup_before_rebuild import OLYMPIADS_DB as RAW_DB
except ImportError:
    try:
        from olympiads import OLYMPIADS_DB as RAW_DB
    except ImportError:
        print("Ошибка: Не найден файл с базой олимпиад")
        sys.exit(1)

print(f"Загружено {len(RAW_DB)} исходных пробников.")

# Ключевые слова, указывающие на наличие картинки
IMG_KEYWORDS = ["рис.", "на рисунке", "схем", "чертеж", "таблиц", "ниже", "справа", "изображен"]

# Шаг 1: Извлекаем все "чистые" задачи
clean_tasks_pool = {}

for combo in RAW_DB:
    c_olympiad = combo.get('olympiad', 'unknown')
    c_olympiad_title = combo.get('olympiad_title', 'Неизвестная олимпиада')
    c_year = combo.get('year', 2023)
    c_round = combo.get('round', 'unknown')
    c_round_title = combo.get('round_title', 'Неизвестный этап')
    c_grade = combo.get('grade', 0)
    
    if not c_grade:
        continue
        
    key = (c_olympiad, c_olympiad_title, c_year, c_round, c_round_title, c_grade)
    
    if key not in clean_tasks_pool:
        clean_tasks_pool[key] = []
        
    for p in combo.get('problems', []):
        text = p.get('text', '').lower()
        if not any(kw in text for kw in IMG_KEYWORDS):
            clean_tasks_pool[key].append(p)

print("Задачи отфильтрованы от картинок.")

# Шаг 2: Формируем новые пробники по 5 задач
NEW_DB = []
probnik_id = 1

for key, tasks in clean_tasks_pool.items():
    c_olympiad, c_olympiad_title, c_year, c_round, c_round_title, c_grade = key
    
    for i in range(0, len(tasks), 5):
        chunk = tasks[i:i+5]
        
        if len(chunk) == 5:
            for j, task in enumerate(chunk):
                task['num'] = j + 1
                
            NEW_DB.append({
                "id": probnik_id,
                "olympiad": c_olympiad,
                "olympiad_title": c_olympiad_title,
                "year": c_year,
                "grade": c_grade,
                "round": c_round,
                "round_title": c_round_title,
                "problems": copy.deepcopy(chunk)
            })
            probnik_id += 1

# Шаг 3: Сохраняем
with open("olympiads.py", "w", encoding="utf-8") as f:
    f.write("# Локальная очищенная база (по 5 задач без картинок)\n")
    f.write("OLYMPIADS_DB = [\n")
    for combo in NEW_DB:
        f.write("    {\n")
        f.write(f'        "id": {combo["id"]},\n')
        f.write(f'        "olympiad": "{combo["olympiad"]}",\n')
        f.write(f'        "olympiad_title": "{combo["olympiad_title"]}",\n')
        f.write(f'        "year": {combo["year"]},\n')
        f.write(f'        "grade": {combo["grade"]},\n')
        f.write(f'        "round": "{combo["round"]}",\n')
        f.write(f'        "round_title": "{combo["round_title"]}",\n')
        f.write('        "problems": [\n')
        for idx, p in enumerate(combo["problems"]):
            f.write("            {\n")
            f.write(f'                "num": {p["num"]},\n')
            text_escaped = p["text"].replace('"', '\\"').replace('\n', '\\n')
            f.write(f'                "text": "{text_escaped}",\n')
            answer_escaped = str(p.get("answer", "")).replace('"', '\\"').replace('\n', '\\n')
            f.write(f'                "answer": "{answer_escaped}",\n')
            solution_escaped = str(p.get("solution", "")).replace('"', '\\"').replace('\n', '\\n')
            f.write(f'                "solution": "{solution_escaped}"\n')
            if idx < len(combo["problems"]) - 1:
                f.write("            },\n")
            else:
                f.write("            }\n")
        f.write('        ]\n')
        if combo["id"] < len(NEW_DB):
            f.write("    },\n")
        else:
            f.write("    }\n")
    f.write("]\n")

print(f"\nГОТОВО! Создана база: {len(NEW_DB)} пробников (по 5 задач).")
print("Перезапустите Flask-сервер!")
