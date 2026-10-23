#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вызвать base-планировщик напрямую (Gemini) и показать raw-ответ для отладки."""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

from services.llm_router import call_llm
from services.figure_plan_schemas import parse_base_plan

COND = (
    "В прямоугольном треугольнике \\(ABC\\) угол \\(C\\) равен \\(90^\\circ\\), "
    "\\(AC = 6\\), \\(BC = 8\\). Найдите расстояние от вершины \\(C\\) до гипотенузы."
)

prompt_path = os.path.join(BASE, "data", "figures", "base_planner_task.txt")
prompt = open(prompt_path, encoding="utf-8").read()

messages = [
    {"role": "system", "content": prompt},
    {"role": "user", "content": f"УСЛОВИЕ:\n{COND}\n\nВерни СТРОГО JSON base-плана."},
]

resp = call_llm(
    "gemini-3.7-flash",
    messages,
    max_tokens=3000,
    role="base",
    timeout=(15, 60),
    response_format={"type": "json_object"},
)

content = resp.get("content", "")
out = {
    "provider": resp.get("provider"),
    "model_id": resp.get("model_id"),
    "content": content,
    "content_len": len(content),
}
with open(os.path.join(BASE, "scripts", "verify", "out", "gemini_base_raw.json"),
          "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

plan = parse_base_plan(content)
print("provider:", resp.get("provider"), "model:", resp.get("model_id"))
print("content_len:", len(content))
print("parse_base_plan ok:", plan is not None)
if plan is not None:
    print("constructions:", len(plan.get("constructions", [])))
    print("types:", [c.get("type") for c in plan.get("constructions", [])])
else:
    print("RAW CONTENT (first 2000):")
    print(content[:2000])
