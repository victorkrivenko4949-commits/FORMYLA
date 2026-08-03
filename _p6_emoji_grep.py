import re, glob, os

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')

pattern = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2700-\u27BF]')
targets = glob.glob('templates/**/*.html', recursive=True) + glob.glob('static/**/*.*', recursive=True) + glob.glob('**/*.py', recursive=True)
hits = []

for path in targets:
    normalized = path.replace('\\', '/')
    if 'group_chats' in normalized or '.env' in normalized:
        continue
    if '.pyc' in path or '__pycache__' in path or '.git' in path:
        continue
    try:
        text = open(path, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        m = pattern.search(line)
        if m:
            emoji_set = set(pattern.findall(line))
            emoji_hex = ','.join(hex(ord(c)) for c in emoji_set)
            hits.append((path, i, line.strip()[:160], emoji_hex))

tpl_hits = [h for h in hits if 'templates' in h[0].replace('\\', '/')]
static_hits = [h for h in hits if 'static' in h[0].replace('\\', '/')]
py_hits = [h for h in hits if h[0].endswith('.py')]

all_codes = set()
for h in hits:
    for c in h[3].split(','):
        if c:
            all_codes.add(c)

lines = []
lines.append(f'=== TOTAL EMOJI HITS: {len(hits)} ===')
lines.append(f'TEMPLATES: {len(tpl_hits)}')
lines.append(f'STATIC: {len(static_hits)}')
lines.append(f'PY FILES: {len(py_hits)}')
lines.append('')
lines.append('--- TEMPLATES ---')
for h in tpl_hits:
    lines.append(f'{h[0]}:{h[1]}: {h[2]}')
lines.append('')
lines.append('--- STATIC ---')
for h in static_hits:
    lines.append(f'{h[0]}:{h[1]}: {h[2]}')
lines.append('')
lines.append('--- PY FILES ---')
for h in py_hits:
    lines.append(f'{h[0]}:{h[1]}: {h[2]}')
lines.append('')
lines.append(f'--- UNIQUE EMOJI CODEPOINTS: {len(all_codes)} ---')
for c in sorted(all_codes):
    lines.append(c)

with open('_recon/p6_emoji_before.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'Done. Total: {len(hits)} hits, Templates: {len(tpl_hits)}, Static: {len(static_hits)}, Py: {len(py_hits)}')
print(f'Unique codepoints: {len(all_codes)}')
