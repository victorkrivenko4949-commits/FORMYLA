"""Fix: move ?v={{ asset_version }} from inside url_for }} to outside."""
import re, glob

def fix_wrong_placement(line):
    """Fix:  url_for(...) ?v={{ asset_version }}}}  ->  url_for(...) }}?v={{ asset_version }}"""
    # Pattern:  filename='xxx.js') ?v={{ asset_version }}}}
    # or:       filename='xxx.css') ?v={{ asset_version }}}}
    # The ?v= got inserted before }} instead of after
    return re.sub(
        r"(filename='[^']+\.(?:css|js)')\s*\)\s*\?v=\{\{\s*asset_version\s*\}\}\}\}",
        r"\1) }}?v={{ asset_version }}",
        line
    )

def fix_also_support_inbox(line):
    return re.sub(
        r'(filename="[^"]+\.(?:css|js)")\s*\)\s*\?v=\{\{\s*asset_version\s*\}\}\}\}',
        r'\1) }}?v={{ asset_version }}',
        line
    )

fixed_files = []
for path in sorted(glob.glob('templates/**/*.html', recursive=True)):
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    content = original
    content = fix_wrong_placement(content)
    content = fix_also_support_inbox(content)
    
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        fixed_files.append(path)
        print(f'FIXED: {path}')

print(f'\nTotal: {len(fixed_files)}')
