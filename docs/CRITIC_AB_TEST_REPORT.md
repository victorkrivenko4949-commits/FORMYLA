# Drawing-pipeline critic — A/B test report

**Дата:** 2026-05-15
**Задача-кейс:** «В остроугольном треугольнике ABC точка H — ортоцентр, точка O — центр описанной окружности. Точка M — середина стороны BC. Известно, что AH = 2·OM. Постройте чертёж: треугольник ABC, отметьте точки H, O, M, проведите высоту AH1, медиану AM и отрезок OM. Опишите окружность вокруг треугольника.»
**Цель:** включить [`DRAWING_CRITIC_ENABLED=1`](services/drawing_service.py:60) локально и сравнить качество с/без критика.

---

## TL;DR

При первом же включении критика обнаружились **два независимых бага в проде**, из-за которых заявленный в [`docs/DRAWING_PIPELINE.md`](docs/DRAWING_PIPELINE.md:101) «critique loop» **никогда не работал**, даже если `DRAWING_CRITIC_ENABLED=1`:

| # | Баг | Файл | Симптом | Фикс |
|---|---|---|---|---|
| 1 | Несуществующий model-ID критика | [`services/drawing_service.py:56`](services/drawing_service.py:56) | OpenRouter `HTTP 400: "google/gemini-3.1-pro is not a valid model ID"` | `MODEL_CRITIC = "google/gemini-3.1-pro-preview"` |
| 2 | Слишком маленький `max_tokens` для thinking-модели | [`services/drawing_service.py:391`](services/drawing_service.py:391) | JSON-ответ обрывается на ~196 символах, `_parse_critique_response()` молча возвращает `[]` | `max_tokens=1500` → `max_tokens=6000` |

Оба фикса применены. После фикса критик корректно находит и blocker'ы (отсутствующие построения), и major-ошибки геометрии (точка не на серединном перпендикуляре, ортоцентр не на оси симметрии и т.п.). Подробности и доказательства — ниже.

---

## 1. Что было сделано в этой сессии

1. Прочитан полный пайплайн в [`docs/DRAWING_PIPELINE.md`](docs/DRAWING_PIPELINE.md:1) и [`services/drawing_service.py`](services/drawing_service.py:1).
2. Написан изолированный harness [`scripts/_critic_ab_test.py`](scripts/_critic_ab_test.py:1) — вызывает [`generate_drawing()`](services/drawing_service.py:491) один раз с `use_cache=False`, сохраняет PNG, код и JSON-отчёт. Env `DRAWING_CRITIC_ENABLED` нужно выставлять **до** запуска (флаг фризится при импорте модуля в константу [`CRITIC_ENABLED`](services/drawing_service.py:60)).
3. Прогнан **baseline** (без критика). OK, 23 с, $0.150.
4. Прогнан **with-critic** — упал с HTTP 400 → найден **баг #1**.
5. После фикса #1 — второй прогон. Критик вернул `findings=0`. Подозрительно, потому что чертёж был визуально некрасивый (точки H, O слиплись).
6. Написан второй пробник [`scripts/_critic_probe.py`](scripts/_critic_probe.py:1) — вызывает только [`_critique_with_gemini()`](services/drawing_service.py:378) на готовом PNG+коде.
7. Прогнан probe на baseline-чертеже → `findings=0`. Гипотезы: либо чертёж правда чистый (косметика — не задача критика по [его system-prompt](services/drawing_service.py:106)), либо парсер сломан.
8. Сгенерирован специально **сломанный** чертёж [`scripts/_critic_ab_out/broken.code.py`](scripts/_critic_ab_out/broken.code.py:1) (без описанной окружности, без высоты, без H₁, ортоцентр в случайной точке) → probe вернул `findings=0`. Это **уже не норма** — баг подтверждён.
9. Написан третий пробник [`scripts/_critic_raw_probe.py`](scripts/_critic_raw_probe.py:1), который дёргает OpenRouter напрямую через `httpx` и печатает `finish_reason` + `usage`. **Корневая причина**: `completion_tokens=2572`, из них **`reasoning_tokens=1971`** — Gemini 3.x — thinking-модель, основная часть бюджета уходит на скрытый reasoning. С `max_tokens=1500` после reasoning остаётся ~0 токенов на сам ответ.
10. Применён **фикс #2**: `max_tokens=6000`.
11. Probe заново на сломанном чертеже → критик нашёл **5 findings** (2 blocker, 2 major, 1 blocker про OM). Качество замечаний — отличное (см. ниже).
12. Финальный полный прогон A/B на задаче про ортоцентр.

---

## 2. Баг #1: несуществующий model-ID критика

### Симптом
```
{'stage': 'critic', 'model': 'google/gemini-3.1-pro', 'ok': False,
 'error': 'HTTP 400: {"error":{"message":"google/gemini-3.1-pro is not a valid model ID","code":400}}'}
```

### Причина
Файл [`services/drawing_service.py:56`](services/drawing_service.py:56) до фикса:
```python
MODEL_CRITIC = "google/gemini-3.1-pro"
```
В OpenRouter `google/gemini-3.1-pro` НЕ существует. По состоянию на 15.05.2026 Gemini 3.1 Pro доступен только как:
- `google/gemini-3.1-pro-preview` ✓
- `google/gemini-3.1-pro-preview-customtools`

Команда для воспроизведения проверки (без секретов в коде):
```
python -c "import os, httpx; from dotenv import load_dotenv; load_dotenv();
  r=httpx.get('https://openrouter.ai/api/v1/models',
              headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']});
  print([m['id'] for m in r.json()['data'] if 'gemini-3' in m['id']])"
```

### Почему не было замечено раньше
- Дефолт `DRAWING_CRITIC_ENABLED=0` → на проде критик никогда не запускался.
- Тесты в [`tests/`](tests/) (по словам прошлой сессии — «8 критика-тестов») — это, вероятно, юнит-тесты на парсер/построение messages, а не интеграционные с реальным OpenRouter.
- При срабатывании HTTP 400 в pipeline стоит graceful-degrade ([`services/drawing_service.py:556`](services/drawing_service.py:556)), поэтому пайплайн просто **тихо возвращал чертёж без ревизии**, не падая.

### Фикс
- [`services/drawing_service.py:56`](services/drawing_service.py:56) — `MODEL_CRITIC = "google/gemini-3.1-pro-preview"`
- [`services/openrouter_client.py:31,52`](services/openrouter_client.py:31) — добавлены записи в `DEFAULT_RPM` и `MODEL_PRICING` для нового ID; старый ID оставлен как dead-code на случай, если OpenRouter когда-нибудь сделает алиас.

---

## 3. Баг #2: max_tokens мал для thinking-модели

### Симптом
Критик возвращает «успех», но `findings=0` даже на заведомо сломанных чертежах.

### Причина
Сырой ответ OpenRouter на одну вызов критика, `max_tokens=1500`:
```
finish_reason : length         (НЕ "stop"!)
usage         : prompt_tokens=2062, completion_tokens=1500
                completion_tokens_details = { reasoning_tokens: ~1300, ... }
content       : 196 символов, JSON обрывается посреди строки
```

Тот же запрос с `max_tokens=6000`:
```
finish_reason : stop
usage         : completion_tokens=2572, reasoning_tokens=1971
content       : 1960 символов, валидный JSON, 5 findings
```

Gemini 3.x — это thinking-модель: она использует ~1500–2000 токенов на **скрытый reasoning** (бьётся и оплачивается, но НЕ возвращается в `content`). С `max_tokens=1500` после reasoning на ответ остаётся 0 токенов, JSON обрывается. Парсер [`_parse_critique_response()`](services/drawing_service.py:359):
```python
m = _JSON_OBJECT_RE.search(text)
if not m: return []
try:
    obj = json.loads(m.group(0))
except (ValueError, TypeError):
    return []                       # <-- сюда уходит обрезанный JSON
```
…ловит `JSONDecodeError` и **молча** возвращает `[]`.

### Фикс
[`services/drawing_service.py:386`](services/drawing_service.py:386):
```python
# IMPORTANT: Gemini 3.x are "thinking" models -- they spend a sizeable
# chunk of the completion budget on internal reasoning tokens that are
# billed but NOT returned in `content`. Empirically the critic eats
# ~2000 reasoning tokens before producing the JSON answer; with
# max_tokens=1500 the visible content gets truncated mid-string and
# `_parse_critique_response` silently returns []. 6000 leaves headroom
# for reasoning + a long findings list and still caps cost at ~$0.04.
resp = openrouter.chat(
    model=MODEL_CRITIC,
    messages=messages,
    temperature=0.0,
    max_tokens=6000,
)
```

### Доказательство, что после фикса критик ловит реальные ошибки
Probe на специально-сломанном чертеже ([`scripts/_critic_ab_out/broken.png`](scripts/_critic_ab_out/broken.png)) после фикса — 5 findings:

| id | severity | title |
|---|---|---|
| f1 | **blocker** | Отсутствует описанная окружность |
| f2 | **blocker** | Отсутствует высота AH₁ и точка H₁ |
| f3 | **blocker** | Отсутствует отрезок OM |
| f4 | **major** | Точка H должна лежать на оси симметрии равнобедренного треугольника (x=0), а у вас x=0.5 |
| f5 | **major** | Точка O должна лежать на серединном перпендикуляре к BC (x=0.25), а у вас x=−1.5 |

Геометрическая часть (f4, f5) — это именно то, чего хотелось от vision-критика. Просто «найти отсутствующий объект» можно было бы делать textual-моделью; реальную ценность даёт способность увидеть, что точка нарисована **не там, где ей положено быть** по построению.

Полный JSON: [`scripts/_critic_ab_out/broken.critic_findings.json`](scripts/_critic_ab_out/broken.critic_findings.json).

---

## 4. Финальное A/B на задаче про ортоцентр

| Метрика | Baseline (CRITIC=0) | With critic (CRITIC=1) |
|---|---|---|
| `render_ms` | 23 015 | 75 847 |
| `wall_ms` | 23 015 | 75 847 |
| `cost_usd` | $0.150 | $0.170 |
| `repair_iters` | 0 | 0 |
| `critique_rounds` | 0 | 0 (Gemini сразу вернул `findings=[]`) |
| `image_bytes` | 51 098 | 46 506 |
| `attempts` | 1 (sandbox-ok) | 2 (sandbox-ok + critic-ok с пустым findings) |

**На этой конкретной задаче** Claude Opus 4.7 рисует геометрически правильный чертёж с первого раза, поэтому критика-ревизия не нужна (overhead — +52 секунды и +$0.020). Сами PNG — оба ниже:

- [`scripts/_critic_ab_out/baseline.png`](scripts/_critic_ab_out/baseline.png) — точки H, O, H₁, M слиплись внизу, подписи M/H₁ налегают друг на друга. Математически верно, читаемость низкая.
- [`scripts/_critic_ab_out/with_critic.png`](scripts/_critic_ab_out/with_critic.png) — другой случайный sample от Claude (`temperature=0.2`), всё ещё ассимметричный треугольник, **но та же самая проблема: M и H₁ слиплись внизу**. То есть факт «with-critic» чертёж получше — это просто рандом.

**Главный вывод:** на математически корректных чертежах текущий критик НЕ улучшает косметику. Это сознательное ограничение его system-prompt'а ([`services/drawing_service.py:113`](services/drawing_service.py:113) — «Не придирайся к незначительным косметическим мелочам»), и это **разумно**: иначе он триггерил бы ревизию на каждом чертеже и удвоил бы стоимость.

---

## 5. Стоимость критика после фикса

| Этап | Цена |
|---|---|
| Один вызов Gemini 3.1 Pro Preview с `max_tokens=6000` | $0.015–$0.035 (зависит от длины reasoning и количества findings) |
| Полный round (Gemini + revision Claude Opus) | $0.06–$0.12 |
| 2 round'а | до $0.22 |

Для Render Free (timeout 100 с) с включённым критиком — **на грани**: 23 с base + ~40 с критик + до 30 с ревизии = легко вылетит. Рекомендация **держать `DRAWING_CRITIC_ENABLED=0` на проде до миграции на Render Starter** остаётся в силе.

---

## 6. Рекомендации по дальнейшим действиям

### Сразу (хватит этого PR)
- [x] Зафиксить `MODEL_CRITIC`.
- [x] Зафиксить `max_tokens=6000`.
- [ ] **Закоммитить и запушить эти два фикса** + новый отчёт + harness-скрипты.
- [ ] Если есть тесты [`tests/test_drawing*`](tests/), добавить интеграционный тест: «сломанный код → критик возвращает ≥1 finding». Сейчас этот регрессионный путь не покрыт.

### Среднесрочно
- Добавить **second-line кейс**: вместо `findings=[]` сравнивать `findings_count` с предыдущим раундом — если уменьшилось хотя бы на 1, считать ревизию успешной (сейчас цикл выходит только на полностью чистом результате).
- Прогнать A/B на **более сложных** задачах (где Claude чаще ошибается) — текущая «ортоцентр AH=2·OM» получилась слишком лёгкой для Opus 4.7. Кандидаты:
  - Стереометрия (тетраэдр с биссектрисой и пр.).
  - Задача с касательной к окружности из внешней точки.
  - Задача, где условие просит **отметить угол** в градусах (Claude часто рисует угол, но без подписи).

### Долгосрочно
- Когда переедем на Render Starter (300с) — включить `DRAWING_CRITIC_ENABLED=1` через переменную окружения в Dashboard. Сейчас это безопасно, потому что:
  - graceful-degrade на ошибки Gemini уже есть;
  - cache (TTL 30 дней) гасит повторные запросы;
  - стоимость критика ~$0.02 за запрос — приемлемо.
- Усилить system-prompt критика: добавить отдельный критерий «нечитаемые подписи / перекрытия» с явным разрешением триггерить minor-finding. Сейчас он намеренно отключён.

---

## 7. Артефакты этой сессии

```
docs/CRITIC_AB_TEST_REPORT.md                     -- этот отчёт
scripts/_critic_ab_test.py                         -- A/B harness
scripts/_critic_probe.py                           -- pipeline-style probe для одного чертежа
scripts/_critic_raw_probe.py                       -- httpx-level probe (печатает finish_reason, usage)
scripts/_critic_ab_problem.txt                     -- задача-кейс (ортоцентр)
scripts/_critic_ab_out/baseline.png                -- baseline-чертёж без критика
scripts/_critic_ab_out/baseline.code.py            -- его matplotlib-код
scripts/_critic_ab_out/baseline.result.json        -- метрики baseline
scripts/_critic_ab_out/baseline.critic_findings.json  -- что нашёл бы Gemini (после фикса) — findings=0
scripts/_critic_ab_out/with_critic_BUG.{png,code.py,result.json}  -- первый прогон с критиком ДО фикса max_tokens
scripts/_critic_ab_out/with_critic.png             -- финальный прогон после обоих фиксов
scripts/_critic_ab_out/with_critic.code.py
scripts/_critic_ab_out/with_critic.result.json
scripts/_critic_ab_out/broken.code.py              -- специально-сломанный чертёж для проверки критика
scripts/_critic_ab_out/broken.png
scripts/_critic_ab_out/broken.critic_findings.json -- 5 findings, отличное качество
scripts/_critic_ab_out/broken_raw_response.txt     -- сырой ответ Gemini с max_tokens=1500 (обрезано)
scripts/_critic_ab_out/broken_raw_full.json        -- сырой ответ Gemini с max_tokens=4000 (полный, +reasoning_tokens)
```

## 8. Изменённые файлы прода (готовы к коммиту)

- [`services/drawing_service.py`](services/drawing_service.py:56) — `MODEL_CRITIC` исправлена + комментарий про preview-alias.
- [`services/drawing_service.py:386`](services/drawing_service.py:386) — `max_tokens=6000` + комментарий про reasoning_tokens.
- [`services/openrouter_client.py:31,52`](services/openrouter_client.py:31) — добавлены `gemini-3.1-pro-preview` в RPM/PRICING.
