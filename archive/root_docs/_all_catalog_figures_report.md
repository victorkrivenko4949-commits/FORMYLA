# Все рисунки, используемые в КАТАЛОГЕ олимпиадной математики

## Сводка

| Система | Источник | Кол-во | Описание |
|---------|----------|--------|----------|
| **Геометрические чертежи** (методы) | [`static/img/vsosh9_geometry/`](static/img/vsosh9_geometry/) | **50 SVG** | Только метод F1 (7 семей, задачи 1.1–7.4) |
| **Problem images** (условия задач) | [`problem_images.py`](problem_images.py) `IMAGE_MAP` | **102 привязки** | (combo_id, problem_num) → путь к файлу |
| **Solution figures** (рисунки-решения) | [`data/solution_figures_index.json`](data/solution_figures_index.json) | **349 ключей, 441 файл** | 11 олимпиад |
| **Problem images files** (доп. файлы) | [`static/problem_images/`](static/problem_images/) | **24 PNG** | Дополнение к IMAGE_MAP |
| **Raw problem images** | [`static/images/problems/`](static/images/problems/) | **669 файлов (447 уникальных)** | Сырые изображения условий |
| **AI-generated drawings** | [`static/generated/`](static/generated/) | AI-сгенерированные | Для pipeline генерации задач |

---

## 1. Геометрические чертежи (метод F1)

**Механизм:** [`services/geometry_drawings.py`](services/geometry_drawings.py) сканирует [`static/img/vsosh9_geometry/`](static/img/vsosh9_geometry/) и вставляет SVG после каждого `<h4>Задача N.M</h4>`.

**Шаблон имени:** `F{code}_{family}.{task}_{nr}.svg`

**Всего файлов: 50** (все для метода F1)

| Семья | Файлы | Описание |
|-------|-------|----------|
| Семья 1 | `F1_1.1_1.svg`, `F1_1.2_1.svg`, `F1_1.3_1.svg`, `F1_1.3_2.svg`, `F1_1.4_1.svg`, `F1_1.4_2.svg` | 6 файлов |
| Семья 2 | `F1_2.1_1.svg`, `F1_2.2_1.svg`, `F1_2.2_2.svg`, `F1_2.3_1.svg`, `F1_2.3_2.svg`, `F1_2.4_1.svg`, `F1_2.4_2.svg` | 7 файлов |
| Семья 3 | `F1_3.1_1.svg`, `F1_3.1_2.svg`, `F1_3.2_1.svg`, `F1_3.3_1.svg`, `F1_3.3_2.svg`, `F1_3.4_1.svg`, `F1_3.4_2.svg` | 7 файлов |
| Семья 4 | `F1_4.1_1.svg`, `F1_4.2_1.svg`, `F1_4.3_1.svg`, `F1_4.3_2.svg`, `F1_4.4_1.svg`, `F1_4.4_2.svg` | 6 файлов |
| Семья 5 | `F1_5.1_1.svg`, `F1_5.1_2.svg`, `F1_5.2_1.svg`, `F1_5.2_2.svg`, `F1_5.3_1.svg`, `F1_5.3_2.svg`, `F1_5.4_1.svg`, `F1_5.4_2.svg` | 8 файлов |
| Семья 6 | `F1_6.1_1.svg`, `F1_6.1_2.svg`, `F1_6.2_1.svg`, `F1_6.2_2.svg`, `F1_6.3_1.svg`, `F1_6.3_2.svg`, `F1_6.4_1.svg`, `F1_6.4_2.svg` | 8 файлов |
| Семья 7 | `F1_7.1_1.svg`, `F1_7.1_2.svg`, `F1_7.2_1.svg`, `F1_7.2_2.svg`, `F1_7.3_1.svg`, `F1_7.3_2.svg`, `F1_7.4_1.svg`, `F1_7.4_2.svg` | 8 файлов |

**Важно:** Методы F2–F14 (и A, B, C, D, E, G, H, I, J) **не имеют** SVG-чертежей.

---

## 2. Problem Images (`IMAGE_MAP`)

**Файл:** [`problem_images.py`](problem_images.py)  
**Всего записей:** 102  
**Структура:** `(combo_id, problem_num) → "path/to/image.png"`

### Все записи IMAGE_MAP

| combo_id | # задачи | Путь |
|----------|----------|------|
| 16 | 1 | `img/olympiads/euler/2016/kl8/regional/zad1_usl_1.png` |
| 35 | 1 | `img/olympiads/euler/2024/kl8/regional/zad1_usl_1.png` |
| 45 | 4 | `problem_images/formula_unity_2020_8_4.png` |
| 57 | 1 | `problem_images/formula_unity_2022_7_1.png` |
| 83 | 1 | `img/olympiads/formula_unity/2024/kl8/final/zad1_usl_1.png` |
| 83 | 2 | `img/olympiads/formula_unity/2024/kl8/final/zad2_usl_1.png` |
| 83 | 3 | `img/olympiads/formula_unity/2024/kl8/final/zad3_usl_1.png` |
| 83 | 4 | `img/olympiads/formula_unity/2024/kl8/final/zad4_usl_1.png` |
| 83 | 5 | `img/olympiads/formula_unity/2024/kl8/final/zad5_usl_1.png` |
| 91 | 1 | `img/olympiads/formula_unity/2024/kl11/final/zad1_usl_1.png` |
| 91 | 2 | `img/olympiads/formula_unity/2024/kl11/final/zad2_usl_1.png` |
| 91 | 3 | `img/olympiads/formula_unity/2024/kl11/final/zad3_usl_1.png` |
| 91 | 4 | `img/olympiads/formula_unity/2024/kl11/final/zad4_usl_1.png` |
| 91 | 5 | `img/olympiads/formula_unity/2024/kl11/final/zad5_usl_1.png` |
| 100 | 3 | `img/olympiads/kurchatov/2016/kl10/qualifying/zad3_usl_1.png` |
| **125** | **4** | **`problem_images/kurchatov_2023_7_4.png`** |
| 187 | 1 | `img/olympiads/lomonosov/2019/kl7/qualifying/zad1_usl_1.png` |
| 187 | 3 | `img/olympiads/lomonosov/2019/kl7/qualifying/zad3_usl_1.png` |
| 187 | 5 | `img/olympiads/lomonosov/2019/kl7/qualifying/zad5_usl_1.png` |
| 189 | 5 | `problem_images/lomonosov_2019_9_5.png` |
| 192 | 2 | `problem_images/lomonosov_2020_7_2.png` |
| 193 | 2 | `problem_images/lomonosov_2020_8_2.png` |
| 194 | 1 | `problem_images/lomonosov_2020_9_1.png` |
| 202 | 2 | `problem_images/lomonosov_2022_5_2.png` |
| 203 | 2 | `problem_images/lomonosov_2022_6_2.png` |
| 206 | 1 | `img/olympiads/lomonosov/2022/kl9/qualifying/zad1_usl_1.png` |
| 213 | 1 | `img/olympiads/lomonosov/2023/kl9/qualifying/zad1_usl_1.png` |
| 216 | 1 | `problem_images/lomonosov_2024_5_1.png` |
| 216 | 4 | `problem_images/lomonosov_2024_5_4.png` |
| 217 | 1 | `problem_images/lomonosov_2024_6_1.png` |
| 217 | 4 | `problem_images/lomonosov_2024_6_4.png` |
| 218 | 5 | `problem_images/lomonosov_2024_7_5.png` |
| 219 | 5 | `problem_images/lomonosov_2024_8_5.png` |
| 230 | 1 | `img/olympiads/phystech/2014/kl11/final/zad1_usl_1.png` |
| 278 | 5 | `problem_images/pvg_2017_5_5.png` |
| 279 | 5 | `problem_images/pvg_2017_6_5.png` |
| 282 | 4 | `problem_images/pvg_2017_9_4.png` |
| 291 | 1 | `img/olympiads/pvg/2018/kl11/qualifying/zad1_usl_1.png` |
| 291 | 2 | `img/olympiads/pvg/2018/kl11/qualifying/zad2_usl_1.png` |
| 291 | 4 | `img/olympiads/pvg/2018/kl11/qualifying/zad4_usl_1.png` |
| 311 | 3 | `img/olympiads/pvg/2022/kl5/qualifying/zad3_usl_1.png` |
| 317 | 1 | `img/olympiads/pvg/2022/kl11/qualifying/zad1_usl_1.png` |
| 317 | 2 | `img/olympiads/pvg/2022/kl11/qualifying/zad2_usl_1.png` |
| 320 | 3 | `img/olympiads/pvg/2023/kl7/qualifying/zad3_usl_1.png` |
| 330 | 2 | `img/olympiads/pvg/2024/kl10/qualifying/zad2_usl_1.png` |
| 341 | 3 | `problem_images/spbgu_2023_6_3.png` |
| 343 | 3 | `problem_images/spbgu_2023_7_3.png` |
| 345 | 2 | `img/olympiads/spbgu/2023/kl8/final/zad2_usl_1.png` |
| 396 | 2 | `problem_images/turgor_2017_9_2.png` |
| 496 | 1 | `img/olympiads/vsosh/2018/kl10/regional/zad1_usl_1.png` |
| 496 | 2 | `img/olympiads/vsosh/2018/kl10/regional/zad2_usl_1.png` |
| 496 | 3 | `img/olympiads/vsosh/2018/kl10/regional/zad3_usl_1.png` |
| 496 | 5 | `img/olympiads/vsosh/2018/kl10/regional/zad5_usl_1.png` |
| 510 | 1 | `img/olympiads/vsosh/2019/kl11/final/zad1_usl_1.png` |
| 510 | 3 | `img/olympiads/vsosh/2019/kl11/final/zad3_usl_1.png` |
| 510 | 4 | `img/olympiads/vsosh/2019/kl11/final/zad4_usl_1.png` |
| 515 | 1 | `img/olympiads/vsosh/2020/kl10/municipal/zad1_usl_1.png` |
| 561 | 3 | `img/olympiads/vsosh/2025/kl11/final/zad3_usl_1.png` |
| 561 | 4 | `img/olympiads/vsosh/2025/kl11/final/zad4_usl_1.png` |
| 561 | 6 | `img/olympiads/vsosh/2025/kl11/final/zad6_usl_1.png` |
| 562 | 2 | `img/olympiads/vsosh/2025/kl11/regional/zad2_usl_1.png` |
| 562 | 3 | `img/olympiads/vsosh/2025/kl11/regional/zad3_usl_1.png` |
| 569 | 1 | `img/olympiads/vysshaya_proba/2013/kl8/final/zad1_usl_1.png` |
| 570 | 1 | `img/olympiads/vysshaya_proba/2013/kl9/final/zad1_usl_1.png` |
| 570 | 2 | `img/olympiads/vysshaya_proba/2013/kl9/final/zad2_usl_1.png` |
| 570 | 3 | `img/olympiads/vysshaya_proba/2013/kl9/final/zad3_usl_1.png` |
| 581 | 1 | `img/olympiads/vysshaya_proba/2015/kl9/final/zad1_usl_1.png` |
| 584 | 2 | `img/olympiads/vysshaya_proba/2016/kl8/final/zad2_usl_1.png` |
| 584 | 3 | `img/olympiads/vysshaya_proba/2016/kl8/final/zad3_usl_1.png` |
| 587 | 1 | `img/olympiads/vysshaya_proba/2017/kl7/final/zad1_usl_1.png` |
| 587 | 2 | `img/olympiads/vysshaya_proba/2017/kl7/final/zad2_usl_1.png` |
| 587 | 3 | `img/olympiads/vysshaya_proba/2017/kl7/final/zad3_usl_1.png` |
| 587 | 4 | `img/olympiads/vysshaya_proba/2017/kl7/final/zad4_usl_1.png` |
| 587 | 5 | `img/olympiads/vysshaya_proba/2017/kl7/final/zad5_usl_1.png` |
| 595 | 4 | `problem_images/vysshaya_proba_2018_10_4.png` |
| 601 | 1 | `img/olympiads/vysshaya_proba/2019/kl11/final/zad1_usl_1.png` |
| 603 | 1 | `img/olympiads/vysshaya_proba/2020/kl8/final/zad1_usl_1.png` |
| 603 | 2 | `img/olympiads/vysshaya_proba/2020/kl8/final/zad2_usl_1.png` |
| 603 | 4 | `img/olympiads/vysshaya_proba/2020/kl8/final/zad4_usl_1.png` |
| 603 | 5 | `img/olympiads/vysshaya_proba/2020/kl8/final/zad5_usl_1.png` |
| 604 | 1 | `img/olympiads/vysshaya_proba/2020/kl9/final/zad1_usl_1.png` |
| 604 | 4 | `img/olympiads/vysshaya_proba/2020/kl9/final/zad4_usl_1.png` |
| 612 | 1 | `img/olympiads/vysshaya_proba/2022/kl7/final/zad1_usl_1.png` |
| 612 | 3 | `img/olympiads/vysshaya_proba/2022/kl7/final/zad3_usl_1.png` |
| 685 | 2 | `img/olympiads/phystech/2020/kl9/final/zad2_usl_1.png` |
| 685 | 3 | `img/olympiads/phystech/2020/kl9/final/zad3_usl_1.png` |
| 690 | 2 | `img/olympiads/phystech/2020/kl11/final/zad2_usl_1.png` |
| 690 | 3 | `img/olympiads/phystech/2020/kl11/final/zad3_usl_1.png` |
| 690 | 4 | `img/olympiads/phystech/2020/kl11/final/zad4_usl_1.png` |
| 690 | 5 | `img/olympiads/phystech/2020/kl11/final/zad5_usl_1.png` |
| 692 | 2 | `img/olympiads/phystech/2022/kl10/final/zad2_usl_1.png` |
| 693 | 2 | `img/olympiads/phystech/2022/kl11/final/zad2_usl_1.png` |
| 693 | 3 | `img/olympiads/phystech/2022/kl11/final/zad3_usl_1.png` |
| 693 | 4 | `img/olympiads/phystech/2022/kl11/final/zad4_usl_1.png` |
| 693 | 5 | `img/olympiads/phystech/2022/kl11/final/zad5_usl_1.png` |
| 729 | 1 | `img/olympiads/formula_unity/2020/kl5/final/zad1_usl_1.png` |
| 729 | 2 | `img/olympiads/formula_unity/2020/kl5/final/zad2_usl_1.png` |
| 729 | 3 | `img/olympiads/formula_unity/2020/kl5/final/zad3_usl_1.png` |
| 729 | 4 | `img/olympiads/formula_unity/2020/kl5/final/zad4_usl_1.png` |
| 731 | 4 | `problem_images/formula_unity_2020_7_4.png` |
| 775 | 1 | `img/olympiads/turgor/2025/kl8/fall_basic/zad1_usl_1.png` |
| 100310 | 4 | `problem_images/formula_unity_2022_6_4.png` |

### Распределение по олимпиадам

| Олимпиада | Кол-во |
|-----------|--------|
| formula_unity | 17 |
| vysshaya_proba | 20 |
| lomonosov | 15 |
| vsosh | 11 |
| phystech | 11 |
| pvg | 9 |
| **kurchatov** | **2** |
| euler | 2 |
| spbgu | 3 |
| turgor | 2 |

---

## 3. Solution Figures (рисунки-решения)

**Файл:** [`data/solution_figures_index.json`](data/solution_figures_index.json)  
**Всего ключей:** 349 (каждый ключ = одна задача)  
**Всего уникальных файлов:** 441  
**Обслуживается:** [`services/solution_figures.py`](services/solution_figures.py)  
**Файлы хранятся в:** `static/solution_figures/`

### По олимпиадам

| Олимпиада | Ключей (задач) | Файлов |
|-----------|----------------|--------|
| **mos** (МОШ) | 216 | - |
| **vsosh** (ВСОШ) | 53 | - |
| **formula_unity** (Формула Единства) | 31 | - |
| **spbgu** (СПбГУ) | 25 | - |
| **turgor** (Тургор) | 23 | - |
| **vysshaya_proba** (Высшая Проба) | 18 | - |
| **kurchatov** (Курчатов) | 17 | - |
| **phystech** (Физтех) | 25 | - |
| **pvg** (ПВГ) | 13 | - |
| **lomonosov** (Ломоносов) | 12 | - |
| **euler** (Эйлер) | 8 | - |

### Все записи Курчатов (17 задач)

| Ключ | Файл |
|------|------|
| `kurchatov\|2016\|10\|qualifying\|3` | `solution_figures/kurchatov_2016_g10_n3_idx374_2bc21a.png` |
| `kurchatov\|2016\|9\|qualifying\|3` | `solution_figures/kurchatov_2016_g9_n3_idx372_165188.png` |
| `kurchatov\|2017\|11\|qualifying\|3` | `solution_figures/kurchatov_2017_g11_n3_idx385_95bd1a.png` |
| `kurchatov\|2017\|9\|qualifying\|3` | `solution_figures/kurchatov_2017_g9_n3_idx382_9350ca.png` |
| `kurchatov\|2018\|11\|qualifying\|5` | `solution_figures/kurchatov_2018_g11_n5_idx399_52f301.png` |
| `kurchatov\|2019\|9\|qualifying\|3` | `solution_figures/kurchatov_2019_g9_n3_idx407_fec03c.png` |
| `kurchatov\|2020\|11\|qualifying\|4` | `solution_figures/kurchatov_2020_g11_n4_idx418_0e7287.png` |
| `kurchatov\|2020\|9\|qualifying\|3` | `solution_figures/kurchatov_2020_g9_n3_idx414_92bf80.png` |
| `kurchatov\|2021\|9\|qualifying\|4` | `solution_figures/kurchatov_2021_g9_n4_idx420_7f3260.png` |
| `kurchatov\|2022\|10\|qualifying\|6` | `solution_figures/kurchatov_2022_g10_n6_idx434_896972.png` |
| `kurchatov\|2022\|9\|qualifying\|2` | `solution_figures/kurchatov_2022_g9_n2_idx432_b4c73e.png` |
| `kurchatov\|2023\|10\|qualifying\|3` | `solution_figures/kurchatov_2023_g10_n3_idx439_92de44.png` |
| `kurchatov\|2023\|11\|qualifying\|4` | `solution_figures/kurchatov_2023_g11_n4_idx440_7ade2a.png` |
| `kurchatov\|2024\|10\|qualifying\|4` | `solution_figures/kurchatov_2024_g10_n4_idx450_36b858.png` |
| `kurchatov\|2024\|11\|qualifying\|5` | `solution_figures/kurchatov_2024_g11_n5_idx452_e6dc27.png` |
| `kurchatov\|2024\|9\|qualifying\|5` | `solution_figures/kurchatov_2024_g9_n5_idx449_f4913b.png` |
| `kurchatov\|2025\|9\|qualifying\|2` | `solution_figures/kurchatov_2025_g9_n2_idx457_41eb61.png` |

### Все уникальные файлы (441 шт.)

Полный список см. в выводе `_analyze_figures.py`, раздел 1.

---

## 4. Problem Images Files (директория `static/problem_images/`)

**Всего файлов: 24**

| Файл | Размер |
|------|--------|
| `formula_unity_2020_7_4.png` | - |
| `formula_unity_2020_8_4.png` | - |
| `formula_unity_2022_6_4.png` | - |
| `formula_unity_2022_7_1.png` | - |
| **`kurchatov_2023_7_4.png`** | - |
| `lomonosov_2019_9_5.png` | - |
| `lomonosov_2020_7_2.png` | - |
| `lomonosov_2020_8_2.png` | - |
| `lomonosov_2020_9_1.png` | - |
| `lomonosov_2022_5_2.png` | - |
| `lomonosov_2022_6_2.png` | - |
| `lomonosov_2024_5_1.png` | - |
| `lomonosov_2024_5_4.png` | - |
| `lomonosov_2024_6_1.png` | - |
| `lomonosov_2024_6_4.png` | - |
| `lomonosov_2024_7_5.png` | - |
| `lomonosov_2024_8_5.png` | - |
| `pvg_2017_5_5.png` | - |
| `pvg_2017_6_5.png` | - |
| `pvg_2017_9_4.png` | - |
| `spbgu_2023_6_3.png` | - |
| `spbgu_2023_7_3.png` | - |
| `turgor_2017_9_2.png` | - |
| `vysshaya_proba_2018_10_4.png` | - |

---

## 5. Raw Problem Images (`static/images/problems/`)

**Всего файлов:** 669 (447 уникальных базовых имён, остальные — копии с " - копия")

### По олимпиадам

| Олимпиада | Уникальных изображений |
|-----------|----------------------|
| fu (formula_unity) | 122 |
| lomonosov | 106 |
| pvg | 72 |
| vysshaya (vysshaya_proba) | 48 |
| vsosh | 41 |
| **kurchatov** | **20** |
| turgor | 18 |
| phystech | 16 |
| euler | 2 |

### Kurchatov-файлы в `static/images/problems/`

| Уникальное имя | Копии |
|----------------|-------|
| `kurchatov_2015_g7_vfig1.png` | +2 копии |
| `kurchatov_2015_g9_vfig1.png` | +2 копии |
| `kurchatov_2016_g6_fig1.png` | +2 копии |
| `kurchatov_2022_g7_fig1.png` | +2 копии |
| `kurchatov_2024_g6_fig1.png` | +2 копии |
| `kurchatov_2024_g7_fig1.png` | +2 копии |
| `kurchatov_2024_g7_fig2.png` | +2 копии |
| `kurchatov_2025_g11_vfig1.png` | +2 копии |
| `kurchatov_2025_g6_fig1.png` | +2 копии |
| `kurchatov_2025_g7_fig1.png` | +2 копии |

**Всего уникальных Kurchatov-изображений:** 10, с копиями — 30 файлов.

---

## 6. Фокус: Курчатов 7 класс, 2023 год, отбор (этап 4), задача 4

Вы запросили конкретно: **Курчатов 7 класс 2023 год отбор этап 4 задача**

### Что найдено

| Система | Статус | Детали |
|---------|--------|--------|
| **IMAGE_MAP** (`problem_images.py`) | ✅ **ЕСТЬ** | `(125, 4): "problem_images/kurchatov_2023_7_4.png"` — combo_id=125, задача №4 |
| **Файл** (`static/problem_images/`) | ✅ **ЕСТЬ** | `static/problem_images/kurchatov_2023_7_4.png` |
| **Solution figures** (`solution_figures_index.json`) | ❌ **НЕТ** | Нет записи `kurchatov\|2023\|7\|*` — есть только 10й и 11й классы |
| **Raw images** (`static/images/problems/`) | ❌ **НЕТ** | Нет `kurchatov_2023_g7_*` — ближайшие: 2022 г7 и 2024 г7 |

### Итог

Единственный рисунок для задачи **Курчатов 7 класс, 2023, отбор, этап 4, задача 4** — это файл:
- [`static/problem_images/kurchatov_2023_7_4.png`](static/problem_images/kurchatov_2023_7_4.png)
- Привязан в [`problem_images.py`](problem_images.py):28 через `(125, 4)` → `"problem_images/kurchatov_2023_7_4.png"`

---

## 7. AI-generated drawings (`static/generated/`)

Директория [`static/generated/`](static/generated/) содержит AI-сгенерированные чертежи в формате `drawing_*.png`, создаваемые пайплайном генерации задач (шаг Opus). Эти файлы динамические и используются в задачах «Дня».

---

## 8. Сводка по методам (из `_methods_images_report.md`)

Дублирую ключевой вывод из предыдущего отчёта:

- **Из 105 методов каталога только метод F1 имеет SVG-чертежи** (50 файлов)
- **Все остальные 104 метода не содержат никаких рисунков**
- В [`data/olympiads/methods_catalog_105.json`](data/olympiads/methods_catalog_105.json) нет markdown-изображений, HTML-тегов `<img>` или ссылок на `.svg`/`.png`/`.jpg`
- Методы A, B, C, D, E, G, H, I, J... не имеют механизма подгрузки изображений

---

## Приложение: Script анализа

Скрипт [`_analyze_figures.py`](_analyze_figures.py) производит полный анализ всех изображений. Запуск:

```bash
python _analyze_figures.py
```
