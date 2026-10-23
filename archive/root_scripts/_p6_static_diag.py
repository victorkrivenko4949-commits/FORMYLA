import re, glob, os
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
pattern = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2700-\u27BF]')
targets = glob.glob('static/**/*.*', recursive=True)
has_hits = {}
no_hits_exts = set()
for path in targets:
    ext = os.path.splitext(path)[1].lower()
    try:
        text = open(path, encoding='utf-8', errors='ignore').read()
    except:
        continue
    if pattern.search(text):
        has_hits[ext] = has_hits.get(ext, 0) + 1
    else:
        no_hits_exts.add(ext)
with open('_recon/p6_static_remaining.txt', 'w', encoding='utf-8') as f:
    f.write('Extensions with remaining emoji hits:\n')
    for ext, cnt in sorted(has_hits.items(), key=lambda x: -x[1]):
        f.write(f'  {ext}: {cnt}\n')
    f.write('\nExtensions without hits:\n')
    for ext in sorted(no_hits_exts):
        f.write(f'  {ext}\n')
print('Written to _recon/p6_static_remaining.txt')
