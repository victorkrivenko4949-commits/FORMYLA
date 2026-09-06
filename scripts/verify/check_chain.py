#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверить фактический резолв цепочки провайдеров для ролей (с .env)."""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

from services import llm_router as r

for role in ("base", "aux", "audit", "solver", "repair", "solver_shadow"):
    logical = r.logical_model_for_role(role)
    providers = r.ROLE_PROVIDER_ORDER.get(role, r.PROVIDER_ORDER)
    chain = r.build_provider_chain(logical, providers=providers)
    print(f"{role}: logical={logical} providers={providers} chain="
          f"{[(c['provider'], c['model_id']) for c in chain]}")

print("\n--- env keys present ---")
print("GEMINI_API_KEY set:", bool((os.environ.get('GEMINI_API_KEY') or '').strip()))
print("GEMINI_API_BASE:", os.environ.get('GEMINI_API_BASE'))
print("odirouter base_url:", r.PROVIDER_BASE_URLS.get('odirouter'))
