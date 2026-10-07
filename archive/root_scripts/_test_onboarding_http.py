# -*- coding: utf-8 -*-
"""STEP 3+4: Complete onboarding HTTP flow via Flask test client."""
import sys
import json

# Import app first (before any IO redirection)
from app import app, db, User
from models_curator import CuratorState

UNKNOWN = '\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439'
USER_ID = 3


def main():
    client = app.test_client()

    # Direct session setup: set _user_id in session
    with client.session_transaction() as sess:
        sess['_user_id'] = str(USER_ID)
        sess['_fresh'] = True

    # Verify login
    r = client.get('/api/chat/unread_total')
    print("=" * 70)
    print(f"1. LOGIN: GET /api/chat/unread_total -> {r.status_code}")
    if r.status_code != 200:
        print(f"   Body: {r.get_data(as_text=True)[:200]}")
        print("   [FAIL]")
        return
    print("   [OK] Logged in as user", USER_ID)

    # -- 2. Cleanup --
    print()
    print("2. CLEANUP: POST /prep/onboarding/answer (_finish)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "_finish", "key": "_finish"})
    print(f"   status={r.status_code} body={r.get_data(as_text=True)[:300]}")

    # -- 3. START --
    print()
    print("3. START: POST /prep/onboarding/answer (_start)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "_start", "key": "_start"})
    assert r.status_code == 200, f"status={r.status_code}"
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    print(f"   step={data.get('step')}")
    print(f"   Body: {body[:500]}")
    assert data.get('step') == 'q1'
    assert UNKNOWN not in body
    print("   [OK]")

    # -- 4. Q1 -> olympiad --
    print()
    print("4. Q1: POST /prep/onboarding/answer (goal=olympiad)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "goal", "key": "olympiad"})
    assert r.status_code == 200
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    print(f"   step={data.get('step')} body={body[:500]}")
    assert data.get('step') == 'q2'
    assert UNKNOWN not in body
    print("   [OK]")

    # -- 5. Q2 -> region (valid key: "region", not "regional") --
    print()
    print("5. Q2: POST /prep/onboarding/answer (olymp_reach=region)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "olymp_reach", "key": "region"})
    assert r.status_code == 200
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    print(f"   step={data.get('step')} body={body[:500]}")
    assert data.get('step') == 'q3'
    assert UNKNOWN not in body
    print("   [OK]")

    # -- 6. Q3 -> m30 (valid key: "m30", not "medium") --
    print()
    print("6. Q3: POST /prep/onboarding/answer (load=m30)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "load", "key": "m30"})
    assert r.status_code == 200
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    print(f"   step={data.get('step')} body={body[:500]}")
    assert data.get('step') == 'q4'
    assert UNKNOWN not in body
    print("   [OK]")

    # -- 7. Q4 -> mid (valid key: "mid", not "6_months") --
    print()
    print("7. Q4: POST /prep/onboarding/answer (deadline=mid)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "deadline", "key": "mid"})
    assert r.status_code == 200
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    step = data.get('step')
    print(f"   step={step} body={body[:500]}")
    assert step in ('anchor1', 'anchor1_unavailable'), f"Unexpected step: {step}"
    assert UNKNOWN not in body
    print("   [OK]")

    if data.get('anchors_unavailable'):
        print("   [WARN] Anchors unavailable, skipping to finish")
        anchor_data = data
    else:
        anchor_data = data

    # -- 8. Anchor1 --
    if anchor_data.get('anchor') and anchor_data['anchor'].get('task_id'):
        tid = anchor_data['anchor']['task_id']
        print()
        print(f"8. ANCHOR1: POST /prep/onboarding/anchor (task_id={tid}, answer=0)")
        r = client.post('/prep/onboarding/anchor',
                        json={"task_id": tid, "answer": "0"})
        assert r.status_code == 200
        data = r.get_json()
        body = json.dumps(data, ensure_ascii=False)
        print(f"   step={data.get('step')} correct={data.get('correct')}")
        print(f"   Body: {body[:500]}")
        assert UNKNOWN not in body
        step = data.get('step')
        assert step in ('anchor2', 'anchor_done'), f"Unexpected step: {step}"

        # -- 9. Anchor2 --
        if data.get('anchor') and data['anchor'].get('task_id'):
            tid2 = data['anchor']['task_id']
            print()
            print(f"9. ANCHOR2: POST /prep/onboarding/anchor (task_id={tid2}, answer=1)")
            r = client.post('/prep/onboarding/anchor',
                            json={"task_id": tid2, "answer": "1"})
            assert r.status_code == 200
            data = r.get_json()
            body = json.dumps(data, ensure_ascii=False)
            print(f"   step={data.get('step')} correct={data.get('correct')}")
            print(f"   Body: {body[:500]}")
            assert UNKNOWN not in body
            assert data.get('finish_ready') == True
            print("   [OK]")
        elif data.get('finish_ready'):
            print()
            print("9. Anchor2 skipped (finish_ready)")
        else:
            print()
            print("9. Anchor2 skipped (no task)")
    else:
        print()
        print("8-9. ANCHORS SKIPPED")

    # -- 10. FINISH --
    print()
    print("10. FINISH: POST /prep/onboarding/answer (_finish)")
    r = client.post('/prep/onboarding/answer',
                    json={"qid": "_finish", "key": "_finish"})
    assert r.status_code == 200
    data = r.get_json()
    body = json.dumps(data, ensure_ascii=False)
    print(f"   done={data.get('done')}")
    print(f"   Body: {body[:800]}")
    assert UNKNOWN not in body
    assert data.get('done') == True
    assert data.get('result') is not None
    rres = data['result']
    print(f"   mu={rres.get('prior_mu')} sigma={rres.get('prior_sigma')} "
          f"start={rres.get('start_level')} test_len={rres.get('test_length')} "
          f"daily={rres.get('daily_tasks')} goal={rres.get('goal')}")
    print("   [OK] ONBOARDING COMPLETED!")

    # -- 11. DB check --
    print()
    print("11. DB CHECK: CuratorState.prep_state")
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=USER_ID).first()
        if cs and cs.prep_state:
            onb = cs.prep_state.get('onboarding', {})
            tq = cs.prep_state.get('test_queue', [])
            print(f"   onboarding: {json.dumps(onb, ensure_ascii=False)[:500]}")
            print(f"   test_queue ({len(tq)} items): {json.dumps(tq, ensure_ascii=False)[:300]}")
            print("   [OK]")
        else:
            print("   [WARN] No CuratorState or prep_state")

    print()
    print("=" * 70)
    print("ALL STEPS PASSED. No 4xx/5xx, no 'Unknown step'.")
    print("=" * 70)


if __name__ == '__main__':
    main()
