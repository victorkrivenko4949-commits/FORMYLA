import os
import re
import sys
sys.path.insert(0, ".")
from olympiads import OLYMPIADS_DB

FOLDER = "static/images/problems/"

# Маппинг префиксов в ключи olympiad из OLYMPIADS_DB
OLYMPIAD_KEYS = {
    "fu": ["Формула Единства", "formula_unity", "fu"],
    "vsosh": ["ВсОШ", "vsosh", "vsesib", "vseros"],
    "vysshaya_proba": ["Высшая проба", "vysshaya_proba", "vyshaya_proba"],
}

IMAGE_MAP = {}
mapped, skipped = 0, 0

for filename in os.listdir(FOLDER):
    if not filename.lower().endswith((".jpg", ".png")) or "копия" in filename:
        continue
        
    # Парсим: fu_2024_g5_fig1.jpg
    match = re.match(r"([a-z_]+)_(\d{4})_g(\d+)_v?fig(\d+)", filename.replace(".jpeg", ".jpg"))
    if not match:
        print(f"Не понял имя: {filename}")
        skipped += 1
        continue
        
    prefix, year_str, grade_str, num_str = match.groups()
    year, grade, num = int(year_str), int(grade_str), int(num_str)
    
    # Ищем олимпиаду
    target_names = OLYMPIAD_KEYS.get(prefix)
    if not target_names:
        # Пытаемся угадать по префиксу
        target_names = [prefix]
        
    # Ищем в базе
    combo_id = None
    for combo in OLYMPIADS_DB:
        c_year = combo.get("year")
        c_grade = combo.get("grade")
        c_olympiad = combo.get("olympiad", "").lower()
        
        # Проверяем год и класс (класс может быть int или str типа "5-6")
        if c_year != year: continue
        
        grade_match = False
        if str(c_grade) == str(grade): grade_match = True
        elif isinstance(c_grade, str) and "-" in c_grade:
            try:
                g_min, g_max = map(int, c_grade.split("-"))
                if g_min <= grade <= g_max: grade_match = True
            except: pass
            
        if not grade_match: continue
        
        # Проверяем название олимпиады
        if any(name.lower() in c_olympiad for name in target_names):
            combo_id = combo.get("id")
            break
            
    if combo_id:
        IMAGE_MAP[f"{combo_id}_{num}"] = f"/static/images/problems/{filename}"
        mapped += 1
    else:
        print(f"Не найдена задача: {prefix} {year} {grade} класс")
        skipped += 1

# Сохраняем в problem_images.py
with open("problem_images.py", "w", encoding="utf-8") as f:
    f.write("IMAGE_MAP = {\n")
    for key, path in sorted(IMAGE_MAP.items()):
        f.write(f'    "{key}": "{path}",\n')
    f.write("}\n")

print(f"ГОТОВО. Привязано: {mapped}, Пропущено: {skipped}")
