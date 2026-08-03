"""P4 checks - write results to p4_output.txt."""
import sys, json, re, os

# Suppress all non-print output
import logging
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.CRITICAL)

out = []

import app as A

# 1. Version
c = A.app.test_client()
r = c.get('/__version', follow_redirects=True)
data = json.loads(r.data)
short_hash = data['commit'][:8]
out.append(f"HASH={short_hash}")
out.append(f"KEYS={sorted(data.keys())}")

# 2. Nine templates
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
        has = short_hash in html
        out.append(f"TMPL|{tmpl}|{path}|{r.status_code}|{has}")
    except Exception as e:
        out.append(f"TMPL|{tmpl}|{path}|ERR|{e}")

# 3. Static version
html = c.get('/', follow_redirects=True).data.decode('utf-8')
css_links = re.findall(r'href="([^"]*\.css[^"]*)"', html)
js_links = re.findall(r'src="([^"]*\.js[^"]*)"', html)
out.append(f"CSS_LINKS={css_links[:5]}")
out.append(f"JS_LINKS={js_links[:5]}")
versioned_css = [l for l in css_links if '?v=' in l]
versioned_js = [l for l in js_links if '?v=' in l]
out.append(f"VERSIONED_CSS={versioned_css[:5]}")
out.append(f"VERSIONED_JS={versioned_js[:5]}")

# Find actual CSS files in static/
static_css = 'static/css'
if os.path.isdir(static_css):
    css_files = os.listdir(static_css)
    out.append(f"STATIC_CSS_FILES={css_files[:10]}")
else:
    out.append("STATIC_CSS_DIR_NOT_FOUND")

# 4. DEPLOY_CHECK
text = open('DEPLOY_CHECK.md', encoding='utf-8').read()
for token in ['srv-d73br5ffte5s73euc56g', 'formyla.net', 'PostgreSQL', 'Auto-Deploy']:
    out.append(f"DEPLOY|{token}|{token in text}")

# 5. Migrations
mig_dir = 'migrations'
py_files = sorted([f for f in os.listdir(mig_dir) if f.endswith('.py')])
out.append(f"MIG_PY_FILES={py_files}")
# Check for tracking mechanism
found_any = False
for f in py_files:
    content = open(os.path.join(mig_dir, f), encoding='utf-8', errors='ignore').read()
    if 'applied' in content.lower() or 'alembic_version' in content.lower() or 'migration_log' in content.lower():
        out.append(f"MIG_TRACK|{f}|FOUND")
        found_any = True
if not found_any:
    out.append("MIG_TRACK|NONE")

# Write to file
with open('p4_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print("DONE")
