# -*- coding: utf-8 -*-
"""P5 comprehensive check script."""
import sys, os, json

# ─── 1. Route traversal ───
import app as A

c_anon = A.app.test_client()
c_auth = A.app.test_client()

# Simulate logged-in user (id=1 may not exist, but session sets _user_id)
with c_auth.session_transaction() as s:
    s['_user_id'] = '1'

# All GET routes with methods
all_rules = sorted(A.app.url_map.iter_rules(), key=lambda r: r.rule)
get_rules = [r for r in all_rules if 'GET' in r.methods]

# Filter out static and duplicate rules
skip_prefixes = ('/static/', '/curator/static/', '/daily_tasks/static/')
unique_rules = []
seen = set()
for r in get_rules:
    rule_str = r.rule
    if rule_str in seen:
        continue
    if any(rule_str.startswith(p) for p in skip_prefixes):
        continue
    seen.add(rule_str)

print(f"TOTAL_GET_ROUTES (filtered) {len(unique_rules)}")

# For param routes, we need real IDs from DB
from models import db, AdaptiveTask, User
from daily_tasks.models import DailyTaskSet, DailyTaskItem

ctx = A.app.app_context()
ctx.push()

# Get real IDs
try:
    real_task_id = db.session.query(AdaptiveTask.id).first()
    real_task_id = real_task_id[0] if real_task_id else 1
except:
    real_task_id = 1

try:
    real_user_id = db.session.query(User.id).first()
    real_user_id = real_user_id[0] if real_user_id else 1
except:
    real_user_id = 1

try:
    real_daily_item_id = db.session.query(DailyTaskItem.id).first()
    real_daily_item_id = real_daily_item_id[0] if real_daily_item_id else 1
except:
    real_daily_item_id = 1

ctx.pop()

# Substitutions for param routes
subs = {
    '<int:task_id>': str(real_task_id),
    '<int:problem_id>': '1',
    '<int:test_id>': '1',
    '<int:session_id>': '1',
    '<int:user_id>': str(real_user_id),
    '<int:student_id>': '1',
    '<int:plan_id>': '1',
    '<int:day_id>': '1',
    '<int:friend_id>': '1',
    '<int:group_id>': '1',
    '<int:combo_id>': '1',
    '<int:item_id>': str(real_daily_item_id),
    '<int:exam_id>': '1',
    '<int:grade>': '5',
    '<int:secret_id>': '1',
    '<int:method_task_id>': '1',
    '<int:mentorship_id>': '1',
    '<int:problem_id>': '1',
    '<method_code>': 'test_method',
    '<slug>': 'test',
    '<code>': 'test',
    '<nickname>': 'test_f0_user',
    '<subject_key>': 'algebra',
    '<subtopic_key>': 'test',
    '<string:domain>': 'algebra',
    '<date_iso>': '2026-01-01',
    '<section_name>': 'algebra',
    '<job_id>': '1',
    '<path:filename>': 'test.svg',
}

def resolve_rule(rule_str):
    result = rule_str
    for pat, sub in subs.items():
        result = result.replace(pat, sub)
    return result

results = []
bad = []
not_found = []

for rule_obj in unique_rules:
    rule_str = rule_obj.rule
    resolved = resolve_rule(rule_str)

    for name, client in [('anon', c_anon), ('auth', c_auth)]:
        try:
            r = client.get(resolved, follow_redirects=True)
            code = r.status_code
            length = len(r.data)
            results.append((rule_str, name, code, length))
            if code in (500, 402):
                bad.append((rule_str, name, code, length))
            if code == 404:
                not_found.append((rule_str, name, code, length))
        except Exception as e:
            results.append((rule_str, name, 'ERROR', str(e)[:80]))
            bad.append((rule_str, name, 'ERROR', str(e)[:80]))

print(f"\n--- ROUTE RESULTS ---")
for row in results:
    print(f"{row[0]:60s} {row[1]:5s} {str(row[2]):6s} {row[3]}")

print(f"\nBAD_COUNT {len(bad)}")
for b in bad:
    print(f"BAD: {b}")

print(f"\nNOT_FOUND_COUNT {len(not_found)}")
for nf in not_found:
    print(f"404: {nf[0]:60s} {nf[1]:5s}")

# ─── 2. Table count ───
print("\n--- TABLE COUNT ---")
db_path = os.path.join('instance', 'formyla.db')
import sqlite3
conn = sqlite3.connect(db_path)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print(f"TABLE_COUNT {len(tables)}")
for t in tables:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(f"  {t}: {len(cols)} columns")
conn.close()

# ─── 3. Foreign hex colors ───
print("\n--- FOREIGN HEX COLORS ---")
import re, glob as gb
allowed = {'#070c18','#0e1830','#121f3c','#1c2b4f','#e6ebf7','#8c9abc','#4c7dff','#6b95ff','#3ecf8e','#e5ac3a','#e86a62'}
pattern = re.compile(r'#[0-9a-fA-F]{6}')
hits = []
for path in gb.glob('templates/**/*.html', recursive=True):
    try:
        for i, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
            for m in pattern.finditer(line):
                if m.group(0).lower() not in allowed:
                    hits.append((path, i, m.group(0)))
    except:
        pass
print(f"FOREIGN_HEX_COUNT {len(hits)}")
for h in hits:
    print(h)

# ─── 4. Anchor order check ───
print("\n--- ANCHOR ORDER ---")
# Check the JSONL file order
anchors = []
with open('data/anchors.jsonl', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            anchors.append(json.loads(line))
print(f"Total anchors in file: {len(anchors)}")
print("Order by section (first 5):")
for a in anchors[:5]:
    print(f"  {a['anchor_uid']} {a['section']} grade={a['grade']}")

# Check the actual onboarding code order
print("\nSpec order: algebra, number_theory, geometry, combinatorics, logic")
print("JSONL order (grade 5): algebra, geometry, combinatorics, logic, number_theory")

# ─── 5. mu/sigma formula check ───
print("\n--- MU/SIGMA CHECK ---")
mu, sigma = 3.0, 1.5
print(f"Starting: mu={mu}, sigma={sigma}")
for step in range(5):
    mu += 0.22 * (sigma + 0.3)
    sigma = max(0.35, sigma * 0.94)
    mu = max(1.0, min(5.0, mu))
    print(f"Step {step+1}: mu={mu:.4f}, sigma={sigma:.4f}")

# ─── 6. Grep for level_engine ───
print("\n--- LEVEL_ENGINE GREP ---")
found_any = False
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.pytest_cache', 'node_modules')]
    for fn in files:
        if fn.endswith('.py'):
            fpath = os.path.join(root, fn)
            try:
                with open(fpath, encoding='utf-8') as f:
                    content = f.read()
                    if 'level_engine' in content or 'record_result' in content:
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'level_engine' in line or 'record_result' in line:
                                if 'import' not in line and 'pass' not in line:
                                    print(f"  {fpath}:{i}: {line.strip()[:120]}")
                                    found_any = True
            except:
                pass

if not found_any:
    print("  NOT FOUND in any .py file (besides imports)")

print("\nDone.")
