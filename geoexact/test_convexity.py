"""Выпуклость названных многоугольников: невыпуклый чертёж не бывает «verified»."""
import numpy as np
import pytest

from geoexact.core import convexity, llm, semantics
from geoexact.core.schema import Constraint, FigurePlan

TEXT = ("Дан выпуклый четырёхугольник ABCD, в котором ∠DAB = 90°. Пусть M — середина "
        "стороны BC. Оказалось, что ∠ADC = ∠BAM. Докажите, что ∠ADB = ∠CAM.")
# Чертёж, который движок выдал до исправления: C выше AB, D ниже — угол при B > 180°.
BAD = {"A": (100., 490.), "B": (350., 490.), "C": (645., 80.), "D": (100., 1125.), "M": (497.5, 285.)}
GOOD = {"A": (0., 0.), "B": (2., 0.), "C": (1., 3.), "D": (0., 4.), "M": (1.5, 1.5)}


def quad_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "M"],
        "constructions": [*({"op": "free_point", "out": p} for p in "ABCD"),
                          {"op": "midpoint", "out": "M", "args": ["B", "C"]}],
        "constraints": [{"type": "angle", "args": ["D", "A", "B"], "value": 90},
                        {"type": "angle_eq", "args": ["A", "D", "C", "B", "A", "M"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"], ["A", "M"]],
                 "right_angles": [["D", "A", "B"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def _np(d):
    return {k: np.array(v, dtype=float) for k, v in d.items()}


def test_text_recognizes_convex_polygons():
    assert convexity.convex_polygons(TEXT) == [("A", "B", "C", "D")]
    assert convexity.convex_polygons("В выпуклом пятиугольнике ABCDE") == [("A", "B", "C", "D", "E")]
    assert convexity.convex_polygons("Постройте ромб ABCD, в котором угол A равен 60°.") == [("A", "B", "C", "D")]
    assert convexity.convex_polygons("В треугольнике ABC проведена медиана AM.") == []
    # «четырёхугольник CDEF — параллелограмм» намеренно не распознаётся (узость)
    assert convexity.convex_polygons("четырёхугольник CDEF — параллелограмм") == []


def test_nonconvex_drawing_is_rejected_with_vertex():
    fails = convexity.convexity_failures(TEXT, quad_plan(), _np(BAD))
    assert len(fails) == 1 and fails[0].startswith(convexity.PREFIX)
    assert "при B" in fails[0]


def test_convex_drawing_passes():
    assert convexity.convexity_failures(TEXT, quad_plan(), _np(GOOD)) == []


def test_missing_vertices_are_left_to_statement_checks():
    coords = {k: v for k, v in _np(BAD).items() if k != "D"}
    assert convexity.convexity_failures(TEXT, quad_plan(), coords) == []


def test_semantic_failures_is_wrapped():
    assert getattr(semantics.semantic_failures, "_convexity", False)
    assert any(f.startswith(convexity.PREFIX)
               for f in semantics.semantic_failures(TEXT, quad_plan(), _np(BAD)))
    assert not any(f.startswith(convexity.PREFIX)
                   for f in semantics.semantic_failures(TEXT, quad_plan(), _np(GOOD)))


def test_injection_is_idempotent_and_only_for_quads():
    plan = quad_plan()
    extra = convexity.convexity_constraints(TEXT, plan)
    assert {tuple(c["args"]) for c in extra} == {("A", "C", "B", "D"), ("B", "D", "A", "C")}
    plan.constraints.extend(Constraint(**c) for c in extra)
    assert convexity.convexity_constraints(TEXT, plan) == []
    assert convexity.convexity_constraints("В выпуклом пятиугольнике ABCDE", plan) == []


def test_formalize_wrapper_adds_constraints_and_warning():
    assert getattr(llm.formalize, "_convexity", False)
    wrapped = convexity._wrap_formalize(lambda *a, **k: (quad_plan(), ["W0"]))
    plan, warn = wrapped(object(), TEXT, "M", False, llm.Budget())
    assert len(plan.constraints) == 4
    assert warn[0] == "W0" and any(w.startswith("CONVEXITY_INJECTED") for w in warn)
    # ошибки модели проходят насквозь
    def boom(*a, **k):
        raise RuntimeError("model")
    with pytest.raises(RuntimeError):
        convexity._wrap_formalize(boom)(object(), TEXT, "M", False, llm.Budget())


def test_injected_constraints_separate_good_from_bad():
    from geoexact.core.gates import constraint_residual
    plan = quad_plan()
    plan.constraints.extend(Constraint(**c) for c in convexity.convexity_constraints(TEXT, plan))
    for coords, ok in ((_np(GOOD), True), (_np(BAD), False)):
        res = [constraint_residual(c.type, [coords[a] for a in c.args], c.value, 1.0)
               for c in plan.constraints if c.type == "opposite_side"]
        assert (max(res) == 0.0) is ok


def test_pipeline_never_reports_nonconvex_as_verified(monkeypatch):
    from geoexact.core.pipeline import generate
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    # модель «забыла» opposite_side; обёртка формализатора при monkeypatch обойдена,
    # поэтому проверяется именно семантический гейт
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (quad_plan(), []))
    r = generate(TEXT, sess=object(), use_cache=False, max_retries=0)
    assert r.ok
    flagged = any(w.startswith(convexity.PREFIX) or convexity.PREFIX in w for w in r.warnings)
    if flagged:
        assert r.verification == "approximate"
    else:
        assert r.verification == "constraints_only"


def test_cache_key_changes_with_engine_suffix():
    from geoexact.core import pipeline
    assert convexity.CACHE_SUFFIX in pipeline.ENGINE_VERSION
