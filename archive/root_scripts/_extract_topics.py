import json

with open('adaptive_data/adaptive_full_9120_fixed.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sections = {}
for t in data:
    sec = t.get('section', '')
    sections[sec] = sections.get(sec, 0) + 1

lines = [f'Всего уникальных подтем (sections): {len(sections)}\n']
for i, (sec, cnt) in enumerate(sorted(sections.items(), key=lambda x: x[0]), 1):
    lines.append(f'{i:3d}. [{sec}] — {cnt} задач')

with open('topics_out.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'OK: {len(lines)} lines written, {len(sections)} unique sections')
