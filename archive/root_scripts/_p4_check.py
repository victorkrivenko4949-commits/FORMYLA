"""P4 acceptance checks — capture raw output."""
import sys, json, re, os

# Suppress most logging
import logging
logging.disable(logging.CRITICAL)

import app as A

# --- Check 1: hash from __version ---
c = A.app.test_client()
r = c.get('/__version', follow_redirects=True)
data = json.loads(r.data)
short = data['commit'][:8]
print('P4_SHORT_HASH:', short)

# --- Check 2: 9 templates ---
templates_routes = [
    ('conference.html', '/conference'),
    ('admin/support_inbox.html', '/admin/support'),
    ('chat.html', '/chat'),
    ('daily_complete.html', '/daily_complete'),
    ('daily_task.html', '/daily_task'),
    ('group_chat.html', '/group_chat'),
    ('my_support.html', '/my/support'),
    ('profile.html', '/profile'),
    ('subject.html', '/subject/algebra'),
]
for tmpl, path in templates_routes:
    with c.session_transaction() as s:
        s['_user_id'] = '1'
    try:
        r = c.get(path, follow_redirects=True)
        html = r.data.decode('utf-8')
        has = short in html
        print(f'TEMPLATE {tmpl} PATH={path} STATUS={r.status_code} HASH={has}')
    except Exception as e:
        print(f'TEMPLATE {tmpl} PATH={path} ERROR={e}')

# --- Check 3: static version ---
html_before = c.get('/', follow_redirects=True).data.decode('utf-8')
m = re.search(r'static/css/style\.css\?v=([^"\']+)', html_before)
v_before = m.group(1) if m else 'NOT FOUND'
print('P4_V_BEFORE:', v_before)

css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'css', 'style.css')
if os.path.exists(css_path):
    with open(css_path, 'a', encoding='utf-8') as f:
        f.write('\n/* p4 probe */\n')
    html_after = c.get('/', follow_redirects=True).data.decode('utf-8')
    m2 = re.search(r'static/css/style\.css\?v=([^"\']+)', html_after)
    v_after = m2.group(1) if m2 else 'NOT FOUND'
    print('P4_V_AFTER:', v_after)
    print('P4_V_CHANGED:', v_before != v_after)
    # Revert
    lines = open(css_path, encoding='utf-8').readlines()
    if lines and '/* p4 probe */' in lines[-1]:
        open(css_path, 'w', encoding='utf-8').writelines(lines[:-1])
    print('P4_REVERTED')
else:
    print('P4_CSS_NOT_FOUND')

# --- Check 4: DEPLOY_CHECK.md tokens ---
text = open('DEPLOY_CHECK.md', encoding='utf-8').read()
for token in ['srv-d73br5ffte5s73euc56g', 'formyla.net', 'PostgreSQL', 'Auto-Deploy']:
    print(f'P4_DEPLOY_{token.replace("-","_").replace(".","_")}:', token in text)

# --- Check 5: migrations tracking ---
mig_dir = 'migrations'
if os.path.isdir(mig_dir):
    files = sorted(os.listdir(mig_dir))
    print('P4_MIGRATIONS_FILES:', files[:20], '... total', len(files))
else:
    print('P4_MIGRATIONS_FILES: NOT FOUND')

print('P4_DONE')
