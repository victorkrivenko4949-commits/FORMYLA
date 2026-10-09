import sys
sys.stdout.reconfigure(encoding='utf-8')
from services.theme_registry import all_themes, themes_of_grade
themes = all_themes()
print('всего theme_id в реестре:', len(themes))
for g in range(5, 12):
    print(f'  {g} класс:', len(themes_of_grade(g)), 'тем')
print()
print('примеры theme_id:', [t[0] for t in themes[:10]])
