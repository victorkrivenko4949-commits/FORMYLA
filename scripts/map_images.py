import os
import re
import sys

sys.path.insert(0, ".")
from problems import PROBLEMS_DB as problems

FOLDER = "static/temp_unpack/images_package/static/images/problems"

# Маппинг префиксов файлов к названиям олимпиад в problems.py
OLYMPIAD_MAP = {
    "fu": ["Формула Единства", "формула единства", "Formulo de Integreco"],
    "vsosh": ["ВсОШ", "Всероссийская", "всош", "Всероссийская олимпиада"],
    "vysshaya_proba": ["Высшая проба", "высшая проба", "Олимпиада Высшая проба"],
    "kurchatov": ["Курчатов", "Курчатовская", "курчатов"],
    "euler": ["Эйлер", "Олимпиада Эйлера"],
}

def parse_filename(filename):
    """Парсит имя файла и возвращает (olympiad_key, year, grade, problem_num) или None"""
    name = os.path.splitext(filename)[0]
    
    # Определяем олимпиаду
    olympiad_key = None
    rest = name
    for key in sorted(OLYMPIAD_MAP.keys(), key=len, reverse=True):
        if name.startswith(key + "_"):
            olympiad_key = key
            rest = name[len(key) + 1:]
            break
    
    if not olympiad_key:
        return None
    
    # Парсим год: 4 цифры
    year_match = re.match(r"(\d{4})_", rest)
    if not year_match:
        return None
    year = int(year_match.group(1))
    rest = rest[len(year_match.group(0)):]
    
    # Парсим класс: g + число
    grade_match = re.match(r"g(\d+)_", rest)
    if not grade_match:
        return None
    grade = int(grade_match.group(1))
    rest = rest[len(grade_match.group(0)):]
    
    # Парсим номер задачи: fig1, vfig2, fig1-5 (где 5 — глобальный номер)
    fig_match = re.match(r"v?fig(\d+)(?:-(\d+))?$", rest)
    if not fig_match:
        return None
    problem_num = int(fig_match.group(1))
    
    return (olympiad_key, year, grade, problem_num)

def find_problem(olympiad_key, year, grade, problem_num):
    """Ищет задачу в problems.py по параметрам"""
    names = OLYMPIAD_MAP.get(olympiad_key, [])
    
    candidates = []
    for p in problems:
        p_year = p.get("year")
        p_grade = p.get("grade")
        p_olympiad = p.get("olympiad", "")
        p_number = p.get("problem_number") or p.get("number")
        
        # Проверяем год
        if p_year != year:
            continue
        
        # Проверяем класс — может быть число или строка "5", "5-6" и т.д.
        grade_str = str(p_grade) if p_grade else ""
        grade_match = False
        if str(grade) == grade_str:
            grade_match = True
        elif "-" in grade_str:
            parts = grade_str.split("-")
            try:
                if int(parts[0]) <= grade <= int(parts[1]):
                    grade_match = True
            except:
                pass
        
        if not grade_match:
            continue
        
        # Проверяем олимпиаду
        olympiad_match = False
        for name in names:
            if name.lower() in p_olympiad.lower():
                olympiad_match = True
                break
        
        if not olympiad_match:
            continue
        
        # Проверяем номер задачи
        if p_number is not None:
            try:
                if int(p_number) == problem_num:
                    candidates.append(p)
            except:
                pass
    
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        print(f"  WARN: найдено {len(candidates)} кандидатов, пропускаю")
        return None
    return None

# Основной цикл
IMAGE_MAP = {}
mapped = 0
skipped = 0
errors = []

files = sorted(os.listdir(FOLDER))
print(f"Всего файлов в папке: {len(files)}\n")

for filename in files:
    if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        continue
    
    parsed = parse_filename(filename)
    if not parsed:
        print(f"SKIP {filename} — не удалось распарсить имя")
        skipped += 1
        continue
    
    olympiad_key, year, grade, problem_num = parsed
    print(f"PARSE {filename} -> {olympiad_key}, {year}, {grade} класс, задача {problem_num}")
    
    problem = find_problem(olympiad_key, year, grade, problem_num)
    if problem:
        pid = problem.get("id") or problem.get("problem_id")
        if pid:
            path = f"/static/temp_unpack/images_package/static/images/problems/{filename}"
            IMAGE_MAP[pid] = path
            mapped += 1
            print(f"  -> привязано к ID: {pid}")
        else:
            print(f"  WARN: задача найдена но нет ID")
            skipped += 1
    else:
        print(f"  NOT FOUND в problems.py")
        skipped += 1

# Записываем в problem_images.py
with open("problem_images.py", "w", encoding="utf-8") as f:
    f.write("# Автоматически сгенерированный маппинг картинок к задачам\n")
    f.write("# Формат: problem_id -> путь к картинке\n\n")
    f.write("IMAGE_MAP = {\n")
    for pid, path in sorted(IMAGE_MAP.items()):
        f.write(f'    "{pid}": "{path}",\n')
    f.write("}\n")

print(f"\n{'='*50}")
print(f"ИТОГО:")
print(f"  Привязано: {mapped}")
print(f"  Пропущено: {skipped}")
print(f"  Записано в problem_images.py")
