# -*- coding: utf-8 -*-
"""
Авточистка текстов задач в olympiads.py (OLYMPIADS_DB).

Применяет регулярки для исправления:
1. Переносы слов (распо- ложены → расположены)
2. Кириллические переменные → латинские (АВС → ABC)
3. "Второй день" → удаление + пометка day=2
4. × → $\\times$
5. <ABC → $\\angle ABC$
6. 90° → $90^\\circ$
7. Переносы строк \\n → пробелы (кроме \\n\\n → абзац)
8. OCR-артефакты: ⩾ → $\\geqslant$, ⩽ → $\\leqslant$

Запуск:
    python scripts/fix_olympiad_text.py --dry-run   # показать примеры
    python scripts/fix_olympiad_text.py --commit     # применить и перезаписать olympiads.py
"""

import re
import sys
import os
import copy
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olympiads import OLYMPIADS_DB

# ── Маппинг кириллица → латиница для переменных ──────────────────
CYRILLIC_TO_LATIN = {
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'К': 'K',
    'М': 'M', 'Н': 'N', 'О': 'O', 'Р': 'P', 'Т': 'T',
    'Х': 'X', 'У': 'Y',
}

# Обычные русские слова, которые НЕ надо латинизировать
RUSSIAN_WORDS = {
    'НО', 'ОН', 'ТО', 'ОТ', 'НЕ', 'ТА', 'ТЕ', 'ТУ', 'НА', 'КА',
    'ОНО', 'ТОТ', 'ТАМ', 'ТУТ', 'КОТ', 'РОТ', 'НОС', 'ТОН',
    'ТОЖЕ', 'ТОМУ', 'КОМУ', 'НЕМУ', 'ТОНЕ', 'ТОНОМ',
    'ЕМУ', 'ЕСТ', 'ОСТ', 'ОСА', 'ОСЕ', 'НОК',
    'ММ', 'СМ', 'КМ', 'КГ', 'МА', 'МО',
}

CYRILLIC_VAR_LETTERS = 'АВСЕКМНОРТХУ'
cyrillic_var_re = re.compile(
    r'(?<![А-Яа-яЁё])([' + CYRILLIC_VAR_LETTERS + r']{2,5})(?![А-Яа-яЁё])'
)


def _inside_dollar(text, pos):
    """Проверяет, находится ли позиция pos внутри $...$."""
    count = 0
    for i in range(pos):
        if text[i] == '$' and (i == 0 or text[i-1] != '\\'):
            count += 1
    return count % 2 == 1


def _latinize_match(m):
    """Заменяет кириллическую 'переменную' на латинскую."""
    word = m.group(1)
    if word in RUSSIAN_WORDS:
        return m.group(0)  # не трогаем
    result = ''
    for ch in word:
        result += CYRILLIC_TO_LATIN.get(ch, ch)
    # Заменяем только саму группу, сохраняя окружение
    return m.group(0).replace(word, result)


def fix_text(text):
    """Применяет все исправления к тексту задачи. Возвращает (new_text, changes_list)."""
    original = text
    changes = []

    # 0. Удаление мусорных строк: метаданные этапов, авторские пометки
    prev = text
    # "Региональный этап, XXXX–XXXX учебный год" и подобные
    text = re.sub(r'\s*\d*\s*(?:Региональный|Заключительный|Муниципальный|Школьный)\s+этап,?\s*\d{4}[–-]\d{4}\s*учебный\s+год\.?\s*(?:Первый|Второй)?\s*(?:день)?\.?\s*', ' ', text)
    # "Первый день" / "Второй день" как отдельная строка
    text = re.sub(r'\s*Первый день\s*', ' ', text)
    # Авторские пометки в конце: "(О. Дмитриев)" или "(С. Берлов)" и т.д.
    # НЕ удаляем — они могут быть частью условия. Удаляем только если в самом конце + цифра
    text = re.sub(r'\s*\([А-Я]\.\s*[А-Яа-я]+\)\s*\d*\s*$', '', text)
    # Мусорные номера в конце текста (типа "6" после авторской пометки)
    text = re.sub(r'\s+\d{1,2}\s*$', '', text)
    text = text.strip()
    if text != prev:
        changes.append('remove-metadata-garbage')

    # 1. Переносы строк: \n\n → специальный маркер, затем \n → пробел
    if '\n' in text:
        text = text.replace('\n\n', '⟪PARA⟫')
        text = text.replace('\n', ' ')
        text = text.replace('⟪PARA⟫', '\n\n')
        # Убираем двойные пробелы
        text = re.sub(r'  +', ' ', text)
        if text != original:
            changes.append('newlines→spaces')

    # 2. Переносы слов: буква-дефис-пробел(ы)-буква
    prev = text
    text = re.sub(r'([а-яА-Яa-zA-Z])-\s+([а-яА-Яa-zA-Z])', r'\1\2', text)
    if text != prev:
        changes.append('hyphen-breaks')

    # 3. "Второй день" — удаляем (day будет проставлен отдельно)
    prev = text
    text = re.sub(r'\s*Второй день\s*', ' ', text)
    text = text.strip()
    if text != prev:
        changes.append('remove-second-day')

    # 4. × → $\\times$ (только если не уже внутри $...$)
    prev = text
    new_text = []
    i = 0
    in_dollar = False
    while i < len(text):
        if text[i] == '$' and (i == 0 or text[i-1] != '\\'):
            in_dollar = not in_dollar
            new_text.append(text[i])
        elif text[i] == '×' and not in_dollar:
            # Проверяем контекст: если окружено пробелами/цифрами
            new_text.append('$\\times$')
        else:
            new_text.append(text[i])
        i += 1
    text = ''.join(new_text)
    if text != prev:
        changes.append('multiply-sign')

    # 5. Угол: <ABC → $\\angle ABC$ (только если < перед 3-4 заглавными буквами,
    #    т.е. это именно угол, а не сравнение типа "x < AD")
    prev = text
    def angle_replace(m):
        if _inside_dollar(text, m.start()):
            return m.group(0)
        # Проверяем что перед < нет буквы/цифры/пробела+буквы (это сравнение)
        pos = m.start()
        if pos > 0 and text[pos-1] in ' \t':
            # Проверяем что перед пробелом стоит буква/цифра (значит это сравнение: "x < ABC")
            pre_pos = pos - 1
            while pre_pos > 0 and text[pre_pos-1] in ' \t':
                pre_pos -= 1
            if pre_pos > 0 and (text[pre_pos-1].isalnum() or text[pre_pos-1] in ')]}'):
                return m.group(0)  # это сравнение, не трогаем
        letters = m.group(1)
        return f'$\\\\angle {letters}$'
    # Паттерн: < перед 3-4 заглавными латинскими буквами (углы: ∠ABC, ∠ABCD)
    text = re.sub(r'<\s*([A-Z]{3,4})(?![a-zA-Z])', angle_replace, text)
    if text != prev:
        changes.append('angle-bracket')

    # 6. Градусы: число° → $число^\\circ$ (только если не внутри $...$)
    prev = text
    def degree_replace(m):
        if _inside_dollar(text, m.start()):
            return m.group(0)
        return f'${m.group(1)}^\\circ$'
    text = re.sub(r'(\d+)°', degree_replace, text)
    if text != prev:
        changes.append('degree-sign')

    # 7. OCR-артефакты: ⩾ → $\\geqslant$, ⩽ → $\\leqslant$
    prev = text
    # Только если не внутри $...$
    result = []
    in_dollar = False
    for i, ch in enumerate(text):
        if ch == '$' and (i == 0 or text[i-1] != '\\'):
            in_dollar = not in_dollar
            result.append(ch)
        elif ch == '⩾' and not in_dollar:
            result.append('$\\geqslant$')
        elif ch == '⩽' and not in_dollar:
            result.append('$\\leqslant$')
        else:
            result.append(ch)
    text = ''.join(result)
    if text != prev:
        changes.append('ocr-geq-leq')

    # 8. Кириллические переменные → латинские
    prev = text
    text = cyrillic_var_re.sub(_latinize_match, text)
    if text != prev:
        changes.append('cyrillic-vars')

    return text, changes


def detect_day(problems):
    """Определяет, какие задачи относятся ко 2-му дню.
    Возвращает dict: num → day (1 или 2)."""
    day_map = {}
    found_second_day = False
    for p in problems:
        text = p.get('text', '') + ' ' + p.get('original_text', '')
        if 'Второй день' in text:
            found_second_day = True
        num = p.get('num', 0)
        day_map[num] = 2 if found_second_day else 1
    
    # Если "Второй день" найден в задаче N, то задачи N и далее — день 2
    # Но текст "Второй день" обычно в конце задачи, значит ЭТА задача уже день 2
    return day_map


# ── Основная логика ──────────────────────────────────────────────

def main():
    mode = '--dry-run'
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if mode not in ('--dry-run', '--commit'):
        print("Использование: python scripts/fix_olympiad_text.py [--dry-run|--commit]")
        sys.exit(1)

    total_fixed = 0
    total_problems = 0
    change_counts = {}
    dry_run_examples = []

    # Глубокая копия для модификации
    db = copy.deepcopy(OLYMPIADS_DB)

    for entry in db:
        entry_id = entry.get('id', '?')
        olympiad = entry.get('olympiad', '?')
        year = entry.get('year', '?')
        grade = entry.get('grade', '?')
        round_key = entry.get('round', '?')

        # Определяем дни
        day_map = detect_day(entry.get('problems', []))

        for p in entry.get('problems', []):
            total_problems += 1
            text = p.get('text', '')
            num = p.get('num', '?')
            label = f"id={entry_id} {olympiad}/{year}/{grade}кл/{round_key} #{num}"

            # Сохраняем оригинал в text_archive (если ещё нет)
            if 'text_archive' not in p:
                p['text_archive'] = text

            # Применяем исправления
            new_text, changes = fix_text(text)

            # Проставляем day
            p['day'] = day_map.get(num, 1)

            if changes:
                total_fixed += 1
                p['text'] = new_text
                for c in changes:
                    change_counts[c] = change_counts.get(c, 0) + 1

                # Собираем примеры для dry-run
                if len(dry_run_examples) < 10:
                    dry_run_examples.append({
                        'label': label,
                        'changes': changes,
                        'before': text[:200],
                        'after': new_text[:200],
                    })

    # ── Вывод результатов ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  РЕЖИМ: {mode}")
    print(f"{'='*60}")
    print(f"Всего задач: {total_problems}")
    print(f"Исправлено: {total_fixed}")
    print(f"\nТипы исправлений:")
    for k, v in sorted(change_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    if dry_run_examples:
        print(f"\n{'─'*60}")
        print("ПРИМЕРЫ БЫЛО/СТАЛО:")
        print(f"{'─'*60}")
        for ex in dry_run_examples:
            print(f"\n📌 {ex['label']} [{', '.join(ex['changes'])}]")
            print(f"  БЫЛО: {ex['before']}")
            print(f"  СТАЛО: {ex['after']}")

    if mode == '--commit':
        # Перезаписываем olympiads.py
        olympiads_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'olympiads.py'
        )
        
        print(f"\n{'='*60}")
        print(f"  ЗАПИСЬ В {olympiads_path}")
        print(f"{'='*60}")

        # Генерируем Python-код
        lines = []
        lines.append("# -*- coding: utf-8 -*-")
        lines.append("# Baza olimpiad s vosstanovlennymi uslovijami")
        lines.append("# Updated: 2026-04-28 (auto-fixed by fix_olympiad_text.py)")
        lines.append("# Fields added: source_url, source_name, official_solution, solution_verified")
        lines.append("# Fields added: text_archive, day")
        lines.append("")
        lines.append("OLYMPIADS_DB = [")

        for entry in db:
            lines.append("    {")
            # Основные поля записи
            for key in ['id', 'olympiad', 'olympiad_title', 'year', 'grade', 'round', 'round_title']:
                if key in entry:
                    lines.append(f"        {json.dumps(key)}: {json.dumps(entry[key], ensure_ascii=False)},")
            
            # Задачи
            lines.append('        "problems": [')
            for p in entry.get('problems', []):
                lines.append("            {")
                for pk in ['num', 'text', 'text_archive', 'answer', 'solution', 'official_solution',
                           'solution_verified', 'original_text', 'day', 'image_url']:
                    if pk in p:
                        val = p[pk]
                        if isinstance(val, str):
                            # Экранируем для Python
                            val_repr = json.dumps(val, ensure_ascii=False)
                        else:
                            val_repr = json.dumps(val, ensure_ascii=False)
                        lines.append(f"                {json.dumps(pk)}: {val_repr},")
                lines.append("            },")
            lines.append("        ],")

            # Остальные поля записи
            for key in ['source_url', 'source_name']:
                if key in entry:
                    lines.append(f"        {json.dumps(key)}: {json.dumps(entry[key], ensure_ascii=False)},")
            
            lines.append("    },")

        lines.append("]")
        lines.append("")

        content = '\n'.join(lines)
        
        with open(olympiads_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Файл перезаписан: {olympiads_path}")
        print(f"   Размер: {len(content)} байт")
        print(f"   Записей: {len(db)}")
    else:
        print(f"\n⚠️  Это --dry-run. Для применения запустите:")
        print(f"    python scripts/fix_olympiad_text.py --commit")


if __name__ == '__main__':
    main()
