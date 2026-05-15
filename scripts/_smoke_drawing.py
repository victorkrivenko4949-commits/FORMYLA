# -*- coding: utf-8 -*-
"""End-to-end smoke test of services.drawing_service.generate_drawing()."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from services.drawing_service import generate_drawing

PROBLEM = "В треугольнике ABC угол A = 60, AB = 5, AC = 7. Нарисуй базовый чертёж."

result = generate_drawing(PROBLEM, app_root=os.getcwd(), use_cache=False)

out_path = os.path.join("static", "generated", "_test_codegen.png")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "wb") as f:
    f.write(result.image_bytes)

print("OK")
print("  model      :", result.model)
print("  bytes      :", len(result.image_bytes))
print("  cost_usd   :", result.cost_usd)
print("  render_ms  :", result.render_ms)
print("  repair_iters:", result.repair_iters)
print("  attempts   :", len(result.attempts))
for a in result.attempts:
    print("    -", a)
print("  saved to   :", out_path)
print()
print("=== generated code ===")
print(result.code)
