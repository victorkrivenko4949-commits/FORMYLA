# -*- coding: utf-8 -*-
"""Раннер корпуса ФОРМУЛА: гоняет фикстуры через верификатор инвариантов.

Запуск:
  cd formyla_v2
  python verify/run_corpus.py
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from verify.invariant_checker import check_invariants

FX = os.path.join(ROOT, "tests", "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


# Адверсариальные кейсы: solver ЗАЯВЛЯЕТ ложное равенство/параллельность/угол.
# Верификатор обязан это поймать (доказывает, что он не штампует PASS).
import math as _m


def _adv_base():
    """Треугольник ABC + точка D на AC (не середина)."""
    return {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "free_point", "id": "D", "x": 360, "y": 250, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ]}


# ADV1: solver ложно заявляет AB=CD (они не равны)
ADV1 = (
    "ADV1 ложное равенство AB=CD",
    _adv_base(),
    {"solvable": True,
     "steps": [{"no": 1, "text": "Отметим AB=CD как равные."}],
     "aux_needed": True,
     "aux_constructions": [
         {"op": "mark_equal_segments", "segments": ["A", "B", "C", "D"],
          "count": 1, "quote": "Отметим AB=CD как равные.", "step_no": 1},
     ]},
)

# ADV2: solver ложно заявляет AB||CD (они не параллельны)
ADV2 = (
    "ADV2 ложная параллельность AB||CD",
    _adv_base(),
    {"solvable": True,
     "steps": [{"no": 1, "text": "Отметим AB параллельно CD."}],
     "aux_needed": True,
     "aux_constructions": [
         {"op": "mark_equal_segments", "segments": ["A", "B", "A", "B"],
          "count": 1, "quote": "Отметим AB как равные.", "step_no": 1},
     ],
    } | {"_parallel": True},  # маркер; реальная parallel_mark ниже
)
# Корректная ADV2: используем parallel_mark прямо в base (заявляем AB||CD).
ADV2 = (
    "ADV2 ложная параллельность AB||CD",
    {"constructions": _adv_base()["constructions"] + [
        {"type": "parallel_mark", "id": "par_false",
         "segments": [["A", "B"], ["C", "D"]]},
    ]},
    {"solvable": True, "steps": [{"no": 1, "text": "AB параллельно CD."}],
     "aux_needed": False, "aux_constructions": []},
)

# ADV3: solver ложно заявляет что D — середина BC (D не на BC и не середина)
ADV3 = (
    "ADV3 ложная середина D=mid(BC)",
    {"constructions": [
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "free_point", "id": "D", "x": 300, "y": 300, "label": "D"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "midpoint_mark", "id": "mm_false",
         "p1": "B", "p2": "D", "p3": "D", "p4": "C"},
    ]},
    {"solvable": True, "steps": [{"no": 1, "text": "D — середина BC."}],
     "aux_needed": False, "aux_constructions": []},
)

# ADV4: solver ложно заявляет прямой угол при A в тупоугольном треугольнике
ADV4 = (
    "ADV4 ложный прямой угол при A",
    {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 200, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "right_angle_mark", "id": "ra_false",
         "vertex": "A", "ray1": "B", "ray2": "C"},
    ]},
    {"solvable": True, "steps": [{"no": 1, "text": "Угол A прямой."}],
     "aux_needed": False, "aux_constructions": []},
)

# ADV5: ложно заявлено равенство углов BAD=DAC, но углы не равны.
# A=(300,80), B=(100,420), C=(520,420), D смещён — углы BAD и DAC различны.
ADV5 = (
    "ADV5 ложное равенство углов BAD=DAC",
    {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        # D намеренно не на биссектрисе — ближе к стороне AB.
        {"type": "free_point", "id": "D", "x": 230, "y": 380, "label": "D"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
        {"type": "equal_angles_mark", "id": "ea_false",
         "angles": [["B", "A", "D"], ["D", "A", "C"]]},
    ]},
    {"solvable": True, "steps": [{"no": 1, "text": "Углы BAD и DAC равны."}],
     "aux_needed": False, "aux_constructions": []},
)

# ADV6: base_plan декларирует инцидентность свободной точки D на окружности
# omega, но координаты D намеренно не на окружности → POINT_NOT_ON_CIRCLE.
ADV6 = (
    "ADV6 точка вне заявленной окружности",
    {"constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80, "label": "A"},
        {"type": "free_point", "id": "B", "x": 100, "y": 420, "label": "B"},
        {"type": "free_point", "id": "C", "x": 520, "y": 420, "label": "C"},
        {"type": "circumcircle", "id": "omega", "p1": "A", "p2": "B", "p3": "C"},
        # D намеренно не на окружности (должна быть на дуге, но координаты мимо).
        {"type": "free_point", "id": "D", "x": 300, "y": 250, "label": "D"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
    ], "incidences": [
        {"point": "D", "on": "circle", "object": "omega"},
    ]},
    {"solvable": True, "steps": [{"no": 1, "text": "D лежит на описанной окружности."}],
     "aux_needed": False, "aux_constructions": []},
)

ADV_CASES = [ADV1, ADV2, ADV3, ADV4, ADV5, ADV6]


# Корпус: (метка задачи, base_plan_fixture, solver_fixture)
CORPUS = [
    ("Средняя линия MN (E8-E19)", "base_plan_midsegment.json", "solver_midsegment.json"),
    ("Параллельная через точку (E15-E16)", "base_plan_parallel_through.json", "solver_parallel_through.json"),
    ("Прямой угол AM=BC/2 (Thales)", "base_plan_right_angle.json", "solver_right_angle_v5.json"),
    ("Параллелограмм ABCK", "base_plan_parallelogram.json", "solver_parallelogram.json"),
    # Новые проблемные задачи (биссектрисы/инцентр, подобие с отношением, касательные):
    ("Биссектрисы → инцентр (НОВАЯ)", "base_plan_bisectors_incenter.json", "solver_bisectors_incenter.json"),
    ("Подобие AD:DB=2:1, DE||BC (НОВАЯ)", "base_plan_similar_ratio.json", "solver_similar_ratio.json"),
    ("Касательные AB=AC, AO-биссектриса (НОВАЯ)", "base_plan_tangent_circle.json", "solver_tangent_circle.json"),
    # Сложные задачи (ортодентр+симметрия, дуга+биссектриса, трапеция):
    ("Ортоцентр + симметрия H' (СЛОЖНАЯ)", "base_plan_orthocenter.json", "solver_orthocenter.json"),
    ("Середина дуги + биссектриса (СЛОЖНАЯ)", "base_plan_arc_bisector.json", "solver_arc_bisector.json"),
    ("Трапеция + средняя линия (СЛОЖНАЯ)", "base_plan_trapezoid_midsegment.json", "solver_trapezoid_midsegment.json"),
]


def main():
    npass = 0
    ntotal = 0
    for label, bp_name, sv_name in CORPUS:
        bp_path = os.path.join(FX, bp_name)
        sv_path = os.path.join(FX, sv_name)
        if not (os.path.exists(bp_path) and os.path.exists(sv_path)):
            print(f"\n### {label}\n  ПРОПУСК: нет фикстуры ({bp_name}/{sv_name})")
            continue
        base = _load(bp_name)
        solver = _load(sv_name)
        ntotal += 1
        print(f"\n### {label}")
        rep = check_invariants(base, solver)
        st = rep["stats"]
        print(f"  stats: points={st['points']} segs={st['segments']} "
              f"labels={st['labels']} ticks={st['ticks']} "
              f"compile_issues={st['compile_issues']}")
        for c in rep["checks"]:
            print(f"  [OK] {c}")
        for w in rep["warnings"]:
            print(f"  [WARN] {w}")
        for e in rep["errors"]:
            print(f"  [FAIL] {e}")
        ok = not rep["errors"]
        if ok:
            npass += 1
            print(f"  => ИТОГ: PASS (ошибок нет, warning'ов: {len(rep['warnings'])})")
        else:
            print(f"  => ИТОГ: FAIL ({len(rep['errors'])} ошибок, "
                  f"{len(rep['warnings'])} warning'ов)")

    # ── Адверсариальные кейсы (должны FAIL) ──
    print("\n" + "="*60)
    print("АДВЕРСАРИАЛЬНЫЕ КЕЙСЫ (ожидается FAIL — верификатор ловит ложь)")
    print("="*60)
    n_adv_caught = 0
    for label, base, solver in ADV_CASES:
        print(f"\n### {label}")
        rep = check_invariants(base, solver)
        for e in rep["errors"]:
            print(f"  [FAIL] {e}")
        if rep["errors"]:
            n_adv_caught += 1
            print(f"  => ПОЙМАНО (верификатор сработал)")
        else:
            print(f"  => НЕ ПОЙМАНО (верификатор пропустил ложь — это баг верификатора!)")
    print(f"\nАдверсариал: {n_adv_caught}/{len(ADV_CASES)} ложных утверждений поймано")

    print(f"\n{'='*60}")
    print(f"КОРПУС: {npass}/{ntotal} задач без ошибок-инвариантов")
    if npass < ntotal:
        print("Остались нарушения инвариантов — см. FAIL выше.")
    else:
        print("Все заявленные равенства/параллельности/углы выполняются.")
    adv_ok = n_adv_caught == len(ADV_CASES)
    print(f"Адверсариал: {'ВСЕ пойманы' if adv_ok else 'ЕСТЬ ПРОПУСКИ'}")
    sys.exit(0 if (npass == ntotal and adv_ok) else 1)


if __name__ == "__main__":
    main()
