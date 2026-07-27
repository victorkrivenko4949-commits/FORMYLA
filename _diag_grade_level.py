import json
with open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8') as f:
    bank = json.load(f)
print(f'Total bank: {len(bank)}')
# L1-L3 count
l13 = [t for t in bank if str(t.get('level','')) in ('1','2','3')]
print(f'L1-L3 tasks: {len(l13)}')
# Grade|Level distribution for L1-L3
grades = {}
for t in l13:
    g = t.get('grade','?')
    l = t.get('level','?')
    key = f'G{g}|L{l}'
    grades[key] = grades.get(key,0)+1
print(f'\nGrade|Level cells (L1-L3): {len(grades)}')
for k in sorted(grades.keys()):
    print(f'  {k}: {grades[k]}')
# Target matrix grades
target = ['G2','G5','G6','G7','G8','G9','G10','G11']
in_matrix = 0
outside = 0
for t in l13:
    g = str(t.get('grade','?'))
    if f'G{g}' in target:
        in_matrix += 1
    else:
        outside += 1
print(f'\nIn target matrix: {in_matrix}')
print(f'Outside matrix: {outside}')
print(f'L4-L5 tasks: {len(bank)-len(l13)}')
