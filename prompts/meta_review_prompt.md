# META REVIEW PROMPT
# Model: anthropic/claude-opus-4.1 | Temperature: 0.2
# Purpose: Review complete variant (5 problems) for coherence
# Input: All 5 problems + analysis profile
# Output: JSON verdict - approve or reject specific positions
# Called ONCE after all 5 problems are generated

---

## System Message

Ты — главный редактор олимпиадного сборника. Проверь ВАРИАНТ ЦЕЛИКОМ (5 задач) на внутреннюю согласованность.

## User Message Template

```
ОЛИМПИАДА: {olympiad_title}, {grade} класс, {round_title}
ДАТА ВАРИАНТА: {date}

═══════════════════════════════════════════════════════
ВАРИАНТ (5 задач):
═══════════════════════════════════════════════════════

ЗАДАЧА 1 (тема: {topic1}, сложность: {diff1}/10):
{statement1}
Ответ: {answer1}

ЗАДАЧА 2 (тема: {topic2}, сложность: {diff2}/10):
{statement2}
Ответ: {answer2}

ЗАДАЧА 3 (тема: {topic3}, сложность: {diff3}/10):
{statement3}
Ответ: {answer3}

ЗАДАЧА 4 (тема: {topic4}, сложность: {diff4}/10):
{statement4}
Ответ: {answer4}

ЗАДАЧА 5 (тема: {topic5}, сложность: {diff5}/10):
{statement5}
Ответ: {answer5}

═══════════════════════════════════════════════════════
ПРОФИЛЬ ОЛИМПИАДЫ:
{style_notes}
Ожидаемое распределение тем: {themes_distribution}
Ожидаемый рост сложности: {expected_difficulties}

═══════════════════════════════════════════════════════
ПРОВЕРЬ:

1. ТЕМЫ НЕ ДУБЛИРУЮТСЯ: все 5 задач на разные темы/подтемы
2. СЛОЖНОСТЬ РАСТЁТ: задача 1 легче задачи 5 (допустимо: +-1 уровень)
3. СТИЛЬ ЕДИНЫЙ: все задачи выглядят как один вариант одной олимпиады
4. НЕТ ПЕРЕСЕЧЕНИЙ: задачи не используют одинаковые числа/конструкции
5. БАЛАНС: есть и вычислительные, и доказательные задачи

Верни ТОЛЬКО валидный JSON:
{
  "verdict": "approve" или "reject",
  "theme_diversity": true/false,
  "difficulty_progression": true/false,
  "style_consistency": true/false,
  "no_overlaps": true/false,
  "balance_ok": true/false,
  "issues": ["список проблем"],
  "reject_positions": [номера задач для перегенерации, если reject],
  "suggestions": ["что исправить"]
}

Если всё хорошо:
{
  "verdict": "approve",
  "theme_diversity": true,
  "difficulty_progression": true,
  "style_consistency": true,
  "no_overlaps": true,
  "balance_ok": true,
  "issues": [],
  "reject_positions": [],
  "suggestions": []
}
```

## Few-shot Examples

### Example 1: APPROVE (good variant)
Variant: difficulties 4, 5, 6, 7, 9. Themes: algebra, geometry, combinatorics, number_theory, logic.
```json
{
  "verdict": "approve",
  "theme_diversity": true,
  "difficulty_progression": true,
  "style_consistency": true,
  "no_overlaps": true,
  "balance_ok": true,
  "issues": [],
  "reject_positions": [],
  "suggestions": []
}
```

### Example 2: REJECT (problem 3 same difficulty as problem 5)
Variant: difficulties 4, 6, 9, 7, 9. Themes: algebra, geometry, algebra, number_theory, combinatorics.
```json
{
  "verdict": "reject",
  "theme_diversity": false,
  "difficulty_progression": false,
  "style_consistency": true,
  "no_overlaps": true,
  "balance_ok": true,
  "issues": ["Задача 3 (сложность 9) сложнее задачи 4 (сложность 7) — нарушена прогрессия", "Задачи 1 и 3 обе на алгебру — дублирование темы"],
  "reject_positions": [3],
  "suggestions": ["Заменить задачу 3 на комбинаторику или логику со сложностью 6-7"]
}
```

## Decision Logic (in code)

- verdict == "approve" -> save variant with status='approved'
- verdict == "reject" -> regenerate only reject_positions (max 2 retries)
- If after 2 meta-review retries still rejected -> mark variant as 'needs_manual_review'
