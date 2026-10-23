import re, glob, os
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
pattern = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2700-\u27BF]')

REPLACE_MAP = {}
for cp in range(0x1F300, 0x1FAFF + 1): REPLACE_MAP[chr(cp)] = ''
for cp in range(0x2600, 0x2700): REPLACE_MAP[chr(cp)] = ''
for cp in range(0x2700, 0x27C0): REPLACE_MAP[chr(cp)] = ''
for cp in range(0x2190, 0x21FF + 1): REPLACE_MAP[chr(cp)] = ''

svg_files = glob.glob('static/**/*.svg', recursive=True)
for f in svg_files:
    try:
        with open(f, 'r', encoding='utf-8', errors='strict') as fh:
            original = fh.read()
    except UnicodeDecodeError:
        continue
    except Exception:
        continue
    if not pattern.search(original):
        continue
    # Find matching lines
    for i, line in enumerate(original.splitlines(), 1):
        if pattern.search(line):
            codes = [hex(ord(c)) for c in pattern.findall(line)]
            print(f'{f}:{i}: CODES={codes}')
    cleaned = original
    for ch_old, ch_new in REPLACE_MAP.items():
        cleaned = cleaned.replace(ch_old, ch_new)
    if cleaned != original:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(cleaned)
        print(f'  -> CLEANED')
