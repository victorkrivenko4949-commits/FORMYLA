#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mini-patch: add scope=all_sections redirect to select-section handler."""
import os

APPPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

with open(APPPATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the select-section handler
old = '''@app.route("/olympiad-test/select-section")
def olympiad_test_select_section():
    """Step 2: Select section for chosen grade."""'''

new = '''@app.route("/olympiad-test/select-section")
def olympiad_test_select_section():
    """Step 2: Select section for chosen grade.
    If scope=all_sections in session, redirect to test start."""
    scope = session.get('olyad_scope', None)'''

if old in content:
    content = content.replace(old, new)
    # Also add the redirect logic after "return redirect('/olympiad-test')"
    old2 = '''        flash('Неверный класс', 'error')
        return redirect('/olympiad-test')
    from services.olympiad_adaptive import get_sections'''
    
    new2 = '''        flash('Неверный класс', 'error')
        return redirect('/olympiad-test')
    if scope == 'all_sections':
        return redirect(f'/olympiad-test/start?grade={grade}')
    from services.olympiad_adaptive import get_sections'''
    
    content = content.replace(old2, new2)
    
    with open(APPPATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("PATCH: select-section scope redirect added")
else:
    print("PATCH: already done or not found")
    # Check if scope is already used
    if 'scope = session.get' in content:
        print("  scope already in select-section - OK")
