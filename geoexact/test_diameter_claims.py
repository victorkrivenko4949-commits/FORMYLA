# -*- coding: utf-8 -*-
"""«(Полу)окружность с диаметром XY»: концы на окружности, центр — середина.

Прод-сценарий (задача 4, живая генерация 24.10.2026): «На полуокружности с
диаметром AD отмечены точки B и C. Точка M — середина отрезка BC. Точка N
такова, что M — середина отрезка AN. Докажите, что прямые BC и DN
перпендикулярны.» Формализатор прочитал «с диаметром AD» как «центр A,
через D»: on_circle(B,A,A,D) — AD стал радиусом, A — центром, прямой угол
в M получился сам (серединный перпендикуляр из центра к хорде), а целевое
BC⊥DN на чертеже не выполнялось. Здесь: верная конфигурация проходит все
проверки, прод-ошибка бракуется с указанием конкретной нарушенной фразы.
"""
from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.diameter_claims import (
    diameter_claims, diameter_failures, _center_failure, _thales_failure)
from geoexact.core.schema import Draw, FigurePlan

PROBLEM = ("4. На полуокружности с диаметром \\(AD\\) отмечены точки \\(B\\) и \\(C\\). "
           "Точка \\(M\\) — середина отрезка \\(BC\\). Точка \\(N\\) такова, что "
           "\\(M\\) — середина отрезка \\(AN\\). Докажите, что прямые \\(BC\\) и "
           "\\(DN\\) перпендикулярны.")

# Верная конфигурация (A=(0,0), D=(10,0), B и C на верхней полуокружности
# радиуса 5 с центром O=(5,0)): B=(2,4) даёт (B-A)·(B-D)=-16+16=0, C=(9,3) —
# -9+9=0; M=(5.5,3.5), N=2M-A=(11,7); BC=(-7,1), DN=(1,7) — целевая
# перпендикулярность BC⊥DN выполнена.
GOOD = {"A": (0, 0), "B": (2, 4), "C": (9, 3), "D": (10, 0),
       "M": (5.5, 3.5), "N": (11, 7), "O": (5, 0)}

# Прод-ошибка 24.10.2026: окружность с ЦЕНТРОМ A радиуса AD, B и C на ней,
# M — середина BC, N — отражение A в M. Угол ABD ≈ 71.6° вместо 90°.
BAD = {"A": (0, 0), "B": (8, 6), "C": (6, -8), "D": (10, 0),
       "M": (7, -1), "N": (14, -2)}


def _plan(circles):
    return FigurePlan(points=["A", "B", "C", "D", "M", "N"],
                     draw=Draw(circles=list(circles)),
                     constructions=[], constraints=[])


def test_claims_parsed_from_problem():
    claims = diameter_claims(PROBLEM)
    assert claims == [("A", "D", True, ["B", "C"])], claims


def test_rev_phrase_parsed():
    claims = diameter_claims("Точки B и C отмечены на окружности с диаметром AD.")
    assert ("A", "D", False, ["B", "C"]) in claims, claims


def test_good_config_passes():
    plan = _plan([["O", "A"]])
    assert diameter_failures(PROBLEM, GOOD, plan) == []


def test_prod_config_named_as_failure():
    plan = _plan([["A", "D"]])  # центр A — прод-план on_circle(B,A,A,D)
    fails = diameter_failures(PROBLEM, BAD, plan)
    assert any("вместо 90°" in f and "точка B" in f for f in fails), fails
    assert any("конец диаметра, а не центр" in f and "A" in f for f in fails), fails


def test_prod_config_without_plan_still_caught():
    # Тот же прод-баг, но план не передан: ловит проверка Фалеса.
    fails = diameter_failures(PROBLEM, BAD, None)
    assert any("точка B" in f and "90°" in f for f in fails), fails
    assert all("конец диаметра, а не центр" not in f for f in fails)


def test_thales_tolerance_is_exact_for_solved_coords():
    # Численное решение держит прямой угол с точностью лучше 1e-3 по косинусу.
    good = dict(GOOD)
    good["B"] = (2.0, 4.0 + 1e-6)   # сдвиг 1e-6 — в пределах терпимости
    assert _thales_failure(good, "B", "A", "D", 10.0) is None


def test_center_check_tolerates_other_circles():
    # Правильная окружность [O, A] нарисована — чужой круг с центром A не флажим.
    plan = _plan([["O", "A"], ["A", "B"]])
    assert _center_failure(plan, GOOD, "A", "D", 10.0) is None


def test_semiside_failure_on_opposite_sides():
    bad = dict(GOOD)
    bad["C"] = (9, -3)   # C переехала на нижнюю полуокружность
    fails = diameter_failures(PROBLEM, bad, None)
    assert any("по одну сторону" in f for f in fails), fails


def test_semiside_names_contradictory_condition():
    # «полуокружность» + «по разные стороны» — противоречие в условии:
    # называем его до анализа координат, даже если рисунок по одну сторону.
    text = ("На полуокружности с диаметром AD отмечены точки B и C, "
            "лежащие по разные стороны от AD.")
    for coords in (dict(GOOD), {**GOOD, "C": (9, -3)}):
        fails = diameter_failures(text, coords, None)
        assert any("противоречиво" in f for f in fails), (coords, fails)


def test_pipeline_rejects_prod_plan(monkeypatch):
    """Прод-план из журнала не подаётся как проверенный: fallback approximate
    с именованной фразой про диаметр (Фалес/центр), не clean constraints_only."""
    from geoexact.core import llm as L, pipeline as P

    def formalize(sess, text, cls, aux, budget, feedback="", prev=""):
        pl = FigurePlan.from_dict({
            "points": ["A", "D", "B", "C", "M", "N"],
            "constructions": [
                {"op": "free_point", "out": "A", "args": []},
                {"op": "free_point", "out": "D", "args": []},
                {"op": "free_point", "out": "B", "args": []},
                {"op": "free_point", "out": "C", "args": []},
                {"op": "midpoint", "out": "M", "args": ["B", "C"]},
                {"op": "reflect_point", "out": "N", "args": ["A", "M"]}],
            "constraints": [
                {"type": "on_circle", "args": ["B", "A", "A", "D"]},
                {"type": "on_circle", "args": ["C", "A", "A", "D"]},
                {"type": "dist", "args": ["A", "D"], "value": 10}],
            "scale_free": True,
            "draw": {"circles": [["A", "D"]],
                     "segments": [["B", "C"], ["A", "N"], ["D", "N"]]},
        })
        return pl, []

    monkeypatch.setattr(L, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(L, "aux_plan", lambda *_, **__: {"steps": []})
    monkeypatch.setattr(L, "formalize", formalize)
    r = P.generate(PROBLEM, False, sess=object(), use_cache=False)
    assert r.ok, (r.stage, r.reason, r.detail)
    assert r.verification == "approximate", (r.verification, r.stage)
    joined = "; ".join(r.warnings or []) + "; " + (r.detail or "")
    assert "диаметром AD" in joined, r.warnings
    assert "вместо 90°" in joined or "конец диаметра" in joined, joined


def test_statement_requirements_include_diameter_segment():
    from geoexact.core.statement import statement_requirements
    segs = statement_requirements(PROBLEM)["segments"]
    assert (("A", "D") in [p for _, p in segs]) or (("D", "A") in [p for _, p in segs]), segs


def test_statement_layer_draws_diameter_segment():
    # Диаметр назван в условии — отрезок обязан быть проведён: слой
    # «проведено и отмечено» достраивает его сам, с пометкой STATEMENT_DRAW.
    from geoexact.core.statement import complete_statement_display
    plan = _plan(["O", "A"])   # AD не проведён
    plan2, notes = complete_statement_display(plan, GOOD, PROBLEM)
    pairs = {frozenset(s) for s in plan2.draw.segments}
    assert frozenset(("A", "D")) in pairs, plan2.draw.segments
    assert any("STATEMENT_DRAW" in n and "AD" in n for n in notes), notes


def test_rules_injected_and_semantic_chain_active():
    from geoexact.core import diameter_claims as dc
    assert dc.install(semantics, L, pipeline) is True   # идемпотентно
    assert "39." in L.SYS_FORMALIZE and "DIAMETER_RULE" in L.SYS_FORMALIZE
    assert getattr(L, "SYS_AUX", "") == "" or "39." in (L.SYS_AUX or "")
    assert getattr(semantics.semantic_failures, "_diameter_claims", False)


def test_engine_version_suffix():
    assert "+diameterClaims1" in pipeline.ENGINE_VERSION, pipeline.ENGINE_VERSION
