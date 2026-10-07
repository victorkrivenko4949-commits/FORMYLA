# -*- coding: utf-8 -*-
"""Acceptance test for onboarding rework using Flask test client."""
import json
import sys
from app import app, db
from models import User

def test_full_onboarding(target_key, deadline_val, label):
    """Run a full onboarding scenario via Flask test client (user 3)."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {label} (target={target_key}, deadline={deadline_val})")
    print(f"{'='*60}")

    with app.test_client() as client:
        with client.session_transaction() as sess:
            user = User.query.filter_by(id=3).first()
            if user:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
                print(f"0. Login as user id={user.id}, grade={getattr(user,'preferred_grade',None)}")
            else:
                print("0. ERROR: user 3 not found!")
                return

        # Step 1: Start onboarding
        r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
        data = r.get_json()
        print(f"1. Start: step={data.get('step')}, grade_auto={data.get('grade_auto')}")

        q = data.get('question', {})
        if q.get('id') == 'grade':
            r = client.post('/prep/onboarding/answer', json={'qid': 'grade', 'key': '9'})
            data = r.get_json()
            print(f"1b. Q1 grade=9: step={data.get('step')}")

        # Q2: target
        r = client.post('/prep/onboarding/answer', json={'qid': 'target', 'key': target_key})
        data = r.get_json()
        print(f"2. Q2 target={target_key}: step={data.get('step')}")

        # Q3: olymp_reach
        r = client.post('/prep/onboarding/answer', json={'qid': 'olymp_reach', 'key': 'region'})
        data = r.get_json()
        print(f"3. Q3 olymp_reach=region: step={data.get('step')}")

        # Q4: load
        r = client.post('/prep/onboarding/answer', json={'qid': 'load', 'key': 'm60'})
        data = r.get_json()
        print(f"4. Q4 load=m60: step={data.get('step')}")

        # Q5: deadline
        r = client.post('/prep/onboarding/answer', json={'qid': 'deadline', 'key': deadline_val})
        data = r.get_json()
        print(f"5. Q5 deadline={deadline_val}: step={data.get('step')}")
        sections_seen = set()

        if data.get('anchor'):
            a = data['anchor']
            sec = a.get('section', '?')
            sections_seen.add(sec)
            print(f"   Anchor 1: id={a['task_id']} section={sec} level={a.get('level')}")

            r = client.post('/prep/onboarding/anchor', json={'task_id': a['task_id'], 'answer': '0'})
            adata = r.get_json()
            print(f"6. Anchor 1 correct={adata.get('correct')}")

            if adata.get('anchor'):
                a2 = adata['anchor']
                sec2 = a2.get('section', '?')
                sections_seen.add(sec2)
                print(f"   Anchor 2: id={a2['task_id']} section={sec2} level={a2.get('level')}")

                r = client.post('/prep/onboarding/anchor', json={'task_id': a2['task_id'], 'answer': '0'})
                adata2 = r.get_json()
                print(f"7. Anchor 2 correct={adata2.get('correct')}")

                if adata2.get('anchor'):
                    a3 = adata2['anchor']
                    sec3 = a3.get('section', '?')
                    sections_seen.add(sec3)
                    print(f"   Anchor 3: id={a3['task_id']} section={sec3} level={a3.get('level')}")

                    r = client.post('/prep/onboarding/anchor', json={'task_id': a3['task_id'], 'answer': '0'})
                    adata3 = r.get_json()
                    print(f"8. Anchor 3 correct={adata3.get('correct')}")

        # Finish
        r = client.post('/prep/onboarding/answer', json={'qid': '_finish', 'key': '_finish'})
        fdata = r.get_json()
        print(f"9. Finish: done={fdata.get('done')}")

        if fdata.get('result'):
            res = fdata['result']
            print(f"   grade={res.get('grade')} target_level={res.get('target_level')}")
            print(f"   prior_mu={res.get('prior_mu')} sigma={res.get('prior_sigma')}")
            print(f"   start_level={res.get('start_level')} route_ceiling={res.get('route_ceiling')}")
            print(f"   deadline_bucket={res.get('deadline_bucket')}")

            anchors = res.get('anchors', [])
            print(f"\n   ┌─────┬──────────────────┬───────┬─────────┐")
            print(f"   │  №  │ Раздел           │ Уров. │ Correct │")
            print(f"   ├─────┼──────────────────┼───────┼─────────┤")
            for a in anchors:
                print(f"   │ {anchors.index(a)+1:>3} │ {a.get('section','?'):<16} │ {a.get('level','?'):>5} │ {str(a.get('correct')):>7} │")
            print(f"   └─────┴──────────────────┴───────┴─────────┘")
            print(f"   Unique sections: {len(sections_seen)} — {'[OK] 3 РАЗНЫХ' if len(sections_seen) >= 3 else ' < 3!'}")

            # DB state
            from models_curator import CuratorState
            cs = CuratorState.query.filter_by(user_id=3).first()
            if cs:
                print(f"\n   prep_state['onboarding']: " +
                      f"grade={cs.prep_state.get('onboarding',{}).get('grade') if cs.prep_state else '?'} " +
                      f"target_level={cs.prep_state.get('onboarding',{}).get('target_level') if cs.prep_state else '?'}")

                if cs.level_by_section:
                    try:
                        lbs = json.loads(cs.level_by_section)
                        print(f"   level_by_section ({len(lbs)} sections):")
                        for sec, val in lbs.items():
                            print(f"     {sec}: mu={val.get('mu',0):.2f} sigma={val.get('sigma',0):.2f} n={val.get('n',0)}")
                    except Exception:
                        print(f"   level_by_section: RAW")
                else:
                    print(f"   level_by_section: EMPTY")

        return {'sections': sections_seen, 'result': fdata.get('result', {})}


if __name__ == '__main__':
    with app.app_context():
        print("="*70)
        print("ONBOARDING ACCEPTANCE TESTS")
        print("="*70)

        r1 = test_full_onboarding('lvl2', 'none', 'target=lvl2')
        r2 = test_full_onboarding('lvl4', '2027-03-15', 'target=lvl4')
        r3 = test_full_onboarding('lvl5', '2026-11-01', 'target=lvl5')

        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        for label, r in [('lvl2', r1), ('lvl4', r2), ('lvl5', r3)]:
            if r:
                secs = r['sections']
                res = r.get('result', {})
                print(f"  {label}: sections={len(secs)} ({secs}) "
                      f"mu={res.get('prior_mu')} ceiling={res.get('route_ceiling')} "
                      f"deadline={res.get('deadline_bucket')}")
