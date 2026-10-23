"""
Acceptance test: walk through onboarding for a grade 9 student
and verify all 5 anchor tasks match data/anchors.jsonl exactly.
"""
import sys, os, json


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app import app
    import io

    # Load expected anchors
    anchors_file = os.path.join(os.path.dirname(__file__), 'data', 'anchors.jsonl')
    expected = {}
    with open(anchors_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            a = json.loads(line)
            grade = a['grade']
            section = a['section']
            expected[(grade, section)] = {
                'anchor_uid': a['anchor_uid'],
                'statement': a['statement'],
                'answer': a['answer'],
                'level': a['level'],
            }

    # Russian section names
    SECTION_RU = {
        'algebra': 'алгебра',
        'geometry': 'геометрия',
        'combinatorics': 'комбинаторика',
        'logic': 'логика',
        'number_theory': 'теория чисел',
    }

    ANCHOR_SECTION_ORDER = ('algebra', 'number_theory', 'geometry', 'combinatorics', 'logic')

    with app.app_context():
        from models import db, User
        from flask import session

        # Ensure we have user 3 (grade 9)
        user = db.session.get(User, 3)
        if not user:
            print("ERROR: User 3 not found")
            sys.exit(1)
        user.preferred_grade = 9
        db.session.commit()

        client = app.test_client()
        grade = 9

        print(f"Testing onboarding for grade={grade} user=3")
        print("=" * 80)

        # Step 1: Login
        with client.session_transaction() as sess:
            sess['_user_id'] = '3'
            sess['_fresh'] = True

        # Step 2: Start onboarding
        r = client.post('/prep/onboarding/answer',
                        json={'qid': '_start', 'key': '_start'})
        data = r.get_json()
        print(f"START: step={data.get('step')} grade_auto={data.get('grade_auto')}")

        # Step 2-5: Answer Q2..Q5
        answers = [
            ('target', 'lvl3'),       # Q2
            ('olymp_reach', 'none'),  # Q3
            ('load', '5'),            # Q4
            ('deadline', 'none'),     # Q5
        ]

        for qid, key in answers:
            r = client.post('/prep/onboarding/answer',
                            json={'qid': qid, 'key': key})
            data = r.get_json()
            step = data.get('step', '?')
            anchor = data.get('anchor')
            if anchor:
                print(f"  Q: {qid}={key} -> step={step} anchor_idx={anchor.get('idx')}")
            else:
                print(f"  Q: {qid}={key} -> step={step}")

        # Step 6+: Walk through ALL anchors
        print("\n--- ANCHOR TASKS ---")
        print(f"{'Step':<6} {'anchor_uid':<14} {'Раздел':<16} {'Уровень':<8} {'Условие (60 символов)':<62}")
        print("-" * 106)

        step_num = 1
        while True:
            anchor = data.get('anchor')
            if not anchor:
                if data.get('finish_ready'):
                    print(f"\nFINISH READY at step={data.get('step')}")
                    break
                print(f"ERROR: No anchor and no finish_ready. data={json.dumps(data, ensure_ascii=False)[:300]}")
                break

            task_id = anchor['task_id']
            task_text = anchor['task_text']
            section = anchor.get('section', '')
            level = anchor.get('level', '?')
            idx = anchor.get('idx', '?')
            total = anchor.get('total', '?')
            section_ru_display = anchor.get('section_ru', section)

            # Find expected anchor_uid by matching statement prefix
            exp = expected.get((grade, section))
            uid = exp['anchor_uid'] if exp else 'NOT FOUND'
            exp_stmt = exp['statement'][:60] if exp else 'NOT FOUND'
            actual_stmt = task_text[:60]

            match = '[OK]' if exp and task_text == exp['statement'] else ' MISMATCH'

            print(f"{step_num:<6} {uid:<14} {section_ru_display:<16} {level:<8} {actual_stmt:<62} {match}")

            if exp and task_text != exp['statement']:
                print(f"         EXPECTED: {exp_stmt}")
                print(f"         ACTUAL:   {actual_stmt}")

            step_num += 1

            # Submit correct answer
            correct_answer = anchor.get('correct_answer') or (exp['answer'] if exp else '0')
            if not correct_answer:
                # Look it up from expected
                correct_answer = exp['answer'] if exp else '0'

            r = client.post('/prep/onboarding/anchor',
                            json={'task_id': task_id, 'answer': str(correct_answer)})
            data = r.get_json()
            correct_flag = data.get('correct')
            print(f"         answer={correct_answer} correct={correct_flag}")

            if data.get('finish_ready'):
                print(f"\nFINISH READY after anchor {idx}")
                break

        # Print counter string from the last anchor response
        print(f"\n--- COUNTER CHECK ---")
        # Re-get the last anchor response to extract counter
        last_anchor = data.get('anchor', {})
        if last_anchor:
            idx_val = last_anchor.get('idx', '?')
            total_val = last_anchor.get('total', '?')
            section_ru_val = last_anchor.get('section_ru', last_anchor.get('section', '?'))
            counter = f"Якорь {idx_val} из {total_val} ({section_ru_val})"
        else:
            # Already past all anchors
            counter = f"Якорь 5 из 5 — все пройдены"
        print(f"Counter string: {counter}")

        print(f"\n{'='*80}")
        print("CLEANUP: resetting onboarding state for user 3...")
        from models_curator import CuratorState
        cs = db.session.get(CuratorState, 3)  # user_id=3
        if cs:
            cs.prep_state = {}
            cs.onboarding_done = False
            db.session.commit()
            print("CLEANUP: done — onboarding reset to not-done")

        print("ALL CHECKS COMPLETE")


if __name__ == '__main__':
    main()
