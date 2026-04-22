# -*- coding: utf-8 -*-
"""
Audit script for task difficulty levels in PROBLEMS_DB.
Checks distribution and flags suspicious level-7 tasks.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems import PROBLEMS_DB
from collections import defaultdict

# Expected solve rates per level
LEVEL_EXPECTED_RATES = {
    1: 0.95,
    2: 0.85,
    3: 0.60,
    4: 0.35,
    5: 0.15,
    6: 0.08,
    7: 0.03,
}

# Level labels
LEVEL_LABELS = {
    1: 'Базовый',
    2: 'Школьный',
    3: 'Школьная олимпиада',
    4: 'Муниципальный',
    5: 'Региональный',
    6: 'Всерос финал',
    7: 'IMO / ELITE',
}

def audit_distribution():
    """Print distribution of tasks by level."""
    print("=" * 60)
    print("AUDIT: Task Difficulty Distribution")
    print("=" * 60)
    
    by_level = defaultdict(list)
    by_grade = defaultdict(lambda: defaultdict(int))
    
    for task in PROBLEMS_DB:
        level = task.get('difficulty', 0)
        grade = task.get('grade', 0)
        by_level[level].append(task)
        by_grade[grade][level] += 1
    
    total = len(PROBLEMS_DB)
    print(f"\nTotal tasks: {total}\n")
    
    print(f"{'Level':<8} {'Label':<25} {'Count':<8} {'%':<8} {'Avg text len':<15}")
    print("-" * 70)
    
    for level in sorted(by_level.keys()):
        tasks = by_level[level]
        count = len(tasks)
        pct = count / total * 100
        avg_len = sum(len(t.get('text', '')) for t in tasks) / count if count else 0
        label = LEVEL_LABELS.get(level, f'Level {level}')
        print(f"{level:<8} {label:<25} {count:<8} {pct:<8.1f} {avg_len:<15.0f}")
    
    print("\n")
    print("Distribution by grade:")
    print(f"{'Grade':<8}", end="")
    for level in range(1, 8):
        print(f"L{level:<6}", end="")
    print()
    print("-" * 60)
    
    for grade in sorted(by_grade.keys()):
        print(f"{grade:<8}", end="")
        for level in range(1, 8):
            count = by_grade[grade].get(level, 0)
            print(f"{count:<7}", end="")
        print()


def flag_suspicious_level7():
    """Flag level-7 tasks that look too simple (short text)."""
    print("\n" + "=" * 60)
    print("SUSPICIOUS LEVEL-7 TASKS (text length < 200 chars)")
    print("=" * 60)
    
    suspicious = []
    for task in PROBLEMS_DB:
        if task.get('difficulty', 0) == 7:
            text = task.get('text', '')
            if len(text) < 200:
                suspicious.append(task)
    
    print(f"\nFound {len(suspicious)} suspicious level-7 tasks:\n")
    
    for i, task in enumerate(suspicious[:20]):  # Show first 20
        print(f"ID: {task.get('id', 'N/A')}")
        print(f"Grade: {task.get('grade', 'N/A')}")
        print(f"Subject: {task.get('subject', 'N/A')}")
        print(f"Text ({len(task.get('text', ''))} chars): {task.get('text', '')[:150]}...")
        print("-" * 40)
    
    if len(suspicious) > 20:
        print(f"... and {len(suspicious) - 20} more")
    
    return suspicious


def export_samples(n_per_level=5):
    """Export sample tasks for each level to a markdown file."""
    import random
    
    by_level = defaultdict(list)
    for task in PROBLEMS_DB:
        level = task.get('difficulty', 0)
        by_level[level].append(task)
    
    lines = ["# difficulty_audit_samples.md\n"]
    lines.append("Sample tasks for visual review against DIFFICULTY_LEVELS.md spec\n")
    
    for level in sorted(by_level.keys()):
        tasks = by_level[level]
        label = LEVEL_LABELS.get(level, f'Level {level}')
        lines.append(f"\n## Level {level} — {label}\n")
        lines.append(f"Total: {len(tasks)} tasks\n")
        
        samples = random.sample(tasks, min(n_per_level, len(tasks)))
        for i, task in enumerate(samples, 1):
            lines.append(f"\n### Sample {i}")
            lines.append(f"- **ID:** {task.get('id', 'N/A')}")
            lines.append(f"- **Grade:** {task.get('grade', 'N/A')}")
            lines.append(f"- **Subject:** {task.get('subject', 'N/A')}")
            lines.append(f"- **Text:** {task.get('text', '')[:300]}")
            lines.append(f"- **Answer:** {task.get('answer', 'N/A')}")
    
    with open('difficulty_audit_samples.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"\nExported samples to difficulty_audit_samples.md")


if __name__ == '__main__':
    audit_distribution()
    flag_suspicious_level7()
    export_samples()
    print("\nAudit complete!")
