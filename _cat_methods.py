import json, sys
with open(r'c:\Users\Redmi\Desktop\Новая папка (2)\data\olympiads\methods_catalog_105.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
sys.stdout.reconfigure(encoding='utf-8')
for i, item in enumerate(data):
    code = item.get('method_code', 'N/A')
    name = item.get('method_name', 'N/A')
    section = item.get('section', 'N/A')
    grades = item.get('grades', [])
    grades_str = ', '.join(str(g) for g in grades) if grades else 'N/A'
    comps = item.get('recommended_competitions', [])
    tags_str = ', '.join(comps) if comps else 'N/A'
    print(f'{code} — {name} — {section} — {grades_str} — {tags_str}')
