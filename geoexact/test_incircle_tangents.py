"""Касательные из точек прямой AC к вписанной окружности: точный план вместо эскиза."""
import numpy as np
import pytest

from geoexact.core import incircle_tangents as it, llm, semantics
from geoexact.core.constructions import execute
from geoexact.core.semantics import _EXACT_THEOREM, semantic_failures

TEXT = ("В неравнобедренном треугольнике ABC биссектрисы угла ABC и смежного с ним угла "
        "пересекают прямую AC в точках B_1 и B_2 соответственно. Из точек B_1 и B_2 проведены "
        "касательные к вписанной окружности треугольника ABC, отличные от прямой AC, касающиеся "
        "её в точках K_1 и K_2. Докажите, что точки B, K_1 и K_2 лежат на одной прямой.")
LATEX = TEXT.replace("ABC", "$ABC$").replace("B_1", "$B_1$").replace("B_2", "$B_2$") \
            .replace("K_1", "$K_1$").replace("K_2", "$K_2$").replace("AC", "$AC$")


def test_recognize_family_and_latex():
    names = {"A": "A", "C": "C", "B": "B", "B1": "B_1", "B2": "B_2", "K1": "K_1", "K2": "K_2"}
    assert it.recognize(TEXT) == names
    assert it.recognize(LATEX) == names
    assert it.recognize("В треугольнике ABC проведена медиана AM.") is None
    assert it.recognize(_EXACT_THEOREM) is None


@pytest.mark.parametrize("B", [(2.5, 4.0), (1.0, 3.0), (5.5, 2.0)])
def test_exact_plan_builds_true_tangents(B):
    plan = it.incircle_tangents_plan(TEXT, False)
    assert plan is not None
    P = execute(plan, free_values=np.array([0., 0., *B, 7., 0.]))
    I, K = P["I"], P["K"]
    r = np.linalg.norm(K - I)
    for touch, src in (("K_1", "B_1"), ("K_2", "B_2")):
        T, S = P[touch], P[src]
        assert abs(np.linalg.norm(T - I) - r) < 1e-9 * r            # точка на окружности
        assert abs((T - S) @ (T - I)) < 1e-7 * r * r                 # касательная ⟂ радиусу
        assert np.linalg.norm(T - K) > 1e-3 * r                      # не совпадает с K
    # внешняя точка — на прямой AC вне отрезка; внутренняя — внутри
    assert abs(P["B_2"][1]) < 1e-9 and not 0 < P["B_2"][0] < 7
    assert abs(P["B_1"][1]) < 1e-9 and 0 < P["B_1"][0] < 7
    # утверждение задачи выполняется на точном чертеже
    assert abs(np.cross(P["K_1"] - P["B"], P["K_2"] - P["B"])) < 1e-7 * r * r
    assert semantic_failures(TEXT, plan, P) == []


def test_theorem_plan_is_wrapped_and_original_still_works():
    assert getattr(semantics.theorem_plan, "_incircle_tangents", False)
    assert semantics.theorem_plan(TEXT, False) is not None
    assert semantics.theorem_plan(_EXACT_THEOREM, False) is not None
    assert semantics.theorem_plan("Постройте треугольник ABC.", False) is None


def test_rules_appended_once():
    assert it.MARK in llm.SYS_FORMALIZE
    assert llm.SYS_FORMALIZE.count("30. Касательная из точки P") == 1
    if isinstance(getattr(llm, "SYS_AUX", None), str):
        assert it.MARK in llm.SYS_AUX


def test_sketch_reports_original_failure():
    from geoexact.core import pipeline
    assert getattr(pipeline._sketch_result, "_incircle_tangents", False)
    base = pipeline.Result(False, "6-solve", "RESIDUAL_TOO_HIGH", "невязка")
    res = pipeline._sketch_result("В треугольнике ABC проведена вписанная окружность.", False, base)
    if res is not None:
        assert any(w.startswith("FALLBACK_FROM: 6-solve RESIDUAL_TOO_HIGH") for w in res.warnings)


@pytest.mark.parametrize("aux", [False, True])
def test_pipeline_draws_without_llm(aux, monkeypatch):
    from geoexact.core.pipeline import generate
    monkeypatch.setattr(llm, "classify", lambda *_: pytest.fail("точный план не должен звать модель"))
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: pytest.fail("точный план не должен звать модель"))
    r = generate(TEXT, with_aux=aux, sess=object(), use_cache=False)
    assert r.ok, (r.stage, r.reason, r.detail)
    assert r.verification == "constraints_only"
    assert r.usage == []
    assert all(n in r.svg for n in ("B_1", "B_2", "K_1", "K_2"))


PDF_TEXT = ("В неравнобедренном треугольнике ABC провели биссектрисы угла ABC и угла, "
            "смежного с ним. Они пересекли прямую AC в точках B₁ и B₂ соответственно. "
            "Из точек B₁ и B₂ провели касательные к окружности, вписанной в треугольник ABC, "
            "отличные от прямой AC. Они касаются этой окружности в точках K₁ и K₂ "
            "соответственно. Докажите, что точки B, K₁ и K₂ лежат на одной прямой.")


def test_pdf_wording_is_recognized():
    """Оригинал задачи 15.3.4: другой порядок слов, два предложения, B₁ юникодом."""
    assert it.recognize(PDF_TEXT) == {"A": "A", "C": "C", "B": "B", "B1": "B_1",
                                      "B2": "B_2", "K1": "K_1", "K2": "K_2"}
    assert it._plain("K₁ и K₂") == "K_1 и K_2"


@pytest.mark.parametrize("aux", [False, True])
def test_pipeline_draws_pdf_wording_without_llm(aux, monkeypatch):
    from geoexact.core.pipeline import generate
    monkeypatch.setattr(llm, "classify", lambda *_: pytest.fail("точный план не должен звать модель"))
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: pytest.fail("точный план не должен звать модель"))
    r = generate(PDF_TEXT, with_aux=aux, sess=object(), use_cache=False)
    assert r.ok, (r.stage, r.reason, r.detail)
    assert r.verification == "constraints_only"
    assert r.usage == []
