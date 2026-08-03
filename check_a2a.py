#!/usr/bin/env python3
import json
with open('all_methods_real_final.json','r',encoding='utf-8') as f:
    methods = json.load(f)
m = next(x for x in methods if x['method_code']=='A2a')
we = m['worked_example_md']
parts = we.split('### Задача')
t2 = parts[2]
print('Has Ответ:', '**Ответ:**' in t2)
print('Has Главным:', '**Что было главным:**' in t2)
# Print where Ответ appears in the text
idx = t2.find('Ответ')
if idx >= 0:
    print('"Ответ" found at position', idx)
    print('Context:', repr(t2[max(0,idx-20):idx+100]))
else:
    print('NO "Ответ" substring at all!')
# Print last 300 chars
print('\nLast 300 chars:')
print(repr(t2[-300:]))
