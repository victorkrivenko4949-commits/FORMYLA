#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from problems import PROBLEMS_DB

# Old tasks only (ID < 11316)
old = [p for p in PROBLEMS_DB if p['id'] < 11316]
print(f"Old tasks (ID < 11316): {len(old)}")

# Movement
movement_re = re.compile(r'движен|скорост|км/ч|м/с|навстречу|поезд|велосипед|автомобил|пешеход|катер|лодк|течени', re.IGNORECASE)
logic_re = re.compile(r'рыцар|лжец|правд|ложь|логик|инвариант|чётност|раскрас|шахматн|фишк|игр\w+\s+двух', re.IGNORECASE)

old_movement = [p for p in old if p.get('subject') == 'movement']
print(f"\nOld movement tasks: {len(old_movement)}")

# Check each old movement task
bad_movement = 0
for p in old_movement:
    text = p.get('text', '')
    is_movement = bool(movement_re.search(text))
    is_logic = bool(logic_re.search(text))
    if not is_movement or is_logic:
        bad_movement += 1
        if bad_movement <= 10:
            label = "NOT_MOVEMENT" if not is_movement else "HAS_LOGIC"
            print(f"\n  ❌ [{label}] ID={p['id']}, grade={p['grade']}, sub={p['subtopic']}")
            print(f"     {text[:150]}")

print(f"\nBad movement tasks: {bad_movement}/{len(old_movement)}")

# Knights_liars
old_kl = [p for p in old if p.get('subject') == 'knights_liars']
print(f"\n\nOld knights_liars tasks: {len(old_kl)}")

kl_re = re.compile(r'рыцар|лжец|правд|ложь|логик|остров|житель|утвержд|говорит|сказал|истин|ложн', re.IGNORECASE)
bad_kl = 0
for p in old_kl:
    text = p.get('text', '')
    if not kl_re.search(text):
        bad_kl += 1
        if bad_kl <= 10:
            print(f"\n  ❌ ID={p['id']}, grade={p['grade']}, sub={p['subtopic']}")
            print(f"     {text[:150]}")

print(f"\nBad knights_liars tasks: {bad_kl}/{len(old_kl)}")
