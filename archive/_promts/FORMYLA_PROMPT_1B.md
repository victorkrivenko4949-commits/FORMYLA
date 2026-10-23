# ПРОМПТ 1Б — закрыть хвосты Т6 и Т10

Короткое задание перед промптом 2. Ничего нового не строится,
закрываются три недоделки прошлого диалога.

---

## Что произошло

Блок Т6 работу сделал, но не закрыл. Созданы `models_dashboard.py`
(31 строка) с моделью `UserDashboardItem`, `services/dashboard_widgets.py`
(83 строки) с `AVAILABLE_WIDGETS` на 11 виджетов,
`routes/dashboard_settings.py` (71 строка) с маршрутом
`/dashboard/settings`, `templates/dashboard_settings.html` (144 строки),
11 файлов в `templates/widgets/`, `tests/test_t6_dashboard.py` (48 строк).

Прогон падает на импорте:

```
tests/test_t6_dashboard.py:4: ImportError: cannot import name
'UserDashboardItem' from 'models'
```

Модель лежит в `models_dashboard.py`, а тест ждёт её в `models.py`.
Это расхождение адреса, а не отсутствие работы.

Карточка Т6 в `_recon/CHAIN_RUN.md` не дописана — есть только строка
СТАРТ от 2026-08-04 16:44. Из-за этого промпт 2 отказался стартовать.

В блоке Т10 один тест из шести падает: `share_progress`. В отчёте
причиной названо ограничение тестовой инфраструктуры. Это не причина,
а описание симптома. Тест надо починить.

---

## Правила

Всё из устава промпта 1 остаётся в силе. Коротко о главном.

Запрещены `git reset`, `git stash`, `git checkout`, `git rm`, force push,
rebase. Прод и Render не трогаются. Формулы уровня не меняются.
`data/anchors.jsonl` не перезаписывается. Тексты задач не редактируются.
Ключи только из `.env`, в отчётах `СКРЫТО`. Методы `olympiad_theory`
не трогать. Ни одного эмодзи.

Удалять тест, ставить `skip` или `xfail` ради зелёного прогона запрещено.

Работу Т10 и Т6 не переписывать заново. Задача — довести до рабочего
состояния то, что уже есть.

Запрещённые слова в отчёте: примерно, около, ~, архитектурно, выходит
за рамки, pre-existing, не связано с нашими изменениями, ожидаемо,
выполняется, ожидается. Нет файла или функции — ровно `NOT FOUND`.

---

## Что сделать

### Шаг 0. Журнал

Дописать в конец `_recon/CHAIN_RUN.md`:

```
## БЛОК T6_ХВОСТЫ — СТАРТ
Время старта: <YYYY-MM-DD HH:MM>
```

### Шаг 1. Разобраться, где живёт модель

Показать фактическое положение дел:

```powershell
Get-ChildItem models*.py | Select-Object Name, Length
Select-String -Path models_dashboard.py -Pattern "class UserDashboardItem"
Select-String -Path models.py -Pattern "class UserDashboardItem"
Select-String -Path tests\test_t6_dashboard.py -Pattern "import"
Select-String -Path routes\dashboard_settings.py -Pattern "import"
```

Для каждого — вывод целиком. Чего нет — `NOT FOUND`.

### Шаг 2. Свести модель в одно место

Все остальные модели проекта лежат в `models.py`. `UserDashboardItem`
должна лежать там же — иначе `db.create_all()` и миграции её не увидят.

Перенести класс `UserDashboardItem` из `models_dashboard.py` в `models.py`.
Класс перенести целиком, как есть, ничего в нём не меняя.

Файл `models_dashboard.py` после переноса удалить обычным удалением файла.
`git rm` не использовать.

Поправить импорты во всех местах, где модель использовалась:
`routes/dashboard_settings.py`, `tests/test_t6_dashboard.py` и везде,
где `grep -rn "models_dashboard"` даст совпадение. После правки:

```powershell
grep -rn "models_dashboard" . --include=*.py
```

Ожидается пусто.

### Шаг 3. Зарегистрировать blueprint

Проверить, зарегистрированы ли в приложении blueprint из
`routes/dashboard_settings.py` и из `routes/parent_teacher.py`:

```powershell
Select-String -Path app.py -Pattern "dashboard_settings|parent_teacher"
```

Если хотя бы один не зарегистрирован — зарегистрировать рядом
с остальными `register_blueprint` в `app.py`.

Затем проверить тестовую фикстуру приложения в `tests/conftest.py`.
Если она собирает приложение отдельно и регистрирует blueprint выборочно —
добавить недостающие. Если фикстура использует то же приложение, что
и боевой код, — ничего не менять и записать это фактом.

### Шаг 4. Починить тест share_progress

Открыть падающий тест в `tests/test_t10_groups.py`, запустить его
отдельно и привести полный вывод ошибки:

```powershell
python -m pytest tests/test_t10_groups.py -k share_progress -q --tb=long
```

Разобрать причину по фактическому тексту ошибки и починить. Чинится
либо фикстура, либо код маршрута, либо сам тест, если он написан
неверно. Что именно правилось и почему — в отчёт.

Если причина в незарегистрированном blueprint — она снимается шагом 3,
и это надо подтвердить повторным прогоном.

### Шаг 5. Приёмка Т6

```powershell
python -m pytest tests/test_t6_dashboard.py -q --tb=short
```

Ожидается 4 passed, 0 failed.

```python
import app as A
c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'
r = c.get('/dashboard/settings', follow_redirects=True)
print('STATUS', r.status_code)
print('LEN', len(r.data))
```

Ожидается 200 и непустая страница.

Проверить, что таблица виджетов создаётся:

```powershell
python -c "import sqlite3;c=sqlite3.connect('instance/formyla.db');[print(r) for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%dashboard%'\")]"
```

Если таблицы нет — создать её тем же способом, каким создаются остальные
таблицы проекта. Перед этим копия базы `formyla.db.bak_T6_хвосты_pre`.

Проверить состав виджетов:

```powershell
python -c "from services.dashboard_widgets import AVAILABLE_WIDGETS; print(len(AVAILABLE_WIDGETS)); [print(k) for k in AVAILABLE_WIDGETS]"
```

Ожидается 11 и перечень ключей.

### Шаг 6. Приёмка Т10

```powershell
python -m pytest tests/test_t10_groups.py -q --tb=short
```

Ожидается 6 passed, 0 failed.

```python
import app as A
c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'
for p in ['/teacher', '/parent', '/dashboard/settings']:
    r = c.get(p, follow_redirects=True)
    print(p, r.status_code)
```

Ни одного 500.

### Шаг 7. Полная базовая линия

```powershell
python -m pytest -q --tb=line
```

Прогон должен дойти до конца, без прерывания на ImportError. Четыре
числа записать. Ориентир: passed около 956, failed 37, skipped 17,
errors 0. Ориентир в отчёт вместо фактического вывода не подставлять.

Если `failed` больше 37 — назвать каждый лишний упавший тест поимённо
и указать, относится он к Т6, к Т10 или к более ранней работе.

### Шаг 8. Дописать карточку Т6

В `_recon/CHAIN_RUN.md` карточка Т6 отсутствует. Дописать её в конец
журнала по обычному формату, с фактическими числами шагов 5 и 7.
Строку СТАРТ от 16:44 не трогать и не удалять.

Отдельной карточкой дописать результат этого задания:

```
## БЛОК T6_ХВОСТЫ — <ГОТОВ|ЧАСТИЧНО|СОРВАЛСЯ>
Время старта: <YYYY-MM-DD HH:MM>
Время финиша: <YYYY-MM-DD HH:MM>
Файлы изменены: <список с числом строк>
Файлы удалены: <список>
Копия базы: <имя или НЕТ>
Коммит: <хеш и сообщение>
Тесты полный прогон: passed=<N> failed=<N> skipped=<N> errors=<N>
Приёмка Т6: <N> из 4
Приёмка Т10: <N> из 6
NOT FOUND: <список или НЕТ>
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: <список или НЕТ>
```

### Шаг 9. Коммит

```
git add -A
git commit -m "chain3b: T6 хвосты — модель в models.py, blueprint, тесты"
```

---

## Про рассылку кода приглашения

В хвостах Т10 записано, что рассылка пригласительного кода группы
по email требует решения человека. Решение принято: рассылки не будет.
Учитель показывает код ученику сам, ученик вводит его на
`/profile/join-group`. Ничего дописывать не нужно, пункт закрыт.
Убрать его из списка открытых вопросов.

---

## Завершение

Новый диалог не создавай, `new_task` не вызывай.

Выведи человеку сводку:

```
ХВОСТЫ ЗАКРЫТЫ

Модель UserDashboardItem: <в models.py | NOT FOUND>
models_dashboard.py: <удалён | остался, причина>
Ссылок на models_dashboard в коде: <N>
Blueprint dashboard_settings: <зарегистрирован | NOT FOUND>
Blueprint parent_teacher: <зарегистрирован | NOT FOUND>

Тесты Т6: <N> из 4
Тесты Т10: <N> из 6
Полный прогон: passed=<N> failed=<N> skipped=<N> errors=<N>

Карточка Т6 в журнале: <дописана | нет, причина>
Коммит: <хеш>
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: <список или НЕТ>
```

Если полный прогон прошёл до конца и обе карточки в журнале стоят
как ГОТОВ, последней строкой напиши ровно это:

ВСТАВЬ ПРОМПТ 2 В НОВЫЙ ДИАЛОГ.

Иначе последней строкой напиши, что именно осталось незакрытым.
