# CH27 отчёт — проверка трёх новых операций

Проверка, что `reflect_point`, `rotate_point` и `mark_intersection(id)`
закрывают задачи, ранее попадавшие в `unsupported`.

## Таблица по 5 задачам

| task_uid | ops | aux_status | creates_ok | issues | численная проверка |
|---|---|---|---|---|---|
| GEN-fill_0453 | 1 | AUX_BUILT | OK | — | A1=2M−A; mid(A,A1)=M (dev 0.00e+00) **OK** |
| GEN-L123-w2_46_s5 | 3 | AUX_BUILT | OK | — | ABCD параллелограмм: AB∥CD, AD∥BC (cross 0.00e+00) **OK** |
| GEN-fill_0452 | 1 | AUX_BUILT | FAIL | UNRESOLVED_POINT:B | rotate(A,B,∠ABC)≈C (dev 6.36e-14) **OK** |
| GEN-fill_0454 | 1 | AUX_BUILT | OK | — | rotate(D,A,∠DAB)≈B (dev 2.84e-14) **OK** |
| GEN-L123-w2_21_s3 | 3 | AUX_BUILT | OK | — | K на AC (dist 0.00e+00, on_seg=True) **OK** |

## Численные проверки (все прошли)

1. **GEN-fill_0453** — `reflect_point A→A1 через M`: середина AA₁ совпадает
   с M с точностью `0.00e+00` (удвоение медианы корректно).

2. **GEN-L123-w2_46_s5** — `reflect_point B→D через M` + отрезки A-D, C-D:
   ABCD — параллелограмм (векторные произведения AB×CD и AD×BC равны
   `0.00e+00`).

3. **GEN-fill_0452** — `rotate_point maps:["A","C"]`: поворот A вокруг B на
   угол ∠ABC даёт точку, совпадающую с C с отклонением `6.36e-14`.

4. **GEN-fill_0454** — `rotate_point maps:["D","B"]` (квадрат): поворот D
   вокруг A на угол ∠DAB даёт B с отклонением `2.84e-14`.

5. **GEN-L123-w2_21_s3** — `draw_parallel id="par_N"` + `mark_intersection
   obj1="par_N"`: точка K лежит на отрезке AC (расстояние `0.00e+00`,
   `segment_contains_point=True`).

## Что построилось полностью

- **4/5 задач** дали `AUX_BUILT` со всеми `creates_point` разрешёнными
  (без issues): fill_0453, w2_46_s5, fill_0454, w2_21_s3.
- **fill_0452** (`rotate_point maps`) численно корректен (dev 6e-14), но
  полный pipeline дал `UNRESOLVED_POINT:B`, потому что **base-планировщик
  LLM не создал точку B** в base-чертеже (пробел base-планировщика, а не
  дефект rotate_point). Детерминированный base с точкой B подтверждает:
  поворот работает.

## Артефакты

- [`scripts/ch27_probe.py`](scripts/ch27_probe.py) — прогон.
- [`output/ch27/probe_results.json`](output/ch27/probe_results.json) — метрики.
- [`output/ch27/gallery.html`](output/ch27/gallery.html) — тёмная галерея
  (фон #0F1729), base/aux парами, с note и численной проверкой.
- [`output/ch27/svg/`](output/ch27/svg) — SVG-файлы.

## Вывод

Все три операции работают корректно и детерминированно. Единственная
незакрытая задача (fill_0452) упирается в base-планировщик, который не
создаёт внутреннюю точку P/B в условии — это не связано с новыми
операциями и лечится отдельно на уровне base-промпта.
