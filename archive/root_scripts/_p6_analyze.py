import os
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')

hits_by_file = {}
with open('_recon/p6_emoji_before.txt', encoding='utf-8') as f:
    for line in f:
        if ':' not in line or line.startswith('===') or line.startswith('TEMPLATES') or line.startswith('STATIC') or line.startswith('PY') or line.startswith('---') or line.startswith('0x'):
            continue
        parts = line.split(':', 1)
        if len(parts) >= 1:
            fname = parts[0]
            hits_by_file[fname] = hits_by_file.get(fname, 0) + 1

for fname, cnt in sorted(hits_by_file.items(), key=lambda x: -x[1])[:40]:
    print(f'{cnt:4d} {fname}')
print(f'\nTotal unique files: {len(hits_by_file)}')
