# -*- coding: utf-8 -*-
"""Find exact Jinja vs disk discrepancy at byte level."""
import os, hashlib, sys

os.environ['PYTHONIOENCODING'] = 'utf-8'

# Read disk content
with open('templates/prep/coach.html', 'rb') as f:
    disk_bytes = f.read()
disk_text = disk_bytes.decode('utf-8')

with open('templates/base.html', 'rb') as f:
    base_disk = f.read()

# Jinja loader
from jinja2 import FileSystemLoader, Environment
loader = FileSystemLoader('templates')
env = Environment(loader=loader)
jinja_source, jinja_fname, uptodate = loader.get_source(env, 'prep/coach.html')
jinja_bytes = jinja_source.encode('utf-8')

print(f"Disk:      {len(disk_bytes)} bytes, MD5: {hashlib.md5(disk_bytes).hexdigest()}")
print(f"Jinja:     {len(jinja_bytes)} bytes, MD5: {hashlib.md5(jinja_bytes).hexdigest()}")
print()

# Find first byte difference
min_bytes = min(len(disk_bytes), len(jinja_bytes))
for i in range(min_bytes):
    if disk_bytes[i] != jinja_bytes[i]:
        print(f"First byte difference at position {i}")
        # Show context around the difference
        start = max(0, i - 50)
        end = min(len(disk_bytes), i + 50)
        
        print(f"\nDisk ({i}):")
        print(repr(disk_bytes[start:end]))
        print(f"\nDisk decoded:")
        print(disk_text[max(0,i-50):min(len(disk_text),i+50)])
        
        jinja_text = jinja_source
        print(f"\nJinja ({i}):")
        print(repr(jinja_bytes[start:end]))
        print(f"\nJinja decoded:")
        print(jinja_text[max(0,i-50):min(len(jinja_text),i+50)])
        break
else:
    print("Files are identical byte-for-byte!")
    if len(disk_bytes) != len(jinja_bytes):
        print(f"But lengths differ: disk={len(disk_bytes)}, jinja={len(jinja_bytes)}")
        # The shorter one is a prefix of the longer one
        if disk_bytes.startswith(jinja_bytes):
            print("Disk has extra content at the end")
            extra = disk_bytes[len(jinja_bytes):]
            print(f"Extra ({len(extra)} bytes): {extra[:200]}")
        elif jinja_bytes.startswith(disk_bytes):
            print("Jinja has extra content at the end")
            extra = jinja_bytes[len(disk_bytes):]
            print(f"Extra ({len(extra)} bytes): {extra[:200]}")
