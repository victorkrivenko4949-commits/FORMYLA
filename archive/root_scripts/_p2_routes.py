"""P2 route traversal script"""
import sys, os
sys.stderr = open(os.devnull, 'w')  # suppress startup logs
import app as A

c_anon = A.app.test_client()
c_auth = A.app.test_client()
with c_auth.session_transaction() as s:
    s['_user_id'] = '1'

rules = [(r.rule, sorted(r.methods - {'OPTIONS', 'HEAD'}), r.endpoint) 
         for r in A.app.url_map.iter_rules() 
         if not r.rule.startswith('/static') and not r.rule.startswith('/debug')]

print(f'TOTAL_RULES_FROM_URL_MAP={len(rules)}')

results = []
errors = []

for rule, methods, ep in rules:
    if 'GET' not in methods and 'POST' not in methods:
        continue
    test_url = rule
    # Parameter substitution
    int_params = {'user_id': 1, 'student_id': 1, 'plan_id': 1, 'day_id': 1, 'problem_id': 1, 
                  'task_id': 1, 'item_id': 1, 'job_id': 1, 'attempt_id': 1, 'mentorship_id': 1,
                  'secret_id': 1, 'combo_id': 1, 'grade': 9}
    str_params = {'nickname': 'testuser', 'subject_key': 'algebra', 'subtopic_key': 'test',
                  'method_code': 'test', 'code': 'test', 'date_iso': '2026-01-01',
                  'section_name': 'test', 'method_task_id': '1', 'filename': 'test.txt',
                  'anchor_uid': 'test_anchor', 'path': 'test.txt'}
    
    if '<' not in rule:
        # Simple route
        if 'GET' in methods:
            for name, client in [('anon', c_anon), ('auth', c_auth)]:
                try:
                    r = client.get(test_url, follow_redirects=True)
                    results.append((test_url, name, r.status_code, len(r.data)))
                except Exception as e:
                    errors.append((test_url, name, str(type(e).__name__), str(e)[:100]))
        if 'POST' in methods and 'GET' not in methods:
            for name, client in [('anon', c_anon), ('auth', c_auth)]:
                try:
                    r = client.post(test_url, follow_redirects=True)
                    results.append((test_url + ' POST', name, r.status_code, len(r.data)))
                except Exception as e:
                    errors.append((test_url + ' POST', name, str(type(e).__name__), str(e)[:100]))
    else:
        # Parameterized route - substitute
        for params, suffix in [(int_params, '_INT'), (str_params, '_STR')]:
            test_url = rule
            for k, v in params.items():
                test_url = test_url.replace(f'<int:{k}>', str(v))
                test_url = test_url.replace(f'<{k}>', str(v))
            if '<' in test_url:
                continue  # still unresolved params
            if 'GET' in methods:
                for name, client in [('anon', c_anon), ('auth', c_auth)]:
                    try:
                        r = client.get(test_url, follow_redirects=True)
                        results.append((test_url, name, r.status_code, len(r.data)))
                    except Exception as e:
                        errors.append((test_url, name, str(type(e).__name__), str(e)[:100]))

# Print results
for row in results:
    print(f'{row[0]:70s} | {row[1]:5s} | {row[2]} | {row[3]}')

bad = [r for r in results if r[2] in (500, 402)]
print(f'BAD_COUNT={len(bad)}')
for b in bad:
    print(f'BAD: {b}')

nf = [r for r in results if r[2] == 404]
print(f'NOT_FOUND_COUNT={len(nf)}')
for n in nf:
    print(f'404: {n}')

print(f'ERROR_COUNT={len(errors)}')
for e in errors:
    print(f'ERROR: {e}')

print(f'TOTAL_CHECKS={len(results)}')
