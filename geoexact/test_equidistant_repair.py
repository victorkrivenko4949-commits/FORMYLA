# -*- coding: utf-8 -*-
"""«BX=XD»: окружность в конструкции равноудалённой точки — переограничение.

Прод-инцидент (задача 2, живой прогон формализатора после перевода на
v4-pro 23.10.2026, план сохранён в журнале сервера): X (BX=XD, X на BC)
закодирован как line_circle(B,C,D,B) — окружность центра D радиуса |DB|
добавляет условие |DX|=|DB|, которого нет в задаче. Солвер давал единственное
решение с RESIDUAL_TOO_HIGH, конвейер падал в вырожденный approximate-чертёж.
Ремонт: серединный перпендикуляр — только когда условие определяет точку
равенством и не задаёт окружность сам."""
import json
import math
from unittest.mock import patch

from geoexact.core import llm as L
from geoexact.core import pipeline
from geoexact.core.equidistant_repair import repair
from geoexact.core.schema import FigurePlan
from geoexact.core import diametral_plan as DP
from geoexact.test_acute_triangle import PROBLEM, _plan

# План с прод-инцидента (журнал сервера, WORKER_PLAN 21:57:39).
PRO_PLAN = {
    "space": "plane",
    "points": ["A", "B", "C", "O", "D", "X", "Y"],
    "constructions": [
        {"op": "free_point", "out": "A"},
        {"op": "free_point", "out": "B"},
        {"op": "free_point", "out": "C"},
        {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
        {"op": "reflect_point", "out": "D", "args": ["A", "O"]},
        {"op": "line_circle", "out": "X", "args": ["B", "C", "D", "B"], "value": 0},
        {"op": "line_circle", "out": "Y", "args": ["B", "C", "D", "C"], "value": 1},
    ],
    "constraints": [
        {"type": "on_segment", "args": ["X", "B", "C"]},
        {"type": "on_segment", "args": ["Y", "B", "C"]},
        {"type": "on_segment", "args": ["X", "B", "Y"]},
        {"type": "dist_eq", "args": ["B", "X", "X", "D"]},
        {"type": "dist_eq", "args": ["C", "Y", "Y", "D"]},
    ],
    "draw": {
        "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"], ["B", "D"],
                     ["C", "D"], ["X", "D"], ["Y", "D"], ["B", "Y"], ["C", "Y"]],
        "circles": [["O", "A"]],
        "hide_labels": ["O"],
    },
    "target": {"kind": "none", "args": []},
    "scale_free": True,
    "notes": "текст условия",
}

CIRCLE_TEXT = ("Прямая BC пересекает окружность с центром D, проходящую через B, "
               "второй раз в X. Дано BX=XD.")


def _pro():
    return FigurePlan.from_dict(json.loads(json.dumps(PRO_PLAN)))


def test_repair_replaces_circle_with_perp_bisector():
    plan = _pro()
    msg = repair(PROBLEM, plan)
    assert msg and "X" in msg and "Y" in msg
    ops = {(c.op, c.out): c for c in plan.constructions}
    # X: серединный перпендикуляр BD, пересечённый с BC
    x = ops[("line_intersect", "X")]
    assert x.args == ["B", "C", "M", "N"]
    assert ops[("midpoint", "M")].args == ["B", "D"]
    assert ops[("perp_point", "N")].args == ["M", "B", "D"]
    # Y: серединный перпендикуляр CD
    y = ops[("line_intersect", "Y")]
    assert y.args == ["B", "C", "M2", "N2"]
    assert ops[("midpoint", "M2")].args == ["C", "D"]
    # ограничения не тронуты, точки добавлены на свои места
    assert [c.args for c in plan.constraints if c.type == "dist_eq"] == \
        [["B", "X", "X", "D"], ["C", "Y", "Y", "D"]]
    assert plan.points[:5] == ["A", "B", "C", "O", "D"]
    assert plan.points.index("M") < plan.points.index("X")
    assert {"M", "N", "M2", "N2"} <= set(plan.points)
    # вспомогательные прямые в слое доп. построений, подписи скрыты
    assert ["M", "N"] in plan.draw.aux_lines and ["M2", "N2"] in plan.draw.aux_lines
    assert {"M", "N", "M2", "N2"} <= set(plan.draw.hide_labels)


def test_repair_noop_on_correct_plan():
    assert repair(PROBLEM, _plan()) is None


def test_text_phrase_required():
    # равенство в плане есть, но условие точку так не определяет — не трогаем
    assert repair("просто текст без равенств", _pro()) is None


def test_text_defined_circle_is_kept():
    """Контрпример советника: условие само задаёт окружность центра D через
    B — тогда line_circle законен, ремонт его не заменяет."""
    assert repair(CIRCLE_TEXT, _pro()) is None


def test_repair_noop_without_signature():
    # валидный план: окружности НЕ «через конец» равенства — сигнатуры нет
    from geoexact.core.schema import Construction
    plan = _pro()
    plan.constructions = [c for c in plan.constructions if c.out not in ("X", "Y")][:5] + [
        Construction(op="free_point", out="K"),
        Construction(op="free_point", out="L"),
        Construction(op="line_circle", out="X", args=["B", "C", "D", "K"], value=0),
        Construction(op="line_circle", out="Y", args=["B", "C", "D", "L"], value=1),
    ]
    plan.points = plan.points + ["K", "L"]
    assert repair(PROBLEM, plan) is None


def test_repair_rolls_back_on_invalid_plan(monkeypatch):
    import geoexact.core.schema as schema
    plan = _pro()
    before = json.dumps(plan.to_dict(), sort_keys=True)
    monkeypatch.setattr(schema, "validate_plan", lambda p: ["сломано"])
    assert repair(PROBLEM, plan) is None
    assert json.dumps(plan.to_dict(), sort_keys=True) == before


def test_rule_and_wrapper_installed():
    assert "EQUIDISTANT_RULE" in L.SYS_FORMALIZE          # правило 38 в промпте
    assert getattr(L.formalize, "_equidistant", False)    # пост-ремонт активен


def _svg_points(svg):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg)
    NS = "{http://www.w3.org/2000/svg}"
    return {c.get("data-point"): (float(c.get("cx")), float(c.get("cy")))
            for c in root.iter(NS + "circle") if c.get("data-point")}


def test_wrapper_fixes_pro_plan_through_real_formalize():
    """Прод-регрессия через НАСТОЯЩУЮ formalize (перехват только llm._chat —
    обёртки и ремонт работают сами): план с окружностями превращается в
    верифицированный чертёж; SVG проверен на остроту, антипод, порядок
    и оба равенства, а не только на статус."""
    def chat(sess, model, system, user, max_out, stage, budget, **kw):
        return json.dumps(PRO_PLAN), None
    with patch.object(L, "_chat", chat), \
         patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}), \
         patch.object(DP, "diametral_plan", lambda t, a: None):  # спец-план выключен — проверяем ремонт
        result = pipeline.generate(PROBLEM, use_cache=False)
    assert result.ok and result.stage == "9-render", (result.stage, result.detail)
    assert result.verification == "constraints_only", result.warnings
    assert any("EQUIDISTANT_FIXED" in w for w in result.warnings)

    pts = _svg_points(result.svg)
    assert {"A", "B", "C", "D", "X", "Y", "O"} <= set(pts)
    uniq = {tuple(round(x, 3) for x in pts[n]) for n in ("A", "B", "C", "D", "X", "Y")}
    assert len(uniq) == 6, "слипшиеся точки на итоговом чертеже"

    import numpy as np
    A, B, C = (np.array(pts[k]) for k in "ABC")
    O, D = np.array(pts["O"]), np.array(pts["D"])

    # острота: все углы треугольника < 90°
    for v, p, q in (("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")):
        u, w = np.array(pts[p]) - np.array(pts[v]), np.array(pts[q]) - np.array(pts[v])
        ang = math.degrees(math.acos(np.clip(u @ w / np.linalg.norm(u) / np.linalg.norm(w), -1, 1)))
        assert ang < 89.0, f"треугольник не острый (угол {v} = {ang:.1f}°)"

    # антипод: D = 2O − A
    assert np.linalg.norm(D - (2 * O - A)) < 1e-6 * max(np.linalg.norm(A - B), 1.0)

    # порядок B-X-Y-C вдоль стороны и оба равенства
    bc = C - B
    t = {k: float((np.array(pts[k]) - B) @ bc / (bc @ bc)) for k in ("X", "Y")}
    assert 0 < t["X"] < t["Y"] < 1, t
    for (p1, p2, q1, q2) in (("B", "X", "X", "D"), ("C", "Y", "Y", "D")):
        d1 = np.linalg.norm(np.array(pts[p1]) - np.array(pts[p2]))
        d2 = np.linalg.norm(np.array(pts[q1]) - np.array(pts[q2]))
        assert abs(d1 - d2) < 1e-3 * max(d1, d2), (p1, p2, d1, d2)


THIRD_EQUALITY_TEXT = ("Дан треугольник ABC и точка D. Точка X на стороне BC такова, "
                       "что BX=XD и XD=DB.")


def test_third_equality_cancels_repair():
    """«BX=XD и XD=DB»: окружность центра D радиуса |DB| задаётся самим
    условием (XD=DB) — ремонт не имеет права её заменять."""
    assert repair(THIRD_EQUALITY_TEXT, _pro()) is None


CAPITAL_CIRCLE_TEXT = ("Окружность с центром D, проходящая через B, пересекает "
                       "прямую BC второй раз в X. Дано BX=XD.")


def test_capital_circle_phrase_recognized():
    """Заглавная «Окружность» в начале предложения тоже распознаётся."""
    assert repair(CAPITAL_CIRCLE_TEXT, _pro()) is None


EQUILATERAL_TEXT = ("Точка X на стороне BC такова, что BX=XD. "
                    "Треугольник BXD равносторонний.")


def test_equilateral_definition_cancels_repair():
    """«Треугольник BXD равносторонний»: XD=DB задаётся условием без знака
    равенства и без слова «окружность» — закрытый шаблон не распознаёт
    конфигурацию, ремонт запрещён; план неизменен (сравнение до/после)."""
    plan = _pro()
    before = json.dumps(plan.to_dict(), sort_keys=True)
    assert repair(EQUILATERAL_TEXT, plan) is None
    assert json.dumps(plan.to_dict(), sort_keys=True) == before


def test_side_mismatch_cancels_repair():
    """В условии сторона BC, а прямая конструкции — другая (AC): имена не
    совпадают с распознанной конфигурацией — ремонт запрещён, план неизменен."""
    plan = _pro()
    for c in plan.constructions:
        if c.out in ("X", "Y"):
            c.args = ["A", "C"] + c.args[2:]   # прямая AC вместо BC
    before = json.dumps(plan.to_dict(), sort_keys=True)
    assert repair(PROBLEM, plan) is None
    assert json.dumps(plan.to_dict(), sort_keys=True) == before


def test_unrecognized_addendum_cancels_repair():
    """Любое дополнение к исходному условию — даже одно предложение —
    снимает право менять конструкцию: совпадать должен весь текст."""
    for addendum in (" Дополнительно XD=DB.", " Треугольник BXD равносторонний."):
        plan = _pro()
        before = json.dumps(plan.to_dict(), sort_keys=True)
        assert repair(PROBLEM + addendum, plan) is None, addendum
        assert json.dumps(plan.to_dict(), sort_keys=True) == before


# Второй прод-инцидент (журнал сервера, WORKER_PLAN 02:00:58 MSK 24.10.2026):
# ОБЕ точки X и Y закодированы как пересечение стороны BC с прямой DA
# (прямой из заключения) — X совпадает с Y, вырожденный approximate-чертёж.
# Draw и target восстановлены вручную: журнал хранит только структурные поля
PRO_PLAN2 = {
    "space": "plane",
    "points": ["A", "B", "C", "O", "D", "X", "Y"],
    "constructions": [
        {"op": "free_point", "out": "A"},
        {"op": "free_point", "out": "B"},
        {"op": "free_point", "out": "C"},
        {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
        {"op": "reflect_point", "out": "D", "args": ["A", "O"]},
        {"op": "line_intersect", "out": "X", "args": ["B", "C", "D", "A"]},
        {"op": "line_intersect", "out": "Y", "args": ["B", "C", "D", "A"]},
    ],
    "constraints": [
        {"type": "dist_eq", "args": ["B", "X", "X", "D"]},
        {"type": "dist_eq", "args": ["C", "Y", "Y", "D"]},
        {"type": "on_segment", "args": ["X", "B", "Y"]},
        {"type": "on_segment", "args": ["Y", "X", "C"]},
    ],
    "draw": {
        "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"], ["B", "D"],
                     ["C", "D"], ["X", "D"], ["Y", "D"], ["B", "Y"], ["C", "Y"]],
        "circles": [["O", "A"]],
        "hide_labels": ["O"],
    },
    "target": {"kind": "none", "args": []},
    "scale_free": True,
    "notes": "текст условия",
}


def _pro2():
    return FigurePlan.from_dict(json.loads(json.dumps(PRO_PLAN2)))


def test_repair_replaces_foreign_line_intersect():
    """Прямая из заключения (DA) в конструкции X/Y — то же переограничение,
    что и окружность: чинится серединными перпендикулярами BD и CD."""
    plan = _pro2()
    msg = repair(PROBLEM, plan)
    assert msg and "X" in msg and "Y" in msg
    ops = {(c.op, c.out): c for c in plan.constructions}
    x = ops[("line_intersect", "X")]
    assert x.args == ["B", "C", "M", "N"]
    assert ops[("midpoint", "M")].args == ["B", "D"]
    y = ops[("line_intersect", "Y")]
    assert y.args == ["B", "C", "M2", "N2"]
    assert ops[("midpoint", "M2")].args == ["C", "D"]
    assert ["M", "N"] in plan.draw.aux_lines and ["M2", "N2"] in plan.draw.aux_lines


def test_repair_idempotent_on_canonical_plan():
    """Повторный прогон по уже починенному плану — no-op: вставленные
    серединные перпендикуляры не заменяются сами собой."""
    plan = _pro2()
    assert repair(PROBLEM, plan)
    before = json.dumps(plan.to_dict(), sort_keys=True)
    assert repair(PROBLEM, plan) is None
    assert json.dumps(plan.to_dict(), sort_keys=True) == before


def test_wrapper_fixes_pro_plan2_through_real_formalize():
    """Регрессия второго инцидента через НАСТОЯЩУЮ formalize: план с прямой
    DA превращается в верный чертёж — SVG проверен полностью."""
    def chat(sess, model, system, user, max_out, stage, budget, **kw):
        return json.dumps(PRO_PLAN2), None
    with patch.object(L, "_chat", chat), \
         patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}), \
         patch.object(DP, "diametral_plan", lambda t, a: None):  # спец-план выключен — проверяем ремонт
        result = pipeline.generate(PROBLEM, use_cache=False)
    assert result.ok and result.stage == "9-render", (result.stage, result.detail)
    assert result.verification == "constraints_only", result.warnings
    assert any("EQUIDISTANT_FIXED" in w for w in result.warnings)

    pts = _svg_points(result.svg)
    assert {"A", "B", "C", "D", "X", "Y", "O"} <= set(pts)
    uniq = {tuple(round(x, 3) for x in pts[n]) for n in ("A", "B", "C", "D", "X", "Y")}
    assert len(uniq) == 6, "слипшиеся точки на итоговом чертеже"

    import numpy as np
    A, B, C = (np.array(pts[k]) for k in "ABC")
    O, D = np.array(pts["O"]), np.array(pts["D"])
    for v, p, q in (("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")):
        u, w = np.array(pts[p]) - np.array(pts[v]), np.array(pts[q]) - np.array(pts[v])
        ang = math.degrees(math.acos(np.clip(u @ w / np.linalg.norm(u) / np.linalg.norm(w), -1, 1)))
        assert ang < 89.0, f"треугольник не острый (угол {v} = {ang:.1f}°)"
    assert np.linalg.norm(D - (2 * O - A)) < 1e-6 * max(np.linalg.norm(A - B), 1.0)
    bc = C - B
    t = {k: float((np.array(pts[k]) - B) @ bc / (bc @ bc)) for k in ("X", "Y")}
    assert 0 < t["X"] < t["Y"] < 1, t
    for (p1, p2, q1, q2) in (("B", "X", "X", "D"), ("C", "Y", "Y", "D")):
        d1 = np.linalg.norm(np.array(pts[p1]) - np.array(pts[p2]))
        d2 = np.linalg.norm(np.array(pts[q1]) - np.array(pts[q2]))
        assert abs(d1 - d2) < 1e-3 * max(d1, d2), (p1, p2, d1, d2)


def test_formalize_plan_journal(capsys):
    """Диагностическая граница: ответ формализатора ДО ремонта попадает в
    журнал (stderr) с номером попытки — при провале пайплайна Result.plan
    подменяется планом фолбэка (скетча), и фактическй ответ модели иначе
    не воспроизвести. Только структурные поля: текст задачи не утекает."""
    def chat(sess, model, system, user, max_out, stage, budget, **kw):
        return json.dumps(PRO_PLAN2), None
    with patch.object(L, "_chat", chat), \
         patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}), \
         patch.object(DP, "diametral_plan", lambda t, a: None):  # спец-план выключен — проверяем ремонт
        result = pipeline.generate(PROBLEM, use_cache=False)
    assert result.ok and result.stage == "9-render", result.stage
    err = capsys.readouterr().err
    assert "текст условия" not in err and '"notes"' not in err    # свободный текст не утекает
    pre = [l for l in err.splitlines() if l.startswith("FORMALIZE_PLAN #")]
    post = [l for l in err.splitlines() if l.startswith("FORMALIZE_REPAIRED #")]
    assert pre and post
    p1 = json.loads(pre[-1].split(" ", 2)[2])
    p2 = json.loads(post[-1].split(" ", 2)[2])
    # одна и та же попытка: до ремонта — прямая DA, после — серединные перпендикуляры
    assert pre[-1].split(" ")[1] == post[-1].split(" ")[1]
    xy_pre = {c["out"]: c for c in p1["constructions"] if c["out"] in ("X", "Y")}
    assert all(c["args"] == ["B", "C", "D", "A"] for c in xy_pre.values())
    xy_post = {c["out"]: c for c in p2["constructions"] if c["out"] in ("X", "Y")}
    assert all(c["op"] == "line_intersect" and c["args"][2] not in ("D", "A")
               for c in xy_post.values())
    assert any(c["op"] == "midpoint" for c in p2["constructions"])
