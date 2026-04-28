# -*- coding: utf-8 -*-
"""
Аудит текстов задач в OLYMPIADS_DB.
Ищет типичные проблемы: кириллические переменные, переносы слов,
нерендерящиеся формулы, служебные заголовки и т.д.

Запуск:
    python scripts/audit_olympiad_text.py
"""

import re
import sys
import os

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olympiads import OLYMPIADS_DB


# ── Вспомогательные функции ───────────────────────────────────────

def _is_russian_word(word):
    """Проверяет, является ли слово обычным русским словом (не переменной)."""
    russian_words = {
        'НО', 'ОН', 'ТО', 'ОТ', 'НЕ', 'ТА', 'ТЕ', 'ТУ', 'НА', 'КА',
        'ОНО', 'ТОТ', 'ТАМ', 'ТУТ', 'КОТ', 'РОТ', 'НОС', 'ТОН',
        'ТОЖЕ', 'ТОМУ', 'КОМУ', 'НЕМУ', 'ТОНЕ', 'ТОНОМ',
        'ЕМУ', 'ЕСТ', 'ОСТ', 'ОСА', 'ОСЕ',
    }
    return word in russian_words


def _inside_dollar(text, pos):
    """Проверяет, находится ли позиция pos внутри $...$."""
    count = 0
    for i in range(pos):
        if text[i] == '$' and (i == 0 or text[i-1] != '\\'):
            count += 1
    return count % 2 == 1


# ── Счётчики ──────────────────────────────────────────────────────
total_problems = 0
issues = {
    'multiply_sign':     [],  # "×" вне $...$
    'cyrillic_vars':     [],  # кириллические переменные (АВС, СД, СМ и т.д.)
    'hyphen_breaks':     [],  # переносы слов "распо- ложены"
    'second_day':        [],  # "Второй день" внутри text
    'angle_bracket':     [],  # "<X" (угол через <)
    'bare_sqrt_frac':    [],  # \sqrt/\frac без $
    'degree_sign':       [],  # 90° без $...$
    'broken_formulas':   [],  # r r r √, ⩾, ⩽ и подобные OCR-артефакты
    'line_breaks_in_text': [],  # \n внутри text (переносы строк из PDF)
}

# Паттерн для кириллических "переменных" — слова из 2-5 букв,
# состоящие ТОЛЬКО из кириллических букв, которые выглядят как латинские переменные
CYRILLIC_VAR_LETTERS = 'АВСЕКМНОРТХУ'
cyrillic_var_pattern = re.compile(
    r'(?<![А-Яа-яЁё])([' + CYRILLIC_VAR_LETTERS + r']{2,5})(?![А-Яа-яЁё])'
)

# Паттерн для переносов слов: буква-дефис-пробел(ы)/перенос-буква
hyphen_break_pattern = re.compile(r'([а-яА-Яa-zA-Z])-\s+([а-яА-Яa-zA-Z])')

# Паттерн для угла через < (напр. <ABC, <АВС)
angle_bracket_pattern = re.compile(r'<\s*([A-ZА-Я]{2,4})')

# Паттерн для \sqrt или \frac вне $...$
bare_math_pattern = re.compile(r'(?<!\$)\\(sqrt|frac|angle|times|cdot|ldots)\b')

# Паттерн для градусов вне $
degree_pattern = re.compile(r'\d+°')

# Паттерн для OCR-артефактов формул
broken_formula_pattern = re.compile(r'(?:r\s+r\s+r\s+√|[⩾⩽]|√\s*\.\s*\d)')

# ── Анализ ────────────────────────────────────────────────────────
examples = {k: [] for k in issues}

for entry in OLYMPIADS_DB:
    entry_id = entry.get('id', '?')
    olympiad = entry.get('olympiad', '?')
    year = entry.get('year', '?')
    grade = entry.get('grade', '?')
    round_key = entry.get('round', '?')

    for p in entry.get('problems', []):
        total_problems += 1
        text = p.get('text', '')
        num = p.get('num', '?')
        label = f"id={entry_id} {olympiad}/{year}/{grade}кл/{round_key} задача#{num}"

        # 1. Знак умножения ×
        if '×' in text:
            issues['multiply_sign'].append(label)
            if len(examples['multiply_sign']) < 5:
                idx = text.index('×')
                snippet = text[max(0, idx-20):idx+20]
                examples['multiply_sign'].append((label, snippet))

        # 2. Кириллические переменные
        matches = cyrillic_var_pattern.findall(text)
        if matches:
            real_vars = [m for m in matches if not _is_russian_word(m)]
            if real_vars:
                issues['cyrillic_vars'].append(label)
                if len(examples['cyrillic_vars']) < 5:
                    examples['cyrillic_vars'].append((label, ', '.join(real_vars[:5])))

        # 3. Переносы слов
        hmatches = hyphen_break_pattern.findall(text)
        if hmatches:
            issues['hyphen_breaks'].append(label)
            if len(examples['hyphen_breaks']) < 5:
                m = hyphen_break_pattern.search(text)
                snippet = text[max(0, m.start()-10):m.end()+10]
                examples['hyphen_breaks'].append((label, snippet))

        # 4. "Второй день"
        if 'Второй день' in text:
            issues['second_day'].append(label)
            if len(examples['second_day']) < 5:
                idx = text.index('Второй день')
                snippet = text[max(0, idx-30):idx+40]
                examples['second_day'].append((label, snippet))

        # 5. Угол через <
        if angle_bracket_pattern.search(text):
            issues['angle_bracket'].append(label)
            if len(examples['angle_bracket']) < 5:
                m = angle_bracket_pattern.search(text)
                snippet = text[max(0, m.start()-10):m.end()+10]
                examples['angle_bracket'].append((label, snippet))

        # 6. \sqrt/\frac без $
        if bare_math_pattern.search(text):
            issues['bare_sqrt_frac'].append(label)
            if len(examples['bare_sqrt_frac']) < 5:
                m = bare_math_pattern.search(text)
                snippet = text[max(0, m.start()-15):m.end()+15]
                examples['bare_sqrt_frac'].append((label, snippet))

        # 7. Градусы без $
        if degree_pattern.search(text):
            for dm in degree_pattern.finditer(text):
                if not _inside_dollar(text, dm.start()):
                    issues['degree_sign'].append(label)
                    if len(examples['degree_sign']) < 5:
                        snippet = text[max(0, dm.start()-10):dm.end()+10]
                        examples['degree_sign'].append((label, snippet))
                    break

        # 8. OCR-артефакты формул
        if broken_formula_pattern.search(text):
            issues['broken_formulas'].append(label)
            if len(examples['broken_formulas']) < 5:
                m = broken_formula_pattern.search(text)
                snippet = text[max(0, m.start()-15):m.end()+15]
                examples['broken_formulas'].append((label, snippet))

        # 9. Переносы строк \n
        if '\n' in text:
            issues['line_breaks_in_text'].append(label)
            if len(examples['line_breaks_in_text']) < 5:
                idx = text.index('\n')
                snippet = text[max(0, idx-15):idx+15].replace('\n', '⏎')
                examples['line_breaks_in_text'].append((label, snippet))


# ── Генерация отчёта ─────────────────────────────────────────────
report_lines = []
report_lines.append("# Аудит текстов задач OLYMPIADS_DB")
report_lines.append(f"\n**Дата**: 2026-04-28")
report_lines.append(f"**Всего записей (вариантов)**: {len(OLYMPIADS_DB)}")
report_lines.append(f"**Всего задач**: {total_problems}")
report_lines.append("")
report_lines.append("## Сводка проблем")
report_lines.append("")
report_lines.append("| # | Проблема | Кол-во задач | % от всех |")
report_lines.append("|---|---------|-------------|-----------|")

issue_names = {
    'multiply_sign':     '× (нерендерящееся умножение)',
    'cyrillic_vars':     'Кириллические переменные (АВС→ABC)',
    'hyphen_breaks':     'Переносы слов (распо- ложены)',
    'second_day':        '"Второй день" внутри text',
    'angle_bracket':     'Угол через < вместо ∠',
    'bare_sqrt_frac':    '\\sqrt/\\frac без $...$',
    'degree_sign':       'Градусы ° без $...$',
    'broken_formulas':   'OCR-артефакты формул (r r r √, ⩾)',
    'line_breaks_in_text': 'Переносы строк \\n в тексте',
}

for i, (key, name) in enumerate(issue_names.items(), 1):
    count = len(issues[key])
    pct = f"{count/total_problems*100:.1f}" if total_problems > 0 else "0"
    report_lines.append(f"| {i} | {name} | {count} | {pct}% |")

report_lines.append("")
report_lines.append("## Примеры проблем")
report_lines.append("")

for key, name in issue_names.items():
    if examples[key]:
        report_lines.append(f"### {name}")
        report_lines.append("")
        for label, snippet in examples[key]:
            report_lines.append(f"- **{label}**")
            report_lines.append(f"  `{snippet}`")
        report_lines.append("")

report_text = '\n'.join(report_lines)

# Сохраняем отчёт
output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'data', 'audit', 'olympiad_text_issues.md')
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(report_text)

# Выводим в консоль
print(report_text)
print(f"\n✅ Отчёт сохранён: {output_path}")
