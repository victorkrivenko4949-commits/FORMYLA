# -*- coding: utf-8 -*-
import sys, os, codecs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
from collections import Counter

tasks = [p for p in PROBLEMS_DB if p.get('subject') == 'algebra' and p.get('subtopic') == 'equations' and p.get('grade') == 5]
levels = Counter(t['difficulty'] for t in tasks)

print('Алгебра -> Уравнения -> 5 класс:')
for l in range(1, 8):
    print(f'  Уровень {l}: {levels.get(l, 0)} задач')
