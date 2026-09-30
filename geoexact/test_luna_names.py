"""Имена точек из ответа Луны обязаны попадать в шаги и на чертёж."""
import numpy as np
import pytest

from geoexact.core import auxplan
from geoexact.core.pipeline import _stale_missing_point
from geoexact.core.schema import FigurePlan


def base_plan():
    return FigurePlan.from_dict({
        "points": list("ABCM"),
        "constructions": [{"op": "free_point", "out": c} for c in "ABC"] + [
            {"op": "midpoint", "out": "M", "args": ["A", "C"]}],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["A", "C"], ["B", "M"]]},
        "scale_free": True})


COORDS = {"A": np.array([0., 0.]), "B": np.array([1., 2.]),
          "C": np.array([4., 0.]), "M": np.array([2., 0.])}


def test_introduced_names_from_luna_text():
    text = ("Продлим медиану BM за точку M на её длину до точки N. "
            "Обозначим также точку пересечения P. Пусть Q — середина AN, "
            "получим точки K и L, отметим R.")
    # M упомянута как «точка M», но существующие точки отсеиваются в apply_aux
    assert auxplan.introduced_names(text) == {"M", "N", "P", "Q", "K", "L", "R"}


def test_existing_and_pair_names_are_not_introductions():
    text = "В треугольнике ABC медиана BM равна высоте AH, AN ∥ BC, ABNC — параллелограмм."
    assert auxplan.introduced_names(text) == set()


def test_step_must_build_the_point_luna_named():
    why = []
    data = {"idea": "Удвоение медианы.", "steps": [
        {"op": "reflect_point", "out": "E", "args": ["B", "M"]}],
        "aux_segments": [["B", "E"]],
        "_expert_text": "Продлим медиану BM за точку M на её длину до точки N."}
    assert auxplan.apply_aux(base_plan(), COORDS, data, why) is None
    assert any("N" in w and "не построена" in w for w in why)


def test_same_step_with_lunas_name_is_accepted():
    data = {"idea": "Удвоение медианы.", "steps": [
        {"op": "reflect_point", "out": "N", "args": ["B", "M"]}],
        "aux_segments": [["B", "N"]],
        "_expert_text": "Продлим медиану BM за точку M на её длину до точки N."}
    plan, coords = auxplan.apply_aux(base_plan(), COORDS, data)
    assert "N" in coords and ["B", "N"] in plan.draw.aux_segments


def test_no_expert_text_means_no_name_requirement():
    data = {"idea": "Удвоение медианы.", "steps": [
        {"op": "reflect_point", "out": "E", "args": ["B", "M"]}],
        "aux_segments": [["B", "E"]]}
    plan, coords = auxplan.apply_aux(base_plan(), COORDS, data)
    assert "E" in coords


def test_stale_missing_point_warning():
    class P:
        points = ["A", "B", "C", "M", "N"]
    gone = "на чертеже нет точки N, названной в условии"
    keep = "на чертеже нет точки K, названной в условии"
    other = "заданное отношение не выполняется"
    assert _stale_missing_point(gone, P()) is True
    assert _stale_missing_point(keep, P()) is False
    assert _stale_missing_point(other, P()) is False
