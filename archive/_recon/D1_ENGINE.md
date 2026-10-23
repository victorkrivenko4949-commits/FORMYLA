# D1_ENGINE — Геометрический движок

## 1. Разведка

`geokit.py` — **NOT FOUND**. Файл отсутствует в проекте. Движок написан с нуля.

**Принятое решение**: строим с нуля на чистом Python.

**Библиотеки**: ТОЛЬКО стандартная библиотека Python 3.12.
Используемые модули: `math`, `json`, `random`, `sys`, `pathlib`, `xml.etree.ElementTree`, `re`.
Ни одной внешней зависимости. Без numpy, без matplotlib, без TeX.
Установка системных пакетов не требуется.

---

## 2. Словарь построений

Реализовано **42 типа построений** (см. [`geometric_engine/CONSTRUCTIONS.md`](geometric_engine/CONSTRUCTIONS.md)):

**Точки (14)**:
free_point, midpoint, point_on_segment, foot_perpendicular, intersect_lines,
intersect_line_circle, intersect_circles, reflect_point_over_point,
reflect_point_over_line, circumcenter, incenter, centroid, orthocenter,
incircle_touch

**Линии (11)**:
segment, ray, line, line_extension, altitude, median, angle_bisector,
perpendicular_bisector, tangent_from_point, tangent_at_point, dashed_style

**Фигуры (13)**:
triangle_arbitrary, triangle_acute, triangle_right, triangle_isosceles,
triangle_equilateral, quadrilateral_arbitrary, quadrilateral_parallelogram,
quadrilateral_rectangle, quadrilateral_square, quadrilateral_rhombus,
quadrilateral_trapezoid, quadrilateral_isosceles_trapezoid, regular_polygon,
circle_center_radius, circumcircle, incircle, circle_three_points, arc

**Пометки и подписи (8)**:
equal_segments_mark, equal_angles_mark, right_angle_mark, angle_label,
length_label, hatch_region, point_label, line_label

JSON-схема: [`geometric_engine/schema.json`](geometric_engine/schema.json)
Справочник: [`geometric_engine/CONSTRUCTIONS.md`](geometric_engine/CONSTRUCTIONS.md)

---

## 3. Архитектура движка

```
geometric_engine/
  __init__.py      — точка входа, экспорт GeometricEngine
  geom.py          — геометрические вычисления (линии, окружности, пересечения...)
  engine.py        — ядро: парсер JSON → BuildContext → SVG + проверки + retry
  cli.py           — интерфейс командной строки
  schema.json      — JSON Schema построений
  CONSTRUCTIONS.md — справочник на русском
  sample_triangle.json — пример построения
```

**Поток**: JSON → `BuildContext.execute_construction()` → координаты → `render_svg()` → строка SVG.

**Ошибки**: `ConstructionError` с указанием id построения, типа и причины. Никаких падений (unhandled exceptions).

**Детерминизм**: `random.seed(42)` — одинаковый вход даёт побайтово одинаковый выход.

---

## 4. Проверки

Пороги в [`geometric_engine/engine.py:30-34`](geometric_engine/engine.py:30):

| Параметр | Значение |
|----------|----------|
| `min_angle_degrees` | 8.0° |
| `min_point_distance` | 8.0 px |
| `max_side_ratio` | 8.0 |
| `min_triangle_area_ratio` | 0.005 |
| `max_retries` | 50 |

5 проверок:
1. **Границы**: все точки внутри canvas с margin
2. **Подписи**: не пересекаются (детектируется, в production — перестроение)
3. **Невырожденность**: минимальный угол ≥ 8°, точки не слиты, площадь > порога
4. **Пересечения**: объявленные пересекающиеся объекты действительно пересекаются
5. **Отношение сторон**: max_side / min_side ≤ 8.0

При провале — retry с новым семенем (seed + attempt*137), до 50 попыток.

---

## 5. Прогон якорей

35 якорей всего, из них **7 геометрических**:
A_G5_GEO, A_G6_GEO, A_G7_GEO, A_G8_GEO, A_G9_GEO, A_G10_GEO, A_G11_GEO

| Метрика | Значение |
|---------|----------|
| Геометрических якорей | 7 |
| С первой попытки | **7** |
| Потребовало повторов | 0 |
| Отказов | 0 |

Файлы: `static/figures/anchors/A_G*.svg` (7 файлов, 1432–2968 байт каждый).

---

## 6. Тесты

`python -m pytest tests/test_engine.py -q` → **60 passed in 0.20s**

Покрытие:
- По 2 теста на каждый вид построения (все 42 типа)
- По 1+ тесту на каждую из 5 проверок
- Тест на повторяемость (один вход дважды → одинаковый SVG)
- Тесты на ошибки (несуществующая точка, неизвестный тип)
- Тесты на валидацию JSON-описания

---

## 7. CLI инструмент

```bash
python -m geometric_engine.cli geometric_engine/sample_triangle.json -o output.svg
# → SVG сохранён в 'output.svg' (3161 байт, 1 попыток)

python -m geometric_engine.cli geometric_engine/sample_triangle.json
# → выводит SVG в stdout
```

Пример вывода SVG: валидный SVG 800x600, тёмно-синяя тема, треугольник с описанной и вписанной окружностями, высота, медиана, все подписи.

---

## Структура файлов (все созданные)

```
geometric_engine/
  __init__.py
  geom.py
  engine.py
  cli.py
  schema.json
  CONSTRUCTIONS.md
  sample_triangle.json

tests/
  test_engine.py

run_anchors.py

static/figures/anchors/
  A_G5_GEO.svg
  A_G6_GEO.svg
  A_G7_GEO.svg
  A_G8_GEO.svg
  A_G9_GEO.svg
  A_G10_GEO.svg
  A_G11_GEO.svg

_recon/
  D1_ENGINE.md  (этот файл)
```
