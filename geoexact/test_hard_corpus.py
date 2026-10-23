"""Hard, varied inputs: the drawing must appear and every recognised relation
must hold exactly on it, whatever the model does.

* a corpus of 40 school/olympiad wordings (LaTeX, OCR, A1/A_1 names, Δ,
  circles, tangents, extensions, midlines...) drawn while the model refuses;
* exact geometric invariants checked on the sketch coordinates;
* noise and random fuzz never crash and never produce broken SVG;
* corrupted model plans (wrong values, dropped points, NaN, garbage objects,
  unexpected exceptions) degrade to an honestly labelled drawing;
* correct plans for ratio/expression wordings are not flagged as mismatched.
"""
import math
import random
import xml.dom.minidom

import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.constructions import execute
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan, PlanError
from geoexact.core.sketch import sketch_plan

HARD = {
    "latex_ratio": (r"В треугольнике $ABC$ на стороне $BC$ взята точка $D$, причём $BD:DC=2:5$. "
                    r"Точка $E$ лежит на стороне $AB$, $AE:EB = 3:1$. Отрезки $AD$ и $CE$ "
                    r"пересекаются в точке $P$. Найдите $AP:PD$.", "ABCDEP"),
    "latex_right": (r"В треугольнике \(ABC\) \(\angle C = 90^\circ\), \(CH\) — высота, "
                    r"\(AC = 6\), \(BC = 8\). Найдите \(CH\).", "ABCH"),
    "delta_medians": ("В ΔABC медианы AA1, BB1 и CC1 пересекаются в точке M. "
                      "Докажите, что AM : MA1 = 2 : 1.", ["A1", "B1", "C1", "M"]),
    "subscript_bisectors": ("В треугольнике ABC проведены биссектрисы AA_1 и BB_1, пересекающиеся "
                            "в точке I. Найдите угол AIB, если угол C = 70°.", ["A_1", "B_1", "I"]),
    "two_midpoints": ("Точки K и L — середины сторон AB и BC треугольника ABC соответственно. "
                      "Докажите, что KL ∥ AC.", "KL"),
    "parallelogram_cevian": ("В параллелограмме ABCD точка M — середина стороны BC, отрезок AM "
                             "пересекает диагональ BD в точке K. Найдите BK : KD.", "MK"),
    "trapezoid_diagonals": ("В трапеции ABCD (AD ∥ BC) AD = 12, BC = 4. Диагонали AC и BD "
                            "пересекаются в точке O. Найдите AO : OC.", "O"),
    "rhombus": ("Диагонали ромба ABCD равны 10 и 24. Найдите сторону ромба.", "ABCD"),
    "square_points": ("В квадрате ABCD точка E — середина стороны CD, точка F лежит на стороне BC "
                      "так, что BF : FC = 1 : 3. Найдите угол AEF.", "EF"),
    "rectangle_point": ("Прямоугольник ABCD, AB = 6, AD = 8. Точка M на стороне AD, AM = 2. "
                        "Найдите BM.", "M"),
    "circumcircle": ("Около треугольника ABC описана окружность с центром O. ∠A = 50°, ∠B = 60°. "
                     "Найдите ∠BOC.", "O"),
    "incircle": ("В треугольник ABC вписана окружность с центром I, касающаяся стороны BC в "
                 "точке K. AB = 7, BC = 8, AC = 9.", "IK"),
    "chords": ("Хорды AB и CD окружности пересекаются в точке E, AE = 4, EB = 6, CE = 3. "
               "Найдите ED.", "ABCDE"),
    "tangent_circles": ("Две окружности с центрами O1 и O2 радиусов 3 и 5 касаются внешним "
                        "образом. Найдите O1O2.", ["O1", "O2"]),
    "tangents": ("Из точки M к окружности с центром O проведены касательные MA и MB. "
                 "∠AMB = 60°.", "MOAB"),
    "hexagon": ("Правильный шестиугольник ABCDEF со стороной 4. Найдите диагональ AD.", "ABCDEF"),
    "quad_diagonals": ("В выпуклом четырёхугольнике ABCD диагонали AC и BD пересекаются в точке O, "
                       "AO = 3, OC = 6, BO = 2, OD = 4.", "O"),
    "isosceles_height": ("В равнобедренном треугольнике ABC с основанием AC проведена высота BH. "
                         "AB = 13, AC = 10. Найдите BH.", "H"),
    "equilateral_mid": ("В равностороннем треугольнике ABC со стороной 6 точка M — середина AB. "
                        "Найдите CM.", "M"),
    "three_cevians": ("В прямоугольном треугольнике ABC (∠C = 90°) CM — медиана, CH — высота, "
                      "CL — биссектриса.", "MHL"),
    "angle_bisector_ray": ("Дан угол AOB, равный 120°. Луч OC — биссектриса угла AOB.", "AOBC"),
    "segment_ratio": ("Отрезок AB = 10, точка C делит его в отношении AC : CB = 3 : 2.", "ABC"),
    "extension": ("На продолжении стороны AB треугольника ABC за точку B взята точка D так, "
                  "что BD = AB.", "D"),
    "cyclic_pentagon": ("Пятиугольник ABCDE вписан в окружность.", "ABCDEO"),
    "lowercase": ("треугольник abc, найдите площадь", "ABC"),
    "unnamed_triangle": ("Найдите площадь треугольника со сторонами 13, 14 и 15.", "ABC"),
    "equilateral_by_equalities": ("В треугольнике ABC AB = BC = CA = 2. Точка O — центр "
                                  "треугольника.", "O"),
    "cevians_through_point": ("Точка M лежит внутри треугольника ABC. Прямые AM, BM, CM "
                              "пересекают стороны BC, CA, AB в точках A1, B1, C1.",
                              ["M", "A1", "B1", "C1"]),
    "cyclic_quad": ("В четырехугольнике ABCD углы A и C прямые. Докажите, что точки A, B, C, D "
                    "лежат на одной окружности.", "ABCD"),
    "altitudes": ("Высоты AD и BE остроугольного треугольника ABC пересекаются в точке H. "
                  "Найдите ∠AHB, если ∠C = 65°.", "DEH"),
    "chord_distance": ("Окружность с центром в точке O и радиусом 5. Хорда AB = 8. "
                       "Найдите расстояние от O до AB.", "OAB"),
    "medial_triangle": ("В треугольнике ABC точки D, E, F — середины сторон BC, CA, AB "
                        "соответственно.", "DEF"),
    "parallelogram_bisector": ("Биссектриса угла A параллелограмма ABCD пересекает сторону BC в "
                               "точке K. AB = 5, AD = 8. Найдите KC.", "K"),
    "midline": ("В трапеции ABCD с основаниями BC и AD средняя линия MN, где M на AB, N на CD.",
                "MN"),
    "legs": ("Катеты прямоугольного треугольника равны 5 и 12. Найдите гипотенузу.", "ABC"),
    "obtuse_isosceles": ("Угол при вершине равнобедренного треугольника равен 120°, боковая "
                         "сторона 6.", "ABC"),
    "hexagon_diagonals": ("Шестиугольник ABCDEF, диагонали AD, BE, CF.", "ABCDEF"),
    "diameter_chord": ("В окружности с центром O проведены диаметр AB и хорда CD, "
                       "перпендикулярная AB.", "OABCD"),
    "inscribed_square": ("Квадрат ABCD вписан в окружность радиуса 4.", "ABCD"),
    "no_names": ("Докажите, что сумма углов треугольника равна 180°.", "ABC"),
}

NOISE = ["", "     ", "!!!???", "x" * 5000, "ABCDEFGHIJKLMNOPQRSTUVWXYZ " * 50,
         "Найдите x: 2x+3=7", "треугольник ABCDEFGHIJ", "\u0000\u0001 треугольник ABC",
         "Треугольник A\u200bBC", "окружность", "угол 30°", "на стороне BC точка D, BD:DC=0:0",
         "BD : DC = 1 : 0 в треугольнике ABC, D на стороне BC", "треугольник ABC " * 800,
         "𝐀𝐁𝐂 треугольник", "Треугольник ABC, точка D на стороне DD.",
         "Треугольник ABC, M — середина AA.", "Хорды AB и AB пересекаются в точке A.",
         "Точки A и A — середины сторон AB и AB.", "В квадрате ABCD диагонали пересекаются в точке A.",
         "Треугольник ABC, AB:BC = 1:1:1:1", "$$$\\(\\)\\[\\]$$ треугольник $ABC$",
         "∠ABC = 400°, треугольник ABC", "Окружность с центром O, касательные OA и OB."]


@pytest.fixture
def refusing_model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})

    def refuse(*_, **__):
        raise PlanError("UNSUPPORTED_CONSTRUCTION", "модель не справилась")

    monkeypatch.setattr(llm, "formalize", refuse)


def coords_of(text):
    built = sketch_plan(text)
    assert built is not None, text
    plan, free = built
    pts = execute(plan, free_values=free)
    return plan, {k: np.asarray(v, dtype=float) for k, v in pts.items()}


def names(spec):
    return list(spec) if isinstance(spec, str) else spec


# ---------------------------------------------------------------- always draws

@pytest.mark.parametrize("key", sorted(HARD))
def test_hard_corpus_always_draws(refusing_model, key):
    text, expected = HARD[key]
    r = generate(text, sess=object(), use_cache=False)
    assert r.ok, (key, r.reason)
    assert r.verification == "sketch" and r.measured is None
    xml.dom.minidom.parseString(r.svg)
    assert set(names(expected)) <= set(r.plan["points"]), (key, r.plan["points"])
    _, pts = coords_of(text)
    assert all(np.all(np.isfinite(v)) for v in pts.values())
    # the sketch is not degenerate: no two distinct points coincide
    vals = list(pts.values())
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            assert np.linalg.norm(vals[i] - vals[j]) > 1e-6, key


# ---------------------------------------------------------------- invariants

def _ratio(P, X, Y):
    return np.linalg.norm(P - X) / np.linalg.norm(Y - X)


def _on_line(P, X, Y):
    d = Y - X
    return abs(d[0] * (P[1] - X[1]) - d[1] * (P[0] - X[0])) / np.linalg.norm(d) < 1e-9


def _angle(A, O, B):
    u, v = A - O, B - O
    return math.degrees(math.acos(np.clip(u @ v / np.linalg.norm(u) / np.linalg.norm(v), -1, 1)))


def _dist(P, Q):
    return float(np.linalg.norm(P - Q))


def test_invariants_ratios_and_intersections():
    _, p = coords_of(HARD["latex_ratio"][0])
    assert _ratio(p["D"], p["B"], p["C"]) == pytest.approx(2 / 7)
    assert _ratio(p["E"], p["A"], p["B"]) == pytest.approx(3 / 4)
    assert _on_line(p["P"], p["A"], p["D"]) and _on_line(p["P"], p["C"], p["E"])
    _, p = coords_of(HARD["segment_ratio"][0])
    assert _ratio(p["C"], p["A"], p["B"]) == pytest.approx(3 / 5)


def test_invariants_medians_and_midpoints():
    _, p = coords_of(HARD["delta_medians"][0])
    for v, m, a, b in (("A", "A1", "B", "C"), ("B", "B1", "A", "C"), ("C", "C1", "A", "B")):
        assert np.allclose(p[m], (p[a] + p[b]) / 2)
        assert _on_line(p["M"], p[v], p[m])
    assert np.allclose(p["M"], (p["A"] + p["B"] + p["C"]) / 3)       # AM : MA1 = 2 : 1
    _, p = coords_of(HARD["medial_triangle"][0])
    assert np.allclose(p["D"], (p["B"] + p["C"]) / 2)
    assert np.allclose(p["E"], (p["C"] + p["A"]) / 2)
    assert np.allclose(p["F"], (p["A"] + p["B"]) / 2)
    _, p = coords_of(HARD["two_midpoints"][0])
    assert np.allclose(p["K"], (p["A"] + p["B"]) / 2)
    assert np.allclose(p["L"], (p["B"] + p["C"]) / 2)


def test_invariants_parallelogram_and_trapezoid():
    _, p = coords_of(HARD["parallelogram_cevian"][0])
    assert np.allclose(p["A"] + p["C"], p["B"] + p["D"])            # really a parallelogram
    assert _ratio(p["K"], p["B"], p["D"]) == pytest.approx(1 / 3)     # BK : KD = 1 : 2
    _, p = coords_of(HARD["parallelogram_bisector"][0])
    assert _on_line(p["K"], p["B"], p["C"])
    assert _angle(p["B"], p["A"], p["K"]) == pytest.approx(_angle(p["K"], p["A"], p["D"]))
    assert _dist(p["B"], p["K"]) == pytest.approx(_dist(p["A"], p["B"]))
    _, p = coords_of(HARD["midline"][0])
    assert np.allclose(p["M"], (p["A"] + p["B"]) / 2)
    assert np.allclose(p["N"], (p["C"] + p["D"]) / 2)
    bc, ad = p["C"] - p["B"], p["D"] - p["A"]
    assert abs(bc[0] * ad[1] - bc[1] * ad[0]) < 1e-9                 # BC ∥ AD
    _, p = coords_of(HARD["trapezoid_diagonals"][0])
    assert _on_line(p["O"], p["A"], p["C"]) and _on_line(p["O"], p["B"], p["D"])


def test_invariants_right_triangle_cevians():
    _, p = coords_of(HARD["three_cevians"][0])
    assert _angle(p["A"], p["C"], p["B"]) == pytest.approx(90)
    assert np.allclose(p["M"], (p["A"] + p["B"]) / 2)
    assert (p["H"] - p["C"]) @ (p["B"] - p["A"]) == pytest.approx(0, abs=1e-9)
    assert _angle(p["A"], p["C"], p["L"]) == pytest.approx(45)
    _, p = coords_of(HARD["latex_right"][0])
    assert _angle(p["A"], p["C"], p["B"]) == pytest.approx(90)
    _, p = coords_of(HARD["altitudes"][0])
    assert (p["D"] - p["A"]) @ (p["C"] - p["B"]) == pytest.approx(0, abs=1e-9)
    assert (p["E"] - p["B"]) @ (p["C"] - p["A"]) == pytest.approx(0, abs=1e-9)
    assert (p["H"] - p["C"]) @ (p["B"] - p["A"]) == pytest.approx(0, abs=1e-9)  # orthocentre


def test_invariants_triangle_kinds():
    _, p = coords_of(HARD["isosceles_height"][0])
    assert _dist(p["A"], p["B"]) == pytest.approx(_dist(p["B"], p["C"]))
    assert np.allclose(p["H"], (p["A"] + p["C"]) / 2)
    _, p = coords_of(HARD["equilateral_by_equalities"][0])
    ab, bc, ca = _dist(p["A"], p["B"]), _dist(p["B"], p["C"]), _dist(p["C"], p["A"])
    assert ab == pytest.approx(bc) == pytest.approx(ca)
    assert np.allclose(p["O"], (p["A"] + p["B"] + p["C"]) / 3)
    _, p = coords_of(HARD["obtuse_isosceles"][0])
    assert max(_angle(p["A"], p["B"], p["C"]), _angle(p["B"], p["A"], p["C"]),
               _angle(p["A"], p["C"], p["B"])) > 90


def test_invariants_circles():
    plan, p = coords_of(HARD["circumcircle"][0])
    r = [_dist(p["O"], p[v]) for v in "ABC"]
    assert r[0] == pytest.approx(r[1]) == pytest.approx(r[2])
    plan, p = coords_of(HARD["incircle"][0])
    assert _on_line(p["K"], p["B"], p["C"])
    rad = _dist(p["I"], p["K"])
    for x, y in (("A", "B"), ("B", "C"), ("C", "A")):
        d = p[y] - p[x]
        dist = abs(d[0] * (p["I"][1] - p[x][1]) - d[1] * (p["I"][0] - p[x][0])) / np.linalg.norm(d)
        assert dist == pytest.approx(rad)
    plan, p = coords_of(HARD["chords"][0])
    r = [_dist(p["O"], p[v]) for v in "ABCD"]
    assert max(r) - min(r) < 1e-9
    assert _on_line(p["E"], p["A"], p["B"]) and _on_line(p["E"], p["C"], p["D"])
    # power of a point: AE * EB = CE * ED
    assert _dist(p["A"], p["E"]) * _dist(p["E"], p["B"]) == pytest.approx(
        _dist(p["C"], p["E"]) * _dist(p["E"], p["D"]))
    assert "O" in plan.draw.hide_labels                  # the text never names the centre
    plan, p = coords_of(HARD["tangents"][0])
    rad = _dist(p["O"], p["R_O"])
    for t in "AB":
        assert _dist(p["O"], p[t]) == pytest.approx(rad)
        assert (p[t] - p["O"]) @ (p[t] - p["M"]) == pytest.approx(0, abs=1e-9)
    assert _dist(p["M"], p["A"]) == pytest.approx(_dist(p["M"], p["B"]))
    plan, p = coords_of(HARD["tangent_circles"][0])
    r1, r2 = _dist(p["O1"], p["R_O1"]), _dist(p["O2"], p["R_O2"])
    assert _dist(p["O1"], p["O2"]) == pytest.approx(r1 + r2)
    plan, p = coords_of(HARD["diameter_chord"][0])
    assert np.allclose(p["O"], (p["A"] + p["B"]) / 2)
    assert (p["D"] - p["C"]) @ (p["B"] - p["A"]) == pytest.approx(0, abs=1e-9)
    assert _dist(p["O"], p["D"]) == pytest.approx(_dist(p["O"], p["A"]))
    for key, verts in (("cyclic_pentagon", "ABCDE"), ("inscribed_square", "ABCD")):
        plan, p = coords_of(HARD[key][0])
        centre = plan.draw.circles[0][0]
        r = [_dist(p[centre], p[v]) for v in verts]
        assert max(r) - min(r) < 1e-9, key
    plan, p = coords_of(HARD["cyclic_quad"][0])
    c = p["O"]
    r = [_dist(c, p[v]) for v in "ABCD"]
    assert max(r) - min(r) < 1e-9


def test_invariants_angle_extension_interior():
    _, p = coords_of(HARD["angle_bisector_ray"][0])
    assert _angle(p["A"], p["O"], p["B"]) == pytest.approx(120)
    assert _angle(p["A"], p["O"], p["C"]) == pytest.approx(60)
    _, p = coords_of(HARD["extension"][0])
    assert _on_line(p["D"], p["A"], p["B"])
    assert _dist(p["B"], p["D"]) == pytest.approx(_dist(p["A"], p["B"]))
    assert _dist(p["A"], p["D"]) == pytest.approx(2 * _dist(p["A"], p["B"]))   # beyond B
    _, p = coords_of(HARD["cevians_through_point"][0])
    for v, foot, x, y in (("A", "A1", "B", "C"), ("B", "B1", "C", "A"), ("C", "C1", "A", "B")):
        assert _on_line(p[foot], p[x], p[y]) and _on_line(p["M"], p[v], p[foot])
        assert 0 < _ratio(p[foot], p[x], p[y]) < 1                  # M really inside
    _, p = coords_of(HARD["square_points"][0])
    assert np.allclose(p["E"], (p["C"] + p["D"]) / 2)
    assert _ratio(p["F"], p["B"], p["C"]) == pytest.approx(1 / 4)


# ---------------------------------------------------------------- noise / fuzz

@pytest.mark.parametrize("text", NOISE)
def test_noise_never_crashes(refusing_model, text):
    r = generate(text, sess=object(), use_cache=False)
    if r.ok:
        xml.dom.minidom.parseString(r.svg)
    else:
        assert r.reason and r.svg is None or not r.ok


def test_random_fuzz_of_sketch_never_crashes():
    rng = random.Random(20260929)
    parts = [h[0] for h in HARD.values()] + NOISE[:16]
    alphabet = "ABCDEFGHKLMNOPQ_1234567890 ,.:;=—-()$\\{}∠°△Δабвгдежзийклмнопрстуфхцчшщыэюя"
    for _ in range(400):
        pieces = [rng.choice(parts) for _ in range(rng.randint(1, 3))]
        text = " ".join(pieces)
        if rng.random() < 0.5:                      # corrupt random characters
            chars = list(text)
            for _ in range(rng.randint(1, 12)):
                if chars:
                    chars[rng.randrange(len(chars))] = rng.choice(alphabet)
            text = "".join(chars)
        built = sketch_plan(text)
        if built is not None:
            plan, free = built
            pts = execute(plan, free_values=free)
            assert all(np.all(np.isfinite(v)) for v in pts.values())


# ---------------------------------------------------------------- corrupted model plans

RATIO = ("В треугольнике ABC на стороне BC взята точка D, причём BD : DC = 1 : 2. "
         "На стороне AC взята точка E, причём AE : EC = 1 : 3. Отрезки AD и BE "
         "пересекаются в точке O. Найдите AO : OD.")


def ratio_plan(d=1 / 3, e=1 / 4, drop=None, constraints=None):
    cons = [
        {"op": "free_point", "out": "A"},
        {"op": "free_point", "out": "B"},
        {"op": "free_point", "out": "C"},
        {"op": "divide_segment", "out": "D", "args": ["B", "C"], "value": d},
        {"op": "divide_segment", "out": "E", "args": ["A", "C"], "value": e},
        {"op": "line_intersect", "out": "O", "args": ["A", "D", "B", "E"]},
    ]
    pts = ["A", "B", "C", "D", "E", "O"]
    if drop:
        cons = [c for c in cons if c["out"] != drop]
        pts.remove(drop)
    segs = [s for s in [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"], ["B", "E"]]
            if drop not in s]
    return FigurePlan.from_dict({
        "points": pts, "constructions": cons,
        "constraints": constraints if constraints is not None else [
            {"type": "angle", "args": ["A", "B", "C"], "value": 64},
            {"type": "angle", "args": ["B", "C", "A"], "value": 52}],
        "draw": {"segments": segs}, "scale_free": True})


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    return lambda fn: monkeypatch.setattr(llm, "formalize", fn)


@pytest.mark.parametrize("label,make", [
    ("wrong_ratio", lambda: ratio_plan(d=1 / 2)),
    ("swapped_ratio", lambda: ratio_plan(e=3 / 4)),
    ("dropped_intersection", lambda: ratio_plan(drop="O")),
    ("dropped_point", lambda: ratio_plan(drop="E")),
])
def test_wrong_model_figure_is_never_presented_as_verified(model, label, make):
    model(lambda *_, **__: (make(), []))
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=1)
    assert r.ok, label
    assert r.verification in {"approximate", "sketch"}, (label, r.verification)
    assert r.measured is None
    xml.dom.minidom.parseString(r.svg)


def test_contradictory_constraints_are_drawn_approximately(model):
    bad = [{"type": "angle", "args": ["A", "B", "C"], "value": 120},
           {"type": "angle", "args": ["B", "C", "A"], "value": 100}]
    model(lambda *_, **__: (ratio_plan(constraints=bad), []))
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=1)
    assert r.ok and r.verification in {"approximate", "sketch"} and r.measured is None


@pytest.mark.parametrize("garbage", [
    lambda: (None, []), lambda: "not a plan", lambda: (ratio_plan(d=float("nan")), []),
    lambda: (ratio_plan(d=float("inf")), []), lambda: (ratio_plan(d=-5.0), []),
    lambda: ({"points": ["A"]}, []), lambda: 42,
])
def test_garbage_from_model_never_crashes(model, garbage):
    model(lambda *_, **__: garbage())
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=1)
    assert r.ok and r.verification in {"approximate", "simplified", "sketch"}
    xml.dom.minidom.parseString(r.svg)


@pytest.mark.parametrize("exc", [RuntimeError("boom"), KeyError("points"), ValueError("x"),
                                 TypeError("y"), ZeroDivisionError()])
def test_unexpected_model_exception_still_draws(model, exc):
    def formalize(*_, **__):
        raise exc

    model(formalize)
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=1)
    assert r.ok and r.verification == "sketch"


def test_recovers_to_verified_after_bad_first_answer(model):
    answers = iter([(ratio_plan(d=1 / 2), []), (ratio_plan(), [])])
    model(lambda *_, **__: next(answers))
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=2)
    assert r.ok and r.verification == "constraints_only" and r.stage == "9-render"


# ---------------------------------------------------------------- no false alarms

CENTROID = ("В треугольнике ABC медианы AM и BN пересекаются в точке G. "
            "Докажите, что AG : GM = 2 : 1 и BG = 2GN.")


def centroid_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "M", "N", "G"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "midpoint", "out": "M", "args": ["B", "C"]},
            {"op": "midpoint", "out": "N", "args": ["A", "C"]},
            {"op": "line_intersect", "out": "G", "args": ["A", "M", "B", "N"]}],
        "constraints": [{"type": "angle", "args": ["A", "B", "C"], "value": 62},
                        {"type": "angle", "args": ["B", "C", "A"], "value": 54}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"], ["B", "N"]]},
        "scale_free": True})


@pytest.mark.parametrize("text,plan", [
    (CENTROID, centroid_plan),
    (RATIO, ratio_plan),
    (RATIO.replace("BD : DC = 1 : 2", "BD:DC=1:2").replace("AE : EC = 1 : 3", "AE/EC = 1/3"),
     ratio_plan),
    (RATIO + " Известно, что AB + BC = 12, AO = 2x.", ratio_plan),
    (RATIO.replace("BD : DC = 1 : 2", "$BD : DC = 1 : 2$"), ratio_plan),
])
def test_correct_plans_are_not_flagged(model, text, plan):
    model(lambda *_, **__: (plan(), []))
    r = generate(text, sess=object(), use_cache=False, max_retries=1)
    assert r.ok and r.verification == "constraints_only", (r.verification, r.warnings)


# ---------------------------------------------------------------- ratio / named-point checker

from geoexact.core.semantics import _ratio_and_point_failures  # noqa: E402

TRI345 = {"A": np.array([0.0, 0.0]), "B": np.array([3.0, 0.0]), "C": np.array([3.0, 4.0]),
          "D": np.array([3.0, 4 / 3]), "A1": np.array([3.0, 2.0])}


@pytest.mark.parametrize("text", [
    "AB : BC : CA = 3 : 4 : 5.",
    "BD : DC = 1 : 2.",
    "$BD:DC=1:2$",
    "BD/DC = 1/2.",
    "Найдите AB : BC.",                         # asked, not stated
    "Может ли AB : BC = 2 : 1?",                # hypothetical
    "AB : BC = 2x : 3.",                        # algebraic, not a numeric ratio
    "Точка пересечения медиан. Точки A, B, C и D.",
    "Точка A1 — середина BC.", "Точка A_1 — середина BC.",
    "Точка А лежит на окружности.",             # Cyrillic А: not a Latin name
])
def test_ratio_checker_accepts_true_or_unclaimed(text):
    assert _ratio_and_point_failures(text, TRI345) == []


@pytest.mark.parametrize("text,needle", [
    ("AB : BC : CA = 3 : 5 : 4.", "отношение"),
    ("BD : DC = 2 : 1.", "отношение"),
    ("BD/DC = 2.", None),                        # a single number is not a chain: ignored
    ("AE : EC = 1 : 3.", "отсутствуют"),
    ("Отрезки AD и BE пересекаются в точке O.", "нет точки O"),
    ("В точках A1, B1 и C1.", "нет точки B1"),
])
def test_ratio_checker_rejects_wrong_or_missing(text, needle):
    fails = _ratio_and_point_failures(text, TRI345)
    if needle is None:
        assert fails == []
    else:
        assert any(needle in f for f in fails), fails
