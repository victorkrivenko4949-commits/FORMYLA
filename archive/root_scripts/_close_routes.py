# -*- coding: utf-8 -*-
"""Batch-add @login_required to unprotected routes that should be closed (TASK 2)."""
import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.splitlines(keepends=True)

# Routes that MUST be closed (add @login_required)
ROUTES_TO_CLOSE = {
    '/sql': 'sql_page',
    '/secrets': 'secrets',
    '/api/secrets': 'api_secrets',
    '/profile': 'profile',
    '/daily-set': 'daily_set_redirect',
    '/call': 'call_page',
    '/conference': 'conference_page',
    '/api/migrate/tables': 'migrate_list_tables',
    '/api/migrate/export': 'migrate_export_table',
    '/olympiads/open': 'olympiad_open',
    '/olympiads/solution/<int:combo_id>': 'olympiad_solution',
    '/api/save_test_result': 'api_save_test_result',
    '/api/profile': 'api_get_profile',
    '/api/set_nickname': 'api_set_nickname',
    '/api/report_task/<int:task_id>': 'report_task',
    '/api/test/start': 'api_test_start',
    '/api/test/active': 'api_test_active',
    '/api/test/<int:session_id>/resume': 'api_test_resume',
    '/api/check_answer': 'check_answer',
    '/api/check_adaptive_answer': 'check_adaptive_answer',
    '/api/support': 'submit_support',
    '/api/feedback': 'submit_feedback',
    '/api/reviews': 'list_site_reviews',
}

count = 0
i = 0
while i < len(lines):
    line = lines[i]
    # Check if this line is @app.route for a route we want to close
    m = re.match(r'@app\.route\(\s*["\'](.+?)["\'].*', line)
    if m:
        route_path = m.group(1)
        # Look ahead for function name and check if it matches
        for j in range(1, 5):
            if i + j < len(lines):
                def_match = re.search(r'def\s+(\w+)', lines[i + j])
                if def_match:
                    func_name = def_match.group(1)
                    # Check if this route+func pair should be closed
                    should_close = False
                    for rp, fn in ROUTES_TO_CLOSE.items():
                        if route_path == rp and func_name == fn:
                            should_close = True
                            break
                    if should_close:
                        # Check if already has @login_required
                        has_login = False
                        for k in range(1, j):
                            if '@login_required' in lines[i + k]:
                                has_login = True
                                break
                        if not has_login:
                            # Insert @login_required before function def
                            indent = re.match(r'(\s*)def', lines[i + j])
                            indent_str = indent.group(1) if indent else ''
                            lines.insert(i + j, f'{indent_str}@login_required\n')
                            count += 1
                            print(f'ADDED @login_required: {route_path} -> {func_name}')
                    break
    i += 1

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'\nTotal routes closed: {count}')
