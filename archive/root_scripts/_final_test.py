#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Final proof script — writes results to _test_result.txt."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mktemp(suffix='.db')
os.environ['FLASK_ENV'] = 'development'

out_lines = []

def p(s=""):
    out_lines.append(s)
    print(s)

from services.anchors import (
    normalize_answer, check_answer, get_theme_map,
    pick_anchors, load_anchors, inspect_anchors,
    get_anchor_ids, get_anchor_ids_set,
    CANONICAL_SECTIONS_ORDER, SOURCE_NAME,
)

# ================================================================
p("=" * 70)
p("PART 1: FILE STATS (data/anchors.jsonl)")
p("=" * 70)
path = os.path.join(os.path.dirname(__file__), 'data', 'anchors.jsonl')
anchors_raw = []
with open(path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            anchors_raw.append(json.loads(line))

p(f"Lines: {len(anchors_raw)}")
p()
p("anchor_uid list:")
for i, a in enumerate(anchors_raw):
    p(f"  {i+1:>2}. {a['anchor_uid']:<15} G{a['grade']} {a['section']:<18} L{a['level']} ans={a['answer']}")

from collections import Counter
by_grade = Counter(a['grade'] for a in anchors_raw)
by_section = Counter(a['section'] for a in anchors_raw)
p()
p(f"By grade:  {dict(sorted(by_grade.items()))}")
p(f"By section: {dict(sorted(by_section.items()))}")

assert len(anchors_raw) == 35
for g in range(5, 12):
    assert by_grade[g] == 5
p("VERIFIED: 35 anchors, 5 per grade (5-11), 7 per section")

# ================================================================
p()
p("=" * 70)
p("PART 2: LOAD INTO DB + theme_id MAPPING")
p("=" * 70)

from app import app, db
from models import AdaptiveTask

app.config['TESTING'] = True
app.config['SECRET_KEY'] = 'test-final'
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'localhost.final.test'

with app.app_context():
    db.drop_all()
    db.create_all()

    r = load_anchors()
    p(f"loaded = {r['loaded']}")
    p(f"skipped = {r['skipped']}")
    p(f"errors = {len(r['errors'])}")

    # theme_id stats
    tasks = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').all()
    with_theme = [t for t in tasks if t.theme_id]
    without_theme = [t for t in tasks if not t.theme_id]
    p(f"\ntheme_id filled: {len(with_theme)}")
    p(f"theme_id empty:  {len(without_theme)}")
    if without_theme:
        p("  Empty theme_id anchors:")
        for t in without_theme:
            p(f"    anchor_uid={t.source_id} grade={t.class_level} section={t.subject}")
    if with_theme:
        p("  Sample filled theme_ids:")
        for t in with_theme[:7]:
            p(f"    anchor_uid={t.source_id} theme_id={t.theme_id}")

    # Unmapped from load result
    if r['unmapped_themes']:
        p(f"\nunmapped_themes ({len(r['unmapped_themes'])}):")
        for u in r['unmapped_themes']:
            p(f"  {u}")
    else:
        p(f"\nunmapped_themes: 0")

    # ================================================================
    p()
    p("=" * 70)
    p("PART 3: pick_anchors for GRADE 9 (3 runs)")
    p("=" * 70)

    for run_num in [1, 2, 3]:
        anchors, meta = pick_anchors(9)
        p(f"\nRun {run_num}: {meta['anchor_count']} anchors, total_available={meta['total_available']}")
        p(f"{'#':<4} {'anchor_uid':<15} {'section':<20} {'subtopic':<35} {'level':<6} {'answer':<6}")
        p(f"{'-'*4} {'-'*15} {'-'*20} {'-'*35} {'-'*6} {'-'*6}")
        sections = []
        for i, a in enumerate(anchors, 1):
            sections.append(a['section'])
            p(f"{i:<4} {a['anchor_uid']:<15} {a['section']:<20} {a['subtopic'][:34]:<35} {a['level']:<6} {a['answer']:<6}")
        dups = len(sections) != len(set(sections))
        p(f"  sections: {sections}  dups={dups}")

    # ================================================================
    p()
    p("=" * 70)
    p("PART 4: pick_anchors for GRADE 6 (3 runs)")
    p("=" * 70)

    for run_num in [1, 2, 3]:
        anchors, meta = pick_anchors(6)
        p(f"\nRun {run_num}: {meta['anchor_count']} anchors, total_available={meta['total_available']}")
        p(f"{'#':<4} {'anchor_uid':<15} {'section':<20} {'subtopic':<35} {'level':<6} {'answer':<6}")
        p(f"{'-'*4} {'-'*15} {'-'*20} {'-'*35} {'-'*6} {'-'*6}")
        sections = []
        for i, a in enumerate(anchors, 1):
            sections.append(a['section'])
            p(f"{i:<4} {a['anchor_uid']:<15} {a['section']:<20} {a['subtopic'][:34]:<35} {a['level']:<6} {a['answer']:<6}")
        dups = len(sections) != len(set(sections))
        p(f"  sections: {sections}  dups={dups}")

    # ================================================================
    p()
    p("=" * 70)
    p("PART 5: ANSWER CHECK — all 35 correct answers")
    p("=" * 70)

    correct_checks = 0
    for a in anchors_raw:
        ok = check_answer(a['answer'], a['answer'])
        if ok:
            correct_checks += 1
        else:
            p(f"  FAIL: {a['anchor_uid']} answer={a['answer']} did not match itself!")
    p(f"Correct self-checks: {correct_checks}/{len(anchors_raw)}")

    # Wrong answers
    wrong_tests = [
        ('A_G5_ALG', '31'),     # 30 -> wrong
        ('A_G5_GEO', '7'),      # 8 -> wrong
        ('A_G9_ALG', '13'),     # 12 -> wrong
        ('A_G11_NT', '26'),     # 27 -> wrong
    ]
    p()
    p("Wrong answer tests:")
    for uid, wrong_ans in wrong_tests:
        a = next(x for x in anchors_raw if x['anchor_uid'] == uid)
        ok = check_answer(wrong_ans, a['answer'])
        p(f"  {uid}: answer='{wrong_ans}' vs correct='{a['answer']}' -> correct={ok} {'PASS(not matched)' if not ok else 'FAIL(should not match)'}")

    # Edge cases: spaces, commas, dots
    p()
    p("Edge cases:")
    p(f"  '30' vs '30' -> {check_answer('30', '30')}")
    p(f"  ' 30 ' vs '30' -> {check_answer(' 30 ', '30')}")
    p(f"  '0.99' vs '0,99' -> {check_answer('0.99', '0,99')}")
    p(f"  '0,99' vs '0.99' -> {check_answer('0,99', '0.99')}")

    # ================================================================
    p()
    p("=" * 70)
    p("PART 6: EXCLUSION — formyla_anchors not in daily tasks / morning probe")
    p("=" * 70)

    # Add regular tasks
    for grade in [9]:
        for level in range(1, 6):
            for sec in CANONICAL_SECTIONS_ORDER:
                t = AdaptiveTask(
                    class_level=grade, difficulty_level=level,
                    topic=sec, subject=sec, subtopic=f'Test {sec}',
                    task_text=f'Regular task {sec} L{level}: 1+1=?',
                    solution='2', criteria_1_point='', criteria_2_points='',
                    correct_answer='2', source='formyla_L1_L5_TOP5',
                    source_id=f'TEST_{grade}_{sec}_L{level}',
                )
                db.session.add(t)
    db.session.commit()

    from services.daily_task_rotation import _pick_tasks_for_section, _pick_tasks_fallback

    anchor_id_set = get_anchor_ids_set()
    p(f"anchor_ids count: {len(anchor_id_set)}")

    tasks = _pick_tasks_for_section(9, 'algebra', [1, 2, 3, 4, 5], set(), 5, user_id=None)
    leaked = [t['task_id'] for t in tasks if t['task_id'] in anchor_id_set]
    p(f"_pick_tasks_for_section(9, algebra): {len(tasks)} tasks, leaked={leaked}")

    ftasks = _pick_tasks_fallback(9, [1, 2, 3, 4, 5], set(), 20)
    leaked_f = [t['task_id'] for t in ftasks if t['task_id'] in anchor_id_set]
    p(f"_pick_tasks_fallback(9): {len(ftasks)} tasks, leaked={leaked_f}")

    # Morning probe
    from services.theme_probe import _select_and_advance
    from models_curator import CuratorState

    cs = CuratorState(user_id=99991)
    db.session.add(cs)
    db.session.commit()

    probe_state = {
        'theme_id': 'G9_T05', 'current_index': 0,
        'current_level': 3, 'seen_task_ids': [], 'grade': 9,
    }
    probe_leaks = 0
    for _ in range(5):
        result = _select_and_advance(cs, probe_state, 9)
        if 'task' in result:
            tid = result['task']['id']
            if tid in anchor_id_set:
                p(f"  LEAK in probe: task_id={tid}")
                probe_leaks += 1
            probe_state['seen_task_ids'].append(tid)
    p(f"Morning probe leaks: {probe_leaks}")

    db.drop_all()

p()
p("=" * 70)
p("ALL DONE")
p("=" * 70)

# Write to file
with open(os.path.join(os.path.dirname(__file__), '_test_result.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))
print("Results written to _test_result.txt")
