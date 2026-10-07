import re, glob, os
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')

pattern = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2700-\u27BF]')

# Only text files: html, js, css, py, svg, json, txt, md
TEXT_EXTS = {'.html', '.js', '.css', '.py', '.svg', '.json', '.txt', '.md', '.yml', '.yaml', '.cfg', '.ini', '.toml'}

targets = []
for pattern_glob in ['templates/**/*.*', 'static/**/*.*', '**/*.py']:
    for f in glob.glob(pattern_glob, recursive=True):
        ext = os.path.splitext(f)[1].lower()
        if ext in TEXT_EXTS:
            targets.append(f)

targets = sorted(set(targets))
hits = []

for path in targets:
    normalized = path.replace('\\', '/')
    if 'group_chats' in normalized or '.env' in normalized or '/.git/' in normalized:
        continue
    if '.pyc' in path or '__pycache__' in path:
        continue
    try:
        with open(path, encoding='utf-8', errors='ignore') as fh:
            text = fh.read()
    except Exception:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            hits.append((path, i, line.strip()[:160]))

tpl_hits = [h for h in hits if 'templates' in h[0].replace('\\', '/')]
static_hits = [h for h in hits if 'static' in h[0].replace('\\', '/')]
py_hits = [h for h in hits if h[0].endswith('.py')]

print(f'TOTAL: {len(hits)}')
print(f'TEMPLATES: {len(tpl_hits)}')
print(f'STATIC: {len(static_hits)}')
print(f'PY: {len(py_hits)}')

if len(hits) <= 50:
    for h in hits:
        print(h)

with open('_recon/p6_emoji_after.txt', 'w', encoding='utf-8') as f:
    f.write(f'TOTAL: {len(hits)}\n')
    f.write(f'TEMPLATES: {len(tpl_hits)}\n')
    f.write(f'STATIC: {len(static_hits)}\n')
    f.write(f'PY: {len(py_hits)}\n\n')
    for h in hits:
        f.write(f'{h[0]}:{h[1]}: {h[2]}\n')
