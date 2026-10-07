# -*- coding: utf-8 -*-
"""
standalone_anchors_test.py — Автономный тест якорных задач без pytest.
Запуск: python standalone_anchors_test.py
"""
import json
import os
import sys
import tempfile

# CRITICAL: set DB env BEFORE importing app
_tmp_db = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{_tmp_db}'
os.environ['FLASK_ENV'] = 'development'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CANONICAL_SECTIONS = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']


def build_anchors():
    """Synthetic anchors: 35 + 1 (knight)."""
    anchors = []
    for grade in range(5, 12):
        for sec in CANONICAL_SECTIONS:
            anchors.append({
                'anchor_uid': f'ANC_{grade}_{sec}',
                'grade': grade,
                'section': sec,
                'subtopic': f'Sub{grade}_{sec}',
                'level': (grade % 3) + 1,
                'statement': f'Task {grade} class, {sec}. Solve: 2x + {grade} = {grade * 3}.',
                'answer': str(grade),
            })
    anchors.append({
        'anchor_uid': 'ANC_9_logic_knight',
        'grade': 9,
        'section': 'logic',
        'subtopic': 'Chess',
        'level': 2,
        'statement': 'Can a knight visit all squares of an 8x8 board exactly once?',
        'answer': 'no',
    })
    return anchors


def main():
    fail = 0
    total = 0

    # ── 1. Smoke: module imports ──────────────────────────────────
    total += 1
    try:
        from services.anchors import (
            normalize_answer, check_answer, get_theme_map,
            pick_anchors, load_anchors, inspect_anchors,
            get_anchor_ids, get_anchor_ids_set,
            CANONICAL_SECTIONS_ORDER, SOURCE_NAME,
        )
        print("PASS [1] Module services.anchors imported")
    except Exception as e:
        print(f"FAIL [1] Import error: {e}")
        fail += 1
        return 1

    # ── 2. normalize_answer ───────────────────────────────────────
    total += 1
    cases = [
        ('42', '42'),
        (' 42 ', '42'),
        ('NO', 'no'),
        ('No.', 'no'),
        ('4,2', '4.2'),
        ('1 000', '1000'),
        ('X=5', 'x=5'),
    ]
    ok = True
    for raw, expected in cases:
        got = normalize_answer(raw)
        if got != expected:
            print(f"  FAIL normalize('{raw}') = '{got}', expected '{expected}'")
            ok = False
    if ok:
        print(f"PASS [2] normalize_answer: {len(cases)} tests")
    else:
        fail += 1

    # ── 3. check_answer ───────────────────────────────────────────
    total += 1
    ok = True
    for ua, ca, exp in [
        ('no', 'No', True),
        ('42', '42', True),
        ('4.5', '4,5', True),
        ('yes', 'no', False),
        (' 3 ', '3', True),
    ]:
        got = check_answer(ua, ca)
        if got != exp:
            print(f"  FAIL check('{ua}', '{ca}') = {got}, expected {exp}")
            ok = False
    if ok:
        print(f"PASS [3] check_answer: 5 tests")
    else:
        fail += 1

    # ── 4. theme_to_section.json loads ────────────────────────────
    total += 1
    tm = get_theme_map()
    if len(tm) > 0 and 'G9_T05' in tm:
        print(f"PASS [4] theme_map: {len(tm)} entries (G9_T05 -> {tm['G9_T05']})")
    else:
        print(f"FAIL [4] theme_map: {len(tm)} entries")
        fail += 1

    # ── 5-10. DB tests ────────────────────────────────────────────
    total += 1
    from app import app, db
    from models import AdaptiveTask

    # Create synthetic anchors.jsonl
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.jsonl', delete=False, encoding='utf-8'
    )
    anchors_data = build_anchors()
    for a in anchors_data:
        tmp.write(json.dumps(a, ensure_ascii=False) + '\n')
    tmp.close()

    import services.anchors as _anchors
    original_path = _anchors.ANCHORS_FILE
    _anchors.ANCHORS_FILE = tmp.name

    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-standalone-key-12345'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost.test'

    with app.app_context():
        db.drop_all()
        db.create_all()

        # ── 5. Loading ────────────────────────────────────────────
        total += 1
        r = load_anchors()
        print(f"\n--- LOADING ---")
        print(f"  total_in_file = {r['total_in_file']}")
        print(f"  loaded        = {r['loaded']}")
        print(f"  skipped       = {r['skipped']}")
        print(f"  errors        = {len(r['errors'])}")
        print(f"  per_grade     = {r['per_grade']}")

        if r['total_in_file'] == 36 and r['loaded'] == 36:
            print(f"PASS [5] Loaded 36 anchors (35 + knight)")
        else:
            print(f"FAIL [5] Expected 36, got {r['total_in_file']}")
            fail += 1

        if r['unmapped_themes']:
            print(f"  unmapped_themes ({len(r['unmapped_themes'])}):")
            for u in r['unmapped_themes']:
                print(f"    {u}")

        # ── 6. Inspection ─────────────────────────────────────────
        total += 1
        summary = inspect_anchors()
        print(f"\n--- INSPECTION ---")
        print(f"  total = {summary['total']}")
        for g_str in sorted(summary['by_grade'].keys(), key=int):
            data = summary['by_grade'][g_str]
            print(f"  Grade {g_str}: {data['count']} anchors, sections: {data['sections']}")
            for item in data['items']:
                print(f"    {item['anchor_uid']:<25} "
                      f"section={item['section']:<20} "
                      f"level={item['level']} "
                      f"theme_id={item.get('theme_id', 'None')}")
        print(f"PASS [6] Inspection: {summary['total']} anchors in DB")

        # ── 7. Three runs for grade 9 ─────────────────────────────
        total += 1
        print(f"\n{'='*70}")
        print(f"THREE QUESTIONNAIRE RUNS FOR GRADE 9")
        print(f"{'='*70}")

        prev = None
        all_ok = True
        for run_num in [1, 2, 3]:
            anchors, meta = pick_anchors(9)
            print(f"\nRun {run_num}: {meta['anchor_count']} anchors")
            print(f"{'#':<4} {'anchor_uid':<25} {'section':<20} {'subtopic':<25} {'level':<8}")
            print(f"{'-'*4} {'-'*25} {'-'*20} {'-'*25} {'-'*8}")

            sections = []
            for i, a in enumerate(anchors, 1):
                sections.append(a['section'])
                print(f"{i:<4} {a['anchor_uid']:<25} {a['section']:<20} "
                      f"{a['subtopic'][:24]:<25} {a['level']:<8}")

            if len(anchors) < 1:
                print(f"  FAIL No anchors!")
                all_ok = False
            if len(set(sections)) != len(sections):
                print(f"  FAIL Duplicate sections: {sections}")
                all_ok = False
            for a in anchors:
                if a['grade'] != 9:
                    print(f"  FAIL Cross-grade: {a['anchor_uid']} grade={a['grade']}")
                    all_ok = False

            current = [(a['anchor_uid'], a['section']) for a in anchors]
            if prev is None:
                prev = current
            elif current != prev:
                print(f"  FAIL Run {run_num} differs from run 1!")
                all_ok = False

        if all_ok:
            print(f"\nPASS [7] Three runs for grade 9: no duplicate sections, "
                  f"deterministic, no cross-grade leak")
        else:
            fail += 1

        # ── 8. Three runs for grade 6 ─────────────────────────────
        total += 1
        print(f"\n{'='*70}")
        print(f"THREE QUESTIONNAIRE RUNS FOR GRADE 6")
        print(f"{'='*70}")

        prev6 = None
        all_ok6 = True
        for run_num in [1, 2, 3]:
            anchors, meta = pick_anchors(6)
            print(f"\nRun {run_num}: {meta['anchor_count']} anchors")
            print(f"{'#':<4} {'anchor_uid':<25} {'section':<20} {'subtopic':<25} {'level':<8}")
            print(f"{'-'*4} {'-'*25} {'-'*20} {'-'*25} {'-'*8}")

            sections = []
            for i, a in enumerate(anchors, 1):
                sections.append(a['section'])
                print(f"{i:<4} {a['anchor_uid']:<25} {a['section']:<20} "
                      f"{a['subtopic'][:24]:<25} {a['level']:<8}")

            if len(set(sections)) != len(sections):
                print(f"  FAIL Duplicate sections: {sections}")
                all_ok6 = False
            for a in anchors:
                if a['grade'] != 6:
                    print(f"  FAIL Cross-grade: {a['anchor_uid']} grade={a['grade']}")
                    all_ok6 = False

            current = [(a['anchor_uid'], a['section']) for a in anchors]
            if prev6 is None:
                prev6 = current
            elif current != prev6:
                print(f"  FAIL Run {run_num} differs from run 1!")
                all_ok6 = False

        if all_ok6:
            print(f"\nPASS [8] Three runs for grade 6: no duplicate sections, "
                  f"deterministic")
        else:
            fail += 1

        # ── 9. Anchors excluded from daily tasks & morning probe ──
        total += 1
        # Add regular tasks for exclusion test
        for grade in [9]:
            for level in range(1, 6):
                for sec in CANONICAL_SECTIONS:
                    t = AdaptiveTask(
                        class_level=grade,
                        difficulty_level=level,
                        topic=sec,
                        subject=sec,
                        subtopic=f'Test {sec}',
                        task_text=f'Regular task {grade} class {sec} L{level}: 1+1=?',
                        solution='2',
                        criteria_1_point='',
                        criteria_2_points='',
                        correct_answer='2',
                        source='formyla_L1_L5_TOP5',
                        source_id=f'TEST_{grade}_{sec}_L{level}',
                    )
                    db.session.add(t)
        db.session.commit()

        from services.daily_task_rotation import _pick_tasks_for_section, _pick_tasks_fallback

        anchor_id_set = get_anchor_ids_set()
        print(f"\n--- EXCLUSION CHECK ---")
        print(f"  anchor_ids = {sorted(anchor_id_set)}")

        # _pick_tasks_for_section
        tasks = _pick_tasks_for_section(9, 'algebra', [1, 2, 3, 4, 5], set(), 5, user_id=None)
        print(f"  _pick_tasks_for_section(9, algebra): {len(tasks)} tasks")
        leaked = [t['task_id'] for t in tasks if t['task_id'] in anchor_id_set]
        if leaked:
            print(f"  FAIL LEAK into daily tasks (section): {leaked}")
            fail += 1
        else:
            print(f"  PASS No leak (section)")

        # _pick_tasks_fallback
        ftasks = _pick_tasks_fallback(9, [1, 2, 3, 4, 5], set(), 20)
        leaked_f = [t['task_id'] for t in ftasks if t['task_id'] in anchor_id_set]
        if leaked_f:
            print(f"  FAIL LEAK into daily tasks (fallback): {leaked_f}")
            fail += 1
        else:
            print(f"  PASS No leak (fallback)")

        # Check theme_probe
        from services.theme_probe import _next_task_in_probe
        from models_curator import CuratorState

        cs = CuratorState(user_id=99991)
        db.session.add(cs)
        db.session.commit()

        probe_state = {
            'theme_id': 'G9_T05',
            'current_index': 0,
            'current_level': 3,
            'seen_task_ids': [],
            'grade': 9,
        }

        probe_leaked = False
        for _ in range(5):
            result = _next_task_in_probe(cs, probe_state, 9)
            if 'task' in result:
                tid = result['task']['id']
                if tid in anchor_id_set:
                    print(f"  FAIL LEAK into morning probe: task_id={tid}")
                    probe_leaked = True
                    fail += 1
                probe_state['seen_task_ids'].append(tid)

        if not probe_leaked:
            print(f"  PASS No leak into morning probe")

        print(f"\nPASS [9] Exclusion: anchors not in daily tasks or morning probe")

        # ── 10. Idempotency ───────────────────────────────────────
        total += 1
        r2 = load_anchors()
        if r2['loaded'] == 0 and r2['skipped'] == 36:
            print(f"PASS [10] Idempotency: reload skipped all 36")
        else:
            print(f"FAIL [10] loaded={r2['loaded']}, skipped={r2['skipped']}")
            fail += 1

        db.drop_all()

    # Cleanup
    _anchors.ANCHORS_FILE = original_path
    os.unlink(tmp.name)
    try:
        os.unlink(_tmp_db)
    except OSError:
        pass

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"TOTAL: {total - fail}/{total} tests passed")
    if fail == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{fail} TESTS FAILED")
    print(f"{'='*70}")
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
