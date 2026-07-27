#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed the database with the 102 methods from secrets_dump.json."""
import sys
import os

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import app
from utils.seed_secrets_utils import seed_secrets_from_json, get_secrets_stats

with app.app_context():
    print("Seeding secrets_dump.json with force=True (will clear existing)...", flush=True)
    result = seed_secrets_from_json(json_file='secrets_dump.json', force=True)
    print(f"Result: {result}", flush=True)

    if result.get('success'):
        stats = get_secrets_stats()
        print(f"\nFinal stats: {stats}", flush=True)
    else:
        print(f"\nERROR: {result.get('error', 'Unknown error')}", flush=True)
        sys.exit(1)
