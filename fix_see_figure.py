#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to remove all instances of '(см. рисунок)' from olympiads.py
"""

def fix_olympiads_file():
    """Remove all '(см. рисунок)' references from olympiads.py"""
    
    # Read the file
    with open('olympiads.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count occurrences before
    count_before = content.count('(см. рисунок)')
    count_before_alt = content.count('(см.\nрисунок)')
    
    print(f"Found {count_before} instances of '(см. рисунок)'")
    print(f"Found {count_before_alt} instances of '(см.\\nрисунок)'")
    
    # Remove all instances
    content = content.replace('(см. рисунок)', '')
    content = content.replace('(см.\nрисунок)', '')
    
    # Also handle variations with different spacing
    content = content.replace('(см.рисунок)', '')
    content = content.replace('( см. рисунок )', '')
    
    # Clean up any double spaces that might result
    while '  ' in content:
        content = content.replace('  ', ' ')
    
    # Write back
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Verify
    with open('olympiads.py', 'r', encoding='utf-8') as f:
        new_content = f.read()
    
    count_after = new_content.count('(см. рисунок)')
    count_after_alt = new_content.count('(см.\nрисунок)')
    
    print(f"\nAfter fix:")
    print(f"Remaining instances of '(см. рисунок)': {count_after}")
    print(f"Remaining instances of '(см.\\nрисунок)': {count_after_alt}")
    
    if count_after == 0 and count_after_alt == 0:
        print("\n✅ SUCCESS: All '(см. рисунок)' references removed!")
    else:
        print("\n⚠️ WARNING: Some instances may remain")

if __name__ == '__main__':
    fix_olympiads_file()
