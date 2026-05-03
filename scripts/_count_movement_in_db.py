#!/usr/bin/env python3
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('data/adaptive_full_db.json', 'r', encoding='utf-8'))

mvt_re = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|из\s+пункта|выехал|'
    r'расстояни\w+\s+между|по\s+течени|против\s+течени|'
    r'велосипедист|пешеход|катер|лодк|поезд',
    re.IGNORECASE
)

print("Movement tasks in adaptive_full_db.json (1+ keyword match):")
by_grade = {}
examples = []
for t in data:
    text = t.get('question', '')
    matches = mvt_re.findall(text)
    if len(matches) >= 1:
        g = int(t.get('grade', 0))
        by_grade[g] = by_grade.get(g, 0) + 1
        if len(examples) < 5:
            examples.append((g, t.get('topic',''), text[:120]))

total = sum(by_grade.values())
for g in sorted(by_grade.keys()):
    print(f"  Grade {g}: {by_grade[g]}")
print(f"  Total: {total}")

print("\nExamples:")
for g, tp, txt in examples:
    print(f"  Grade {g}, topic='{tp}':")
    print(f"    {txt}")
    print()
