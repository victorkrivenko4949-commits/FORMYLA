#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full proof with REAL anchors.jsonl from owner."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmp_db = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + tmp_db
os.environ['FLASK_ENV'] = 'development'

out_lines = []

def p(s=""):
    out_lines.append(s)
    print(s)

from app import app, db
from models import AdaptiveTask, User
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['SECRET_KEY'] = 'proof-real'
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'proof.real'

with app.app_context():
    db.create_all()

    # Create user
    u = User(id=1, email='test@test.com', preferred_grade=9)
    db.session.add(u)
    db.session.commit()

    from services.anchors import load_anchors, pick_anchors, check_answer

    # ====== P1: Integrity check ======
    p("=" * 70)
    p("P1: Integrity check")
    p("=" * 70)
    try:
        r = load_anchors()
        p(f"loaded={r['loaded']}")
        p(f"skipped={r['skipped']}")
        p(f"errors={len(r['errors'])}")
        p("Integrity: PASSED (no RuntimeError)")
    except RuntimeError as e:
        p(f"Integrity: FAILED - {e}")

    # ====== P2: Clean old synthetic, load real ======
    p()
    p("=" * 70)
    p("P2: DB state")
    p("=" * 70)
    old_synthetic = AdaptiveTask.query.filter(
        AdaptiveTask.source == 'formyla_anchors',
        AdaptiveTask.source_id.like('ANC_%')
    ).count()
    p(f"Synthetic (ANC_*) before: {old_synthetic}")
    real_anchors = AdaptiveTask.query.filter(
        AdaptiveTask.source == 'formyla_anchors',
        AdaptiveTask.source_id.like('A_G%')
    ).count()
    p(f"Real (A_G*) before: {real_anchors}")
    total = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').count()
    p(f"Total formyla_anchors: {total}")

    # ====== P3: Full questionnaire run for grade 9 via pick_anchors ======
    p()
    p("=" * 70)
    p("P3: Questionnaire grade 9 — pick_anchors")
    p("=" * 70)

    from services.daily_task_rotation import SECTION_NAMES_RU

    for run_num in [1]:
        anchors, meta = pick_anchors(9)
        p(f"Run: {meta['anchor_count']} anchors")
        p(f"{'#':<3} {'anchor_uid':<15} {'section_ru':<20} {'level':<6} {'text[:60]'}")
        p(f"{'-'*3} {'-'*15} {'-'*20} {'-'*6} {'-'*60}")
        for i, a in enumerate(anchors, 1):
            t = AdaptiveTask.query.get(a['db_id'])
            ru = SECTION_NAMES_RU.get(a['section'], a['section'])
            text = a['statement'][:60]
            p(f"{i:<3} {a['anchor_uid']:<15} {ru:<20} {a['level']:<6} {text}")
            # Verify text matches DB
            db_text = t.task_text[:60] if t else 'MISSING'
            if a['statement'] != db_text:
                p(f"  TEXT MISMATCH: anchor={a['statement'][:60]}")
                p(f"                 db={db_text}")

    # ====== P4: Same for grade 6 and 11 ======
    p()
    p("=" * 70)
    p("P4a: Questionnaire grade 6")
    p("=" * 70)
    anchors6, _ = pick_anchors(6)
    p(f"{'#':<3} {'anchor_uid':<15} {'section_ru':<20} {'level':<6} {'text[:60]'}")
    p(f"{'-'*3} {'-'*15} {'-'*20} {'-'*6} {'-'*60}")
    for i, a in enumerate(anchors6, 1):
        ru = SECTION_NAMES_RU.get(a['section'], a['section'])
        p(f"{i:<3} {a['anchor_uid']:<15} {ru:<20} {a['level']:<6} {a['statement'][:60]}")

    p()
    p("=" * 70)
    p("P4b: Questionnaire grade 11")
    p("=" * 70)
    anchors11, _ = pick_anchors(11)
    p(f"{'#':<3} {'anchor_uid':<15} {'section_ru':<20} {'level':<6} {'text[:60]'}")
    p(f"{'-'*3} {'-'*15} {'-'*20} {'-'*6} {'-'*60}")
    for i, a in enumerate(anchors11, 1):
        ru = SECTION_NAMES_RU.get(a['section'], a['section'])
        p(f"{i:<3} {a['anchor_uid']:<15} {ru:<20} {a['level']:<6} {a['statement'][:60]}")

    # ====== P5: Correct answers -> mu per section ======
    p()
    p("=" * 70)
    p("P5: Correct answers — mu after each step")
    p("=" * 70)

    from services.level_engine import record_result, get_state, DEFAULT_MU, DEFAULT_SIGMA

    anchors9, _ = pick_anchors(9)
    for step_idx, a in enumerate(anchors9):
        section = a['section']
        correct = check_answer(a['answer'], a['answer'])
        result = record_result(1, section, int(a['level']), correct)
        state = get_state(1)
        by_sec = state.get('by_section', {})
        print_line = f"Step {step_idx+1}: {a['anchor_uid']} -> "
        for sec in ['algebra','number_theory','geometry','combinatorics','logic']:
            mu = by_sec.get(sec, {}).get('mu', float('nan'))
            print_line += f"{sec}={mu:.3f} "
        p(print_line)

    # ====== P6: Wrong answers -> mu drops ======
    p()
    p("=" * 70)
    p("P6: Wrong answer test (1 anchor)")
    p("=" * 70)
    wrong_result = record_result(1, 'algebra', 3, False)
    state = get_state(1)
    p(f"After wrong: algebra mu={state['by_section'].get('algebra',{}).get('mu',float('nan')):.3f}")
    p(f"  Global mu={state['mu']:.3f}")

    # ====== P7: Counter string ======
    p()
    p("=" * 70)
    p("P7: Counter")
    p("=" * 70)
    with open('templates/prep/onboarding.html', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if 'TOTAL_ANCHORS' in line or 'Якорь' in line:
                p(f"  line {i}: {line.rstrip()[:120]}")

    db.drop_all()

# ====== P8: regression_night.py ======
p()
p("=" * 70)
p("P8: regression_night.py output")
p("=" * 70)

import subprocess
try:
    result = subprocess.run(
        [sys.executable, 'regression_night.py'],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True, text=True, timeout=300,
        env={**os.environ, 'DATABASE_URL': 'sqlite:///formyla.db'}
    )
    # Extract D-lines and errors
    for line in result.stdout.split('\n'):
        if any(tag in line for tag in ['D1','D2','D3','D4','D5','S5','PASS','FAIL','ERROR','Итого','Всего']):
            p(line.rstrip()[:200])
        elif 'section' in line.lower() and 'counts' in line.lower():
            p(line.rstrip()[:200])
    p(f"Exit code: {result.returncode}")
    if result.returncode != 0:
        p("STDERR (last 20):")
        for line in result.stderr.split('\n')[-20:]:
            if line.strip():
                p(line.rstrip()[:200])
except Exception as e:
    p(f"FAILED: {e}")

p()
p("=" * 70)
p("DONE")
p("=" * 70)

with open('_proof_real.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))
print("Written to _proof_real.txt")
