# -*- coding: utf-8 -*-
"""Демонстрация P10 — все функции куратора на синтетических данных."""
import json, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

from curator.messenger import build_curator_message, validate_message, get_curator_card

# Синтетические факты для демонстрации
demo_facts = {
    "cycle_day": 3,
    "slice_done": False,
    "slice_total": 7,
    "today_total": 5,
    "today_solved": 0,
    "today_correct": 0,
    "today_pending": 5,
    "debt_size": 4,
    "debt_days_count": 2,
    "debt_burns_tomorrow": 2,
    "streak_days": 2,
    "missed_days_last_week": 2,
    "level_now": 3,
    "level_week_ago": 2,
    "level_delta": 1,
    "weakest_sections": [
        {"section": "geometry", "accuracy_pct": 25.0, "total_attempts": 8, "mu": 2.0},
        {"section": "combinatorics", "accuracy_pct": 50.0, "total_attempts": 6, "mu": 3.0},
    ],
    "tomorrow_subtopic": "G7_T012_S2",
    "tomorrow_section": "geometry",
    "method_code": "G1",
    "method_name": "Отрезки и углы",
    "method_source_line": "methods_catalog_105.json: method_code=G1",
    "grade": 7,
}

print("=" * 70)
print("ЗАДАЧА 2: ФАКТЫ — get_student_facts (синтетические данные)")
print("=" * 70)
print(json.dumps(demo_facts, ensure_ascii=False, indent=2))

print("\n" + "=" * 70)
print("ЗАДАЧА 3: СООБЩЕНИЯ — build_curator_message")
print("=" * 70)
msg = build_curator_message(demo_facts)
print(f"Сообщение: {msg!r}")

print("\n" + "=" * 70)
print("ЗАДАЧА 3: ПОВОДЫ — каждый по отдельности")
print("=" * 70)

# Повод 1: вчера ничего не решено
f1 = dict(demo_facts)
f1["debt_size"] = 0
f1["debt_burns_tomorrow"] = 0
f1["level_delta"] = 0
f1["weakest_sections"] = []
f1["method_code"] = None
f1["method_name"] = None
m1 = build_curator_message(f1)
print(f"  yesterday_zero: {m1!r}")

# Повод 2: есть долг и часть сгорит
f2 = dict(demo_facts)
f2["today_solved"] = 3
f2["level_delta"] = 0
f2["weakest_sections"] = []
f2["method_code"] = None
f2["method_name"] = None
m2 = build_curator_message(f2)
print(f"  debt_burns:     {m2!r}")

# Повод 3: срез не закончен
f3 = {
    "cycle_day": 4,
    "slice_done": False,
    "slice_total": 7,
    "today_total": 5,
    "today_solved": 3,
    "today_correct": 2,
    "today_pending": 2,
    "debt_size": 0,
    "debt_days_count": 0,
    "debt_burns_tomorrow": 0,
    "streak_days": 5,
    "missed_days_last_week": 0,
    "level_now": 3,
    "level_week_ago": 3,
    "level_delta": 0,
    "weakest_sections": [],
    "tomorrow_subtopic": None,
    "tomorrow_section": None,
    "method_code": None,
    "method_name": None,
    "method_source_line": None,
    "grade": 7,
}
m3 = build_curator_message(f3)
print(f"  slice_pending:  {m3!r}")

# Повод 4: уровень вырос
f4 = {
    "cycle_day": None, "slice_done": False, "slice_total": 0,
    "today_total": 5, "today_solved": 4, "today_correct": 4, "today_pending": 1,
    "debt_size": 0, "debt_days_count": 0, "debt_burns_tomorrow": 0,
    "streak_days": 7, "missed_days_last_week": 0,
    "level_now": 4, "level_week_ago": 3, "level_delta": 1,
    "weakest_sections": [],
    "tomorrow_subtopic": None, "tomorrow_section": None,
    "method_code": None, "method_name": None, "method_source_line": None,
    "grade": 7,
}
m4 = build_curator_message(f4)
print(f"  level_up:       {m4!r}")

# Повод 5: уровень просел
f5 = dict(f4)
f5["level_now"] = 2
f5["level_week_ago"] = 3
f5["level_delta"] = -1
m5 = build_curator_message(f5)
print(f"  level_down:     {m5!r}")

# Повод 6: слабый раздел
f6 = {
    "cycle_day": None, "slice_done": False, "slice_total": 0,
    "today_total": 5, "today_solved": 3, "today_correct": 2, "today_pending": 2,
    "debt_size": 0, "debt_days_count": 0, "debt_burns_tomorrow": 0,
    "streak_days": 3, "missed_days_last_week": 1,
    "level_now": 3, "level_week_ago": 3, "level_delta": 0,
    "weakest_sections": [
        {"section": "number_theory", "accuracy_pct": 20.0, "total_attempts": 10, "mu": 1.8},
    ],
    "tomorrow_subtopic": None, "tomorrow_section": None,
    "method_code": None, "method_name": None, "method_source_line": None,
    "grade": 9,
}
m6 = build_curator_message(f6)
print(f"  weak_section:   {m6!r}")

# Повод 7: завтрашняя тема и метод
f7 = {
    "cycle_day": None, "slice_done": False, "slice_total": 0,
    "today_total": 5, "today_solved": 5, "today_correct": 5, "today_pending": 0,
    "debt_size": 0, "debt_days_count": 0, "debt_burns_tomorrow": 0,
    "streak_days": 10, "missed_days_last_week": 0,
    "level_now": 4, "level_week_ago": 4, "level_delta": 0,
    "weakest_sections": [],
    "tomorrow_subtopic": "G8_T025_S0",
    "tomorrow_section": "algebra",
    "method_code": "D1",
    "method_name": "Делимость",
    "method_source_line": "methods_catalog_105.json: method_code=D1",
    "grade": 8,
}
m7 = build_curator_message(f7)
print(f"  tomorrow_method:{m7!r}")

print("\n" + "=" * 70)
print("ЗАДАЧА 4: ПРОВЕРКА ФАКТОВ")
print("=" * 70)

# Валидное сообщение
valid, reason = validate_message(m7, f7)
print(f"  Валидное сообщение: {valid}, reason={reason!r}")

# Сообщение с выдуманным числом
fake_msg = "Ты решил 15 задач из 5. Уровень 7 из 8."
valid2, reason2 = validate_message(fake_msg, f7)
print(f"  Выдуманное число (15): {valid2}, reason={reason2!r}")

# Сообщение с выдуманным названием
fake_msg2 = "Раздел Интегралы — 0% верных."
valid3, reason3 = validate_message(fake_msg2, f7)
print(f"  Выдуманное название: {valid3}, reason={reason3!r}")

print("\n" + "=" * 70)
print("ЗАДАЧА 5: КАРТОЧКА (данные для HTML)")
print("=" * 70)
card = {
    "message": m7,
    "facts": {k: f7.get(k) for k in ["cycle_day","slice_done","today_total","today_solved",
        "today_correct","debt_size","debt_days_count","debt_burns_tomorrow",
        "streak_days","level_now","level_delta","method_code","method_name"]}
}
print(json.dumps(card, ensure_ascii=False, indent=2))

print("\n" + "=" * 70)
print("ЗАДАЧА 5: ФРАГМЕНТ HTML КАРТОЧКИ")
print("=" * 70)
html = """<!-- CURATOR CARD — над блоком долга -->
<div class="dt-curator-card" style="
  background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%);
  border: 1px solid rgba(76,125,255,0.25);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  color: #c8d6e5;
  font-size: 14px;
  line-height: 1.6;
">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
    <span style="font-weight:700;font-size:15px;color:#7b9fff;">Куратор</span>
  </div>
  <div style="color:#e0e8f0;">
    Завтра тема требует метода D1 «Делимость».
  </div>
</div>"""
print(html)

print("\nГОТОВО.")
