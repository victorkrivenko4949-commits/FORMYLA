import json
from collections import defaultdict

tasks = []
with open('FORMYLA_L1_L5_TOP5.jsonl', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            tasks.append(json.loads(line))

print(f'Total tasks: {len(tasks)}')

# Sections per grade
sg = defaultdict(set)
for t in tasks:
    sg[t['grade']].add(t['section'])

for g in sorted(sg):
    print(f'Grade {g}: {len(sg[g])} sections: {sorted(sg[g])}')

print()

# Themes per section (grade 5 example)
st = defaultdict(lambda: defaultdict(int))
for t in tasks:
    if t['grade'] == 5:
        st[t['section']][t['theme']] += 1

for s in sorted(st):
    print(f'  Section [{s}]: {len(st[s])} themes, {sum(st[s].values())} tasks')
    for th, cnt in sorted(st[s].items(), key=lambda x: -x[1])[:5]:
        print(f'    - {th}: {cnt} tasks')

print()
print('Tasks per grade:')
for g in sorted(set(t['grade'] for t in tasks)):
    print(f'  Grade {g}: {sum(1 for t in tasks if t["grade"]==g)}')

print()
print('Tasks per level:')
for lvl in sorted(set(t['level'] for t in tasks)):
    print(f'  L{lvl}: {sum(1 for t in tasks if t["level"]==lvl)}')
