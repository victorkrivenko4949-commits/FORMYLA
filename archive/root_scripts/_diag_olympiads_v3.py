#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic v3: detailed analysis of bad tasks + routing."""
import sys
from collections import defaultdict

OUT = open("_diag_v3_report.txt", "w", encoding="utf-8")

def echo(s=""):
    OUT.write(s + "\n")
    OUT.flush()

from olympiads import OLYMPIADS_DB

echo(f"Total olympiads: {len(OLYMPIADS_DB)}")
echo()

# ===== 1. Full detail on 5 bad tasks =====
echo("=" * 70)
echo("DETAILED BAD TASKS (condition contains solution)")
echo("=" * 70)

bad_ids = [82, 85, 540, 556, 607]
for o in OLYMPIADS_DB:
    if o['id'] in bad_ids:
        echo(f"\n--- ID {o['id']}: {o['olympiad_title']} {o['year']} g{o['grade']} ---")
        echo(f"  round: {o.get('round')} / {o.get('round_title')}")
        echo(f"  source_url: {o.get('source_url','')}")
        for p in o.get('problems', []):
            t = p.get('text','')
            s = p.get('solution','')
            a = p.get('answer','')
            echo(f"\n  Problem #{p['num']}:")
            echo(f"    TEXT ({len(t)} chars):")
            for i in range(0, len(t), 200):
                echo(f"      {repr(t[i:i+200])}")
            echo(f"    ANSWER: {repr(a)}")
            echo(f"    SOLUTION ({len(s)} chars):")
            for i in range(0, len(s), 200):
                echo(f"      {repr(s[i:i+200])}")
            echo(f"    SOLUTION_STATUS: {repr(p.get('solution_status',''))}")

echo()
echo("=" * 70)
echo("HOW MANY TASKS HAVE ANSWER/SOLUTION IN TEXT FIELD?")
echo("=" * 70)
total_bad = 0
for o in OLYMPIADS_DB:
    for p in o.get('problems', []):
        t = p.get('text','')
        if any(kw in t for kw in ['Решение:', 'Ответ:', 'Решение.=', 'Ответ.=']):
            total_bad += 1
echo(f"Total problem entries with solution keywords in 'text': {total_bad}")

echo()
echo("=" * 70)
echo("TASKS WHERE SOLUTION FIELD CONTAINS PROBLEM TEXT")
echo("=" * 70)
swapped = []
for o in OLYMPIADS_DB:
    oid = o['id']
    for p in o.get('problems', []):
        s = p.get('solution','')
        if any(s.startswith(kw) for kw in ['Задача', 'Условие', 'На доске', 'Даны', 'Дан']):
            swapped.append((oid, p['num'], s[:150]))
        if p.get('solution_status',''):
            swapped.append((oid, p['num'], f"solution_status={repr(p['solution_status'])}"))
echo(f"Swapped/solution_status tasks: {len(swapped)}")
for oid, pnum, preview in swapped[:30]:
    echo(f"  [{oid}] prob#{pnum}: {preview}")

echo()
echo("=" * 70)
echo("VSOSH 2025 g9 (ID 556) - PROBLEM 4 FULL TEXT")
echo("=" * 70)
for o in OLYMPIADS_DB:
    if o['id'] == 556:
        for p in o.get('problems', []):
            if p['num'] == 4:
                echo(f"  TEXT ({len(p.get('text',''))} chars):")
                echo(f"    {repr(p.get('text',''))}")
                echo(f"  ANSWER: {repr(p.get('answer',''))}")
                echo(f"  SOLUTION ({len(p.get('solution',''))} chars):")
                echo(f"    {repr(p.get('solution',''))}")

echo()
echo("=" * 70)
echo("FORMULA UNITY 2024 g7 (ID 82) - PROBLEM 5 FULL TEXT")
echo("=" * 70)
for o in OLYMPIADS_DB:
    if o['id'] == 82:
        for p in o.get('problems', []):
            if p['num'] == 5:
                echo(f"  TEXT ({len(p.get('text',''))} chars):")
                echo(f"    {repr(p.get('text',''))}")
                echo(f"  ANSWER: {repr(p.get('answer',''))}")
                echo(f"  SOLUTION ({len(p.get('solution',''))} chars):")
                echo(f"    {repr(p.get('solution',''))}")

echo()
echo("=" * 70)
echo("Higher School 2021 g7 (ID 607) - ALL PROBLEMS")
echo("=" * 70)
for o in OLYMPIADS_DB:
    if o['id'] == 607:
        for p in o.get('problems', []):
            echo(f"\n  Problem #{p['num']}:")
            echo(f"    TEXT ({len(p.get('text',''))} chars): {repr(p.get('text','')[:300])}")
            echo(f"    SOLUTION ({len(p.get('solution',''))} chars): {repr(p.get('solution','')[:300])}")
            echo(f"    ANSWER: {repr(p.get('answer',''))}")

echo()
echo("DONE")
OUT.close()
print(f"Report written to _diag_v3_report.txt")
