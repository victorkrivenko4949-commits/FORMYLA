# -*- coding: utf-8 -*-
"""Fix prompt files: L1..L8 -> L1..L5."""
import sys

for fname in ['daily_tasks/pipeline/prompts/gpt_audit.md', 'daily_tasks/pipeline/prompts/opus_fix.md']:
    with open(fname, 'r', encoding='utf-8') as f:
        lines = f.read()

    # Replace headers
    lines = lines.replace('КАЛИБРОВКА СЛОЖНОСТИ L1..L8', 'КАЛИБРОВКА СЛОЖНОСТИ L1..L5')
    lines = lines.replace('по калибровке L1..L8', 'по калибровке L1..L5')
    lines = lines.replace('целое число 1..8', 'целое число 1..5')
    lines = lines.replace('(1..8)', '(1..5)')

    # Remove L6-L8 definitions and merge into L5
    # gpt_audit style
    old = '- **L5**: муниципальный (окружной) этап ВсОШ. Нужна нетривиальная идея, 2–3 шага.\n- **L6**: региональный этап ВсОШ. Требует комбинации идей, аккуратного перебора или конструкции.\n- **L7**: заключительный этап ВсОШ (лёгкие/средние номера). Серьёзная олимпиадная техника, нетривиальная оценка плюс конструкция.\n- **L8**: заключительный этап ВсОШ (сложные номера) / международный уровень. Глубокая идея, многоходовое доказательство.'
    new = '- **L5**: муниципальный этап ВсОШ и выше. Нужна нетривиальная идея, 2–3+ шага, региональный/заключительный этапы, комбинация идей, глубокая идея, многоходовое доказательство.'
    lines = lines.replace(old, new)

    # opus_fix style
    old2 = '- L5: муниципальный этап ВсОШ. Нетривиальная идея, 2–3 шага.\n- L6: региональный этап ВсОШ. Комбинация идей, аккуратный перебор или конструкция.\n- L7: заключительный этап ВсОШ (лёгкие/средние номера). Серьёзная техника, оценка + конструкция.\n- L8: заключительный этап ВсОШ (сложные номера) / международный уровень. Глубокая идея, многоходовое доказательство.'
    new2 = '- L5: муниципальный этап ВсОШ и выше. Нетривиальная идея, 2–3+ шага, региональный/заключительный этапы, комбинация идей, глубокая идея, многоходовое доказательство.'
    lines = lines.replace(old2, new2)

    # Fix level references
    lines = lines.replace('— это L5–L6, а НЕ L8', '— это L4–L5')
    lines = lines.replace('— это L5–L6, а НЕ L7+', '— это L4–L5')
    lines = lines.replace('— L4–L6, а НЕ L7', '— L3–L5')
    lines = lines.replace('— L5–L6, а не L8', '— L4–L5')
    lines = lines.replace('— L5–L6, а не L7+', '— L4–L5')
    lines = lines.replace('L7/L8', 'L5')
    lines = lines.replace('это ≤ L6', 'это L5')
    lines = lines.replace('L5–L6, а НЕ L7+', 'L4–L5')
    lines = lines.replace('L5–L6, а НЕ L8', 'L4–L5, а не L5')
    lines = lines.replace('L8 в геометрии', 'L5 в геометрии')
    lines = lines.replace('не дают L7/L8', 'не дают L5')
    lines = lines.replace('L5–L6, а не L8', 'L4–L5, а не L5')
    lines = lines.replace('L5–L6, а не L7+', 'L4–L5')

    with open(fname, 'w', encoding='utf-8') as f:
        f.write(lines)
    print(f'{fname}: done')
print('All done')
