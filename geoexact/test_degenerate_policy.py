# -*- coding: utf-8 -*-
"""Вырожденность с учётом семантики плана: законные конфигурации проходят.

Регрессии коммита 7585ffd1 (DEGENERATE_FIGURE): трисектор-задача с D на
продолжении CA и высота CH≡M при M=midpoint(A,B) браковались решателем,
хотя их геометрия верна и гейт корректности их принимает.
"""
import sys

import numpy as np
import pytest

from geoexact.core import solver, semantics, gates, pipeline, llm
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.degenerate_policy import install as dp_install, named_figure_failures

sys.path.insert(0, ".")

TRISECTOR = ("На стороне BC треугольника ABC отмечены точки M и N так, что BM = MN = NC. "
             "Прямая, параллельная AN и проходящая через точку M, пересекает продолжение "
             "стороны AC за точку A в такой точке D, что AB = CD. Найдите AB, "
             "если BC = 12, cos(2∠CAN) = 0.64.")


def _midfoot_plan():
    """M=midpoint(A,B); C на перпендикуляре через M; H=foot(C,A,B)≡M — совпадение построенных точек."""
    return FigurePlan.from_dict({
        "points": ["A", "B", "M", "C", "H"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "midpoint", "out": "M", "args": ["A", "B"]},
            {"op": "perp_point", "out": "C", "args": ["M", "A", "B"], "value": 2},
            {"op": "foot", "out": "H", "args": ["C", "A", "B"]}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["C", "H"]]},
        "scale_free": False})


def test_module_is_installed():
    assert getattr(solver.degenerate_figure, "_degenerate_policy", False)
    assert getattr(solver._drawn_triangles, "_degenerate_policy", False)
    assert "+dgp" in pipeline.ENGINE_VERSION


def test_collinear_by_construction_triangle_is_not_degenerate():
    """ACD коллинеарны по условию (D на продолжении CA, on_segment в плане) — не вырождение."""
    plan = semantics.trisected_parallel_plan(TRISECTOR, False)
    sols = solve(plan, n_seeds=8)
    assert sols, "решатель не нашёл решения трисектор-задачи"
    ok = [s for s in sols if s.ok]
    assert ok, [s.reason for s in sols[:3]]
    g = gates.gate_correctness(plan, ok[0])
    assert g.ok, g.failures[:3]


def test_coincident_constructed_points_are_not_degenerate():
    """H=foot(C,A,B) совпадает с M=midpoint(A,B) — предупреждение гейта, не отказ решателя."""
    plan = _midfoot_plan()
    sols = solve(plan, n_seeds=8)
    ok = [s for s in sols if s.ok]
    assert ok, [s.reason for s in sols[:3]]
    g = gates.gate_correctness(plan, ok[0])
    assert g.ok, g.failures[:3]
    assert any("CONSTRUCTED_COINCIDENCE" in w for w in g.warnings)


def test_free_points_coinciding_is_still_degenerate():
    """Схема не допускает dist=0, поэтому проверяем саму политику напрямую."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [],
        "draw": {"segments": [["A", "C"], ["B", "C"]]},
        "scale_free": True})
    coords = {"A": np.array([0.0, 0.0]), "B": np.array([1e-9, 0.0]),
              "C": np.array([0.0, 5.0])}
    assert "совпали" in solver.degenerate_figure(plan, coords)


def test_undeclared_collinear_triangle_is_still_degenerate():
    """Три соединённые точки на одной прямой без объявления коллинеарности — отказ."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABCD"],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "C"]]},
        "scale_free": False})
    coords = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]),
              "C": np.array([2.0, 0.0]), "D": np.array([1.0, 3.0])}
    assert "схлопнулся" in solver.degenerate_figure(plan, coords)


def test_semantic_failures_keeps_all_wrapper_markers():
    """Маркеры всех обёрток видны на внешней функции (functools.wraps)."""
    assert getattr(semantics.semantic_failures, "_convexity", False)
    assert getattr(semantics.semantic_failures, "_radius_claims", False)
    assert getattr(semantics.semantic_failures, "_degenerate_policy", False)


def test_named_triangle_cannot_be_a_segment(monkeypatch, text="Дан треугольник ABC. Постройте чертёж."):
    """Отрезок вместо треугольника не получает статус «проверено».

    Раньше это отвергал решатель (DEGENERATE_FIGURE); после разрешения
    объявленной коллинеарности защиту принимает текстовая проверка:
    «треугольник ABC» с нулевой площадью — жёсткая ошибка семантики.
    """
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABD"]
        + [{"op": "midpoint", "out": "C", "args": ["A", "B"]}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"]]},
        "target": {"kind": "none", "args": []}, "scale_free": False})
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (plan, []))
    result = pipeline.generate(text, sess=object(), use_cache=False, max_retries=1)
    assert result.ok                      # чертёж показан
    assert result.verification != "constraints_only"
    assert result.verification == "approximate"
    assert any("вырожден" in w for w in result.warnings)


@pytest.mark.parametrize("text", ["Треугольник ABC. Постройте чертёж.",
                                  "△ABC. Постройте чертёж."])
def test_named_triangle_writing_variants(monkeypatch, text):
    test_named_triangle_cannot_be_a_segment(monkeypatch, text=text)


def test_constructed_point_on_free_vertex_is_caught_by_text(monkeypatch):
    """«Медиана BD» с D=line_intersect(A,B,A,C)=A — не медиана.

    Решатель такое точное совпадение пропускает (контракт: неверная фигура
    показывается как approximate с причиной), защиту держит текстовая
    проверка CEVIAN — в том числе при скрытой метке D, когда гейт видит
    лишь безобидный псевдоним.
    """
    text = "В треугольнике ABC проведена медиана BD."
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"]
        + [{"op": "line_intersect", "out": "D", "args": ["A", "B", "A", "C"]}],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["B", "D"]],
                 "hide_labels": ["D"]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    coords = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 3.0]),
              "C": np.array([-2.0, 5.0]), "D": np.array([0.0, 0.0])}
    # решатель принимает (точное совпадение с участием построенной точки)
    assert solver.degenerate_figure(plan, coords) == ""
    # текстовая проверка видит подмену медианы
    assert any("CEVIAN" in f for f in semantics.semantic_failures(text, plan, coords))
    # end-to-end: статус не «проверено»
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (plan, []))
    result = pipeline.generate(text, sess=object(), use_cache=False, max_retries=1)
    assert result.ok
    assert result.verification != "constraints_only"
    assert any("не является серединой" in w for w in result.warnings)


def test_median_and_height_checks_unit():
    """Верная медиана/высота проходят, неверные — отказ."""
    tri = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 3.0]),
          "C": np.array([-2.0, 5.0])}
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "M", "H"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    good = dict(tri, M=(tri["A"] + tri["C"]) / 2)
    assert semantics.semantic_failures("В треугольнике ABC проведена медиана BM.", plan, good) == []
    bad = dict(tri, M=tri["A"])
    assert any("CEVIAN" in f for f in
               semantics.semantic_failures("В треугольнике ABC проведена медиана BM.", plan, bad))
    # высота: основание на стороне и перпендикуляр — ок; совпадение с вершиной — отказ
    d = tri["C"] - tri["A"]
    foot = tri["A"] + d * float(np.dot(tri["B"] - tri["A"], d) / (d @ d))
    ok_h = dict(tri, H=foot)
    assert semantics.semantic_failures("В треугольнике ABC проведена высота BH.", plan, ok_h) == []
    assert any("CEVIAN" in f for f in
               semantics.semantic_failures("В треугольнике ABC проведена высота BH.", plan, dict(tri, H=tri["A"])))


def test_flat_angle_mark_is_not_a_degenerate_triangle():
    """Отмеченный угол ≈180° (без третьей стороны) не становится «схлопнувшимся треугольником»."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABCD"],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["A", "D"]],
                "angle_marks": [{"pts": ["A", "B", "C"], "text": "175°"}]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    coords = {"A": np.array([0.0, 0.0]), "B": np.array([2.0, 0.0]),
              "C": np.array([4.0, 0.0]), "D": np.array([1.0, 2.0])}
    assert solver.degenerate_figure(plan, coords) == ""
    assert ("A", "B", "C") not in [tuple(sorted(t)) for t in solver._drawn_triangles(plan)]


def test_named_figure_failures_unit():
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    flat = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]), "C": np.array([2.0, 0.0])}
    good = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]), "C": np.array([2.0, 3.0])}
    assert len(named_figure_failures("Дан треугольник ABC", plan, flat)) == 1
    assert named_figure_failures("Дан треугольник ABC", plan, good) == []
    # трисектор: назван ABC (невырожден), коллинеарность ACD условием не треугольник
    tri_plan = semantics.trisected_parallel_plan(TRISECTOR, False)
    sols = [s for s in solve(tri_plan, n_seeds=8) if s.ok]
    assert sols and named_figure_failures(TRISECTOR, tri_plan, sols[0].coords) == []


def test_near_coincident_distinct_points_are_still_degenerate():
    """Две РАЗНЫЕ построенные точки на 0.1% габарита — по-прежнему отказ."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "AB"]
        + [{"op": "midpoint", "out": "C", "args": ["A", "B"]},
           {"op": "divide_segment", "out": "D", "args": ["A", "B"], "value": 0.501}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 4}],
        "draw": {"segments": [["A", "C"], ["C", "D"], ["D", "B"]]},
        "target": {"kind": "none", "args": []}, "scale_free": False})
    coords = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]),
              "C": np.array([2.0, 0.0]), "D": np.array([2.004, 0.0])}
    why = solver.degenerate_figure(plan, coords)
    assert why and ("слиплись" in why or "совпали" in why)


def test_install_is_idempotent():
    assert dp_install(solver) is False   # всё уже установлено: повтор — no-op
    assert getattr(solver.degenerate_figure, "_degenerate_policy", False)


def test_pipeline_trisector_without_model():
    """Полный конвейер без модели: точный план, статус проверенного чертежа, без предупреждений."""
    result = pipeline.generate(TRISECTOR, with_aux=False, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.verification == "constraints_only"
    assert result.warnings == []


# ---------------------------------------------------------------- параллелограмм

_PARA_TEXT = ("В остроугольном треугольнике ABC с ∠BAC = 60° проведена биссектриса AD. "
              "Докажите, что BB₁CC₁ — параллелограмм.")
_PARA_SIDES = [["B", "B_1"], ["B_1", "C"], ["C", "C_1"], ["C_1", "B"]]


def _para_plan(segments=None, points=("A", "B", "B_1", "C", "C_1")):
    return FigurePlan.from_dict({
        "points": list(points),
        "constructions": [{"op": "free_point", "out": n} for n in points],
        "constraints": [],
        "draw": {"segments": list(_PARA_SIDES if segments is None else segments)},
        "target": {"kind": "none", "args": []}, "scale_free": True})


def _para_coords(parallel=True):
    # порядок обхода B -> B_1 -> C -> C_1: B_1-B = C-C_1, C_1-B = C-B_1
    return {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]),
            "B_1": np.array([2.0, 1.0]),
            "C": np.array([0.0, 3.0]) if parallel else np.array([0.5, 2.5]),
            "C_1": (np.array([2.0, 2.0]) if parallel else np.array([2.0, 2.2]))}


def test_parallelogram_claim_with_subscripts_passes_on_correct_figure():
    assert named_figure_failures(_PARA_TEXT, _para_plan(), _para_coords()) == []


def test_parallelogram_claim_with_subscripts_catches_wrong_figure():
    fails = named_figure_failures(_PARA_TEXT, _para_plan(), _para_coords(parallel=False))
    assert any("не является невырожденным параллелограммом" in f for f in fails)


def test_parallelogram_claim_requires_all_sides_drawn():
    plan = _para_plan(segments=[["B", "B_1"], ["B_1", "C"]])
    fails = named_figure_failures(_PARA_TEXT, plan, _para_coords())
    assert any("не все стороны параллелограмма" in f for f in fails)


def test_parallelogram_claim_ascii_and_unicode_subscripts():
    from geoexact.core.degenerate_policy import parallelogram_names
    assert parallelogram_names(_PARA_TEXT) == [("B", "B_1", "C", "C_1")]
    ascii_text = _PARA_TEXT.replace("BB₁CC₁", "BB_1CC_1")
    assert parallelogram_names(ascii_text) == [("B", "B_1", "C", "C_1")]


def test_parallelogram_claim_without_word_quadrilateral():
    """«ABCD — параллелограмм» без слова «четырёхугольник» — semantics не видит."""
    text = "Докажите, что ABCD — параллелограмм."
    points = ("A", "B", "C", "D")
    plan = FigurePlan.from_dict({
        "points": list(points),
        "constructions": [{"op": "free_point", "out": n} for n in points],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    ok = {"A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]),
          "C": np.array([5.0, 2.0]), "D": np.array([1.0, 2.0])}
    bad = dict(ok, C=np.array([5.5, 1.0]))
    assert named_figure_failures(text, plan, ok) == []
    assert any("параллелограммом" in f for f in named_figure_failures(text, plan, bad))


def test_parallelogram_semantics_forms_not_duplicated():
    """Формулировки, которые проверяет semantics, обёртка не дублирует."""
    from geoexact.core.degenerate_policy import parallelogram_names
    assert parallelogram_names("Четырёхугольник ABCD — параллелограмм.") == []
    assert parallelogram_names("Параллелограмм ABCD.") == []
    # косвенные падежи и «является» semantics не покрывает — проверяет обёртка
    assert parallelogram_names("Стороны параллелограмма ABCD равны.") == [("A", "B", "C", "D")]
    assert parallelogram_names("Четырёхугольник ABCD является параллелограммом.") \
        == [("A", "B", "C", "D")]


def test_parallelogram_claim_end_to_end():
    """Через semantic_failures: неверный параллелограмм — жёсткая ошибка."""
    fails = semantics.semantic_failures(_PARA_TEXT, _para_plan(), _para_coords(parallel=False))
    assert any("PARALLELOGRAM" in f for f in fails)


def test_parallelogram_claim_dash_eto_form():
    """«BB₁CC₁ — это параллелограмм»: тире и связка — независимые части."""
    from geoexact.core.degenerate_policy import parallelogram_names
    assert parallelogram_names("Докажите, что BB₁CC₁ — это параллелограмм.") \
        == [("B", "B_1", "C", "C_1")]
    assert parallelogram_names("BB₁CC₁ является параллелограммом.") \
        == [("B", "B_1", "C", "C_1")]


def test_parallelogram_claim_missing_vertex_is_hard_failure():
    coords = dict(_para_coords())
    del coords["C_1"]
    fails = named_figure_failures(_PARA_TEXT, _para_plan(), coords)
    assert any("отсутствуют вершины параллелограмма" in f and "C_1" in f
               for f in fails)


def test_parallelogram_claim_end_to_end_status(monkeypatch):
    """Неверный параллелограмм — статус не «проверено», причина PARALLELOGRAM."""
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (_para_plan(), []))
    # свободные точки: решатель размещает их как угодно, параллелограммом
    # они не станут — проверка обязана понизить статус
    result = pipeline.generate(_PARA_TEXT, sess=object(), use_cache=False, max_retries=1)
    assert result.ok
    assert result.verification != "constraints_only"
    assert any("параллелограмм" in w for w in result.warnings)
