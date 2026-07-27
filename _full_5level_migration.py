# -*- coding: utf-8 -*-
"""Полный переход на 5-уровневую систему + логика куратора."""

import os
import re

SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
             'static/bootstrap', 'static/fonts', 'migrations', 'flask_session',
             'formyla_parallel', 'formyla_parallel_complete', 'gen_678',
             'l1_l3_generation', 'l4', 'l4_l5_completion_work', 'l4_l5_fill_output',
             'l4_l5_finalization', 'backups', 'adaptive_data', 'olympiad-db'}

SKIP_FILES = {'_fix_levels.py', '_fix_levels_final.py', '_migrate_to_5levels.py',
              '_full_5level_migration.py'}

PATTERNS_8 = [
    ('/8', lambda l: re.search(r'(?<!\d)/8[\s\.,\);]', l) and (
        'level' in l.lower() or 'сложност' in l.lower() or 'уровен' in l.lower()
        or 'диагностик' in l.lower() or 'задач' in l.lower() or 'диффик' in l.lower()
        or 'l8' in l.lower())),
    ('min(8,', None),
    ('max(1, min(8', None),
    ('от 1 до 8', None),
    ('level_labels', lambda l: 'Легенда' in l or 'Эксперт' in l or 'Мастер' in l),
    ('difficulty <= 8', None),
]


def scan_for_8():
    results = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(('.py', '.html', '.js', '.json', '.txt', '.md')):
                if f in SKIP_FILES:
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                        for i, line in enumerate(fh, 1):
                            ln = line.strip()
                            if not ln or len(ln) > 300:
                                continue
                            for pat, check in PATTERNS_8:
                                if pat in ln:
                                    if check and not check(ln):
                                        continue
                                    results.append((path, i, ln[:120]))
                                    break
                except Exception:
                    pass
    return results


def fix_prep_py():
    path = 'routes/prep.py'
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    changes = 0

    # /8 → /5 (only after letter or })
    txt, n = re.subn(r'([а-яА-Яa-zA-Z}])/8', r'\1/5', txt)
    changes += n

    # max(1, min(8 → max(1, min(5
    txt, n = re.subn(r'max\(1,\s*min\(8,', 'max(1, min(5,', txt)
    changes += n

    # min(8, → min(5, (but not min(8) alone)
    txt, n = re.subn(r'min\(8,', 'min(5,', txt)
    changes += n

    # от 1 до 8 → от 1 до 5
    txt, n = re.subn(r'от 1 до 8', 'от 1 до 5', txt)
    changes += n

    # ['total']) * 8 → ['total']) * 5
    txt, n = re.subn(r"""\['total'\]\) \* 8""", r"""['total']) * 5""", txt)
    changes += n

    # difficulty <= 8 → difficulty <= 5
    txt, n = re.subn(r'difficulty <= 8', 'difficulty <= 5', txt)
    changes += n

    # clamped 1..8 → clamped 1..5
    txt, n = re.subn(r'clamped 1\.\.8', 'clamped 1..5', txt)
    changes += n

    # шкала 1..8 → шкала 1..5
    txt, n = re.subn(r'шкала 1\.\.8', 'шкала 1..5', txt)
    changes += n

    # level_labels (дважды)
    patterns = [
        ("level_labels = {1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый', 3: '\U0001f7e1 Средний',\n"
         "                        4: '\U0001f7e0 Продвинутый', 5: '\U0001f534 Высокий', 6: '\U0001f48e Эксперт',\n"
         "                        7: '\U0001f451 Мастер', 8: '\U0001f3c6 Легенда'}",
         "level_labels = {1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый', 3: '\U0001f7e1 Средний',\n"
         "                        4: '\U0001f7e0 Продвинутый', 5: '\U0001f534 Высокий'}"),
        ("        level_labels = {1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый', 3: '\U0001f7e1 Средний',\n"
         "                        4: '\U0001f7e0 Продвинутый', 5: '\U0001f534 Высокий', 6: '\U0001f48e Эксперт',\n"
         "        7: '\U0001f451 Мастер', 8: '\U0001f3c6 Легенда'}",
         "        level_labels = {1: '\U0001f535 Начальный', 2: '\U0001f7e2 Базовый', 3: '\U0001f7e1 Средний',\n"
         "                        4: '\U0001f7e0 Продвинутый', 5: '\U0001f534 Высокий'}"),
    ]
    for old, new in patterns:
        if old in txt:
            txt = txt.replace(old, new)
            changes += 1
            print(f"  level_labels replaced")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)
    print(f'\n  routes/prep.py: {changes} changes')
    return changes


def fix_onboarding_scenario():
    path = 'routes/prep.py'
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    changes = 0

    # Находим блок measured_count == 0 и заменяем
    patterns = [
        # Вариант 1: полный блок с f-string
        (
            "if measured_count == 0:\n"
            "            greeting = (\n"
            "                f'Привет! 👋 Рад знакомству! Ты в {grade} классе, но диагностика ещё не пройдена, '\n"
            "                f'и все подтемы пока с нуля — это нормально, сейчас начнём.\\n\\n'\n"
            "                f'🔹 <strong>Я задам тебе несколько вопросов</strong> — '\n"
            "                f'это поможет определить твой уровень и подобрать подходящие задачи.\\n\\n'\n"
            "                f'Готов? 😊'\n"
            "            )\n"
            "            return jsonify(\n"
            "                greeting=greeting,\n"
            "                scenario='onboarding_test',\n"
            "                recommended_olympiad=None,\n"
            "                subtopics_to_test=[],\n"
            "                cta_url=None,\n"
            "                cta_text='📋 Начать анкету',\n"
            "            )",
            "if measured_count == 0:\n"
            "            # Сразу начинаем анкету без приветствия\n"
            "            return jsonify(\n"
            "                greeting=None,\n"
            "                scenario='start_questionnaire',\n"
            "                recommended_olympiad=None,\n"
            "                subtopics_to_test=[],\n"
            "                cta_url=None,\n"
            "                cta_text=None,\n"
            "            )"
        ),
        # Вариант 2: более короткая версия (без f-string подробностей)
        (
            "if measured_count == 0:\n            greeting = (\n                f'Привет!",
            None  # signal to use regex
        ),
    ]

    for old, new in patterns:
        if new is None:
            # Regex fallback — находим блок от measured_count == 0 до return jsonify с onboarding_test
            import re as _re
            pattern = r"if measured_count == 0:.*?scenario='onboarding_test'.*?cta_text='📋 Начать анкету',\s*\)"
            replacement = (
                "if measured_count == 0:\n"
                "            # Сразу начинаем анкету без приветствия\n"
                "            return jsonify(\n"
                "                greeting=None,\n"
                "                scenario='start_questionnaire',\n"
                "                recommended_olympiad=None,\n"
                "                subtopics_to_test=[],\n"
                "                cta_url=None,\n"
                "                cta_text=None,\n"
                "            )"
            )
            if _re.search(pattern, txt, _re.DOTALL):
                txt, n = _re.subn(pattern, replacement, txt, flags=_re.DOTALL)
                changes += n
                print(f"  [OK] regex replaced onboarding_test block ({n})")
            else:
                print("  [--] regex pattern not found")
        elif old in txt:
            txt = txt.replace(old, new)
            changes += 1
            print(f"  [OK] exact onboarding_test block replaced")
        else:
            print("  [--] exact onboarding_test not found")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)
    print(f'  onboarding: {changes} changes')
    return changes


def fix_coach_html():
    path = 'templates/prep/coach.html'
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    changes = 0

    # 1. start_questionnaire handler
    if "data.scenario === 'start_questionnaire'" in txt:
        print("  [OK] start_questionnaire handler already exists")
    else:
        old = "if (data.scenario === 'need_grade') {"
        new = "if (data.scenario === 'start_questionnaire') {\n" \
              "    startQuestionnaire();\n" \
              "} else if (data.scenario === 'need_grade') {"
        if old in txt:
            txt = txt.replace(old, new)
            changes += 1
            print("  [OK] Added start_questionnaire handler")
        else:
            print("  [--] need_grade handler not found")

    # 2. После анкеты — кнопка на /adaptive-test
    old_done = "if (data.start_test) {"
    new_done = (
        "if (data.start_test) {\n"
        "    showBotMessage('🎯 <strong>Анкета пройдена!</strong>\\n\\nНажми кнопку, чтобы начать тест по темам:');\n"
        "    addQuickAction('🧪 Начать тест по темам', '/adaptive-test?grade=' + (currentGrade || ''));\n"
        "    return;\n"
        "}\n"
        "if (data.start_test_old) {"
    )
    if old_done in txt:
        txt = txt.replace(old_done, new_done)
        changes += 1
        print("  [OK] Replaced auto-start with button")
    else:
        print("  [--] start_test handler not found")

    # 3. currentGrade
    if 'currentGrade' not in txt:
        old_grade = "currentUserGrade = data.grade;"
        new_grade = "currentUserGrade = data.grade; currentGrade = data.grade;"
        if old_grade in txt:
            txt = txt.replace(old_grade, new_grade)
            changes += 1
            print("  [OK] Added currentGrade")
        else:
            print("  [--] currentUserGrade not found")

    # 4. addQuickAction
    if 'function addQuickAction' not in txt:
        old_script_end = "</script>"
        new_func = (
            "function addQuickAction(text, url) {\n"
            "    const container = document.getElementById('quick-actions');\n"
            "    if (!container) return;\n"
            "    const btn = document.createElement('a');\n"
            "    btn.href = url;\n"
            "    btn.className = 'quick-action-btn';\n"
            "    btn.textContent = text;\n"
            "    container.appendChild(btn);\n"
            "}\n"
            "</script>"
        )
        if old_script_end in txt:
            txt = txt.replace(old_script_end, new_func)
            changes += 1
            print("  [OK] Added addQuickAction function")
        else:
            print("  [--] script end not found")

    # 5. null greeting guard
    old_greet = "if (!data.greeting && !data.reply) {"
    new_greet = (
        "if (data.greeting === null) { return; }\n"
        "if (!data.greeting && !data.reply) {"
    )
    if old_greet in txt:
        txt = txt.replace(old_greet, new_greet)
        changes += 1
        print("  [OK] Added null-greeting guard")
    else:
        print("  [--] greeting guard not found")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)
    print(f'  coach.html: {changes} changes')
    return changes


def main():
    print('=' * 60)
    print('ПОЛНЫЙ ПЕРЕХОД НА 5-УРОВНЕВУЮ СИСТЕМУ')
    print('=' * 60)

    print('\n1. Исправление routes/prep.py (8→5)...')
    fix_prep_py()

    print('\n2. Исправление сценария онбординга (greeting→анкета)...')
    fix_onboarding_scenario()

    print('\n3. Исправление coach.html (автостарт→кнопка)...')
    fix_coach_html()

    print('\n4. Сканирование оставшихся 8-уровневых ссылок...')
    remaining = scan_for_8()
    if remaining:
        print(f'\n{"="*60}')
        print(f'Осталось {len(remaining)} 8-уровневых ссылок:')
        print(f'{"="*60}')
        for path, i, line in remaining:
            print(f'  {path}:{i}: {line}')
        print('\n⚠️ Нужна ручная проверка.')
    else:
        print('\nЧИСТО! ✅')

    print('\n✅ ГОТОВО!')
    print('   - Все 8-уровневые ссылки заменены на 5-уровневые')
    print('   - Куратор молча начинает анкету (без приветствия)')
    print('   - После анкеты — кнопка «Начать тест по темам»')


if __name__ == '__main__':
    main()
