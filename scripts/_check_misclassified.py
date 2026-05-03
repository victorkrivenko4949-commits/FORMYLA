#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check for misclassified tasks: logic/invariants in movement, knights_liars with wrong content, etc."""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

# ─── Check movement tasks for logic/invariant content ─────────────────────────
print("=" * 70)
print("MOVEMENT tasks that look like LOGIC/INVARIANTS")
print("=" * 70)

logic_re = re.compile(
    r'рыцар|лжец|правд|ложь|логик|инвариант|чётност|нечётност|'
    r'раскрас|шахматн|клетк\w+\s+доск|фишк|жетон|'
    r'говорит\s+правду|всегда\s+лж|всегда\s+говор',
    re.IGNORECASE
)

movement_tasks = [p for p in PROBLEMS_DB if p.get('subject') == 'movement']
print(f"\nTotal movement tasks: {len(movement_tasks)}")
misclass_movement = []
for p in movement_tasks:
    text = p.get('text', '')
    if logic_re.search(text):
        misclass_movement.append(p)
        print(f"\n  ❌ ID={p['id']}, grade={p['grade']}, subtopic={p['subtopic']}")
        print(f"     {text[:150]}")

print(f"\nMisclassified in movement: {len(misclass_movement)}")

# ─── Check knights_liars tasks for wrong content ─────────────────────────────
print("\n" + "=" * 70)
print("KNIGHTS_LIARS tasks that DON'T look like logic")
print("=" * 70)

kl_tasks = [p for p in PROBLEMS_DB if p.get('subject') == 'knights_liars']
print(f"\nTotal knights_liars tasks: {len(kl_tasks)}")

kl_keywords = re.compile(
    r'рыцар|лжец|правд|ложь|логик|остров|житель|утвержд|'
    r'говорит|сказал|заявил|соврал|истин|ложн',
    re.IGNORECASE
)

misclass_kl = []
for p in kl_tasks:
    text = p.get('text', '')
    if not kl_keywords.search(text):
        misclass_kl.append(p)
        print(f"\n  ❌ ID={p['id']}, grade={p['grade']}, subtopic={p['subtopic']}")
        print(f"     {text[:150]}")

print(f"\nNot matching knights_liars: {len(misclass_kl)}")

# ─── Check ALL tasks: logic content in wrong subjects ─────────────────────────
print("\n" + "=" * 70)
print("Tasks with LOGIC content in NON-logic subjects")
print("=" * 70)

logic_content_re = re.compile(
    r'рыцар\w*\s+и\s+лжец|остров\w*\s+рыцар|остров\w*\s+лжец|'
    r'рыцарь|лжец\b',
    re.IGNORECASE
)

wrong_logic = []
for p in PROBLEMS_DB:
    if p.get('subject') in ('knights_liars',):
        continue
    text = p.get('text', '')
    if logic_content_re.search(text):
        wrong_logic.append(p)
        print(f"\n  ❌ ID={p['id']}, subject={p['subject']}, grade={p['grade']}")
        print(f"     {text[:150]}")

print(f"\nLogic tasks in wrong subjects: {len(wrong_logic)}")

# ─── Check for invariant/game tasks in wrong subjects ─────────────────────────
print("\n" + "=" * 70)
print("INVARIANT/GAME tasks in wrong subjects (should be combinatorics)")
print("=" * 70)

invariant_re = re.compile(
    r'инвариант|чётност\w+\s+нечётност|раскрас\w+\s+клет|'
    r'шахматн\w+\s+доск|фишк\w+\s+на\s+доск|'
    r'игр\w+\s+двух\s+игрок|первый\s+игрок|второй\s+игрок|'
    r'выигрышн\w+\s+стратег',
    re.IGNORECASE
)

wrong_invariant = []
for p in PROBLEMS_DB:
    if p.get('subject') in ('combinatorics',):
        continue
    text = p.get('text', '')
    if invariant_re.search(text):
        wrong_invariant.append(p)
        if len(wrong_invariant) <= 10:
            print(f"\n  ❌ ID={p['id']}, subject={p['subject']}, grade={p['grade']}")
            print(f"     {text[:150]}")

print(f"\nInvariant/game tasks in wrong subjects: {len(wrong_invariant)}")

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Movement with logic content: {len(misclass_movement)}")
print(f"  Knights_liars without logic: {len(misclass_kl)}")
print(f"  Logic in wrong subjects: {len(wrong_logic)}")
print(f"  Invariants in wrong subjects: {len(wrong_invariant)}")
total_issues = len(misclass_movement) + len(misclass_kl) + len(wrong_logic) + len(wrong_invariant)
print(f"  TOTAL issues: {total_issues}")
