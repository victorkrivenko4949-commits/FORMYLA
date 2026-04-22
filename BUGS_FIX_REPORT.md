# BUGS_FIX_REPORT.md

## FORMYLA — Bug Fix Report
**Дата:** 2026-04-23  
**Статус:** ✅ Все 3 бага исправлены

---

## БАГ 1: Переработка страницы Daily Quest

### Проблема
`templates/daily.html` отображался как сырой markdown без стилей. Использовался `enumerate()` (недоступен в Jinja2). Тема задачи не переводилась на русский.

### Исправления

**`templates/daily.html`** — полностью переписан:
- Структура: Hero (streak) → AI-интро → Прогресс → Сетка задач → Награды
- Jinja2 `enumerate()` заменён на `loop.index0`
- Словарь перевода тем: `{'algebra': 'Алгебра', 'geometry': 'Геометрия', ...}`
- Markdown `ai_comment` рендерится через `| safe` (конвертируется в роуте)

**`static/css/daily.css`** — полностью переписан по спецификации:
- CSS переменные: `--daily-neon: #38ef7d`, `--daily-teal: #11998e`, `--daily-flame: #f97316`
- `.daily-hero` с градиентным фоном и glow
- `.streak-flame` с анимацией `flame-flicker`
- `.streak-number` с gradient text (72px, font-weight 900)
- `.task-card` с состояниями: `done`, `current` (pulse анимация), `locked`
- `.btn-start` с gradient background
- Mobile-first: breakpoint 768px

**`app.py` — `daily_quest_main()`** — добавлен markdown → HTML конвертер:
```python
import markdown as md_lib
ai_comment_html = Markup(md_lib.markdown(quest.ai_comment, extensions=['nl2br']))
```
Fallback через regex если `markdown` не установлен.

### HTML-дамп (ключевые элементы)
```html
<section class="daily-hero">
  <span class="streak-flame">🔥</span>
  <span class="streak-number">5</span>
  <span class="streak-label">дней подряд</span>
</section>

<article class="task-card current">
  <div class="task-number">1</div>
  <div class="task-topic">АЛГЕБРА</div>
  <a href="/daily/task/0" class="btn-start">🚀 Решить</a>
</article>
```

---

## БАГ 2: Привязка Yandex ID

### Проблема
Кнопка "Привязать" в профиле вела на `/link_yandex` → `/yandex_login` → проверка `YANDEX_CLIENT_ID` → если не настроен, редирект на `/login` → редирект на `/` (пользователь уже залогинен).

### Исправления

**`app.py` — `yandex_login_start()`**:
```python
if not client_id:
    flash('Яндекс OAuth не настроен на сервере.', 'error')
    if current_user.is_authenticated:
        return redirect(url_for('profile'))  # ← было: redirect(url_for('login'))
    return redirect(url_for('login'))
```

**`app.py` — `/auth/yandex/login`**:
```python
# Поддержка linking_mode из JSON тела (для виджета на профиле)
is_linking = session.pop('linking_mode', False) or data.get('linking_mode', False)
```

**`templates/profile.html`** — кнопка заменена на YaAuthSuggest виджет:
```html
<div id="yandex-link-loading">Загрузка...</div>
<div id="yandex-link-container" style="display: none;"></div>
```

JS инициализация (аналогично login.html):
```javascript
window.YaAuthSuggest.init({
    client_id: clientId,
    response_type: "token",
    redirect_uri: domain + "/yandex_receiver"
}, domain, { view: "button", parentId: "yandex-link-container", ... })
.then(result => result.handler())
.then(data => {
    fetch('/auth/yandex/login', {
        method: 'POST',
        body: JSON.stringify({ access_token: data.access_token, linking_mode: true })
    })
})
```

> **Важно для продакшена:** Добавить в Yandex Developer Console:
> - `https://formyla-com.onrender.com/yandex_receiver`
> - `http://localhost:5001/yandex_receiver`

---

## БАГ 3: "Задачи дня" в navbar

### Проблема
Ссылка на Daily Quest отсутствовала в навигации.

### Исправления

**`templates/base.html`** — добавлена ссылка в `<nav>`:
```html
{% if current_user.is_authenticated %}
<a href="{{ url_for('daily_quest_main') }}" class="daily-link">
  <span class="daily-icon">🔥</span>
  Задачи дня
  {% set dq = current_user.today_quest() %}
  {% if dq and dq.completed_count >= dq.total_count %}
    <span class="daily-badge done">✓</span>
  {% elif dq %}
    <span class="daily-badge">{{ dq.completed_count }}/{{ dq.total_count }}</span>
  {% else %}
    <span class="daily-badge new">NEW</span>
  {% endif %}
</a>
{% endif %}
```

**`models.py` — `User.today_quest()`**:
```python
def today_quest(self):
    from datetime import date
    return DailyQuest.query.filter_by(
        user_id=self.id, date=date.today()
    ).first()
```

**`static/style.css`** — добавлены стили:
```css
.daily-link {
    background: linear-gradient(135deg, rgba(17,153,142,0.2), rgba(56,239,125,0.2));
    border: 1px solid rgba(56,239,125,0.35);
    border-radius: 8px;
    padding: 8px 14px;
}
.daily-badge { background: #38ef7d; color: #000; }
.daily-badge.done { background: #11998e; color: #fff; }
.daily-badge.new { background: #f97316; animation: pulse-new 1.5s infinite; }
```

---

## Статус сервера

| Роут | Статус | Описание |
|------|--------|----------|
| `GET /` | 200 ✅ | Главная страница |
| `GET /daily` | 302 ✅ | Redirect to login (корректно для анонимных) |
| `GET /api/daily/status` | 200 ✅ | JSON статус (для залогиненных) |
| `GET /profile` | 200 ✅ | Профиль с Yandex виджетом |

---

## Коммиты

```
eccaa31 fix(daily): proper styling with FORMYLA design system + markdown render + Yandex link + navbar
bf9f33e fix: PROBLEMS_DB list format, Jinja2 enumerate, Yandex OAuth redirect
```
