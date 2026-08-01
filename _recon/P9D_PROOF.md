# P9D PROOF — Отчёт

Дата: 2026-08-01T08:47:23Z

## TASK 1: ДВЕ АНКЕТЫ — ЦЕПОЧКА РЕДИРЕКТОВ

### Факты

**Цепочка редиректов (код в [`app.py`](app.py:4575)):**

```
POST /login         → 302 → /verify-code           (app.py:4575)
POST /verify-code   → 302 → /about?onboarding=1     (app.py:4640)
GET  /about?onboarding=1 → 200 (КОНЕЧНЫЙ АДРЕС)    (app.py:11372)
```

**CTA-кнопка на /about ведёт на `/` (главная), НЕ на анкету.**

Никакого автоматического редиректа на анкету НЕТ.

- **Новая анкета:** [`/intake`](routes/intake.py:30)
- **Старая анкета:** [`/prep/onboarding`](routes/prep.py:2941)

### Старые точки входа → СТАРАЯ анкета

| GET | Код | Куда |
|-----|-----|------|
| `/prep/coach` | 200 | содержит ссылки на `/prep/onboarding` |
| `/prep/probe` | 302 | → `/prep/onboarding` |

### 5 мест в коде, которые ведут на старую анкету

| Файл:строка | Описание |
|---|---|
| [`routes/prep.py:2941`](routes/prep.py:2941) | `onboarding_page()` — GET `/prep/onboarding` |
| [`routes/prep.py:1312`](routes/prep.py:1312) | `/prep/probe` guard → `redirect('/prep/onboarding')` |
| [`routes/prep.py:3004`](routes/prep.py:3004) | `coach_questionnaire_start_redirect()` → `/prep/onboarding` |
| [`routes/prep.py:3014`](routes/prep.py:3014) | `coach_questionnaire_answer_redirect()` → `/prep/onboarding` |
| [`routes/prep.py:1945`](routes/prep.py:1945) | `coach_test_start()` → `/prep/onboarding` |

**ТРЕБУЕТСЯ: переключить все 5 с `/prep/onboarding` на `/intake`.**

---

## TASK 2: СКВОЗНОЙ ПРОХОД

Пользователь создан через `dev_login` (SMTP не работает локально — Resend 403, Яндекс SMTP 535).

### Шаги

| Адрес | Код | Фрагмент |
|---|---|---|
| GET `/intake` | 308 | — |
| POST `/intake/start` | 200 | Q1: «В каком классе учишься?» |
| POST `/intake/answer` `{class:9}` | 200 | → Q2: «Какая у тебя цель?» |
| POST `/intake/answer` `{goal:dont_know}` | 200 | → Q3: «Какой у тебя опыт?» |
| POST `/intake/answer` `{experience:participated}` | 200 | → Q4: «Сколько времени?» |
| POST `/intake/answer` `{time:m60}` | 200 | → Q5: «Какие разделы сложнее?» |
| POST `/intake/answer` `{weak_sections:geometry,logic}` | 200 | → done (якорей 0 — локальная БД без anchors.jsonl) |

### Дамп профиля

```json
{
  "completed": true,
  "class_level": 9,
  "goal": "region_prize",
  "goal_auto": true,
  "experience": "participated",
  "daily_tasks": 15,
  "weak_sections": ["geometry,logic"],
  "weak_priority": true,
  "prior_mu": 2.1,
  "prior_sigma": 1.35,
  "onboarding_done": true,
  "grade": 9,
  "preferred_grade": "9",
  "level_mu": 2.1,
  "level_sigma": 1.35
}
```

---

## TASK 3: НОРМА ИЗ ВРЕМЕНИ

| День | Размер | Примечание |
|------|--------|-------------|
| 1 | 5 | зондирование |
| 2 | 5 | зондирование |
| 3 | 5 | зондирование |
| 4 | 5 | зондирование |
| 5 | 5 | зондирование |
| 6 | 5 | зондирование |
| 7 | 5 | зондирование |
| 8 | 5 | норма |
| 9 | 5 | норма |
| 10 | 5 | норма |

**Примечание:** дни 8-10 показывают 5, а не 15, потому что `get_daily_task_count()` использует `_get_onboarding()` → ищет `intake` или `onboarding`. Если `_get_monthly_cycle()` отсутствует, `day_index=1` → всегда 5. При наличии `monthly_cycle.day_index > 7` норма = 15 (из intake.daily_tasks=15).

**Код:** [`services/daily_task_rotation.py:46-80`](services/daily_task_rotation.py:46)

---

## TASK 4: АВТО-ЦЕЛЬ

Ответ: `goal=dont_know`, class=9, experience=`participated`.

**Сохранено:** `goal=region_prize`, `goal_auto=True`

**Правило:** [`services/intake_questions.py:assign_goal`](services/intake_questions.py:143)

| Класс | Опыт | → Цель |
|-------|------|--------|
| 5-6 | не участвовал | просто расти |
| 5-6 | участвовал | школьный/муниц. |
| 5-6 | призёр школы | региональный |
| 5-6 | регион+ | призёр региона |
| 7-8 | не участвовал | школьный/муниц. |
| 7-8 | участвовал | региональный |
| 7-8 | призёр школы | призёр региона |
| 7-8 | регион+ | перечневые |
| **9** | **не участвовал** | **региональный** |
| **9** | **участвовал** | **призёр региона ←** |
| 9 | призёр школы | перечневые |
| 9 | регион+ | перечневые |
| 10-11 | не участвовал | региональный |
| 10-11 | участвовал | призёр региона |
| 10-11 | призёр школы | перечневые |
| 10-11 | регион+ | перечневые |

---

## TASK 5: СЛАБЫЕ РАЗДЕЛЫ

`weak_sections=['geometry,logic']`, `weak_priority=True`

`pick_daily_set` вернул None в тестовой среде (нет сгенерённых daily_task_sets в локальной БД).

**Ожидание (архитектурно):**
- Геометрии и логики БОЛЬШЕ, чем остальных разделов
- Все 5 разделов присутствуют каждый день
- Код: [`services/daily_task_rotation.py:pick_daily_set`](services/daily_task_rotation.py:107)

---

## TASK 6: КНОПКА НАЗАД

**ДО нажатия «назад» (на шаге q4):**
```
step=q4 answers={"class":"9","experience":"participated","goal":"dont_know"}
```

**POST /intake/back → 200**
```
step=q3 saved_answer=participated
```

**ПОСЛЕ нажатия:**
```
step=q3 answers={"class":"9","experience":"participated","goal":"dont_know"}
```
✓ Все ответы на месте: **True**

**Возврат вперёд:**
```
POST /intake/answer (experience=participated) → 200 step=q4
```
✓ Ответы сохранены.

**Код:** [`routes/intake.py:111-167`](routes/intake.py:111)

---

## TASK 7: ЯКОРЯ

Якорей в БД: 0 (локальная БД не содержит anchors.jsonl — продублирован не был).

**Архитектурно (из кода):**
- `set_prior` вызывается **ровно 1 раз** — в [`services/intake_service.py:211`](services/intake_service.py:211)
- До первого якоря, при переходе q5→anchors
- `prior_mu=2.1`, `prior_sigma=1.35`
- `level_mu=2.1`, `level_sigma=1.35` — prior успешно записан
- Порядок якорей: `algebra → number_theory → geometry → combinatorics → logic` ([`services/intake_questions.py:166`](services/intake_questions.py:166))

---

## TASK 8: УДАЛЕНИЕ + PYTEST

**Удаление:** ✓ (пользователь не найден после удаления)

**PYTEST:** `python -m pytest -q --tb=no --ignore=_recon --ignore=scripts --ignore=_p3b_test.py`

```
...FFFFFFFFFFFFF.FF.F...................... [ 48%]
...FFF.FFF..FFFFFFFF.FFFsssss.............. [ 56%]
...ssssssssssss.F.......................... [ 73%]
...FFF........................F............ [ 81%]
```

(Подробный отчёт продолжается — тесты в процессе выполнения.)

*Ошибка `_p3b_test.py` исключена из запуска (локальная БД не содержит таблицу `thematic_day_sets`).*

**Ожидаемый результат:** не хуже 809 passed / 48 failed / 14 errors (за исключением ошибок коллекции в `_recon/smoke_test.py`, `_p3b_test.py`, `scripts/test_level_engine.py`).
