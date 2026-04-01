#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HuggingFace Problems Migrator
Converts hf_problems.jsonl to the format expected by migrator.py
and migrates to problems.py database.
"""

import os
import sys
import json
import shutil

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configuration
HF_PROBLEMS_JSONL = "data/hf_problems.jsonl"
CONVERTED_JSONL = "data/generated_problems.jsonl"
PROBLEMS_PY = "problems.py"

# Subject title mapping
SUBJECT_TITLES = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "knights_liars": "Рыцари и лжецы",
    "movement": "Задачи на движение",
    "other": "Разное"
}


def convert_hf_to_standard_format():
    """
    Convert hf_problems.jsonl to the standard format expected by migrator.py
    
    HuggingFace format:
    {
        "subject": "algebra",
        "subtopic": "Уравнения",
        "grade": 7,
        "difficulty": 2,
        "title": "Олимпиадная задача",
        "text": "...",
        "answer": "...",
        "solution": "...",
        "source": "HuggingFace",
        "source_dataset": "d0rj/ROMB-1.0"
    }
    
    Standard format (required by migrator.py):
    {
        "subject": "algebra",
        "subject_title": "Алгебра",
        "subtopic": "equations",
        "subtopic_title": "Уравнения",
        "grade": 7,
        "difficulty": 2,
        "title": "Олимпиадная задача",
        "text": "...",
        "answer": "...",
        "solution": "...",
        "source": "HuggingFace",
        "source_url": ""
    }
    """
    print("=" * 70)
    print("HuggingFace Problems Format Converter")
    print("=" * 70)
    
    if not os.path.exists(HF_PROBLEMS_JSONL):
        print(f"❌ File not found: {HF_PROBLEMS_JSONL}")
        print("   Please run hf_importer.py first to download problems")
        return False
    
    # Read HF problems
    hf_problems = []
    skipped = 0
    
    print(f"\n📥 Reading from: {HF_PROBLEMS_JSONL}")
    
    try:
        with open(HF_PROBLEMS_JSONL, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    problem = json.loads(line)
                    hf_problems.append(problem)
                except json.JSONDecodeError as e:
                    print(f"⚠️  Line {line_num}: Invalid JSON, skipping")
                    skipped += 1
    except Exception as e:
        print(f"❌ Error reading {HF_PROBLEMS_JSONL}: {e}")
        return False
    
    print(f"✓ Loaded {len(hf_problems)} problems")
    if skipped > 0:
        print(f"⚠️  Skipped {skipped} invalid entries")
    
    # Convert to standard format
    converted_problems = []
    
    print(f"\n🔄 Converting to standard format...")
    
    for problem in hf_problems:
        # Get subject title
        subject = problem.get("subject", "other")
        subject_title = SUBJECT_TITLES.get(subject, "Разное")
        
        # Subtopic is already in Russian from DeepSeek
        subtopic_title = problem.get("subtopic", "Разное")
        
        # Create subtopic key (lowercase, no spaces)
        # For now, we'll use the Russian title as-is since our app.py uses Russian subtopic titles
        subtopic = subtopic_title
        
        # Build standard format
        converted = {
            "subject": subject,
            "subject_title": subject_title,
            "subtopic": subtopic,
            "subtopic_title": subtopic_title,
            "grade": problem.get("grade", 5),
            "difficulty": problem.get("difficulty", 2),
            "title": problem.get("title", "Олимпиадная задача"),
            "text": problem.get("text", ""),
            "answer": problem.get("answer", ""),
            "solution": problem.get("solution", ""),
            "source": problem.get("source", "HuggingFace"),
            "source_url": f"Dataset: {problem.get('source_dataset', 'unknown')}"
        }
        
        converted_problems.append(converted)
    
    print(f"✓ Converted {len(converted_problems)} problems")
    
    # Save to converted file
    print(f"\n💾 Saving to: {CONVERTED_JSONL}")
    
    try:
        os.makedirs("data", exist_ok=True)
        with open(CONVERTED_JSONL, 'w', encoding='utf-8') as f:
            for problem in converted_problems:
                f.write(json.dumps(problem, ensure_ascii=False) + '\n')
        
        print(f"✓ Saved {len(converted_problems)} problems to {CONVERTED_JSONL}")
        
    except Exception as e:
        print(f"❌ Error writing {CONVERTED_JSONL}: {e}")
        return False
    
    return True


def migrate_to_problems_py():
    """
    Migrate converted problems to problems.py using the standard migrator logic.
    """
    print("\n" + "=" * 70)
    print("Migrating to problems.py")
    print("=" * 70)
    
    if not os.path.exists(CONVERTED_JSONL):
        print(f"❌ File not found: {CONVERTED_JSONL}")
        return False
    
    # Read converted problems
    problems = []
    skipped = 0
    
    try:
        with open(CONVERTED_JSONL, 'r', encoding='utf-8') as f:
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
                        print(f"⚠️  Line {line_num}: Missing fields {missing}, skipping")
                        skipped += 1
                        
                except json.JSONDecodeError as e:
                    print(f"⚠️  Line {line_num}: Invalid JSON, skipping")
                    skipped += 1
                    
    except Exception as e:
        print(f"❌ Error reading {CONVERTED_JSONL}: {e}")
        return False
    
    print(f"\n📊 Statistics:")
    print(f"   Loaded: {len(problems)} tasks")
    print(f"   Skipped: {skipped} invalid entries")
    
    if len(problems) == 0:
        print("❌ No valid problems to migrate")
        return False
    
    # Create backup
    if os.path.exists(PROBLEMS_PY):
        backup_path = PROBLEMS_PY + ".bak"
        shutil.copy2(PROBLEMS_PY, backup_path)
        print(f"\n💾 Backup created: {backup_path}")
    
    # Write to problems.py
    try:
        with open(PROBLEMS_PY, 'w', encoding='utf-8') as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write(f"# База задач из HuggingFace — {len(problems)} задач\n\n")
            f.write("PROBLEMS_DB = ")
            json.dump(problems, f, ensure_ascii=False, indent=0)
            f.write("\n")
        
        print(f"✓ Written {len(problems)} problems to {PROBLEMS_PY}")
        
        # Verify import
        import importlib.util
        spec = importlib.util.spec_from_file_location("problems_test", PROBLEMS_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        print(f"✓ Verification: Successfully loaded {len(module.PROBLEMS_DB)} tasks from new file")
        
        return True
        
    except Exception as e:
        print(f"❌ Error writing {PROBLEMS_PY}: {e}")
        print("   Backup preserved")
        return False


def main():
    """Main execution function."""
    print("=" * 70)
    print("HuggingFace Problems Migrator")
    print("=" * 70)
    print("\nThis script will:")
    print("1. Convert hf_problems.jsonl to standard format")
    print("2. Migrate to problems.py database")
    print("3. Create backup of existing problems.py")
    
    # Step 1: Convert format
    if not convert_hf_to_standard_format():
        print("\n❌ Conversion failed")
        return 1
    
    # Step 2: Migrate to problems.py
    if not migrate_to_problems_py():
        print("\n❌ Migration failed")
        return 1
    
    print("\n" + "=" * 70)
    print("✅ MIGRATION COMPLETE!")
    print("=" * 70)
    print(f"\nYour problems are now available in {PROBLEMS_PY}")
    print("Restart your Flask app to see the new problems on the website.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
