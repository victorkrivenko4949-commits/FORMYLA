# -*- coding: utf-8 -*-
import re, json

s_prep = open('routes/prep.py','r',encoding='utf-8').read()
s_onb = open('services/onboarding.py','r',encoding='utf-8').read()

# coach_chat block in prep.py
idx1 = s_prep.find('prep_state[\'onboarding\'] = {')
block1 = s_prep[idx1:idx1+600]

# onboarding.py block
idx2 = s_onb.find('prep_state[\'onboarding\'] = {')
block2 = s_onb[idx2:idx2+600]

# Extract all single-quoted dict keys
fields_a = sorted(set(re.findall(r"\'(\w+)\':", block1)))
fields_b = sorted(set(re.findall(r"\'(\w+)\':", block2)))

out = []
out.append('=== PATH A: routes/prep.py:2566 (chat curator) ===')
out.append(f'Fields ({len(fields_a)}): {fields_a}')
out.append('')
out.append('=== PATH B: services/onboarding.py:885 (tree) ===')
out.append(f'Fields ({len(fields_b)}): {fields_b}')
out.append('')
out.append(f'IDENTICAL: {fields_a == fields_b}')
out.append(f'Count A={len(fields_a)}, Count B={len(fields_b)}')
out.append(f'Both have 17 fields: {len(fields_a)==17 and len(fields_b)==17}')

with open('_fields_compare.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(out))
print('DONE')
