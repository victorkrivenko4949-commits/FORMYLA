# -*- coding: utf-8 -*-
"""Ремонт медианы «в треугольнике XYZ — медиану VM» + базовая фигура наброска.

Прод-кейс (27.10.2026, задача пользователя): «в треугольнике BLC — медиану
BM» формализатор строил как M=midpoint(B,L), а не midpoint(L,C). С такой M
точки B,H,L,M коллинеарны на высоте BH ⟂ AC, ∠MHC=90° всегда — система
нерешаема, конвейер падал в схематичный набросок, который рисовал только
четырёхугольник KLHM из вопроса вместо треугольника ABC из условия.
"""
import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import pipeline, semantics
from geoexact.core.degenerate_policy import _cevians
from geoexact.core.median_point import median_claims, repair
from geoexact.core.schema import FigurePlan, validate_plan
from geoexact.core.sketch import sketch_plan
from geoexact.core.solver import solve

PROD_TEXT = (
    "В остроугольном треугольнике ABC со стороной AC = 1 провели высоту BH, "
    "в треугольнике BHC — биссектрису CL, в треугольнике BLC — медиану BM. "
    "Прямая AL пересекает сторону BC в точке K, причём ∠BHK = ∠MHC = 15°. "
    "Найдите площадь четырёхугольника KLHM.")

PROD_TEXT_LATEX = (
    "В остроугольном треугольнике \\(ABC\\) со стороной \\(AC = 1\\) провели высоту \\(BH\\), "
    "в треугольнике \\(BHC\\) — биссектрису \\(CL\\), в треугольнике \\(BLC\\) — медиану \\(BM\\). "
    "Прямая \\(AL\\) пересекает сторону \\(BC\\) в точке \\(K\\), причём "
    "\\(\\angle BHK = \\angle MHC = 15^\\circ\\). "
    "Найдите площадь четырёхугольника \\(KLHM\\).")

# FORMALIZE_PLAN #2 прод-задания (job 3b5df16f…): медиана построена на BL.
WRONG_MEDIAN_PLAN = {
    "space": "plane",
    "points": ["A", "B", "C", "H", "L", "M", "K"],
    "constructions": [
        {"op": "free_point", "out": "A", "args": [], "value": None},
        {"op": "free_point", "out": "B", "args": [], "value": None},
        {"op": "free_point", "out": "C", "args": [], "value": None},
        {"op": "foot", "out": "H", "args": ["B", "A", "C"], "value": None},
        {"op": "bisector_point", "out": "L", "args": ["C", "H", "B"], "value": None},
        {"op": "midpoint", "out": "M", "args": ["B", "L"], "value": None},
        {"op": "line_intersect", "out": "K", "args": ["A", "L", "B", "C"], "value": None},
    ],
    "constraints": [
        {"type": "dist", "args": ["A", "C"], "value": 1},
        {"type": "angle", "args": ["B", "H", "K"], "value": 15},
        {"type": "angle", "args": ["M", "H", "C"], "value": 15},
        {"type": "on_segment", "args": ["H", "A", "C"], "value": None},
        {"type": "on_segment", "args": ["L", "H", "B"], "value": None},
        {"type": "on_segment", "args": ["M", "B", "L"], "value": None},
        {"type": "on_segment", "args": ["K", "B", "C"], "value": None},
    ],
    "draw": {"segments": [["A", "B"], ["B", "C"], ["A", "C"], ["B", "H"],
                          ["C", "L"], ["B", "M"], ["A", "L"], ["H", "K"], ["M", "H"]]},
    "scale_free": False,
}


def test_engine_suffix():
    assert "+medianFix1" in pipeline.ENGINE_VERSION


def test_median_claims_plain_and_latex():
    assert median_claims(PROD_TEXT) == [("B", "M", "L", "C")]
    assert median_claims(PROD_TEXT_LATEX) == [("B", "M", "L", "C")]


def test_median_claims_ignore_later_triangle():
    # последующее упоминание ABD не перетягивает медиану BM треугольника ABC
    text = ("В треугольнике ABC провели медиану BM, а в треугольнике ABD — "
            "высоту BH. Найдите площадь треугольника ABM.")
    assert median_claims(text) == [("B", "M", "A", "C")]
    # «в треугольнике BLC — медиану BM»: владелец BLC, а не первый ABC
    assert median_claims(PROD_TEXT) == [("B", "M", "L", "C")]


def test_degenerate_policy_parses_bm_not_lc():
    # «в треугольнике BLC — медиану BM» раньше парсилась как «LC — медиана»,
    # и CEVIAN-проверка требовала C быть серединой стороны треугольника.
    cevians = _cevians(PROD_TEXT)
    assert ("медиана", "B", "M") in cevians
    assert ("медиана", "L", "C") not in cevians


def test_repair_rewrites_plan():
    plan = FigurePlan.from_dict(WRONG_MEDIAN_PLAN)
    msg = repair(PROD_TEXT, plan)
    assert msg and "LC" in msg and "BL" in msg
    mid = [c for c in plan.constructions if c.out == "M"][0]
    assert sorted(mid.args) == ["C", "L"]
    onseg = [c for c in plan.constraints if c.type == "on_segment" and c.args[0] == "M"]
    assert onseg and sorted(onseg[0].args[1:]) == ["C", "L"]
    # остальные части плана не тронуты
    assert [c.out for c in plan.constructions] == ["A", "B", "C", "H", "L", "M", "K"]
    assert len(plan.constraints) == 7


def test_repaired_plan_solves_exactly():
    plan = FigurePlan.from_dict(WRONG_MEDIAN_PLAN)
    assert repair(PROD_TEXT, plan)
    sols = solve(plan, n_seeds=24, seed=0)
    good = [s for s in sols if s.ok]
    assert good, [str(getattr(s, "reason", "")) for s in sols[:3]]
    P = {k: np.asarray(v, dtype=float) for k, v in good[0].coords.items()}
    # AC = 1 и оба угла 15°
    assert abs(float(np.hypot(*(P["C"] - P["A"]))) - 1) < 1e-9
    for a, v, b in (("B", "H", "K"), ("M", "H", "C")):
        u, w = P[a] - P[v], P[b] - P[v]
        ang = float(np.degrees(np.arccos(
            float(u @ w) / (np.hypot(*u) * np.hypot(*w)))))
        assert abs(ang - 15) < 1e-6, (a, v, b, ang)
    # M — середина LC
    assert float(np.hypot(*(P["M"] - (P["L"] + P["C"]) / 2))) < 1e-9


def test_semantic_median_check_fires_on_wrong_foot():
    plan = FigurePlan.from_dict(WRONG_MEDIAN_PLAN)
    sols = solve(plan, n_seeds=8, seed=0)
    best = min(sols, key=lambda s: getattr(s, "residual", float("inf")))
    fails = semantics.semantic_failures(PROD_TEXT, plan, best.coords)
    assert any("не середина LC" in f for f in fails)


def test_semantic_checks_pass_on_correct_plan():
    data = dict(WRONG_MEDIAN_PLAN)
    data["constructions"] = list(data["constructions"])
    data["constructions"][5] = {"op": "midpoint", "out": "M", "args": ["L", "C"], "value": None}
    data["constraints"] = list(data["constraints"])
    data["constraints"][5] = {"type": "on_segment", "args": ["M", "L", "C"], "value": None}
    plan = FigurePlan.from_dict(data)
    plan.draw.segments = [["A", "B"], ["B", "C"], ["A", "C"], ["B", "H"],
                          ["C", "L"], ["B", "M"], ["A", "L"], ["H", "K"], ["M", "H"]]
    sols = solve(plan, n_seeds=24, seed=0)
    good = [s for s in sols if s.ok]
    assert good
    fails = semantics.semantic_failures(PROD_TEXT, plan, good[0].coords)
    # биссектриса CL проверяется по владеющему треугольнику BHC (а не первому
    # ABC: раньше была ложная ошибка «CL не является биссектрисой ABC»),
    # медиана BM — по BLC
    assert not any("биссектриса" in f or "медиана" in f for f in fails), fails


@pytest.mark.parametrize("text", [PROD_TEXT, PROD_TEXT_LATEX])
def test_sketch_base_is_triangle_not_question_quad(text):
    # раньше базой наброска выбирался четырёхугольник KLHM из вопроса
    built = sketch_plan(text)
    assert built is not None
    plan, free = built
    assert set("ABC") <= set(plan.points)
    assert all(n in plan.points for n in "KLHM")
    assert ["A", "B"] in [list(s) for s in plan.draw.segments]
    assert ["B", "C"] in [list(s) for s in plan.draw.segments]
    # чевианы условия показаны
    for seg in (("B", "H"), ("C", "L"), ("B", "M"), ("A", "L")):
        assert list(seg) in [list(s) for s in plan.draw.segments], seg


def test_full_pipeline_median_repaired_not_sketch(monkeypatch, tmp_path):
    """Полный конвейер: ошибочный план формализатора (M=midpoint(B,L))
    чинится обёрткой, полная конфигурация (треугольник ABC со всеми
    чевианами) решается и рендерится, а не падает в sketch со схемой
    KLHM. Статус — честный approximate: проверка частного положения
    не отключена и сообщает о равенствах KL=HL, HM=KM.

    HTTP-слой подменён записанным ответом модели: вся цепочка обёрток
    formalize (включая ремонт медианы), валидация, решатель, гейты и
    рендер работают по-настоящему. Это НЕ проверка живого ответа API.
    """
    import json
    from types import SimpleNamespace

    from geoexact.core import llm
    from geoexact.core import pipeline

    monkeypatch.setattr(llm, "classify",
                        lambda *_a, **_k: {"ok": True, "class": "M", "space": "plane"})

    def fake_post(_sess, payload):
        content = json.dumps(WRONG_MEDIAN_PLAN, ensure_ascii=False)
        body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
        return SimpleNamespace(status_code=200, text="", json=lambda: body)

    monkeypatch.setattr(llm, "_post_limited", fake_post)
    result = pipeline.generate(PROD_TEXT, sess=object(), use_cache=False, with_aux=False)
    assert result.ok, (result.stage, result.reason, result.detail)
    # НЕ sketch: полная конфигурация с repaired-медианой доходит до рендера.
    # Статус честный approximate: автоматическая проверка «частного
    # положения» не отключена и сообщает о равенствах KL=HL, HM=KM (они
    # следуют из условия, но распознавание доказанных равенств — отдельная
    # задача, здесь честность важнее статуса).
    assert "sketch" not in result.stage, result.stage
    assert result.verification == "approximate", (result.verification, result.warnings)
    assert any("равны на чертеже" in w for w in result.warnings), result.warnings
    assert result.svg and "svg" in result.svg
    # в итоговом плане медиана уже на правильной стороне
    mid = [c for c in result.plan["constructions"] if c["out"] == "M"][0]
    assert sorted(mid["args"]) == ["C", "L"]
    # чертёж содержит треугольник ABC и чевианы условия (не только KLHM)
    drawn = {tuple(s) for s in result.plan["draw"]["segments"]}
    for seg in (("A", "B"), ("B", "C"), ("A", "C"), ("B", "H"),
                ("A", "L"), ("H", "K"), ("M", "H")):
        assert seg in drawn or seg[::-1] in drawn, seg
