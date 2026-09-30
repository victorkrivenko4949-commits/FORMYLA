"""The auxiliary layer: deterministic trapezoid rule, model steps, and validation."""
import copy

import numpy as np
import pytest

from geoexact.core import auxplan, llm
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve

TRAP = ("В трапеции ABCD основания AD и BC. Диагонали AC = 6 и BD = 8, средняя линия равна 5.\n\n"
        "Найдите:\n\n1. Угол между диагоналями.\n\n2. Площадь трапеции.\n\n3. Высоту трапеции.")


def trap_plan(with_mid_aux=True):
    return FigurePlan.from_dict({
        "points": list("ABCDMN"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABCD"] + [
            {"op": "midpoint", "out": "M", "args": ["A", "B"]},
            {"op": "midpoint", "out": "N", "args": ["C", "D"]}],
        "constraints": [{"type": "parallel", "args": ["A", "D", "B", "C"]},
                        {"type": "dist", "args": ["A", "C"], "value": 6},
                        {"type": "dist", "args": ["B", "D"], "value": 8},
                        {"type": "dist", "args": ["M", "N"], "value": 5}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"], ["A", "C"], ["B", "D"]],
                 "aux_segments": [["M", "N"]] if with_mid_aux else []},
        "scale_free": True})


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})

    def set_plan(plan, aux=None):
        monkeypatch.setattr(llm, "formalize", lambda *_, **__: (copy.deepcopy(plan), []))
        if aux is None:
            def fail(*_, **__):
                raise AssertionError("the model must not be asked here")
            monkeypatch.setattr(llm, "aux_plan", fail)
        else:
            monkeypatch.setattr(llm, "aux_plan", lambda *_, **__: aux)
    return set_plan


def solved(plan_dict):
    plan = FigurePlan.from_dict(plan_dict)
    sol = next(s for s in solve(plan, n_seeds=6) if s.ok)
    return {k: np.asarray(v, float) for k, v in sol.coords.items()}


def test_trapezoid_diagonal_is_translated_even_if_model_drew_only_midline(model):
    model(trap_plan())
    r = generate(TRAP, True, sess=object(), use_cache=False)
    assert r.ok and r.verification == "constraints_only"
    d = r.plan["draw"]
    assert ["C", "E"] in d["aux_segments"] and ["D", "E"] in d["aux_segments"]
    P = solved(r.plan)
    cross = lambda u, v: u[0] * v[1] - u[1] * v[0]
    assert abs(cross(P["E"] - P["A"], P["D"] - P["A"])) < 1e-8         # E on line AD
    assert np.allclose(P["E"], P["D"] + (P["C"] - P["B"]))             # BD moved by BC
    assert np.linalg.norm(P["C"] - P["E"]) == pytest.approx(np.linalg.norm(P["B"] - P["D"]))
    # данные длины подписаны, равенство перенесённой диагонали — той же цифрой
    labels = {frozenset(m["pts"]): m["text"] for m in d["length_marks"]}
    assert labels[frozenset("AC")] == "6" and labels[frozenset("BD")] == "8"
    assert labels[frozenset("CE")] == labels[frozenset("BD")] == "8"
    assert r.plan["notes"] == "" or "диагонал" in r.plan["notes"].lower()


def test_trapezoid_rule_absent_in_plain_mode(model):
    model(trap_plan(False))
    r = generate(TRAP, False, sess=object(), use_cache=False)
    assert "E" not in r.plan["points"]


def test_trapezoid_bases_ab_cd_are_rotated():
    plan = trap_plan()
    text = "В трапеции ABCD основания AB и CD. Диагонали AC = 6 и BD = 8."
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([3., 2.]),
              "D": np.array([1., 2.]), "M": np.array([2., 0.]), "N": np.array([2., 2.])}
    data = auxplan.trapezoid_diagonals(plan, coords, text)
    step = data["steps"][0]
    assert step["op"] == "translate" and step["args"] == ["A", "C", "D"]      # bases BA and CD
    plan2, out = auxplan.apply_aux(plan, coords, data)
    assert np.allclose(out["E"], [-1., 0.]) or np.allclose(out["E"], coords["A"] + coords["D"] - coords["C"])


def test_model_steps_median_doubling(model):
    plan = FigurePlan.from_dict({
        "points": list("ABCM"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"] + [
            {"op": "midpoint", "out": "M", "args": ["B", "C"]}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 5},
                        {"type": "dist", "args": ["A", "C"], "value": 7},
                        {"type": "dist", "args": ["A", "M"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"]]}, "scale_free": True})
    aux = {"idea": "Удвоение медианы", "steps": [{"op": "reflect_point", "out": "D", "args": ["A", "M"]}],
           "aux_segments": [["B", "D"], ["C", "D"]]}      # the model forgot the segment MD
    model(plan, aux)
    r = generate("В треугольнике ABC AB = 5, AC = 7, медиана AM = 4. Найдите BC.", True,
                 sess=object(), use_cache=False)
    d = r.plan["draw"]
    assert ["M", "D"] in d["aux_segments"]                # the continuation is added
    P = solved(r.plan)
    assert np.allclose(P["D"], 2 * P["M"] - P["A"])
    assert np.allclose(P["A"] + P["D"], P["B"] + P["C"])  # ABDC is a parallelogram
    labels = {frozenset(m["pts"]): m["text"] for m in d["length_marks"] if "text" in m}
    assert labels.get(frozenset("MD")) == labels.get(frozenset("AM"))     # same length label


@pytest.mark.parametrize("bad", [
    None, "text", [], {}, {"steps": []}, {"steps": "x"},
    {"steps": [{"op": "midpoint", "out": "D", "args": ["A"]}]},                       # arity
    {"steps": [{"op": "eval", "out": "D", "args": ["A", "B"]}]},                      # unknown op
    {"steps": [{"op": "midpoint", "out": "A", "args": ["B", "C"]}]},                  # name taken
    {"steps": [{"op": "midpoint", "out": "d", "args": ["B", "C"]}]},                  # bad name
    {"steps": [{"op": "midpoint", "out": "D", "args": ["B", "Z"]}]},                  # unknown point
    {"steps": [{"op": "midpoint", "out": "D", "args": ["B", "C"]}]},                  # no primitives
    {"steps": [{"op": "midpoint", "out": "D", "args": ["A", "A"]}], "aux_segments": [["A", "D"]]},
    {"steps": [{"op": "divide_segment", "out": "D", "args": ["A", "B"], "value": "x"}],
     "aux_segments": [["A", "D"]]},
    {"steps": [{"op": "divide_segment", "out": "D", "args": ["A", "B"], "value": 1e9}],
     "aux_segments": [["A", "D"]]},
    {"steps": [{"op": "divide_segment", "out": "D", "args": ["A", "B"], "value": float("nan")}],
     "aux_segments": [["A", "D"]]},
    {"steps": [{"op": "homothety", "out": "D", "args": ["A", "B"], "value": 4}],
     "aux_segments": [["A", "D"]]},                                                    # far away
    {"steps": [{"op": "line_intersect", "out": "D", "args": ["A", "B", "A", "B"]}],
     "aux_segments": [["A", "D"]]},                                                    # parallel
    {"steps": [{"op": "midpoint", "out": f"P{i}", "args": ["A", "B"]} for i in range(9)],
     "aux_segments": [["A", "P1"]]},                                                   # too many
    {"steps": [{"op": "midpoint", "out": "D", "args": ["D", "B"]}], "aux_segments": [["B", "D"]]},
])
def test_invalid_aux_data_is_rejected(bad):
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([1., 3.])}
    plan = FigurePlan.from_dict({"points": list("ABC"),
                                 "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
                                 "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
                                 "scale_free": True})
    assert auxplan.apply_aux(plan, coords, bad) is None


def test_coincident_point_is_rejected():
    """A fully degenerate construction (reflect A about A) still adds nothing:
    the aliased point drops out and no new line remains."""
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([1., 3.])}
    plan = FigurePlan.from_dict({"points": list("ABC"),
                                 "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
                                 "draw": {"segments": [["A", "B"]]}, "scale_free": True})
    same = {"steps": [{"op": "reflect_point", "out": "D", "args": ["A", "A"]}],
            "aux_segments": [["A", "D"]]}
    why: list = []
    assert auxplan.apply_aux(plan, coords, same, why) is None
    assert any("уже есть на чертеже" in w for w in why)


def _midpoint_figure():
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([2., 3.]),
              "M": np.array([2., 0.])}      # M — already the midpoint of AB
    plan = FigurePlan.from_dict({
        "points": list("ABCM"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"]
        + [{"op": "midpoint", "out": "M", "args": ["A", "B"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]}, "scale_free": True})
    return plan, coords


def test_construction_landing_on_an_existing_point_uses_it():
    """The model re-derives a point the figure already has (K = midpoint AB = M):
    the existing point is used and the rest of the construction is drawn."""
    plan, coords = _midpoint_figure()
    data = {"idea": "медиана из C", "steps": [
        {"op": "midpoint", "out": "K", "args": ["A", "B"]}],
        "aux_segments": [["C", "K"]]}
    out = auxplan.apply_aux(plan, coords, data)
    assert out is not None
    new_plan, new_coords = out
    assert ["C", "M"] in [list(s) for s in new_plan.draw.aux_segments]
    assert "K" not in new_coords and "K" not in new_plan.points
    assert data["_alias"] == {"K": "M"}


def test_taken_name_that_rebuilds_the_same_point_is_accepted():
    """out = an existing point's name, and the construction gives exactly it."""
    plan, coords = _midpoint_figure()
    data = {"idea": "медиана из C", "steps": [
        {"op": "midpoint", "out": "M", "args": ["A", "B"]}],
        "aux_segments": [["C", "M"]]}
    out = auxplan.apply_aux(plan, coords, data)
    assert out is not None
    new_plan, new_coords = out
    assert ["C", "M"] in [list(s) for s in new_plan.draw.aux_segments]
    assert set(new_coords) == set(coords)          # no point was added


def test_taken_name_at_another_place_is_still_rejected():
    plan, coords = _midpoint_figure()
    data = {"steps": [{"op": "midpoint", "out": "C", "args": ["A", "B"]}],
            "aux_segments": [["A", "C"]]}
    why: list = []
    assert auxplan.apply_aux(plan, coords, data, why) is None
    assert any("занято" in w for w in why)


def test_alias_feeds_later_steps_and_lists():
    """A later step and aux list refer to the aliased name: they resolve to the
    existing point, not to a missing one."""
    plan, coords = _midpoint_figure()
    data = {"steps": [
        {"op": "midpoint", "out": "K", "args": ["A", "B"]},
        {"op": "translate", "out": "G", "args": ["K", "B", "C"]}],    # G = K + (C-B)
        "aux_segments": [["C", "K"], ["C", "G"]]}
    out = auxplan.apply_aux(plan, coords, data)
    assert out is not None
    new_plan, new_coords = out
    assert ["C", "M"] in [list(s) for s in new_plan.draw.aux_segments]
    assert "G" in new_coords and data["_alias"] == {"K": "M"}


def test_statement_points_extracts_figure_letters():
    assert auxplan.statement_points("В треугольнике ABC проведена медиана AM.") == list("ABCM")
    assert auxplan.statement_points("В трапеции ABCD основания AD и BC.") == list("ABCD")
    assert auxplan.statement_points("") == []


@pytest.mark.parametrize("failure", [
    lambda *_, **__: (_ for _ in ()).throw(llm.PlanError("NETWORK_UNCERTAIN", "нет")),
    lambda *_, **__: (_ for _ in ()).throw(RuntimeError("boom")),
    lambda *_, **__: "not json",
    lambda *_, **__: {"steps": [{"op": "eval"}]},
])
def test_planner_failure_keeps_main_figure(monkeypatch, failure):
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    plan = FigurePlan.from_dict({
        "points": list("ABC"), "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 5},
                        {"type": "dist", "args": ["B", "C"], "value": 6},
                        {"type": "dist", "args": ["A", "C"], "value": 7}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]}, "scale_free": True})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (plan, []))
    monkeypatch.setattr(llm, "aux_plan", failure)
    r = generate("Треугольник ABC со сторонами 5, 6, 7.", True, sess=object(), use_cache=False)
    assert r.ok and r.verification == "constraints_only" and r.plan["draw"]["aux_segments"] == []


def test_planner_not_called_in_plain_mode_but_always_asked_with_aux(monkeypatch, model):
    calls = []
    plan = trap_plan(True)
    model(plan, None)
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: calls.append(k.get("deep")) or {})
    generate("Треугольник ABC со сторонами 5, 6, 7.", False, sess=object(), use_cache=False)
    assert calls == []
    generate("Дана трапеция ABCD, MN — средняя линия.", True, sess=object(), use_cache=False)
    # even when the figure already has auxiliary lines, the model decides
    assert len(calls) == 1


def test_collapsed_model_drawing_falls_back_to_sketch_with_construction(model):
    plan = trap_plan()
    plan.constraints.extend(FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"], "constructions": [],
        "constraints": [{"type": "on_segment", "args": ["B", "A", "D"]},
                        {"type": "on_segment", "args": ["C", "B", "C"]}]}).constraints)
    model(plan, None)                    # request failed: the classical rule is the fallback
    r = generate(TRAP, True, sess=object(), use_cache=False)
    assert r.ok
    d = r.plan["draw"]
    if r.verification == "sketch":
        assert {frozenset(s) for s in d["segments"]} >= {frozenset("AC"), frozenset("BD")}
        assert "E" in r.plan["points"]
        ticks = {frozenset(m["pts"]) for m in d["equal_marks"]}
        assert {frozenset("BD"), frozenset("CE")} <= ticks


def test_sketch_draws_both_named_diagonals():
    from geoexact.core.sketch import sketch_plan
    plan, _ = sketch_plan(TRAP)
    segs = {frozenset(s) for s in plan.draw.segments}
    assert frozenset("AC") in segs and frozenset("BD") in segs


def _bare_triangle(notes):
    return FigurePlan.from_dict({
        "points": list("ABC"), "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 5},
                        {"type": "dist", "args": ["B", "C"], "value": 6},
                        {"type": "dist", "args": ["A", "C"], "value": 7}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]}, "scale_free": True,
        "notes": notes})


def test_text_never_claims_a_construction_that_is_not_drawn(monkeypatch, model):
    model(_bare_triangle("Проведём через C прямую, параллельную AB, и продолжим сторону BA."),
          {"idea": "", "steps": []})
    r = generate("Треугольник ABC со сторонами 5, 6, 7.", True, sess=object(), use_cache=False)
    assert r.ok and r.plan["notes"] == "" and "параллельную" not in r.svg
    assert not r.plan["draw"]["aux_segments"]


def test_model_answer_is_drawn_and_text_matches_drawing(monkeypatch, model):
    seen = {}
    aux = {"idea": "Прямая через C параллельно AB", "steps": [
        {"op": "parallel_point", "out": "P", "args": ["C", "A", "B"], "value": 1.0}],
        "aux_segments": [["C", "P"]]}
    model(_bare_triangle("Проведём через C прямую, параллельную AB."))

    def planner(sess, text, figure, budget, deep=True):
        seen["figure"] = figure
        return aux
    monkeypatch.setattr(llm, "aux_plan", planner)
    r = generate("Треугольник ABC со сторонами 5, 6, 7.", True, sess=object(), use_cache=False)
    assert "имена точек из условия" in seen["figure"]
    assert ["C", "P"] in r.plan["draw"]["aux_segments"]
    assert r.plan["notes"] == "Прямая через C параллельно AB"


def test_builtin_theorem_gets_its_auxiliary_from_the_model_not_from_code(monkeypatch):
    """The hand-written figure stays, but its fixed auxiliary lines are not drawn."""
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    monkeypatch.setattr(llm, "classify", lambda *_: (_ for _ in ()).throw(AssertionError))
    answers = {"idea": "Средняя линия", "steps": [
        {"op": "midpoint", "out": "N", "args": ["B", "F"]}],
        "aux_segments": [["D", "N"]]}
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: answers)
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    segs = {frozenset(s) for s in r.plan["draw"]["aux_segments"]}
    assert frozenset("BM") not in segs and frozenset("DF") not in segs
    assert frozenset("DN") in segs


def test_builtin_theorem_model_says_nothing_to_add(monkeypatch):
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {"idea": "", "steps": []})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    assert r.plan["draw"]["aux_segments"] == []


def test_claims_hold_rejects_words_that_contradict_the_drawing():
    from geoexact.core.auxplan import claims_hold
    c = {"B": (0, 0), "D": (1, 0), "G": (3, 0), "C": (0, 4), "E": (1, 4)}
    assert claims_hold("Продлить так, что DG = BD", {**c, "G": (2, 0)})
    assert not claims_hold("Продлить так, что DG = BD", c)          # DG = 2, BD = 1
    assert claims_hold("CE ∥ BD", c) and not claims_hold("CG ∥ BD", c)
    assert claims_hold("точка Q такая, что PQ = AB", c)              # unknown points ignored
    assert claims_hold("", c) and claims_hold(None, c)


def test_production_worker_path_starts_model_request_without_session(monkeypatch):
    """The web worker calls generate() without sess; the model must still be asked."""
    from geoexact.core import pipeline
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    calls = []
    monkeypatch.setattr(llm, "make_session", lambda: object())
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: calls.append(k.get("deep")) or
                        {"idea": "", "steps": []})
    r = generate(_PARALLELOGRAM_PROOF, True, use_cache=False)
    assert r.ok and len(calls) == 1


def test_drawing_that_contradicts_the_models_words_is_not_shown(monkeypatch):
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {
        "idea": "Продлить CD за D до G так, что DG = BD", "steps": [
            {"op": "divide_segment", "out": "G", "args": ["C", "D"], "value": 2}],
        "aux_segments": [["B", "G"]]})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    assert r.plan["draw"]["aux_segments"] == [] and "G" not in r.plan["points"]


def _bce_expert(monkeypatch, text, data):
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: text)
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: {**data, "_expert_text": text})
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {"idea": "", "steps": []})


BCE_STEPS = {"idea": "Через D параллельно AC до K на BC; тогда BK = BD.", "steps": [
    {"op": "parallel_point", "out": "K", "args": ["D", "A", "C"], "value": 1.0}],
    "aux_segments": [["D", "K"], ["K", "B"]]}


def test_expert_answer_is_drawn_when_it_survives_the_checks(monkeypatch):
    """Gemini's construction for BE = BF: K on BC with DK ∥ AC (proof: BKE = CBF)."""
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    _bce_expert(monkeypatch, "Продлить ED до K на BC, DK ∥ AC. Тогда BK = BD и KE = BC.",
                {"idea": "K на BC, DK ∥ AC", "steps": [
                    {"op": "line_intersect", "out": "K", "args": ["D", "K0", "B", "C"]}]})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    # whatever the steps do, an unusable answer must not break the drawing
    assert r.ok


def test_expert_words_that_contradict_the_drawing_are_rejected(monkeypatch):
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF
    _bce_expert(monkeypatch, "Отложим G так, что DG = BD.", {
        "idea": "G", "steps": [{"op": "divide_segment", "out": "G", "args": ["C", "D"], "value": 2}],
        "aux_segments": [["B", "G"]]})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    assert r.plan["draw"]["aux_segments"] == []


def test_expert_without_key_falls_back_to_quick_answer(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import pytest as _pt
    with _pt.raises(llm.PlanError):
        llm.expert_text(object(), "задача")


def test_expert_stream_is_parsed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    class R:
        status_code = 200

        def iter_lines(self, decode_unicode=True, chunk_size=512):
            yield 'data: {"choices":[{"delta":{"content":"Провести "}}]}'
            yield ""
            yield 'data: {"choices":[{"delta":{"content":"BE"},"finish_reason":"stop"}]}'
            yield "data: [DONE]"

    class S:
        def post(self, url, **kw):
            assert kw["stream"] is True and kw["json"]["model"] == llm.EXPERT_MODEL
            assert kw["headers"]["Authorization"] == "Bearer k"
            return R()
    assert llm.expert_text(S(), "задача") == "Провести BE"


def test_parallel_intersect_and_stray_value_are_normalised():
    from geoexact.core.auxplan import apply_aux
    from geoexact.core.semantics import _PARALLELOGRAM_PROOF, proof_parallelogram_plan
    plan = proof_parallelogram_plan(_PARALLELOGRAM_PROOF, False)
    coords = {k: np.asarray(v, float) for k, v in
              next(s for s in solve(plan, n_seeds=6) if s.ok).coords.items()}
    data = {"idea": "Через D параллельно AC до K на BC: BK = BD, KD = KC.", "steps": [
        {"op": "parallel_intersect", "out": "K", "args": ["D", "A", "C", "B", "C"]}],
        "aux_segments": [["D", "K"], ["E", "K"], ["B", "K"]]}
    got = apply_aux(plan, coords, data)
    assert got is not None
    new_plan, new = got
    n = np.linalg.norm
    assert abs(n(new["B"] - new["K"]) - n(new["B"] - new["D"])) < 1e-9        # BK = BD
    assert abs(n(new["K"] - new["D"]) - n(new["K"] - new["C"])) < 1e-9        # KD = KC
    assert abs(n(new["K"] - new["E"]) - n(new["B"] - new["C"])) < 1e-9        # KE = BC
    from geoexact.core.auxplan import claims_hold
    assert claims_hold(data["idea"] + " KE = BC", new)
    # a numeric last argument is the value, not a point
    assert apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "parallel_point", "out": "P", "args": ["D", "A", "C", 1]}],
        "aux_segments": [["D", "P"]]}) is not None


def test_expert_accepts_the_odirouter_key_name(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ODIROUTER_API_KEY", "odi")
    seen = {}

    class R:
        status_code = 200

        def iter_lines(self, decode_unicode=True, chunk_size=512):
            yield 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'

    class S:
        def post(self, url, **kw):
            seen.update(url=url, auth=kw["headers"]["Authorization"])
            return R()
    assert llm.expert_text(S(), "задача") == "ok"
    assert seen["auth"] == "Bearer odi" and seen["url"].endswith("/chat/completions")
