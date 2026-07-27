#!/usr/bin/env python3
"""Diagnostic: check day-splitting for all olympiads from year 2020."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) or '.')
from olympiads import OLYMPIADS_DB
from utils.olympiad_days import split_problems_by_day, detect_day_from_round, is_two_day

# Find all olympiads from 2020
print("=" * 80)
print("2020 OLYMPIADS - DAY SPLITTING DIAGNOSTIC")
print("=" * 80)

for d in OLYMPIADS_DB:
    if str(d.get('year')) != '2020':
        continue
    
    slug = d.get('olympiad', '')
    grade = d.get('grade', 0)
    rnd = d.get('round', '')
    title = d.get('olympiad_title', slug)
    round_title = d.get('round_title', rnd)
    problems = d.get('problems', [])
    n = len(problems)
    
    is_2day = is_two_day(slug, rnd, grade)
    detect_day = detect_day_from_round(round_title, rnd)
    
    # What would split_problems_by_day return?
    blocks = split_problems_by_day(problems, slug, rnd, grade)
    n_blocks = len(blocks)
    
    # Determine which case was hit
    has_day_field = any('day' in p for p in problems)
    
    conditions = []
    if has_day_field:
        conditions.append("CASE A (has 'day' field)")
    elif is_2day and n >= 6 and n % 2 == 0:
        conditions.append(f"CASE B (is_two_day={is_2day}, n={n}>=6, even)")
    else:
        reasons = []
        if not is_2day:
            reasons.append(f"!is_two_day(slug='{slug}', round='{rnd}', grade={grade})")
        if n < 6:
            reasons.append(f"n={n}<6")
        if n % 2 != 0:
            reasons.append(f"n={n} is odd")
        conditions.append(f"CASE C (reasons: {'; '.join(reasons)})")
    
    day_info = f"combo_day={detect_day}" if detect_day else "combo_day=None"
    
    if n_blocks > 1:
        day_labels = [b['day'] for b in blocks]
        probs_per_day = [len(b['problems']) for b in blocks]
        print(f"[SPLIT] {title:30s} | {slug:20s} | grade={str(grade):2s} | round={rnd:15s} | {n}p -> {n_blocks} blocks days={day_labels} probs={probs_per_day} | {conditions[0]}")
    else:
        print(f"[FLAT]  {title:30s} | {slug:20s} | grade={str(grade):2s} | round={rnd:15s} | {n}p -> 1 block {day_info} | {conditions[0]}")

print("=" * 80)
print("SUMMARY: Olympiads in TWO_DAY_RULES that DON'T split (Case C)")
print("=" * 80)

from utils.olympiad_days import TWO_DAY_RULES
for (slug, rnd), classes in sorted(TWO_DAY_RULES.items()):
    for d in OLYMPIADS_DB:
        if d.get('olympiad') == slug and d.get('round') == rnd and str(d.get('year')) == '2020':
            grade = d.get('grade', 0)
            problems = d.get('problems', [])
            n = len(problems)
            blocks = split_problems_by_day(problems, slug, rnd, grade)
            if len(blocks) <= 1 and int(grade) in classes:
                title = d.get('olympiad_title', slug)
                print(f"  {title:30s} grade={str(grade):2s} n={n}p | is_two_day={is_two_day(slug, rnd, grade)} | n>=6={n>=6} | even={n%2==0}")
