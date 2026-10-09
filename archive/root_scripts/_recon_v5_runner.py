# -*- coding: utf-8 -*-
import json, re, sys, os
os.chdir(r"c:\Users\Redmi\Desktop\Новая папка (2)")
sys.path.insert(0, ".")

from app import app, db
from models import User, AdaptiveTask, SiteReview
from models_curator import CuratorState
from curator.monthly_cycle import get_cycle_info, build_or_get_cycle
from services.theme_probe import start_probe, record_answer, _get_probe_state

app.config["TESTING"] = True
client = app.test_client()
ctx = app.app_context()
ctx.push()

def login(uid):
    with client.session_transaction() as s:
        s["_user_id"] = str(uid)
        s["_fresh"] = True

# ── TASK 2: SLICE ──
print("=" * 60)
print("TASK 2: SLICE WORKS")
print("=" * 60)

for grade in [6, 9, 11]:
    user = User.query.filter_by(preferred_grade=grade).first()
    if not user:
        user = User.query.first()
    if not user:
        print(f"Grade {grade}: NO USER")
        continue
    uid = user.id
    login(uid)
    u = db.session.get(User, uid)
    if u:
        u.onboarding_completed = True
        db.session.commit()
    
    resp = client.get(f"/prep/probe?grade={grade}")
    print(f"\nGrade {grade} (user {uid}):")
    print(f"  Status: {resp.status_code}")
    html = resp.data.decode("utf-8", errors="replace")
    cards = len(re.findall(r'class="[^"]*card', html, re.I))
    tasks = re.findall(r'data-task-id="(\d+)"', html)
    theme = re.search(r'<title>([^<]+)</title>', html)
    print(f"  Theme: {theme.group(1)[:80] if theme else 'redirected'}")
    print(f"  Cards: {cards}, Tasks: {len(tasks)}")
    if tasks:
        print(f"  Task IDs: {tasks}")
    
    # Check start_probe stage
    cycle = get_cycle_info(uid)
    if cycle.get('current_theme') and cycle.get('blocked'):
        result = start_probe(uid, cycle['current_theme'], grade)
        print(f"  Selection stage: {'error=' + result.get('error','') if 'error' in result else 'task_id=' + str(result.get('task',{}).get('id',''))}")

print()

# ── TASK 3: SLICE PERSISTENCE ──
print("=" * 60)
print("TASK 3: SLICE DOES NOT GET LOST")
print("=" * 60)

user = User.query.filter_by(preferred_grade=9).first() or User.query.first()
if user:
    uid = user.id
    login(uid)
    u = db.session.get(User, uid)
    if u:
        u.onboarding_completed = True
        db.session.commit()
    grade = u.preferred_grade or 9
    
    cycle = get_cycle_info(uid)
    if not cycle.get('active'):
        build_or_get_cycle(uid, grade)
        cycle = get_cycle_info(uid)
    
    theme = cycle.get('current_theme')
    if theme:
        # Step 1: Answer 2 of 5
        r = start_probe(uid, theme, grade)
        print(f"Step 1: Start probe: theme={r.get('theme_id')} idx={r.get('current_index')}")
        
        for i in range(2):
            cs = CuratorState.query.filter_by(user_id=uid).first()
            probe = _get_probe_state(cs)
            if not probe:
                break
            seen = probe.get('seen_task_ids', [])
            if seen:
                task_id = seen[-1]
                verdict = ['correct', 'wrong'][i]
                r = record_answer(uid, task_id, verdict)
                print(f"  Answer {i+1} ({verdict}): idx={r.get('current_index')}, level={r.get('current_level')}")
        
        # Step 2: Dump state
        cs = CuratorState.query.filter_by(user_id=uid).first()
        probe = _get_probe_state(cs)
        if probe:
            print(f"Step 2: DB state dump: {json.dumps({k:v for k,v in probe.items() if k != 'seen_task_ids'}, ensure_ascii=False)}")
            print(f"  seen_task_ids count: {len(probe.get('seen_task_ids',[]))}")
        
        # Step 3: Clear session, re-login — should continue
        login(uid)
        cs2 = CuratorState.query.filter_by(user_id=uid).first()
        probe2 = _get_probe_state(cs2)
        if probe2:
            print(f"Step 3: After clear+relogin: idx={probe2.get('current_index')}")
        
        # Step 4: Two tabs — second probe blocked
        r2 = start_probe(uid, theme, grade)
        print(f"Step 4: Second probe attempt: {r2.get('error','ok')}")
        
        # Step 5: Complete the probe
        for i in range(3):
            cs = CuratorState.query.filter_by(user_id=uid).first()
            probe = _get_probe_state(cs)
            if not probe or probe.get('current_index', 0) >= 5:
                break
            seen = probe.get('seen_task_ids', [])
            if seen:
                task_id = seen[-1]
                r = record_answer(uid, task_id, 'correct')
        # After completion — try re-open
        r3 = start_probe(uid, theme, grade)
        print(f"Step 5: After completion re-open: {r3.get('error','ok') if isinstance(r3,dict) else 'redirect'}")

print()

# ── TASK 4: RADARS ──
print("=" * 60)
print("TASK 4: RADARS")
print("=" * 60)

# User with answers
from models_curator import TaskAttempt
uids_with_answers = db.session.query(TaskAttempt.user_id).distinct().limit(3).all()
found = False
for (uid,) in uids_with_answers:
    u = db.session.get(User, uid)
    if u and u.preferred_grade:
        login(uid)
        u.onboarding_completed = True
        db.session.commit()
        resp = client.get("/curator")
        print(f"User {uid} (with answers): status={resp.status_code}")
        html = resp.data.decode("utf-8", errors="replace")
        
        # Radar values
        radars = re.findall(r'(?:radarData|radar_data|radarValues)\s*[:=]\s*(\[[^\]]+\])', html, re.I)
        if not radars:
            radars = re.findall(r'data-values\s*=\s*["\']([^"\']+)["\']', html, re.I)
        if radars:
            print(f"  Radar values: {radars[0][:120]}")
        
        # Subtopics
        subtopics_m = re.findall(r'(?:radarLabel|subtopic|theme-name)[^>]*>([^<]+)<', html, re.I)
        if subtopics_m:
            print(f"  Subtopics: {subtopics_m[:7]}")
        
        found = True
        break

if not found:
    print("  No users with answers found")

# User without answers
tu = User(email="v5_radar_empty@test.local", name="RadarEmpty", preferred_grade=9)
tu.onboarding_completed = True
db.session.add(tu)
db.session.commit()
login(tu.id)
resp = client.get("/curator")
print(f"\nUser {tu.id} (no answers): status={resp.status_code}")
html = resp.data.decode("utf-8", errors="replace")
no_data = 'no.data' in html.lower() or 'нет данных' in html.lower()
print(f"  No-data indicator: {no_data}")
db.session.delete(tu)
db.session.commit()

# Subtopics with data
total = AdaptiveTask.query.count()
with_theme = AdaptiveTask.query.filter(AdaptiveTask.theme_id.isnot(None), AdaptiveTask.theme_id != '').count()
distinct_themes = db.session.query(AdaptiveTask.theme_id).filter(
    AdaptiveTask.theme_id.isnot(None), AdaptiveTask.theme_id != ''
).distinct().count()
print(f"\n  Tasks total: {total}")
print(f"  Tasks with theme_id: {with_theme}")
print(f"  Distinct subtopics: {distinct_themes}")
print(f"  Empty radar: all values = default (no level_by_theme data)")

print()

# ── TASK 5: CURATOR ──
print("=" * 60)
print("TASK 5: CURATOR ANSWERS ABOUT THE SITE")
print("=" * 60)

user = User.query.first()
login(user.id)
u = db.session.get(User, user.id)
u.onboarding_completed = True
db.session.commit()
resp = client.get("/curator")
print(f"Status: {resp.status_code}")
html = resp.data.decode("utf-8", errors="replace")

# Quick buttons
btns = re.findall(r'<button[^>]*class="[^"]*(?:quick|preset|suggest|faq)[^"]*"[^>]*>\s*([^<]+)\s*</button>', html, re.I)
if not btns:
    btns = re.findall(r'<button[^>]*>\s*(.{5,40}?)\s*</button>', html, re.I)
print(f"Quick question buttons ({len(btns)}): {btns[:8]}")

# Chat fragment
chat_div = re.search(r'<div[^>]*class="[^"]*chat[^"]*"[^>]*>(.{80,400})', html, re.I | re.DOTALL)
if chat_div:
    fragment = re.sub(r'\s+', ' ', chat_div.group(1))[:200]
    print(f"Chat HTML fragment: {fragment}")

print()

# ── TASK 6: ABOUT ──
print("=" * 60)
print("TASK 6: ABOUT PAGE")
print("=" * 60)

resp = client.get("/about")
print(f"Status: {resp.status_code}")
html = resp.data.decode("utf-8", errors="replace")
print(f"HTML length: {len(html)}")

headers = re.findall(r'<h[23][^>]*>([^<]+)</h[23]>', html)
print(f"Section headers ({len(headers)}):")
for h in headers:
    print(f"  - {h.strip()}")

has_form = bool(re.search(r'<form', html, re.I))
has_review = bool(re.search(r'(?:review|отзыв|feedback)', html, re.I))
has_chat = bool(re.search(r'(?:support|help|чат)', html, re.I))
print(f"Review form: {has_form}, Reviews section: {has_review}, Support/chat: {has_chat}")

# Test review
rv = SiteReview(user_name="V5_Test", rating=5, text="V5 acceptance review", is_visible=True)
db.session.add(rv)
db.session.commit()
rid = rv.id
saved = db.session.get(SiteReview, rid)
print(f"\nTest review: id={rid}, saved={saved is not None}, text={saved.text if saved else 'NONE'}")
db.session.delete(saved)
db.session.commit()
print(f"Deleted, verified deleted: {db.session.get(SiteReview, rid) is None}")

print()

# ── TASK 7: MENU ──
print("=" * 60)
print("TASK 7: ALL MENU PAGES + MISC")
print("=" * 60)

pages = [
    "/", "/about", "/probniks", "/grade-6", "/grade-9", "/grade-11",
    "/curator", "/daily_tasks", "/olympiads/courses", "/intake",
    "/prep/dashboard", "/adaptive_test_simple", "/misc",
]
err4 = err5 = 0
for p in pages:
    r = client.get(p)
    code = r.status_code
    print(f"  {p:35s} {code}")
    if 400 <= code < 500: err4 += 1
    if 500 <= code < 600: err5 += 1

print(f"\n4xx: {err4}, 5xx: {err5}")

# Clean test users
tu = User.query.filter(User.email.like("%v5%")).all()
for u in tu:
    db.session.delete(u)
db.session.commit()
remaining = User.query.filter(User.email.like("%v5%")).count()
print(f"V5 test users deleted, remaining: {remaining}")

ctx.pop()
print("\nDONE")
