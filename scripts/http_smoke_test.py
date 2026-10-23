#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HTTP smoke test — uses Flask session cookie to identify current task."""
import sys, os, json, sqlite3, requests, re, hmac, hashlib, base64, zlib
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

BASE = "http://127.0.0.1:5000"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")
JSONL = os.path.join(ROOT, "FORMYLA_L1_L5_TOP5.jsonl")
from dotenv import load_dotenv
_dotenv_path = os.path.join(ROOT, '.env')
if os.path.exists(_dotenv_path):
    load_dotenv(_dotenv_path)
SECRET = os.environ.get('SECRET_KEY', 'dev-secret-key-LOCAL-ONLY-NOT-FOR-PRODUCTION')

def log(msg):
    sys.stdout.write(f"[smoke] {msg}\n"); sys.stdout.flush()

def banner(t):
    sys.stdout.write(f"\n{'='*60}\n  {t}\n{'='*60}\n"); sys.stdout.flush()

# Load JSONL
TASKS = {}
with open(JSONL, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        t = json.loads(line)
        TASKS[t['task_uid']] = t

def db_state(uid):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT level_mu, level_sigma, level_by_section, prep_state FROM curator_state WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"mu": None, "sigma": None, "by_section": {}, "prep_state": {}}
    bs = json.loads(row["level_by_section"]) if row["level_by_section"] else {}
    ps = json.loads(row["prep_state"]) if row["prep_state"] else {}
    return {"mu": row["level_mu"], "sigma": row["level_sigma"], "by_section": bs, "prep_state": ps}

def get_session_data(session_cookie):
    """Decode Flask signed session cookie."""
    try:
        s = URLSafeTimedSerializer(SECRET, salt='cookie-session',
                                   signer_kwargs={'key_derivation': 'hmac'},
                                   serializer=TaggedJSONSerializer())
        return s.loads(session_cookie)
    except Exception as e:
        log(f"Session decode failed: {e}")
        return {}

def get_current_task_from_session(sess):
    """Extract current task_uid from session cookie."""
    cookie = sess.cookies.get('session', '')
    if not cookie:
        return None
    data = get_session_data(cookie)
    uid = data.get('olyad_current_task', '')
    return uid if uid else None

s = requests.Session()

def main():
    uid = 1

    banner("1. LOGIN")
    s.get(f"{BASE}/dev_login?uid=1", allow_redirects=True)
    log("Done")

    banner("2. DB BEFORE")
    bef = db_state(uid)
    log(f"mu={bef['mu']}  bs={json.dumps(bef['by_section'], ensure_ascii=False)}")

    banner("3. START TEST")
    s.get(f"{BASE}/olympiad-test?length=10&level_hint=2&scope=all_sections")
    r = s.get(f"{BASE}/olympiad-test/select-section?grade=7", allow_redirects=True)
    log(f"After select-section: {r.status_code}")

    if 'olympiad_test_run' not in (r.text or ''):
        # Manual fallback: go direct to start
        r = s.get(f"{BASE}/olympiad-test/start?grade=7", allow_redirects=True)
        log(f"Direct start: {r.status_code}")

    banner("4. ANSWER 10 TASKS")
    sections = {}

    for i in range(1, 11):
        should_correct = (i <= 7)

        if i > 1:
            r = s.get(f"{BASE}/olympiad-test/start", allow_redirects=True)

        # Decode session to get task_uid
        task_uid = get_current_task_from_session(s)
        if task_uid and task_uid in TASKS:
            t = TASKS[task_uid]
            ans_to_send = (t.get('answer', '') or '').strip() if should_correct else "WRONG_ANSWER_99999"
            sec = (t.get('section', '') or '').strip()
            lvl = t.get('level', 2)
        else:
            # Fallback: try statement matching
            import re as _re
            m = _re.search(r'font-size:\s*1\.05em.*?<div[^>]*>(.*?)</div>', (r.text or '').replace('\n',' '), _re.DOTALL)
            if not m:
                m = _re.search(r'1\.05em[^>]*>\s*(.{30,}?)\s*</div>', (r.text or '').replace('\n',' '), _re.DOTALL)
            if m:
                stmt = _re.sub(r'<[^>]+>', '', m.group(1)).strip()[:120].replace('\n',' ').replace('\r',' ')
                best, best_len = None, 0
                for uid2, t2 in TASKS.items():
                    ts = (t2.get('statement','') or '').strip()[:120].replace('\n',' ').replace('\r',' ')
                    c = sum(1 for a,b in zip(stmt, ts) if a==b)
                    if c > best_len and c >= 30:
                        best_len, best = c, uid2
                if best:
                    t = TASKS[best]
                    ans_to_send = (t.get('answer','') or '').strip() if should_correct else "WRONG_ANSWER_99999"
                    sec = (t.get('section','') or '').strip()
                    lvl = t.get('level', 2)
                    log(f"  #{i:2d} matched statement (len={best_len}, uid={best[:16]}...)")
                else:
                    ans_to_send = "0"
                    sec, lvl = "unknown", 2
                    log(f"  #{i:2d} match FAILED (best_len={best_len})")
            else:
                ans_to_send = "0"
                sec, lvl = "unknown", 2
                log(f"  #{i:2d} div not found")
        if task_uid:
            log(f"  #{i:2d} session uid={task_uid[:16]}... sec={sec} L{lvl}")

        r = s.post(f"{BASE}/olympiad-test/start", data={'answer': ans_to_send, 'solution': ''},
                   allow_redirects=True)
        ok = 'pravilno' in (r.text or '').lower() or 'correct' in (r.text or '').lower()
        sections[sec] = sections.get(sec, 0) + 1
        log(f"  #{i:2d} | {sec:<20s} L{lvl} {'OK' if ok else 'WRONG'} (want {'OK' if should_correct else 'WRONG'})")

    banner("5. DB AFTER")
    aft = db_state(uid)
    log(f"mu={aft['mu']}  bs={json.dumps(aft['by_section'], ensure_ascii=False)}")

    banner("6. PREP_STATE")
    ps = aft['prep_state']
    log(f"test_queue: {ps.get('test_queue','N/A')}")
    log(f"last_test:  {json.dumps(ps.get('last_test',{}), ensure_ascii=False)}")

    banner("7. SUMMARY")
    log(f"Tasks: {sum(sections.values())}")
    log(f"Sections: {json.dumps(sections, ensure_ascii=False)}")
    log(f"mu: {bef['mu']} -> {aft['mu']}")
    if bef['mu'] is not None and aft['mu'] is not None:
        log(f"  delta: {aft['mu']-bef['mu']:+.3f}")

    return 0

if __name__ == '__main__':
    sys.exit(main())
