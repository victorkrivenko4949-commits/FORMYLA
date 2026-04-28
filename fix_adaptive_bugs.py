# -*- coding: utf-8 -*-
# Fix adaptive test bugs A, B, D in app.py

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

fixes_applied = []

# FIX 1 (Bug B): Add canonical answer trust instruction to system prompt
# The AI must trust the canonical answer, not re-solve the task
OLD_SYSTEM_INTRO = '''                system_prompt = """Ты — справедливое жюри математической олимпиады.
Твоя задача: оценить решение ученика и дать конструктивный фидбек.'''

NEW_SYSTEM_INTRO = '''                system_prompt = """Ты — проверяющий математических задач платформы FORMYLA.
У тебя ЕСТЬ правильный ответ из базы данных. Твоя задача: сравнить ответ ученика с КАНОНИЧЕСКИМ ответом и дать конструктивный фидбек.

КРИТИЧЕСКИ ВАЖНО:
❌ ЗАПРЕЩЕНО решать задачу заново своим способом
❌ ЗАПРЕЩЕНО утверждать что канонический ответ неверен
❌ ЗАПРЕЩЕНО предлагать альтернативные "правильные" ответы
✅ ОБЯЗАТЕЛЬНО доверяй полю "Правильный ответ" — это истина из базы данных
✅ Сравнивай ответ ученика ТОЛЬКО с каноническим ответом'''

if OLD_SYSTEM_INTRO in content:
    content = content.replace(OLD_SYSTEM_INTRO, NEW_SYSTEM_INTRO, 1)
    fixes_applied.append('FIX 1 (Bug B): Added canonical answer trust instruction')
else:
    fixes_applied.append('FIX 1 SKIP: pattern not found')

# FIX 2 (Bug A): Fix misleading "+2 уровня" label in system prompt
# Backend only does +1 for score=2, so the label is wrong
OLD_SCORE2_LABEL = '   score = 2 (ИДЕАЛЬНО, +2 уровня):'
NEW_SCORE2_LABEL = '   score = 2 (ИДЕАЛЬНО, +1 уровень):'

if OLD_SCORE2_LABEL in content:
    content = content.replace(OLD_SCORE2_LABEL, NEW_SCORE2_LABEL, 1)
    fixes_applied.append('FIX 2 (Bug A): Fixed score=2 label from "+2 уровня" to "+1 уровень"')
else:
    fixes_applied.append('FIX 2 SKIP: pattern not found')

# FIX 3 (Bug A): Fix UI verdict label for score=2 in adaptive_test_simple.html
# This is in templates, not app.py - handled separately

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('app.py fixes:')
for fix in fixes_applied:
    print(f'  {fix}')

# FIX 4 (Bug A): Fix "+1 уровень" label in adaptive_test_simple.html
with open('templates/adaptive_test_simple.html', 'r', encoding='utf-8') as f:
    html = f.read()

OLD_VERDICT_CORRECT = '''    if (result.score === 2) {
        verdictHTML = `
            <div class="verdict-success">
                ✅ Верно! +1 уровень
                <div class="level-badge">Уровень: ${result.new_level}/7</div>
            </div>
        `;'''

NEW_VERDICT_CORRECT = '''    if (result.score === 2) {
        verdictHTML = `
            <div class="verdict-success">
                ✅ Верно! Уровень: ${result.new_level}/7 (+1)
                <div class="level-badge">Уровень: ${result.new_level}/7</div>
            </div>
        `;'''

if OLD_VERDICT_CORRECT in html:
    html = html.replace(OLD_VERDICT_CORRECT, NEW_VERDICT_CORRECT, 1)
    print('FIX 4 (Bug A): Fixed verdict label in adaptive_test_simple.html')
else:
    print('FIX 4 SKIP: pattern not found in template')

with open('templates/adaptive_test_simple.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('All fixes applied successfully.')
