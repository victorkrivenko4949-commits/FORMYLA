#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to remove ALL instances of 'см. рисунок' (with and without parentheses)
"""

def fix_file(filename):
    """Remove all 'см. рисунок' references from a file"""
    
    try:
        # Read the file
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count occurrences before
        patterns = [
            '(см. рисунок)',
            '(см.\nрисунок)',
            '(см.рисунок)',
            '( см. рисунок )',
            'см. рисунок',
            'см.\nрисунок',
            'см.рисунок',
        ]
        
        total_before = sum(content.count(p) for p in patterns)
        
        if total_before == 0:
            print(f"{filename}: No instances found, skipping")
            return 0
        
        print(f"{filename}: Found {total_before} instances")
        
        # Remove all instances
        for pattern in patterns:
            content = content.replace(pattern, '')
        
        # Clean up any double spaces that might result
        while '  ' in content:
            content = content.replace('  ', ' ')
        
        # Write back
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Verify
        with open(filename, 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        total_after = sum(new_content.count(p) for p in patterns)
        
        print(f"{filename}: After fix - {total_after} instances remaining")
        
        if total_after == 0:
            print(f"{filename}: ✓ SUCCESS")
        else:
            print(f"{filename}: ✗ WARNING: Some instances remain")
        
        return total_before - total_after
    
    except Exception as e:
        print(f"{filename}: ERROR - {e}")
        return 0

if __name__ == '__main__':
    files_to_fix = ['olympiads.py', 'problems.py']
    
    print("="*60)
    print("REMOVING ALL 'см. рисунок' REFERENCES")
    print("="*60)
    
    total_removed = 0
    for filename in files_to_fix:
        removed = fix_file(filename)
        total_removed += removed
        print()
    
    print("="*60)
    print(f"TOTAL REMOVED: {total_removed} instances")
    print("="*60)
