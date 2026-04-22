# FIXES_LOG.md — Daily Quest Bug Fixes

## Fix 1: Navbar "Задачи дня" button

**Проблема:** Кнопка была внутри `{% if current_user.is_authenticated %}` — не видна гостям.

**Решение:**
- `templates/base.html`: убрали условие `is_authenticated` снаружи ссылки
- Класс изменён с `.daily-link` на `.daily-nav-link` (по спецификации)
- CSS обновлён: оранжево-зелёный градиент, анимация огня
- Версионирование CSS: `?v={{ asset_version }}` (cache bust)
- `app.py`: добавлен `app.jinja_env.globals['asset_version']`

**Верификация:**
```
curl http://127.0.0.1:5001/ | grep daily-nav-link
→ <a href="/daily" class="daily-nav-link">  ✅
```

---

## Fix 2: Кнопка "Решить" на карточках задач

**Проблема:** Кнопка использовала класс `btn-start` вместо `btn-solve`.

**Решение:**
- `templates/daily.html`: изменён класс `btn-start` → `btn-solve`
- Текст: "🚀 Решить" → "🚀 Решить задачу"
- `static/style.css`: добавлен `.btn-solve` с зелёным градиентом

**Верификация:**
```
curl http://127.0.0.1:5001/daily | grep btn-solve
→ class="btn-solve"  ✅
```

---

## Fix 3: Уровень сложности для новичков (был 7, стал 3)

**Проблема:** `_generate_random_quest()` брал случайные задачи из всего PROBLEMS_DB, включая уровень 7.

**Решение:**
- `services/daily_quest_service.py`: фильтрация задач по `difficulty <= 3` для новичков
- Логирование уровней при генерации квеста

**Верификация:**
```
Логи при входе на /daily для нового юзера:
→ Random quest for user X: levels=[2, 3, 3, 2, 3]  ✅
```

---

## Mastery Dashboard

**Добавлено:**
- `templates/profile.html`: новый блок с кольцами прогресса, радар-диаграммой, AI-рекомендацией
- `static/css/mastery.css`: стили дашборда
- `static/js/mastery_radar.js`: Chart.js радар
- `app.py`: `compute_mastery_view()` — данные из TopicMastery

---

## Коммиты

```
acd7394 fix(nav): Daily Quest button globally visible v3 + mastery dashboard + difficulty fix
```
