# -*- coding: utf-8 -*-
"""Прогоняем точную solution-строку G6.17 через render-пайплайн,
чтобы проверить, ломается ли \\sqrt[3]{} где-либо."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Берём реальную строку из JSON-сидера
data = json.loads((ROOT/"data/olympiads/vsosh_10_11_full.json").read_text(encoding="utf-8"))
g617 = next(t for t in data if t.get("number") == "G6.17")
sol = g617["solution"]
print("=== RAW solution (G6.17) ===")
print(repr(sol))
print()

def show(label, fn, text):
    try:
        out = fn(text)
    except Exception as e:
        out = f"<ERROR {e}>"
    changed = (out != text)
    has_sqrt3 = "\\sqrt[3]" in (out or "")
    print(f"--- {label} | changed={changed} | sqrt[3]_present={has_sqrt3}")
    if changed:
        print("    OUT:", repr(out))
    print()
    return out

# 1) latex_validator.normalize_math_text (вызывается в render_task_text)
from services.latex_validator import normalize_math_text as lv_norm
t1 = show("latex_validator.normalize_math_text", lv_norm, sol)

# 2) math_text_normalizer.normalize_math_text (вызывается в md_render)
from services.math_text_normalizer import normalize_math_text as mtn_norm
t2 = show("math_text_normalizer.normalize_math_text", mtn_norm, sol)

# 3) md_render (полный markdown путь)
from services.md_render import md_render
out3 = str(md_render(sol))
print("--- md_render | sqrt[3]_present:", "\\sqrt[3]" in out3)
print("    HTML snippet:", out3[:400])
print()

# 4) Проверим _sanitize_ai_latex из app.py — он содержит '³'->'^{3}' замену.
#    Импортируем аккуратно (app.py тяжёлый; вытащим функцию через regex-exec нельзя,
#    поэтому проверим на синтетических строках вручную ниже).
print("=== Синтетический тест замены ³ -> ^{3} (app._sanitize_ai_latex логика) ===")
import re
def sanitize_like_app(text):
    s = text
    s = s.replace('²', '^{2}').replace('³', '^{3}')
    s = re.sub(r'√\s*\(([^()]*)\)', r'\\sqrt{\1}', s)
    s = re.sub(r'√\s*([a-zA-Z0-9]+)', r'\\sqrt{\1}', s)
    s = re.sub(r'∛\s*\(([^()]*)\)', r'\\sqrt[3]{\1}', s)
    s = re.sub(r'∛\s*([a-zA-Z0-9]+)', r'\\sqrt[3]{\1}', s)
    return s

for probe in [
    r"\sqrt[3]{a^2b^2c^2}",      # корректный — не должен пострадать
    "∛(a²b²c²)",                  # юникод cbrt со скобками
    "³√(a²b²c²)",                 # ³ + √ раздельно  <-- ВОТ ОПАСНЫЙ КЕЙС
    "³√a",
]:
    print(f"  IN : {probe!r}")
    print(f"  OUT: {sanitize_like_app(probe)!r}")
    print()
