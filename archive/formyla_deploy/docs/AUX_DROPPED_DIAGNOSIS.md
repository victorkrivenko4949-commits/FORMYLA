# FORMYLA — почему GPT возвращает aux, но чертёж «не появляется»

## TL;DR

GPT (`solver`) отрабатывает корректно, `aux_compiler.py` собирает валидный
план, `GeometricEngine.build()` рисует правильный aux‑SVG (центр `O`,
основания `A₁/B₁/C₁`, окружность). Пользователю показывается только базовый
треугольник, потому что **`audit_rendered_figure()` в `visual_audit.py`
возвращает непустой `errors[]`, и `_run_solver_aux_job()` немедленно вызывает
`_drop_aux(job, base_svg, "aux_visual_check_failed")`**.

Виновата не модель и не компилятор, а пост‑рендер аудит. И у него в текущей
обвязке нет ни лога, ни fallback‑поведения — любая ошибка (даже
косметическая, вроде `LABEL_COLLISION`) роняет весь aux.

## Точка отказа в коде

`routes/figures_generator.py` — функция `_run_solver_aux_job()`, стадия
`visual_check` (строки 1895–1905):

```python
# ── visual_check (повторно) ──
_set_stage(job, "visual_check")
try:
    visual = audit_rendered_figure(aux_svg, aux_ctx, merged, condition_text,
                                   settings=engine.settings)
except Exception:
    visual = None
if visual and visual.get("errors"):
    _drop_aux(job, base_svg, "aux_visual_check_failed")
    _charge_credit(job_id)
    return
```

Три проблемы в этих 10 строках:

1. **Любая ошибка = дроп.** Не различаются HARD‑ошибки (реально ломающие
   чертёж — пересечения линий, отсутствующие точки) и SOFT‑ошибки
   (`LABEL_COLLISION`, `TICK_OVERLAP`, «подпись слишком близко к линии» и
   т.п.). Для базового чертежа выше (строки 1559–1589) те же самые ошибки
   ТОЛЬКО логируются через `_record_stage` и **не приводят к failure**. Для
   aux — приводят. Это ассиметрия, из‑за которой aux‑построения (у которых
   объективно больше подписей и рисок → выше шанс `LABEL_COLLISION`) почти
   всегда отбраковываются.

2. **Нет `_record_stage(job_id, "visual_check", …)`.** В отличие от base
   (1578–1589), aux‑ветка не пишет ни `error_codes`, ни `visual_score`.
   Поэтому в БД и UI видно только `aux_dropped_reason="aux_visual_check_failed"`
   без деталей — вы не знаете, какие именно правила сработали.

3. **`except Exception: visual = None` молча глотает падение.** Если
   `audit_rendered_figure` кинул исключение (например, из‑за нового типа
   построения `incircle` — нативной цепочки `incenter + 3 altitude + circle`,
   которую аудит не ожидал), aux считается прошедшим (`visual is None` не
   попадает в `if visual and visual.get("errors")`). Но зато другие сценарии
   (успешный аудит с одним косметическим warning) — не проходят.

## Почему это особенно сильно бьёт по incircle

По README (`_recognize_incircle()` в `aux_compiler.py:340`) для вписанной
окружности компилятор синтезирует:

- 1 × `incenter`
- 3 × `line` (биссектрисы `A→O`, `B→O`, `C→O`)
- 3 × `altitude` (перпендикуляры из `O` на стороны, `foot_id = A₁/B₁/C₁`)
- 1 × `circle_center_radius`

Итого: 1 новая точка `O` + 3 новые точки `A₁/B₁/C₁` + 3 биссектрисы + 3
перпендикуляра + окружность. Все они получают подписи. Основания
`A₁/B₁/C₁` сидят прямо на сторонах треугольника, а `O` — во внутренней
области, куда «стекаются» все 6 линий. Практически гарантированные события:

- `LABEL_COLLISION` между `A₁` и подписью стороны `BC` (или её длиной).
- `LABEL_NEAR_LINE` для `O`.
- `TICK_OVERLAP`, если стороны уже несут метки равенства.

Ни одно из этих событий не означает, что чертёж неверен. Но текущая
логика на них падает.

## Как это чинить (три уровня, начиная с самого дешёвого)

### Уровень 1 (минимальный патч, ~5 строк) — не роняем aux на soft‑ошибках

`routes/figures_generator.py`, заменить блок 1895–1905:

```python
# ── visual_check (повторно) ──
_set_stage(job, "visual_check")
_t_visual = time.perf_counter()
try:
    visual = audit_rendered_figure(aux_svg, aux_ctx, merged, condition_text,
                                   settings=engine.settings)
except Exception as e:
    logger.warning("[figures_gen] aux visual_check crashed job %d: %s", job_id, e)
    visual = None

# Классифицируем ошибки: hard роняет aux, soft — только логируется.
HARD_VISUAL_CODES = {
    "MISSING_POINT", "MISSING_LABEL", "DEGENERATE_TRIANGLE",
    "LINE_OUT_OF_CANVAS", "POINT_NOT_ON_LINE", "CIRCLE_RADIUS_ZERO",
    # добавить сюда только то, что реально означает «чертёж неверен»
}
errors = (visual or {}).get("errors", []) or []
hard = [e for e in errors if e.split(":")[0] in HARD_VISUAL_CODES]
soft = [e for e in errors if e.split(":")[0] not in HARD_VISUAL_CODES]

if visual is not None:
    _record_stage(
        job_id, "visual_check",
        coverage_score=visual.get("visual_score"),
        validation_passed=(not hard),
        error_codes=[e.split(":")[0] for e in errors],
        latency_ms=int((time.perf_counter() - _t_visual) * 1000),
        visual_score=visual.get("visual_score"),
        label_collisions=len([e for e in errors if "LABEL_COLLISION" in e]),
    )

if hard:
    _drop_aux(job, base_svg, "aux_visual_check_failed")
    _charge_credit(job_id)
    return

if soft:
    # Не роняем aux, но помечаем для UI.
    job.aux_reason = (job.aux_reason or "") + f" [visual_warnings: {len(soft)}]"
    db.session.commit()
```

Точный список `HARD_VISUAL_CODES` нужно свести с содержимым
`services/visual_audit.py` (он не приложен к бандлу — нужен для окончательной
версии). До получения файла безопасный вариант — начать с ПУСТОГО `HARD_*`
set (то есть визуал‑аудит становится чисто логирующим для aux, как и для
base). Это гарантированно чинит текущий баг ценой того, что визуальные
проблемы будут только в логе, а не блокирующими.

### Уровень 2 — трактовать аудит как «мягкий» и для aux, и для base

Симметрия с base‑ветвью (1559–1589), где `visual` только пишется в
`_record_stage` и участвует лишь в `_needs_llm_audit(...)`. Тот же паттерн
для aux: сохранить `errors`/`visual_score` в БД, а решение о дропе принимать
только по `answer_verdict` (уже есть, 1828) и `usefulness.get("useful")`
(уже есть, 1874). Визуальный аудит становится тем, чем и должен быть —
инструментом диагностики, а не гейтом.

### Уровень 3 — научить `visual_audit.py` понимать `incircle`‑цепочку

Отдельная задача, но правильная в долгую. В `_recognize_incircle()` уже
проставляются semantic‑теги на построениях; аудит должен видеть это и:

- не считать пересечение биссектрис в `O` за `LINE_CROSS`;
- разрешать подпись `A₁/B₁/C₁` прижатой к стороне (это по определению foot);
- давать окружности приоритет над рисками равенства при коллизии.

## Как отладить у себя за 3 шага

1. Запустить конкретную задачу с incircle и включить debug‑лог визуал‑аудита
   (или временно `logger.warning("[figures_gen] aux visual errors: %s", errors)`
   сразу после вызова `audit_rendered_figure`). Вы увидите точный список
   кодов ошибок — это и есть ответ, какие правила ложно срабатывают.

2. Сохранить `aux_svg` до дропа (`open("/tmp/aux_before_drop.svg","w")…`) и
   открыть глазами. Если чертёж выглядит корректно — баг в аудите, а не в
   движке (я готов ставить на это, судя по README).

3. Применить патч Уровня 1 с пустым `HARD_VISUAL_CODES` (то есть закомментить
   `if hard: _drop_aux(...)`). Проверить, что incircle показывается. Затем
   постепенно добавлять коды в `HARD_*`, которые действительно означают
   поломку.

## Чего мне не хватает, чтобы дать окончательный патч

К бандлу не приложены:

- `services/visual_audit.py` (главный подозреваемый — там формируется
  `errors[]`, который валит aux);
- `services/aux_compiler.py` (нужен, чтобы точно понимать, какие типы
  построений идут в `merged` для incircle — от этого зависит список
  безопасных semantic‑тегов);
- `services/aux_usefulness.py`, `services/figure_completeness_audit.py` —
  для полноты картины пайплайна.

Если пришлёте `visual_audit.py` (или хотя бы код `audit_rendered_figure` и
таблицу кодов ошибок), я:

- составлю точный `HARD_VISUAL_CODES` под вашу семантику;
- покажу, какие правила аудита прямо противоречат синтезированному
  incircle‑плану;
- дам патч, который лечит корень проблемы, а не симптом.
