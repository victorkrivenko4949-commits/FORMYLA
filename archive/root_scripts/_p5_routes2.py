# -*- coding: utf-8 -*-
"""P5 route traversal - fixed version."""
import app as A

c_anon = A.app.test_client()
c_auth = A.app.test_client()

with c_auth.session_transaction() as s:
    s['_user_id'] = '1'

# Get real IDs from live DB
ctx = A.app.app_context()
ctx.push()
from models import db, AdaptiveTask, User
from daily_tasks.models import DailyTaskItem

try:
    r_task = db.session.query(AdaptiveTask.id).first()
    real_task_id = r_task[0] if r_task else 1
except:
    real_task_id = 1

try:
    r_user = db.session.query(User.id).first()
    real_user_id = r_user[0] if r_user else 1
except:
    real_user_id = 1

try:
    r_ditem = db.session.query(DailyTaskItem.id).first()
    real_ditem_id = r_ditem[0] if r_ditem else 1
except:
    real_ditem_id = 1

ctx.pop()

# All rules with GET
rules = [r for r in A.app.url_map.iter_rules() if 'GET' in r.methods]
# Deduplicate by rule string
seen = set()
unique_rules = []
for r in rules:
    if r.rule not in seen:
        seen.add(r.rule)
        unique_rules.append(r)

# Skip static
skip_prefixes = ('/static/', '/curator/static/', '/daily_tasks/static/')
filtered = [r for r in unique_rules if not any(r.rule.startswith(p) for p in skip_prefixes)]

print(f"TOTAL_GET_ROUTES: {len(filtered)}")

# Substitutions
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
    '<int:item_id>': str(real_ditem_id),
    '<int:exam_id>': '1',
    '<int:grade>': '5',
    '<int:secret_id>': '1',
    '<int:method_task_id>': '1',
    '<int:mentorship_id>': '1',
    '<method_code>': 'test_method',
    '<slug>': 'test',
    '<code>': 'test',
    '<nickname>': 'test_user',
    '<subject_key>': 'algebra',
    '<subtopic_key>': 'test',
    '<string:domain>': 'algebra',
    '<date_iso>': '2026-01-01',
    '<section_name>': 'algebra',
    '<job_id>': '1',
    '<path:filename>': 'test.svg',
}

def resolve(r):
    s = r
    for k, v in subs.items():
        s = s.replace(k, v)
    return s

bad = []
nf_list = []
results = []

for rule_obj in filtered:
    resolved = resolve(rule_obj.rule)
    for name, client in [('anon', c_anon), ('auth', c_auth)]:
        try:
            r = client.get(resolved, follow_redirects=True)
            code = r.status_code
            length = len(r.data)
            results.append((rule_obj.rule, name, code, length))
            if code in (500, 402):
                bad.append((rule_obj.rule, name, code, repr(r.data[:200])))
            if code == 404:
                nf_list.append((rule_obj.rule, name))
        except Exception as e:
            results.append((rule_obj.rule, name, 'ERR', str(e)[:80]))
            bad.append((rule_obj.rule, name, 'ERR', str(e)[:80]))

print(f"\n--- RESULTS ({len(results)} entries) ---")
for row in results:
    print(f"{row[0]:55s} {row[1]:5s} {str(row[2]):4s} {row[3]}")

print(f"\nBAD_COUNT={len(bad)}")
for b in bad:
    print(f"  BAD: {b[0]} {b[1]} {b[2]}")
print(f"404_COUNT={len(nf_list)}")
for nf in nf_list:
    print(f"  404: {nf[0]} {nf[1]}")
print("DONE")
