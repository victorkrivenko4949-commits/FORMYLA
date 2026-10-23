# -*- coding: utf-8 -*-
"""Режим доп. построения, сквозной прогон: чертёж всегда имеет финальный вид.

«Главное, чтоб чертёж всегда имел финальный вид — то есть всё, что в итоге»:
запускаем НАСТОЯЩИЙ конвейер generate(with_aux=True) целиком — решатель,
гейты, применение построения, проверка меток, рендер — заменяя только LLM-вызовы
(формализатор и эксперт) заранее выверенными ответами. Прод-задача: медианы 9 и
12 под углом 150°, построение «обозначить точку пересечения и провести CO»."""
import xml.etree.ElementTree as ET

from geoexact.core import llm as L
from geoexact.core import pipeline
from geoexact.test_angle_marks_layout import _medians_plan

NS = "http://www.w3.org/2000/svg"

PROBLEM = ("в треугольнике ABC медианы из A и B соответственно пересекают "
           "стороны в точках A1 и B1, и медианы пересекаются под углом 150, "
           "они равны 9 и 12 соответственно, найти площадь ABC")

EXPERT_PROSE = ("Обозначить точку пересечения медиан O и провести отрезок CO, "
                "чтобы разбить треугольник на три равновеликих треугольника "
                "AOB, BOC, COA. Медиана делится точкой пересечения 2:1, поэтому "
                "AO = 6, BO = 8, OA1 = 3, OB1 = 4.")

# ответ aux_plan/aux_plan_from_text по новому контракту SYS_AUXPLAN:
# построение + числовые подписи результата (что получается в итоге)
AUX_DATA = {
    "idea": "Провести отрезок из C в точку пересечения медиан G: три "
            "равновеликих треугольника, AG = 6, BG = 8.",
    "steps": [],
    "aux_segments": [["C", "G"]],
    "result_marks": [
        {"pts": ["A", "G"], "text": "6"},
        {"pts": ["G", "A_1"], "text": "3"},
        {"pts": ["B", "G"], "text": "8"},
        {"pts": ["G", "B_1"], "text": "4"},
    ],
}


def _texts(svg):
    root = ET.fromstring(svg)
    out = []
    for el in root.iter("{" + NS + "}text"):
        content = (el.text or "") + "".join(t.text or "" for t in el)
        out.append(content.strip())
    return root, out


def _mock_llm(monkeypatch):
    monkeypatch.setattr(L, "formalize", lambda *a, **k: (_medians_plan(), []))
    monkeypatch.setattr(L, "expert_text", lambda *a, **k: EXPERT_PROSE)
    monkeypatch.setattr(L, "aux_plan_from_text", lambda *a, **k: AUX_DATA)
    monkeypatch.setattr(L, "aux_plan", lambda *a, **k: AUX_DATA)
    monkeypatch.setattr(L, "aux_plan_repair", lambda *a, **k: AUX_DATA)
    monkeypatch.setattr(L, "classify", lambda *a, **k: {"ok": True, "class": "M", "space": "plane"})


def test_aux_mode_final_view_end_to_end(monkeypatch):
    _mock_llm(monkeypatch)
    result = pipeline.generate(PROBLEM, with_aux=True, use_cache=False)
    assert result.ok, result.detail
    assert result.svg and result.svg_base

    # ── финальный вид (с построением): всё, что в итоге ───────────────────
    root, texts = _texts(result.svg)
    assert any("C" == t for t in texts)                      # фигура на месте
    assert "G" in texts                                     # точка обозначена
    assert "150°" in texts                                  # угол задачи
    for t in ("6", "3", "4", "8"):                          # результат построения
        assert t in texts, f"подпись результата {t} пропала"
    # построение нарисовано: пунктирный отрезок C-G в слое aux (по координатам
    # точек-кружков — у aux-линий нет data-point)
    aux = root.find(".//{" + NS + "}g[@id='aux']")
    assert aux is not None
    dots = {e.get("data-point"): (float(e.get("cx")), float(e.get("cy")))
            for e in root.iter("{" + NS + "}circle") if e.get("data-point")}
    c_pos, g_pos = dots["C"], dots["G"]
    aux_lines = aux.findall("{" + NS + "}line")
    def near(a, b):
        return abs(a - b) < 0.5
    assert any(
        (near(float(e.get("x1")), c_pos[0]) and near(float(e.get("y1")), c_pos[1])
         and near(float(e.get("x2")), g_pos[0]) and near(float(e.get("y2")), g_pos[1]))
        or (near(float(e.get("x1")), g_pos[0]) and near(float(e.get("y1")), g_pos[1])
            and near(float(e.get("x2")), c_pos[0]) and near(float(e.get("y2")), c_pos[1]))
        for e in aux_lines), "отрезок построения C-G не нарисован"
    # «только 6 3 4 8»: полные длины в финальном виде скрыты кусками
    assert not any("9" in t and "=" in t for t in texts), texts
    assert not any("12" in t and "=" in t for t in texts), texts
    # дуга широкого угла компактная (прошлый фикс работает и здесь)
    import math
    arcs = [e for e in root.iter("{" + NS + "}path")
            if "arc" in (e.get("class") or "").split()]
    radii = []
    for e in arcs:
        t = (e.get("d") or "").split()
        if len(t) == 11 and t[3] == "A":
            radii.append(float(t[4]))
    assert radii and max(radii) <= 20.0

    # ── базовый вид (переключатель «без построения»): данное на месте ─────
    _, base_texts = _texts(result.svg_base)
    assert any("9" in t and "=" in t for t in base_texts)   # AA_1 = 9
    assert any("12" in t and "=" in t for t in base_texts)  # BB_1 = 12
    assert not [t for t in base_texts if t in ("6", "3", "4", "8")]

    # ── статус эксперта и заметка об обозначенной точке ───────────────────
    assert result.expert_status == "OK"
    assert "обозначена построением" in (result.notes or "")
    # чертёж прошёл проверку (не approximate-фолбэк)
    assert result.verification == "constraints_only", result.verification


def test_aux_mode_final_view_without_model_marks(monkeypatch):
    """Модель не прислала result_marks — финальный вид всё равно полный:
    куски 6/3/4/8 выводятся теоремой о медианах автоматически."""
    bare = {k: v for k, v in AUX_DATA.items() if k != "result_marks"}
    _mock_llm(monkeypatch)
    monkeypatch.setattr(L, "aux_plan_from_text", lambda *a, **k: bare)
    monkeypatch.setattr(L, "aux_plan", lambda *a, **k: bare)
    monkeypatch.setattr(L, "aux_plan_repair", lambda *a, **k: bare)
    result = pipeline.generate(PROBLEM, with_aux=True, use_cache=False)
    assert result.ok, result.detail
    _, texts = _texts(result.svg)
    for t in ("6", "3", "4", "8"):
        assert t in texts, f"без подписей модели кусок {t} не выведен"
    assert not any("9" in t and "=" in t for t in texts)


def test_aux_mode_refusal_is_explicit(monkeypatch):
    """Построение не нарисовать (совпадает с уже нарисованным) — чертёж жив,
    но неполнота не замалчивается: статус эксперта REJECTED с причиной."""
    refused = {"idea": "провести сторону AB", "steps": [], "aux_segments": [["A", "B"]]}
    _mock_llm(monkeypatch)
    for name in ("aux_plan_from_text", "aux_plan", "aux_plan_repair"):
        monkeypatch.setattr(L, name, lambda *a, **k: refused)
    result = pipeline.generate(PROBLEM, with_aux=True, use_cache=False)
    assert result.ok, result.detail                    # чертёж построен
    assert str(result.expert_status).startswith("REJECTED"), result.expert_status
    assert "отрезк" in str(result.expert_status)      # причина дошла до пользователя
    # в финальном SVG нет линий построения (равные штрихи-деления медианы —
    # это факты условия, а не построение) — и он не притворяется полным
    root, texts = _texts(result.svg)
    aux = root.find(".//{" + NS + "}g[@id='aux']")
    assert aux is not None
    segs = [ln for ln in aux.findall("{" + NS + "}line")
            if ln.get("data-kind") == "segments"]
    assert not segs, segs                              # нет линий построения
    for t in ("A", "B", "C"):                         # базовая фигура на месте
        assert t in texts
