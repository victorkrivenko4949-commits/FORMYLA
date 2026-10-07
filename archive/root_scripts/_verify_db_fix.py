#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the KaTeX fix is applied in the database"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import OlympiadSecret

with app.app_context():
    s = OlympiadSecret.query.filter_by(title='E10. Двойной счёт').first()
    if s is None:
        print("ERROR: E10. Двойной счёт not found in DB!")
        sys.exit(1)
    
    content = s.content
    idx = content.find('разноцветных')
    print(f'ID: {s.id}')
    print(f'Title: {s.title}')
    print(f'"разноцветных" at index: {idx}')
    
    # Show context
    start = max(0, idx - 20)
    end = min(len(content), idx + 60)
    ctx = content[start:end]
    print(f'Context: ...{ctx}...')
    
    # Check if \# is present before разноцветных
    before = content[idx-5:idx]
    print(f'Characters before "разноцветных": {repr(before)}')
    
    if '#' in before:
        print("WARNING: '#' still found before 'разноцветных' - fix may not have been applied!")
    else:
        print("SUCCESS: No '#' before 'разноцветных' - fix confirmed in database!")
