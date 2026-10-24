# -*- coding: utf-8 -*-
"""model_routes: формализатор (оба пути, A и B) на deepseek-v4-pro.

Проверяется и словарь ROUTES, и фактическая отправка модели через настоящие
formalize/formalize_space (перехват llm._chat), включая повторную попытку.
"""
import json
import types

from geoexact.core import llm as L
from geoexact.core import model_routes

EXPECTED = {
    ("A", "S"):  ("deepseek-v4-pro", 4000),
    ("A", "M"):  ("deepseek-v4-pro", 6000),
    ("A", "L"):  ("deepseek-v4-pro", 10000),
    ("A", "XL"): ("deepseek-v4-pro", 10000),
    ("B", "S"):  ("deepseek-v4-pro", 6000),
    ("B", "M"):  ("deepseek-v4-pro", 10000),
    ("B", "L"):  ("deepseek-v4-pro", 10000),
    ("B", "XL"): ("deepseek-v4-pro", 10000),
}

# Минимальный валидный план: три свободные точки, одна дистанция, треугольник.
PLAN_JSON = json.dumps({
    "points": ["A", "B", "C"],
    "constructions": [
        {"op": "free_point", "out": "A"},
        {"op": "free_point", "out": "B"},
        {"op": "free_point", "out": "C"},
    ],
    "constraints": [{"type": "dist", "args": ["A", "B"], "value": 5}],
    "draw": {
        "segments": [["A", "B"], ["B", "C"], ["C", "A"]],
        "aux_segments": [], "aux_lines": [], "aux_rays": [], "aux_circles": [],
        "aux_points": [], "lines": [], "rays": [], "circles": [],
        "arcs": [], "angle_marks": [], "length_marks": [], "equal_marks": [],
        "hide_labels": [],
    },
    "target": {"kind": "dist", "args": ["A", "B"]},
})

PROBLEM = "в треугольнике ABC сторона AB равна 5, найдите сторону BC"


def _stub_routes():
    return types.SimpleNamespace(ROUTES={
        ("A", "S"):  ("deepseek-v4-flash", 4000),
        ("A", "M"):  ("deepseek-v4-flash", 6000),
        ("A", "L"):  ("deepseek-v4-flash", 8000),
        ("A", "XL"): ("deepseek-v4-pro", 10000),
        ("B", "S"):  ("deepseek-v4-flash", 6000),
        ("B", "M"):  ("deepseek-v4-flash", 10000),
        ("B", "L"):  ("deepseek-v4-flash", 10000),
        ("B", "XL"): ("deepseek-v4-flash", 10000),
    })


def test_install_exact_pairs_both_paths():
    stub = _stub_routes()
    model_routes.install(stub)
    assert {k: stub.ROUTES[k] for k in EXPECTED} == EXPECTED


def test_install_env_off_is_noop(monkeypatch):
    monkeypatch.setenv("GEOEXACT_PRO_FORMALIZE", "0")
    stub = _stub_routes()
    model_routes.install(stub)
    assert stub.ROUTES[("A", "S")] == ("deepseek-v4-flash", 4000)
    assert stub.ROUTES[("B", "XL")] == ("deepseek-v4-flash", 10000)


def test_install_appends_cache_suffix():
    stub = _stub_routes()
    pipe = types.SimpleNamespace(ENGINE_VERSION="3.0")
    model_routes.install(stub, pipeline_module=pipe)
    assert pipe.ENGINE_VERSION == "3.0" + model_routes.CACHE_SUFFIX


def test_real_llm_routes_patched():
    """Импорт geoexact.core применяет обёртку к настоящему llm.ROUTES."""
    for key, route in EXPECTED.items():
        assert L.ROUTES[key] == route


def _recorder(seen):
    def chat(sess, model, system, user, max_out, stage, budget,
             temperature=0.0, thinking=False, reason=False, json_mode=True):
        seen.append({"model": model, "max_out": max_out, "stage": stage,
                     "thinking": thinking})
        return PLAN_JSON, None
    return chat


def test_formalize_sends_pro_path_a(monkeypatch):
    """Настоящая formalize, путь A: запрос фактически уходит на v4-pro."""
    seen = []
    monkeypatch.setattr(L, "_chat", _recorder(seen))
    plan, _ = L.formalize(object(), PROBLEM, "M", False, L.Budget(cap=0.10))
    assert len(seen) == 1
    assert seen[0]["model"] == "deepseek-v4-pro"
    assert seen[0]["max_out"] == EXPECTED[("A", "M")][1]
    assert seen[0]["stage"] == "formalize-A"
    assert plan.points == ["A", "B", "C"]


def test_formalize_sends_pro_path_b(monkeypatch):
    seen = []
    monkeypatch.setattr(L, "_chat", _recorder(seen))
    L.formalize(object(), PROBLEM, "M", True, L.Budget(cap=0.10))
    assert len(seen) == 1
    assert seen[0]["model"] == "deepseek-v4-pro"
    assert seen[0]["max_out"] == EXPECTED[("B", "M")][1]
    assert seen[0]["stage"] == "formalize-B"


def test_formalize_retry_stays_pro(monkeypatch):
    """Повторная формализация после отказа движка — модель та же, лимит шире."""
    seen = []
    monkeypatch.setattr(L, "_chat", _recorder(seen))
    L.formalize(object(), PROBLEM, "M", False, L.Budget(cap=0.10),
                feedback="BAD_PLAN: исправь")
    assert len(seen) == 1
    assert seen[0]["model"] == "deepseek-v4-pro"
    assert seen[0]["max_out"] >= 8000
    assert seen[0]["thinking"] is True


def test_formalize_space_sends_pro(monkeypatch):
    seen = []
    monkeypatch.setattr(L, "_chat", _recorder(seen))
    L.formalize_space(object(), PROBLEM, "M", False, L.Budget(cap=0.10))
    assert len(seen) == 1
    assert seen[0]["model"] == "deepseek-v4-pro"
    assert seen[0]["stage"] == "formalize-3D"


def test_call_log_wraps_chat(caplog, monkeypatch):
    """Обёртка журнализирует фактическю модель и этап вызова (без текста
    задачи) — источник живого подтверждения по логам сервиса."""
    import logging
    import geoexact.core.model_routes as mr
    monkeypatch.setattr(L, "_chat", lambda *a, **k: ("{}", None))
    with caplog.at_level(logging.INFO, logger="geoexact.routes"):
        # свежая обёртка поверх заглушки
        mr._install_call_log(L)
        L._chat(object(), "deepseek-v4-pro", "sys", "user", 1000,
                "formalize-A", L.Budget(cap=0.10))
    assert any("model=deepseek-v4-pro" in r.message and "stage=formalize-A" in r.message
               for r in caplog.records)
    # текст задачи в журнал не попадает
    assert not any("user" == r.message or "sys" in r.message[:4] for r in caplog.records)


def test_call_log_includes_thinking(caplog, monkeypatch):
    """Флаг thinking в строке вызова: без него по журналу нельзя отличить
    вызовы с рассуждением от быстрых — а это гипотеза о нестабильности
    формализации (pro без thinking)."""
    import logging
    import geoexact.core.model_routes as mr
    calls = []

    def fake_chat(*a, **k):
        calls.append((a, k))
        return ("{}", None)

    monkeypatch.setattr(L, "_chat", fake_chat)
    with caplog.at_level(logging.INFO, logger="geoexact.routes"):
        mr._install_call_log(L)
        L._chat(object(), "deepseek-v4-pro", "sys", "user", 1000,
                "formalize-A", L.Budget(cap=0.10), thinking=True)
        L._chat(object(), "deepseek-v4-pro", "sys", "user", 1000,
                "formalize-A", L.Budget(cap=0.10))
    msgs = [r.message for r in caplog.records if "llm call" in r.message]
    assert any("thinking=1" in m for m in msgs)
    assert any("thinking=0" in m for m in msgs)
