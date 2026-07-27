# -*- coding: utf-8 -*-
"""Deep investigation of Jinja template caching issue."""
import os, hashlib, sys

os.environ['PYTHONIOENCODING'] = 'utf-8'

# 1. Read the file directly multiple times to rule out OS caching
print("=" * 60)
print("1. READING FILE DIRECTLY (multiple times)")
for i in range(3):
    with open('templates/prep/coach.html', 'rb') as f:
        data = f.read()
    md5 = hashlib.md5(data).hexdigest()
    print(f"   Read #{i+1}: {len(data)} bytes, MD5: {md5}")

print()

# 2. Compare with Jinja2 FileSystemLoader
print("2. JINJA2 FileSystemLoader.get_source()")
from jinja2 import FileSystemLoader, Environment
loader = FileSystemLoader('templates')

# Fresh environment
env = Environment(loader=loader)

# Get source directly from loader
source, fname, uptodate = loader.get_source(env, 'prep/coach.html')
source_bytes = source.encode('utf-8')
source_md5 = hashlib.md5(source_bytes).hexdigest()
print(f"   Loader returned: {len(source_bytes)} bytes, MD5: {source_md5}")
print(f"   Template file: {fname}")

# Check uptodate function
is_uptodate = uptodate()
print(f"   uptodate() returns: {is_uptodate}")

# Check what Jinja's cache has
print(f"   Jinja2 env.cache type: {type(env.cache).__name__}")

# Get compiled template
tmpl = env.get_template('prep/coach.html')
print(f"   Template object: {type(tmpl).__name__}")
print(f"   Template filename: {tmpl.filename}")
if hasattr(tmpl, 'module'):
    print(f"   Module loaded from: {getattr(tmpl.module, '__file__', 'N/A')}")

print()

# 3. Check if there's a __pycache__ with compiled template
print("3. SEARCHING FOR .pyc CACHE FILES")
import glob
for pyc in glob.glob('**/__pycache__/*.pyc', recursive=True):
    if 'coach' in pyc.lower():
        size = os.path.getsize(pyc)
        mtime = os.path.getmtime(pyc)
        import datetime
        mt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"   {pyc} ({size} bytes, {mt})")

print()

# 4. Try reading the file as the OS sees it (alternative path separators)
print("4. CHECKING WINDOWS FILE SYSTEM")
for path in ['templates/prep/coach.html', 'templates\\prep\\coach.html', 
             os.path.join('templates', 'prep', 'coach.html')]:
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"   {path}: EXISTS, {size} bytes")
    else:
        print(f"   {path}: NOT FOUND")

print()

# 5. Check if text mode vs binary mode affects the content
print("5. TEXT MODE VS BINARY MODE")
with open('templates/prep/coach.html', 'r', encoding='utf-8') as f:
    text_data = f.read()
text_bytes = text_data.encode('utf-8')
print(f"   Text mode: {len(text_bytes)} bytes")
print(f"   Binary mode: {len(data)} bytes")
print(f"   Match: {data == text_bytes}")

print()

# 6. What's the content that Jinja returns vs disk?
print("6. COMPARING CONTENT (first 100 diff bytes)")
disk_text = data.decode('utf-8')
jinja_text = source

# Find first difference
min_len = min(len(disk_text), len(jinja_text))
for i in range(min_len):
    if disk_text[i] != jinja_text[i]:
        print(f"   First difference at position {i}")
        print(f"   Disk: ...{disk_text[max(0,i-50):i+50]}...")
        print(f"   Jinja: ...{jinja_text[max(0,i-50):i+50]}...")
        break
else:
    if len(disk_text) != len(jinja_text):
        print(f"   Lengths differ: disk={len(disk_text)}, jinja={len(jinja_text)}")
        print(f"   Disk has extra content starting at position {min_len}:")
        print(f"   ...{disk_text[min_len:min_len+200]}...")
