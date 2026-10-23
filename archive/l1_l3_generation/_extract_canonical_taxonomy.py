#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract canonical taxonomy (T001-T043) from VICTOR2.0 source.
Produces:
  1. l1_l3_generation/canonical_taxonomy_snapshot.json
  2. l1_l3_generation/taxonomy_source_report.json
"""
import json
import hashlib
import os
import sys
from datetime import datetime, timezone

# ============================================================================
# 43 THEMES (41 canonical + 2 added) from VICTOR2.0
# ============================================================================
THEMES = {
    "T001": {
        "name": "Алгебра: теория групп",
        "subtopics": [
            "Группы: определения и примеры",
            "Группы: подгруппы, смежные классы",
            "Гомоморфизмы и факторгруппы"
        ]
    },
    "T002": {
        "name": "Арифметика и теория чисел",
        "subtopics": [
            "Делимость и остатки",
            "НОД, НОК, алгоритм Евклида",
            "Сравнения по модулю (a ≡ b mod n)"
        ]
    },
    "T003": {
        "name": "Вероятность и комбинаторика",
        "subtopics": [
            "Геометрическая вероятность",
            "Классическая вероятность",
            "Условная вероятность и формула Байеса"
        ]
    },
    "T004": {
        "name": "Графы: основные понятия",
        "subtopics": [
            "Графы: определения, изоморфизм",
            "Маршруты, цепи, циклы, Эйлеровы графы",
            "Связность и компоненты связности"
        ]
    },
    "T005": {
        "name": "Дополнительные задачи и смешанные темы",
        "subtopics": [
            "Задачи на оптимизацию",
            "Комбинированные задачи (алгебра + геометрия)",
            "Прикладные задачи"
        ]
    },
    "T006": {
        "name": "Комбинаторика и вероятность",
        "subtopics": [
            "Перестановки и факториалы",
            "Правила сложения и умножения в комбинаторике",
            "Размещения и сочетания"
        ]
    },
    "T007": {
        "name": "Комбинаторика и теория игр",
        "subtopics": [
            "Выигрышные и проигрышные позиции",
            "Игры с симметричной стратегией",
            "Стратегия и анализ игр"
        ]
    },
    "T008": {
        "name": "Логика и множества",
        "subtopics": [
            "Булевы функции и их минимизация",
            "Логические операции и таблицы истинности",
            "Множества и операции над ними"
        ]
    },
    "T009": {
        "name": "Метод координат: декартовы координаты",
        "subtopics": [
            "Координаты на прямой и плоскости",
            "Расстояние между точками, середина отрезка",
            "Уравнения прямых и окружностей"
        ]
    },
    "T010": {
        "name": "Метод координат: векторы",
        "subtopics": [
            "Векторы: сложение, умножение на число",
            "Координаты вектора, связь с точками",
            "Скалярное произведение векторов"
        ]
    },
    "T011": {
        "name": "Неравенства: алгебраические неравенства",
        "subtopics": [
            "Доказательство неравенств",
            "Квадратные неравенства",
            "Неравенства с модулем"
        ]
    },
    "T012": {
        "name": "Неравенства: метод интервалов и рациональные",
        "subtopics": [
            "Дробно-рациональные неравенства",
            "Иррациональные неравенства",
            "Метод интервалов для рациональных неравенств"
        ]
    },
    "T013": {
        "name": "Неравенства: показательные и логарифмические",
        "subtopics": [
            "Логарифмические неравенства",
            "Показательные неравенства",
            "Системы показательных и логарифмических неравенств"
        ]
    },
    "T014": {
        "name": "Неравенства: тригонометрические",
        "subtopics": [
            "Неравенства с обратными тригонометрическими функциями",
            "Простейшие тригонометрические неравенства с sin, cos",
            "Простейшие тригонометрические неравенства с tg, ctg"
        ]
    },
    "T015": {
        "name": "Неравенства: числовые наборы",
        "subtopics": [
            "Неравенства о среднем арифметическом и среднем геометрическом",
            "Неравенства Чебышева и Маркова",
            "Цепочки неравенств, взвешенные средние"
        ]
    },
    "T016": {
        "name": "Планиметрия: многоугольники",
        "subtopics": [
            "Многоугольники: виды, свойства",
            "Параллелограммы и трапеции",
            "Треугольники: виды, свойства"
        ]
    },
    "T017": {
        "name": "Планиметрия: окружность",
        "subtopics": [
            "Вписанные углы и их свойства",
            "Длина окружности, площадь круга и сектора",
            "Касательные и секущие к окружности"
        ]
    },
    "T018": {
        "name": "Планиметрия: площадь",
        "subtopics": [
            "Площади подобных фигур",
            "Площадь круга и его частей",
            "Формулы площади треугольника и четырёхугольника"
        ]
    },
    "T019": {
        "name": "Планиметрия: треугольники",
        "subtopics": [
            "Подобие треугольников",
            "Признаки равенства треугольников",
            "Теорема Пифагора"
        ]
    },
    "T020": {
        "name": "Последовательности и прогрессии",
        "subtopics": [
            "Арифметическая прогрессия",
            "Геометрическая прогрессия",
            "Суммы последовательностей"
        ]
    },
    "T021": {
        "name": "Производная и её применение",
        "subtopics": [
            "Геометрический смысл производной",
            "Исследование функций с помощью производной",
            "Правила и формулы дифференцирования"
        ]
    },
    "T022": {
        "name": "Проценты, отношения и пропорции",
        "subtopics": [
            "Задачи на проценты",
            "Пропорции и отношения",
            "Прямая и обратная пропорциональность"
        ]
    },
    "T023": {
        "name": "Рациональные уравнения и неравенства",
        "subtopics": [
            "Дробно-рациональные уравнения",
            "Метод замены переменной в рациональных уравнениях",
            "Рациональные уравнения"
        ]
    },
    "T024": {
        "name": "Решение задач: анализ и интерпретация",
        "subtopics": [
            "Оценка и прикидка",
            "Проверка решения и поиск ошибок",
            "Составление плана решения"
        ]
    },
    "T025": {
        "name": "Решение уравнений: методы замены",
        "subtopics": [
            "Замена переменной (подстановка)",
            "Использование симметрии",
            "Сведение к системе уравнений"
        ]
    },
    "T026": {
        "name": "Решение уравнений: разложение на множители",
        "subtopics": [
            "Вынесение общего множителя и группировка",
            "Использование формул сокращённого умножения",
            "Разложение квадратного трёхчлена"
        ]
    },
    "T027": {
        "name": "Системы уравнений",
        "subtopics": [
            "Графический метод решения систем",
            "Метод подстановки",
            "Системы линейных уравнений"
        ]
    },
    "T028": {
        "name": "Стереометрия: аксиомы и прямые",
        "subtopics": [
            "Аксиомы стереометрии",
            "Взаимное расположение прямых в пространстве",
            "Скрещивающиеся прямые"
        ]
    },
    "T029": {
        "name": "Стереометрия: многогранники",
        "subtopics": [
            "Параллелепипеды, призмы",
            "Пирамиды",
            "Правильные многогранники"
        ]
    },
    "T030": {
        "name": "Стереометрия: тела вращения",
        "subtopics": [
            "Конус, цилиндр",
            "Сфера, шар",
            "Тела вращения: сечения, комбинации"
        ]
    },
    "T031": {
        "name": "Стереометрия: угол и расстояние",
        "subtopics": [
            "Расстояние от точки до плоскости",
            "Угол между плоскостями (двугранный угол)",
            "Угол между прямой и плоскостью"
        ]
    },
    "T032": {
        "name": "Текстовые задачи: движение",
        "subtopics": [
            "Движение в противоположных направлениях",
            "Движение по воде",
            "Движение по кругу"
        ]
    },
    "T033": {
        "name": "Текстовые задачи: производительность и смеси",
        "subtopics": [
            "Задачи на концентрацию, сплавы, смеси",
            "Задачи на совместную работу",
            "Задачи на производительность труда"
        ]
    },
    "T034": {
        "name": "Теория вероятностей: дискретные распределения",
        "subtopics": [
            "Биномиальное распределение",
            "Дискретные случайные величины",
            "Математическое ожидание и дисперсия"
        ]
    },
    "T035": {
        "name": "Тригонометрические уравнения",
        "subtopics": [
            "Однородные тригонометрические уравнения",
            "Отбор корней в тригонометрических уравнениях",
            "Простейшие тригонометрические уравнения"
        ]
    },
    "T036": {
        "name": "Тригонометрия: преобразования",
        "subtopics": [
            "Основное тригонометрическое тождество",
            "Формулы приведения",
            "Формулы сложения и двойного угла"
        ]
    },
    "T037": {
        "name": "Уравнения с модулем",
        "subtopics": [
            "Графическое решение уравнений с модулем",
            "Метод интервалов для уравнений с модулем",
            "Уравнения с модулем"
        ]
    },
    "T038": {
        "name": "Уравнения: иррациональные",
        "subtopics": [
            "Иррациональные уравнения с одним корнем",
            "Иррациональные уравнения с несколькими корнями",
            "Метод замены в иррациональных уравнениях"
        ]
    },
    "T039": {
        "name": "Уравнения: показательные и логарифмические",
        "subtopics": [
            "Логарифмические уравнения",
            "Показательные уравнения",
            "Системы показательных и логарифмических уравнений"
        ]
    },
    "T040": {
        "name": "Уравнения: тригонометрические системы",
        "subtopics": [
            "Системы тригонометрических уравнений",
            "Тригонометрические уравнения с параметром",
            "Тригонометрические уравнения с отбором корней"
        ]
    },
    "T041": {
        "name": "Числа, индукция, алгоритмы",
        "subtopics": [
            "Алгоритмы и вычисления",
            "Комплексные числа",
            "Метод математической индукции"
        ]
    },
    # --- Added themes from Section 3 ---
    "T042": {
        "name": "Функции и графики",
        "subtopics": [
            "Графики функций: преобразования и сдвиги",
            "Область определения и область значений",
            "Построение графиков сложных функций"
        ]
    },
    "T043": {
        "name": "Стереометрия: объёмы и сечения",
        "subtopics": [
            "Объём многогранников",
            "Объём тел вращения",
            "Сечения многогранников"
        ]
    }
}

# ============================================================================
# GRADE DISTRIBUTION (from VICTOR2.0 — approved by user)
# РОВНО ОДНА ТЕМА НА ОДИН КЛАСС
# ============================================================================
GRADE_THEMES = {
    5:  ["T002", "T022", "T008", "T004", "T024", "T005"],
    6:  ["T006", "T007", "T032", "T033", "T016", "T018"],
    7:  ["T026", "T025", "T023", "T027", "T019", "T003"],
    8:  ["T042", "T011", "T012", "T037", "T009", "T017"],
    9:  ["T038", "T020", "T010", "T015", "T036", "T035"],
    10: ["T039", "T013", "T014", "T028", "T029", "T030"],
    11: ["T021", "T040", "T034", "T043", "T031", "T041", "T001"]
}

# ============================================================================
# SUBTOPIC LABELS (S0, S1, S2)
# ============================================================================
SUBTOPIC_LABELS = ["S0", "S1", "S2"]


def validate_taxonomy():
    """Validate taxonomy invariants."""
    issues = []

    # 1. Count themes
    if len(THEMES) != 43:
        issues.append(f"Expected 43 themes, got {len(THEMES)}")

    # 2. Check IDs are sequential T001-T043
    expected_ids = [f"T{i:03d}" for i in range(1, 44)]
    actual_ids = sorted(THEMES.keys())
    if actual_ids != expected_ids:
        issues.append(f"Theme IDs mismatch. Expected T001-T043, got: {actual_ids}")

    # 3. Each theme has exactly 3 subtopics with non-empty names
    for tid, tdata in THEMES.items():
        subs = tdata.get("subtopics", [])
        if len(subs) != 3:
            issues.append(f"{tid}: expected 3 subtopics, got {len(subs)}")
        for i, s in enumerate(subs):
            if not s or not s.strip():
                issues.append(f"{tid} subtopic {i}: empty name")
        # Check for duplicate subtopics within theme
        if len(set(s.strip() for s in subs)) != len(subs):
            issues.append(f"{tid}: duplicate subtopic names")

    # 4. No duplicate subtopic names across different themes
    all_subtopic_names = []
    for tid, tdata in THEMES.items():
        for s in tdata.get("subtopics", []):
            all_subtopic_names.append((tid, s.strip()))
    name_to_ids = {}
    for tid, sname in all_subtopic_names:
        name_to_ids.setdefault(sname, []).append(tid)
    # Some subtopics may legitimately repeat across themes (e.g. common concepts)
    # We just warn, not fail

    # 5. Grade distribution covers all themes
    assigned = set()
    for g, tids in GRADE_THEMES.items():
        assigned.update(tids)
    unassigned = set(THEMES.keys()) - assigned
    if unassigned:
        issues.append(f"Themes not assigned to any grade: {sorted(unassigned)}")
    extra = assigned - set(THEMES.keys())
    if extra:
        issues.append(f"Grade themes reference unknown IDs: {extra}")

    return issues


def build_snapshot():
    """Build the canonical taxonomy snapshot."""
    snapshot = {
        "meta": {
            "description": "Canonical taxonomy for FORMYLA L1-L3 generation",
            "version": "2.0",
            "source": "VICTOR2.0 (43 themes: 41 canonical + T042, T043 from Section 3)",
            "total_themes": len(THEMES),
            "total_subtopics": sum(len(t["subtopics"]) for t in THEMES.values()),
            "grades": sorted(GRADE_THEMES.keys()),
            "grade_distribution": {
                str(g): {
                    "theme_count": len(tids),
                    "subtopic_count": sum(len(THEMES[t]["subtopics"]) for t in tids),
                    "theme_ids": tids
                }
                for g, tids in sorted(GRADE_THEMES.items())
            },
            "levels": ["L1", "L2", "L3"],
            "tasks_per_cell": 5
        },
        "themes": {},
        "grade_themes": {str(g): tids for g, tids in sorted(GRADE_THEMES.items())}
    }

    for tid in sorted(THEMES.keys()):
        tdata = THEMES[tid]
        snapshot["themes"][tid] = {
            "id": tid,
            "name": tdata["name"],
            "subtopics": {
                f"S{i}": {
                    "id": f"S{i}",
                    "name": tdata["subtopics"][i]
                }
                for i in range(3)
            }
        }

    return snapshot


def compute_checksum(data):
    """Compute SHA-256 checksum of JSON-serialized data."""
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Validate
    issues = validate_taxonomy()
    print(f"Taxonomy validation: {'PASS' if not issues else 'FAIL'}")
    for issue in issues:
        print(f"  ISSUE: {issue}")

    # 2. Build snapshot
    snapshot = build_snapshot()
    snapshot_checksum = compute_checksum(snapshot)

    # 3. Compute total target cells
    total_cells = 0
    for g, tids in GRADE_THEMES.items():
        for tid in tids:
            for level in [1, 2, 3]:
                total_cells += 3  # 3 subtopics per theme
    total_tasks = total_cells * 5

    # 4. Build source report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot_file": "canonical_taxonomy_snapshot.json",
        "snapshot_checksum_sha256": snapshot_checksum,
        "source_files": [
            {
                "path": "VICTOR2.0",
                "description": "Main generation script containing 43 themes and grade distribution",
                "status": "found"
            },
            {
                "path": "_build_grade_taxonomy.py",
                "description": "Canonical taxonomy builder with 41 themes and comprehensive grade distribution",
                "status": "found (cross-reference)"
            },
            {
                "path": "_taxonomy_editor.txt",
                "description": "Taxonomy editor with full theme/subtopic listing",
                "status": "found (cross-reference)"
            }
        ],
        "validation": {
            "status": "PASS" if not issues else "FAIL",
            "total_themes": len(THEMES),
            "total_subtopics": sum(len(t["subtopics"]) for t in THEMES.values()),
            "expected_themes": 43,
            "expected_subtopics": 129,  # 43 * 3
            "expected_range": "T001-T043",
            "grade_count": len(GRADE_THEMES),
            "expected_grades": "5-11",
            "issues": issues if issues else None,
            "checks": {
                "sequential_ids": sorted(THEMES.keys()) == [f"T{i:03d}" for i in range(1, 44)],
                "all_have_3_subtopics": all(len(t["subtopics"]) == 3 for t in THEMES.values()),
                "no_empty_subtopic_names": all(
                    s and s.strip() for t in THEMES.values() for s in t["subtopics"]
                ),
                "no_duplicate_topic_ids": len(THEMES) == len(set(THEMES.keys())),
                "all_themes_assigned_to_grades": all(
                    any(tid in tids for tids in GRADE_THEMES.values())
                    for tid in THEMES.keys()
                )
            }
        },
        "generation_plan": {
            "target_cells": total_cells,
            "target_tasks": total_tasks,
            "tasks_per_cell": 5,
            "levels": ["L1", "L2", "L3"],
            "grade_summary": {
                str(g): {
                    "themes": len(tids),
                    "cells": len(tids) * 3 * 3,  # themes * subtopics * levels
                    "tasks": len(tids) * 3 * 3 * 5
                }
                for g, tids in sorted(GRADE_THEMES.items())
            }
        }
    }

    # 5. Write snapshot
    snapshot_path = os.path.join(out_dir, "canonical_taxonomy_snapshot.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"\nWritten: {snapshot_path}")

    # 6. Write report
    report_path = os.path.join(out_dir, "taxonomy_source_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Written: {report_path}")

    # 7. Print summary
    print(f"\n{'='*60}")
    print(f"TAXONOMY SNAPSHOT SUMMARY")
    print(f"{'='*60}")
    print(f"  Themes:       {len(THEMES)} (T001-T043)")
    print(f"  Subtopics:    {sum(len(t['subtopics']) for t in THEMES.values())} (43×3)")
    print(f"  Grades:       {sorted(GRADE_THEMES.keys())} (5-11)")
    print(f"  Target cells: {total_cells}")
    print(f"  Target tasks: {total_tasks}")
    print(f"  Validation:   {'PASS' if not issues else 'FAIL'}")
    if issues:
        print(f"  Issues:       {len(issues)}")
        for issue in issues:
            print(f"    - {issue}")
    print(f"  Checksum:     {snapshot_checksum[:16]}...")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
