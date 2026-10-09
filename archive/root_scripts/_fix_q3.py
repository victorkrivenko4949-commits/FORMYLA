# -*- coding: utf-8 -*-
"""Q3 fix: remove old radar from curator prompt when level_by_section exists."""
path = "routes/prep.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Line 2470 area: find and replace the prompt construction
old = '''    radar_block = "\\n".join(radar_lines) or "  (нет данных)"
    plan_block = "\\n".join(plan_lines) or "  (планов нет)"

    prompt = (
        f"{card_text}\\n\\n"
        f"ДАННЫЕ ОБ УЧЕНИКЕ (из профиля):\\n"
        f"Радар подтем (навык 0-100):\\n{radar_block}\\n\\n"
        f"Слабые подтемы: {weak_names_str}\\n\\n"
        f"Планы подготовки:\\n{plan_block}\\n\\n"
        f"ВОПРОС УЧЕНИКА: {message}"
    )'''

new = '''    plan_block = "\\n".join(plan_lines) or "  (планов нет)"

    # Q3 (2026-07-28): if level_by_section exists, card_text already has mu 1..5;
    # remove old radar (0-100) to avoid two conflicting scales in one prompt.
    _has_by_section = bool(student_card.get("level_by_section")) if student_card else False
    if _has_by_section:
        prompt = (
            f"{card_text}\\n\\n"
            f"Слабые подтемы: {weak_names_str}\\n\\n"
            f"Планы подготовки:\\n{plan_block}\\n\\n"
            f"ВОПРОС УЧЕНИКА: {message}"
        )
    else:
        # Fallback for users without level_by_section data
        radar_block = "\\n".join(radar_lines) or "  (нет данных)"
        prompt = (
            f"{card_text}\\n\\n"
            f"ДАННЫЕ ОБ УЧЕНИКЕ (из профиля):\\n"
            f"Радар подтем (навык 0-100):\\n{radar_block}\\n\\n"
            f"Слабые подтемы: {weak_names_str}\\n\\n"
            f"Планы подготовки:\\n{plan_block}\\n\\n"
            f"ВОПРОС УЧЕНИКА: {message}"
        )'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Q3 fix APPLIED successfully")
else:
    print("OLD block NOT FOUND")
    # Debug: find the area
    idx = content.find("radar_block")
    if idx > 0:
        print(repr(content[idx:idx+200]))
