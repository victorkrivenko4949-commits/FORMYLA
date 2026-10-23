#!/usr/bin/env python3
"""Fix E17: replace 'Что в этой задаче было главным' with 'Что было главным'"""
import json

d = json.load(open('all_methods_real_final.json', 'r', encoding='utf-8'))
m = next(x for x in d if x['method_code'] == 'E17')
we = m['worked_example_md']
we = we.replace('**Что в этой задаче было главным:**', '**Что было главным:**')
m['worked_example_md'] = we

json.dump(d, open('all_methods_real_final.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('E17 fixed!')
print(f'Has **Что было главным:**: {"**Что было главным:**" in we}')
