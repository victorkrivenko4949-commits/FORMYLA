import sys, json
sys.stdout.reconfigure(encoding='utf-8')

# Load canonical taxonomy
with open('canonical_taxonomy.json', 'r', encoding='utf-8') as f:
    canon = json.load(f)

# What levels exist?
levels = set()
grades = set()
themes = {}
for ck, info in canon.items():
    g = info.get('grade')
    l = info.get('level')
    t = info.get('theme_name')
    levels.add(l)
    grades.add(g)
    key = (g, l, t)
    themes[key] = themes.get(key, 0) + 1

print('=== Canonical Taxonomy Summary ===')
print(f'Total cells: {len(canon)}')
print(f'Grades: {sorted(grades)}')
print(f'Levels: {sorted(levels)}')
print()
print('=== All (grade, level, theme_name) combos ===')
for key in sorted(themes.keys(), key=lambda x: (int(x[0]) if x[0] else 0, x[1], x[2])):
    print(f'  G{key[0]}, L{key[1]}, "{key[2]}" ({themes[key]} cells)')
print()
print('=== Grade 5 topics ===')
for key in sorted(themes.keys(), key=lambda x: (x[1], x[2])):
    if key[0] == 5:
        print(f'  L{key[1]}, "{key[2]}"')
