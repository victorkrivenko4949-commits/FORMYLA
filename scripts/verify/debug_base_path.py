#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Воспроизвести точный путь _plan_call для base (Gemini) и показать этапы."""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

from routes import figures_generator as fg
from services.llm_router import call_llm
from services.figure_plan_schemas import parse_base_plan

COND = (
    "В прямоугольном треугольнике \\(ABC\\) угол \\(C\\) равен \\(90^\\circ\\), "
    "\\(AC = 6\\), \\(BC = 8\\). Найдите расстояние от вершины \\(C\\) до гипотенузы."
)

prompt = open(os.path.join(BASE, "data", "figures", "base_planner_task.txt"),
              encoding="utf-8").read()

# Точный путь _plan_call: подстановка плейсхолдеров + _call_deepseek (call_llm)
system_prompt = prompt
for key, value in {"condition_text": COND, "repair_feedback": ""}.items():
    system_prompt = system_prompt.replace("{" + key + "}", str(value))

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "Верни строго JSON."},
]

resp = call_llm(
    "gemini-3.7-flash",
    messages,
    max_tokens=3000,
    role="base",
    timeout=(15, 60),
    logger=None,
)
content = (resp.get("content") or "").strip()
print("content_len:", len(content))
print("content startswith ```:", content.startswith("```"))

json_str = fg._extract_json(content)
print("_extract_json ok:", json_str is not None)
if json_str:
    print("json_str len:", len(json_str))

    # _repair_figure_json
    try:
        repaired = fg._repair_figure_json(json_str)
        if isinstance(repaired, dict):
            json_str = json.dumps(repaired, ensure_ascii=False)
            print("repaired to dict, len:", len(json_str))
    except Exception as e:
        print("repair error:", e)

    plan = parse_base_plan(json_str)
    print("parse_base_plan ok:", plan is not None)
    if plan is not None:
        v = fg.validate_figure_json(plan)
        print("validate_figure_json.valid:", v.get("valid"))
        print("validate errors:", v.get("errors"))
else:
    print("RAW (first 500):", content[:500])
