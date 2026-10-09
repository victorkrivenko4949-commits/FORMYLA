"""Извлекаем 135 тем из актуального taxonomy_by_grade.json (корневой)."""
import json

with open('taxonomy_by_grade.json', 'r', encoding='utf-8') as f:
    root = json.load(f)

grades_data = root['grades']

# Собираем темы
grade_themes = {}
theme_defs = {}
section_map = {}
theme_id_counter = {}
all_themes = []

for grade_key, grade_info in sorted(grades_data.items()):
    grade_num = int(grade_key.replace('grade_', ''))
    themes = grade_info.get('themes', [])
    grade_list = []
    for t in themes:
        tid = t.get('id', '')
        tname = t.get('name', '')
        section = t.get('section', '')
        desc = t.get('description', '')
        grade_list.append({
            'theme_id': tid,
            'theme': tname,
            'section': section,
            'description': desc
        })
        if tid and tname:
            theme_defs[tid] = {
                'name': tname,
                'section': section,
                'grade': grade_num,
                'description': desc
            }
        if section and section not in section_map:
            section_map[section] = []
        if tid and section:
            if tid not in section_map.get(section, []):
                section_map.setdefault(section, []).append(tid)
    grade_themes[grade_num] = grade_list
    all_themes.extend(grade_list)

print(f"Всего тем: {len(all_themes)}")
for g in sorted(grade_themes.keys()):
    print(f"  {g} класс: {len(grade_themes[g])} тем")

# Сохраняем для конвейера
output = {
    "meta": {
        "total_themes": len(all_themes),
        "grades": list(grade_themes.keys()),
        "total_cells": len(all_themes) * 3
    },
    "grade_themes": {str(k): v for k, v in grade_themes.items()},
    "theme_definitions": theme_defs,
    "sections": section_map
}

with open('l1_l3_generation/taxonomy_by_grade.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nСохранено: l1_l3_generation/taxonomy_by_grade.json")
print(f"  Ожидаемых ячеек L1-L3: {len(all_themes) * 3}")
