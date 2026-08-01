# -*- coding: utf-8 -*-
"""Audit all Flask routes for @login_required presence."""
import re, sys, os

sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'test'

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

routes = []
i = 0
while i < len(lines):
    line = lines[i]
    m = re.match(r'@app\.route\(["\']([^"\']+)["\'].*', line)
    if m:
        route_path = m.group(1)
        has_login = False
        has_admin = False
        # check next 3 lines for decorators
        for j in range(1, 4):
            if i + j < len(lines):
                next_line = lines[i + j]
                if '@login_required' in next_line:
                    has_login = True
                if '@admin_required' in next_line:
                    has_admin = True
                if 'def ' in next_line:
                    func_name = re.search(r'def\s+(\w+)', next_line)
                    func_name = func_name.group(1) if func_name else '?'
                    break
        else:
            func_name = '?'
        methods = ['GET']
        if 'POST' in line:
            methods = ['POST']
        if 'GET' in line and 'POST' in line:
            methods = ['GET', 'POST']
        routes.append((route_path, has_login, has_admin, func_name, methods))
    i += 1

print("=== ROUTES WITHOUT @login_required ===")
unprotected = [(r, f, a, m) for r, l, a, f, m in routes if not l]
for r, f, a, methods in sorted(unprotected):
    admin_tag = " [ADMIN]" if a else ""
    print(f"UNPROTECTED: {r:50s} -> {f:30s} {','.join(methods)}{admin_tag}")

print(f"\nTotal routes: {len(routes)}")
print(f"Unprotected: {len(unprotected)}")
print(f"Protected: {len(routes) - len(unprotected)}")

# Now also check route files for blueprint routes
route_files = [
    'routes/account.py', 'routes/admin_daily_pool.py', 'routes/admin_daily_tasks_stats.py',
    'routes/admin_olympiads.py', 'routes/admin_support.py', 'routes/chat_presence.py',
    'routes/concierge.py', 'routes/conference_api.py', 'routes/decorators.py',
    'routes/drawing.py', 'routes/drawing_diag.py', 'routes/drawing_history.py',
    'routes/friends.py', 'routes/grade.py', 'routes/handwriting.py',
    'routes/intake.py', 'routes/olympiad.py', 'routes/olympiad_prep.py',
    'routes/prep.py', 'routes/room_state.py', 'routes/telegram_auth.py',
    'routes/wb_call.py', 'routes/wb_meet.py', 'routes/wb_ws.py',
]

print("\n=== BLUEPRINT ROUTES ===")
for rf in route_files:
    if not os.path.exists(rf):
        continue
    with open(rf, 'r', encoding='utf-8') as f:
        bp_content = f.read()
    # Find blueprint registration in app.py to get prefix
    with open('app.py', 'r', encoding='utf-8') as f:
        app_content = f.read()
    # Find prefix
    bp_name = re.sub(r'\.py$', '', rf.replace('routes/', ''))
    prefix_match = re.search(r'(\w+)_bp\s*=\s*Blueprint\(.*?url_prefix\s*=\s*["\']([^"\']+)["\']', app_content)
    # Simpler: find route decorator patterns
    bp_routes = list(re.finditer(r'@(\w+_bp)\.route\(["\\\']([^"\\\']+)["\\\'].*?\)(.*?)\n(?:\s*@login_required\s*\n)?\s*def\s+(\w+)', bp_content, re.DOTALL))
    # Just list all route decorators
    for m in re.finditer(r'@(\w+_bp)\.route\(["\']([^"\']+)["\'].*?\)', bp_content):
        rp = m.group(2)
        # Check next line for login_required
        pos = m.end()
        rest = bp_content[pos:pos+60]
        has_log = '@login_required' in rest
        print(f'BLUEPRINT: {rf}:{rp:40s} -> {"PROTECTED" if has_log else "UNPROTECTED"}')
