#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check which of the 250 empty tasks were covered by audit."""
import json

fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
empty = [t for t in fixed if not t.get('statement')]
empty_oids = set(t.get('original_id', '') for t in empty)
print(f'empty oids: {len(empty_oids)}')

audit = json.load(open('audit_675_full_results.json', 'r', encoding='utf-8'))
audit_oids = set()
for k, v in audit.items():
    if isinstance(v, dict):
        audit_oids.add(v.get('original_id', ''))
print(f'audit oids: {len(audit_oids)}')

in_audit = empty_oids & audit_oids
not_in_audit = empty_oids - audit_oids
print(f'in audit: {len(in_audit)}')
print(f'NOT in audit: {len(not_in_audit)}')

lines = []
lines.append('=== 250 empty tasks: audit coverage ===')
lines.append(f'In audit results: {len(in_audit)}')
lines.append(f'NOT in audit results: {len(not_in_audit)}')

lines.append('')
lines.append('First 20 empty task IDs NOT in audit:')
for oid in sorted(not_in_audit)[:20]:
    lines.append(f'  {oid}')

lines.append('')
lines.append('First 20 empty task IDs IN audit:')
for oid in sorted(in_audit)[:20]:
    lines.append(f'  {oid}')

open('_diag4_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('DONE')
