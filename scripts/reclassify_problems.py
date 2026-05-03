#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reclassify all 9476 tasks in problems.py:
1. Detect movement tasks by keywords → subject='movement'
2. Map new subtopics to existing SUBTOPICS structure
3. Ensure every task has valid subject + subtopic
"""
import sys, os, re, json
sys.stdout.reconfigure(encoding='utf-8')

# ─── Movement detection ──────────────────────────────────────────────────────

MOVEMENT_KEYWORDS = re.compile(
    r'движен|скорост|поезд|велосипед|автомобил|пешеход|катер|лодк|течени|'
    r'км/ч|м/с|навстречу|вдогонку|обгон|догнал|выехал|отправил|'
    r'расстояни\w+\s+между\s+город|из\s+пункта\s+[A-ZА-Я]\s+в\s+пункт|'
    r'из\s+города|прибыл|приехал|проехал|пройти\s+путь|весь\s+путь|'
    r'средн\w+\s+скорост|собственн\w+\s+скорост|скорость\s+течен',
    re.IGNORECASE
)

# ─── Subtopic mapping: new subtopics → existing valid subtopics ──────────────
# Valid subtopics per subject (from app.py SUBTOPICS):
# algebra: equations, inequalities, text_problems
# geometry: basics, circles, triangles
# number_theory: divisibility, primes_and_equations
# combinatorics: counting, dirichlet_and_graphs, games_and_invariants
# movement: linear, circular
# knights_liars: basic_logic, complex_logic

SUBTOPIC_REMAP = {
    # Algebra subtopics → existing algebra subtopics
    'natural_numbers': 'equations',
    'fractions': 'equations',
    'decimal_fractions': 'equations',
    'percentages': 'text_problems',
    'equations_word_problems': 'text_problems',
    'positive_negative': 'equations',
    'rational_numbers': 'equations',
    'ratios_proportions': 'text_problems',
    'linear_equations': 'equations',
    'algebraic_expressions': 'equations',
    'linear_systems': 'equations',
    'powers_monomials': 'equations',
    'polynomials_fsu': 'equations',
    'functions_graphs': 'equations',
    'rational_fractions': 'equations',
    'square_roots': 'equations',
    'quadratic_equations': 'equations',
    'integer_powers': 'equations',
    'equation_systems': 'equations',
    'quadratic_function': 'equations',
    'equations_inequalities': 'inequalities',
    'progressions': 'equations',
    'exp_log_functions': 'equations',
    'trigonometry': 'equations',
    'derivatives': 'equations',
    'integrals': 'equations',
    'exp_log_equations': 'equations',
    'optimization': 'text_problems',
    'complex_numbers': 'equations',

    # Geometry subtopics → existing geometry subtopics
    'areas_volumes': 'basics',
    'coordinates': 'basics',
    'triangles_parallel': 'triangles',
    'quadrilaterals_areas': 'basics',
    'circles_vectors': 'circles',
    'polyhedra': 'basics',
    'stereometry_parallel_perp': 'basics',
    'volumes': 'basics',
    'solids_of_revolution': 'basics',

    # Number theory subtopics → existing
    'divisibility': 'divisibility',

    # Combinatorics subtopics → existing
    'probability_basics': 'counting',
    'combinatorics_probability': 'counting',

    # Movement subtopics → existing
    'linear': 'linear',
    'circular': 'circular',

    # Knights/liars subtopics → existing
    'basic_logic': 'basic_logic',
    'complex_logic': 'complex_logic',
}

# Valid subjects and their subtopics
VALID_SUBTOPICS = {
    'algebra': {'equations', 'inequalities', 'text_problems'},
    'geometry': {'basics', 'circles', 'triangles'},
    'number_theory': {'divisibility', 'primes_and_equations'},
    'combinatorics': {'counting', 'dirichlet_and_graphs', 'games_and_invariants'},
    'movement': {'linear', 'circular'},
    'knights_liars': {'basic_logic', 'complex_logic'},
}


def reclassify_task(task):
    """Reclassify a single task. Returns modified task dict."""
    text = task.get('text', '')
    subject = task.get('subject', 'algebra')
    subtopic = task.get('subtopic', 'equations')

    # Step 1: Detect movement tasks
    if subject != 'movement' and MOVEMENT_KEYWORDS.search(text):
        # Check it's really a movement problem (not just mentioning speed in passing)
        # Count keyword matches
        matches = len(MOVEMENT_KEYWORDS.findall(text))
        if matches >= 2:  # At least 2 movement keywords
            task['subject'] = 'movement'
            task['subtopic'] = 'linear'
            return task

    # Step 2: Remap subtopic to valid one
    if subtopic in SUBTOPIC_REMAP:
        new_subtopic = SUBTOPIC_REMAP[subtopic]
        task['subtopic'] = new_subtopic
    
    # Step 3: Validate subject+subtopic combination
    valid_subs = VALID_SUBTOPICS.get(subject, set())
    if task['subtopic'] not in valid_subs:
        # Fallback to first valid subtopic for this subject
        if valid_subs:
            task['subtopic'] = sorted(valid_subs)[0]
        else:
            # Unknown subject, default to algebra
            task['subject'] = 'algebra'
            task['subtopic'] = 'equations'

    return task


def main():
    problems_path = 'problems.py'
    
    # Read and parse
    print("Reading problems.py...")
    with open(problems_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    exec_globals = {}
    exec(compile(content, problems_path, 'exec'), exec_globals)
    problems = exec_globals['PROBLEMS_DB']
    print(f"Loaded {len(problems)} tasks")

    # Stats before
    print("\n=== BEFORE ===")
    subjects_before = {}
    for p in problems:
        s = p.get('subject', '?')
        subjects_before[s] = subjects_before.get(s, 0) + 1
    for s, c in sorted(subjects_before.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    # Reclassify
    movement_reclassified = 0
    subtopic_remapped = 0
    
    for task in problems:
        old_subject = task.get('subject')
        old_subtopic = task.get('subtopic')
        
        reclassify_task(task)
        
        if task['subject'] != old_subject:
            movement_reclassified += 1
        if task['subtopic'] != old_subtopic:
            subtopic_remapped += 1

    print(f"\nReclassified to movement: {movement_reclassified}")
    print(f"Subtopics remapped: {subtopic_remapped}")

    # Stats after
    print("\n=== AFTER ===")
    subjects_after = {}
    for p in problems:
        s = p.get('subject', '?')
        subjects_after[s] = subjects_after.get(s, 0) + 1
    for s, c in sorted(subjects_after.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    # Subtopic stats
    print("\n=== SUBTOPICS AFTER ===")
    for subject in sorted(VALID_SUBTOPICS.keys()):
        tasks = [p for p in problems if p.get('subject') == subject]
        print(f"\n  {subject} ({len(tasks)} tasks):")
        sub_counts = {}
        for p in tasks:
            st = p.get('subtopic', '?')
            sub_counts[st] = sub_counts.get(st, 0) + 1
        for st, c in sorted(sub_counts.items(), key=lambda x: -x[1]):
            valid = '✅' if st in VALID_SUBTOPICS.get(subject, set()) else '❌'
            print(f"    {valid} {st}: {c}")

    # Movement tasks by grade
    movement_tasks = [p for p in problems if p.get('subject') == 'movement']
    print(f"\n=== MOVEMENT BY GRADE ===")
    mg = {}
    for p in movement_tasks:
        g = p.get('grade', '?')
        mg[g] = mg.get(g, 0) + 1
    for g in sorted(mg.keys()):
        print(f"  Grade {g}: {mg[g]}")

    # Write back
    print("\nWriting corrected problems.py...")
    
    # Build new file content
    lines = ['PROBLEMS_DB = [\n']
    for i, task in enumerate(problems):
        text_escaped = task['text'].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        answer_escaped = str(task['answer']).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        
        entry = (
            f'    {{\n'
            f'        "id": {task["id"]},\n'
            f'        "subject": "{task["subject"]}",\n'
            f'        "subtopic": "{task["subtopic"]}",\n'
            f'        "grade": {task["grade"]},\n'
            f'        "difficulty": {task["difficulty"]},\n'
            f'        "text": "{text_escaped}",\n'
            f'        "answer": "{answer_escaped}"\n'
            f'    }}'
        )
        if i < len(problems) - 1:
            entry += ','
        lines.append(entry + '\n')
    lines.append(']\n')

    with open(problems_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    # Verify
    try:
        compile(open(problems_path, 'r', encoding='utf-8').read(), problems_path, 'exec')
        print("✅ Syntax check PASSED")
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return

    exec_globals2 = {}
    exec(compile(open(problems_path, 'r', encoding='utf-8').read(), problems_path, 'exec'), exec_globals2)
    print(f"✅ Final count: {len(exec_globals2['PROBLEMS_DB'])} tasks")


if __name__ == '__main__':
    main()
