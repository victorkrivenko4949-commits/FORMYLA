"""One-shot fix: add ?v={{ asset_version }} to all static css/js links missing it."""
import re, glob

EXCLUDE_PATHS = {'.png', '.ico', 'favicon', 'apple-touch-icon'}

def should_skip(line):
    for ex in EXCLUDE_PATHS:
        if ex in line.lower():
            return True
    return False

def fix_static_link(line):
    """If line has url_for('static' pointing to .css or .js without ?v=, add it."""
    if "url_for('static'" not in line and 'url_for("static"' not in line:
        return line
    if '?v=' in line:
        return line
    if not any(ext in line for ext in ['.css', '.js']):
        return line
    if should_skip(line):
        return line
    
    # Pattern:  }}  or  }}defer or  }}>
    # Insert ?v={{ asset_version }} before the closing braces
    # Match the }} that closes url_for
    # Look for: filename='xxx.css' OR filename='xxx.js' followed by whitespace and }}
    
    # Simpler: find the url_for closing }} and insert before it
    # But the line might have more after: }}
    # We need to find the specific }} that closes url_for
    
    # Strategy: find the }} that comes after url_for('static'... and before the end of the tag
    idx = line.find("url_for('static'")
    if idx == -1:
        idx = line.find('url_for("static"')
    if idx == -1:
        return line
    
    # Find the matching }} after this
    rest = line[idx:]
    close_idx = rest.find('}}')
    if close_idx == -1:
        return line
    
    # Insert ?v={{ asset_version }} before }}
    before = line[:idx + close_idx]
    after = line[idx + close_idx:]
    return before + '?v={{ asset_version }}' + after

fixed_files = []

for path in sorted(glob.glob('templates/**/*.html', recursive=True)):
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    lines = original.split('\n')
    new_lines = [fix_static_link(line) for line in lines]
    new_content = '\n'.join(new_lines)
    
    if new_content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        fixed_files.append(path)
        print(f'FIXED: {path}')

print(f'\nTotal files fixed: {len(fixed_files)}')
if not fixed_files:
    print('(no files needed fixing)')
