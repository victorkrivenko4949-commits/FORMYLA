# -*- coding: utf-8 -*-
"""CH21 PART 1: one-task aux dump — «Проведём высоту AH»."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

os.environ["FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED"] = "1"
os.environ["FIGURE_SEMANTIC_COLORS_ENABLED"] = "true"
os.environ["FIGURE_CREDITS_ENFORCED"] = "false"

from dotenv import load_dotenv
load_dotenv()

from services.llm_router import call_llm, logical_model_for_role  # noqa: E402

prompt = open("data/figures/aux_planner_task.txt", encoding="utf-8").read()

condition = "В равнобедренном треугольнике ABC известно, что AB = AC и угол BAC равен 40°. Найдите углы ABC и ACB."
solution = ("1. Проведём высоту AH из вершины A на сторону BC.\n"
            "2. В равнобедренном треугольнике высота к основанию является биссектрисой.\n"
            "3. Поэтому угол BAH равен 20°.\n"
            "4. Углы ABC и ACB равны 70°.")
base_plan = json.dumps({
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80},
        {"type": "free_point", "id": "B", "x": 120, "y": 400},
        {"type": "free_point", "id": "C", "x": 480, "y": 400},
        {"type": "triangle_isosceles", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ],
}, ensure_ascii=False)

prompt = prompt.replace("{condition_text}", condition)
prompt = prompt.replace("{numbered_solution_text}", solution)
prompt = prompt.replace("{base_plan_json}", base_plan)
prompt = prompt.replace("{repair_feedback}", "")

r = call_llm(logical_model_for_role("aux"),
             [{"role": "system", "content": prompt},
              {"role": "user", "content": "Верни строго JSON."}],
             role="aux", thinking_mode="disabled")

print("provider:", r.get("provider"))
print("thinking_mode:", r.get("thinking_mode"))
print("finish_reason:", r.get("finish_reason"))
print("reasoning_tokens:", r.get("reasoning_tokens"))
print("=== RAW CONTENT ===")
print(r.get("content"))
