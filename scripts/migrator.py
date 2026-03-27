#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database Migrator for FORMYLA Platform
Migrates generated tasks and solutions from JSONL files to Python database files.
"""

import os
import sys
import json
import shutil
import argparse
import importlib.util

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
PROBLEMS_JSONL = "data/generated_problems.jsonl"
SOLUTIONS_JSONL = "data/generated_solutions.jsonl"
PROBLEMS_PY = "problems.py"
OLYMPIADS_PY = "olympiads.py"


def create_backup(filepath):
    """Create backup of file before modification."""
    if os.path.exists(filepath):
        backup_path = filepath + ".bak"
        shutil.copy2(filepath, backup_path)
        print(f"[OK] Backup created: {backup_path}")
        return backup_path
    return None


def migrate_problems(dry_run=False):
    """
    Migrate generated problems from JSONL to problems.py
    
    Args:
        dry_run: If True, only analyze without writing
    """
    print("\n" + "=" * 70)
    print("MIGRATING PROBLEMS")
    print("=" * 70)
    
    if not os.path.exists(PROBLEMS_JSONL):
        print(f"[WARNING] File not found: {PROBLEMS_JSONL}")
        print("   Skipping problems migration")
        return
    
    # Read JSONL
    problems = []
    skipped = 0
    
    try:
        with open(PROBLEMS_JSONL, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    task = json.loads(line)
                    
                    # Validate required fields
                    required = ['subject', 'subject_title', 'subtopic', 'subtopic_title', 
                               'grade', 'difficulty', 'title', 'text', 'answer', 'solution']
                    
                    if all(field in task for field in required):
                        # Assign new ID
                        task['id'] = len(problems) + 1
                        problems.append(task)
                    else:
                        missing = [f for f in required if f not in task]
                        print(f"  [WARNING] Line {line_num}: Missing fields {missing}, skipping")
                        skipped += 1
                        
                except json.JSONDecodeError as e:
                    print(f"  [WARNING] Line {line_num}: Invalid JSON, skipping")
                    skipped += 1
                    
    except Exception as e:
        print(f"[ERROR] Error reading {PROBLEMS_JSONL}: {e}")
        return
    
    print(f"\n📊 Statistics:")
    print(f"   Loaded: {len(problems)} tasks")
    print(f"   Skipped: {skipped} invalid entries")
    
    if dry_run:
        print("\n[DRY RUN] Would write to problems.py")
        return
    
    # Create backup
    create_backup(PROBLEMS_PY)
    
    # Write to problems.py
    try:
        with open(PROBLEMS_PY, 'w', encoding='utf-8') as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write(f"# База задач для раздела Разделы — {len(problems)} задач\n\n")
            f.write("PROBLEMS_DB = ")
            json.dump(problems, f, ensure_ascii=False, indent=0)
            f.write("\n")
        
        print(f"[OK] Written to {PROBLEMS_PY}")
        
        # Verify import
        spec = importlib.util.spec_from_file_location("problems_test", PROBLEMS_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        print(f"[OK] Verification: Loaded {len(module.PROBLEMS_DB)} tasks from new file")
        
    except Exception as e:
        print(f"[ERROR] Error writing {PROBLEMS_PY}: {e}")
        print("   Backup preserved")


def migrate_solutions(dry_run=False):
    """
    Migrate generated solutions from JSONL to olympiads.py
    
    Args:
        dry_run: If True, only analyze without writing
    """
    print("\n" + "=" * 70)
    print("MIGRATING SOLUTIONS")
    print("=" * 70)
    
    if not os.path.exists(SOLUTIONS_JSONL):
        print(f"[WARNING] File not found: {SOLUTIONS_JSONL}")
        print("   Skipping solutions migration")
        return
    
    # Import current olympiads
    from olympiads import OLYMPIADS_DB
    
    # Read solutions
    solutions_map = {}
    skipped = 0
    
    try:
        with open(SOLUTIONS_JSONL, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    sol = json.loads(line)
                    
                    if 'olympiad_id' in sol and 'problem_num' in sol and 'solution' in sol:
                        key = (sol['olympiad_id'], sol['problem_num'])
                        solutions_map[key] = sol['solution']
                    else:
                        print(f"  [WARNING] Line {line_num}: Missing required fields, skipping")
                        skipped += 1
                        
                except json.JSONDecodeError:
                    print(f"  [WARNING] Line {line_num}: Invalid JSON, skipping")
                    skipped += 1
                    
    except Exception as e:
        print(f"[ERROR] Error reading {SOLUTIONS_JSONL}: {e}")
        return
    
    print(f"\n📊 Statistics:")
    print(f"   Loaded: {len(solutions_map)} solutions")
    print(f"   Skipped: {skipped} invalid entries")
    
    # Update OLYMPIADS_DB
    updated_count = 0
    for olympiad in OLYMPIADS_DB:
        olympiad_id = olympiad.get('id')
        for problem in olympiad.get('problems', []):
            problem_num = problem.get('num')
            key = (olympiad_id, problem_num)
            
            if key in solutions_map:
                problem['solution'] = solutions_map[key]
                updated_count += 1
    
    print(f"   Updated: {updated_count} problems in olympiads")
    
    if dry_run:
        print("\n[DRY RUN] Would write to olympiads.py")
        return
    
    # Create backup
    create_backup(OLYMPIADS_PY)
    
    # Write to olympiads.py
    try:
        with open(OLYMPIADS_PY, 'w', encoding='utf-8') as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write("База олимпиадных пробников по математике.\n")
            f.write(f"Всего пробников: {len(OLYMPIADS_DB)}\n")
            f.write(f"Всего задач: {sum(len(o.get('problems', [])) for o in OLYMPIADS_DB)}\n")
            f.write('"""\n\n')
            f.write("OLYMPIADS_INFO = ")
            
            # Import OLYMPIADS_INFO from current file
            from olympiads import OLYMPIADS_INFO
            json.dump(OLYMPIADS_INFO, f, ensure_ascii=False, indent=4)
            f.write("\n\n")
            
            f.write("OLYMPIADS_DB = ")
            json.dump(OLYMPIADS_DB, f, ensure_ascii=False, indent=0)
            f.write("\n")
        
        print(f"[OK] Written to {OLYMPIADS_PY}")
        
        # Verify import
        spec = importlib.util.spec_from_file_location("olympiads_test", OLYMPIADS_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        print(f"[OK] Verification: Loaded {len(module.OLYMPIADS_DB)} olympiads from new file")
        
    except Exception as e:
        print(f"[ERROR] Error writing {OLYMPIADS_PY}: {e}")
        print("   Backup preserved")


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Migrate generated data to database files')
    parser.add_argument('--dry-run', action='store_true', help='Analyze without writing')
    args = parser.parse_args()
    
    print("=" * 70)
    print("FORMYLA Database Migrator")
    print("=" * 70)
    
    if args.dry_run:
        print("\n[DRY RUN] No files will be modified")
    else:
        print("\n[PRODUCTION] Files will be overwritten")
        print("   Backups will be created automatically")
    
    # Migrate problems
    migrate_problems(dry_run=args.dry_run)
    
    # Migrate solutions
    migrate_solutions(dry_run=args.dry_run)
    
    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
