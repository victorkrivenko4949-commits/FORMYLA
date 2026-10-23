#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диагностика olympiads.py: поиск проблем."""
import sys, os, re, json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from olympiads import OLYMPIADS_DB
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)

print(f"Total olympiads: {len(OLYMPIADS_DB)}")

# 1. Поиск олимпиад с day/день в полях
print("\n=== 1. Олимпиады с day/день в полях ===")
for o in OLYMPIADS_DB:
    olymp_key = f"{o.get('olympiad','?')} {o.get('year','?')} g{o.get('grade','?')}"
    for k, v in o.items():
        if k not in ('id','olympiad','olympiad_title','year','grade','round','round_title','problems','source_url','source{
