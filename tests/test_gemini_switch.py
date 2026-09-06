# -*- coding: utf-8 -*-
"""Tests 24-38: REC-5/REC-6/REC-1/REC-8 — перенос ролей на Gemini (OdiRouter).

Без реальных сетевых вызовов.  Проверяются:
  * блокировка provider::model (REC-6);
  * role -> provider/model резолв (REC-5 Part 5);
  * solver-v2 промпт (REC-1) — геометрический, с few-shot, ключевые фразы;
  * max_tokens + response_format json_object (REC-8);
  * пустой content -> SolverEmptyResponse;
  * shadow-режим (Part 6).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services import llm_router as router  # noqa: E402
from services import solution_generator as sg  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for env in (
        "NOVITA_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY",
        "GEMINI_API_BASE", "GEMINI_BASE_URL",
        "FIGURE_BASE_MODEL", "FIGURE_AUX_MODEL", "FIGURE_AUDIT_MODEL",
        "FIGURE_REPAIR_MODEL", "FIGURE_SOLVER_MODEL",
        "FIGURE_SOLVER_SHADOW_MODEL", "FIGURE_SOLVER_SHADOW_PROVIDER",
        "FIGURE_SOLVER_GEMINI_SHADOW",
        "FIGURE_BASE_PROVIDER", "FIGURE_AUX_PROVIDER", "FIGURE_AUDIT_PROVIDER",
        "FIGURE_REPAIR_PROVIDER", "FIGURE_SOLVER_PROVIDER",
    ):
        monkeypatch.delenv(env, raising=False)
    router.clear_model_cache()
    yield
    router.clear_model_cache()


def _set_key(monkeypatch, provider, value="key"):
    monkeypatch.setenv(router.PROVIDER_API_KEY_ENV[provider], value)


def _ok_resp(content):
    """Фабрика 200-ответа с content и пустым usage."""

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [{"message": {"content": content,
                                         "finish_reason": "stop"}}],
                "usage": {},
            }

    return _Resp()


# ── 24. smoke: odirouter base_url дополняется /chat/completions ──
def test_odirouter_base_url_appends_chat_completions(monkeypatch):
    monkeypatch.setenv("GEMINI_API_BASE", "https://api.odirouter.ai/v1")
    assert router._odirouter_base_url() == "https://api.odirouter.ai/v1/chat/completions"


def test_odirouter_base_url_does_not_double_append(monkeypatch):
    monkeypatch.setenv("GEMINI_API_BASE", "https://api.odirouter.ai/v1/chat/completions")
    assert router._odirouter_base_url() == "https://api.odirouter.ai/v1/chat/completions"


# ── 25. blocking granularity: pro не блокирует flash ──
def test_provider_model_blocking_isolated():
    router.clear_model_cache()
    router.mark_provider_model_unreachable("deepseek_direct", "deepseek-v4-pro", 600)
    assert router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-pro")
    assert not router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-flash")
    assert not router.is_provider_model_unreachable("novita", "deepseek-v4-pro")
    router.clear_model_cache()


def test_record_transport_error_blocks_only_pair(monkeypatch):
    router.clear_model_cache()
    # Порог по умолчанию 2.
    assert not router.record_transport_error("deepseek_direct", "deepseek-v4-pro")
    assert router.record_transport_error("deepseek_direct", "deepseek-v4-pro")
    assert router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-pro")
    assert not router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-flash")
    router.clear_model_cache()


def test_reset_transport_errors_clears_counter():
    router.clear_model_cache()
    router.record_transport_error("deepseek_direct", "deepseek-v4-pro")
    router.reset_transport_errors("deepseek_direct", "deepseek-v4-pro")
    # После сброса первая ошибка не должна блокировать (порог 2).
    assert not router.record_transport_error("deepseek_direct", "deepseek-v4-pro")
    router.clear_model_cache()


# ── 26. role -> provider/model резолв (REC-5 Part 5) ──
def test_role_default_models_gemini_for_structural_roles():
    assert router.logical_model_for_role("base") == "gemini-3.7-flash"
    assert router.logical_model_for_role("aux") == "gemini-3.7-flash"
    assert router.logical_model_for_role("audit") == "gemini-3.7-flash"


def test_role_default_models_deepseek_for_solver_repair():
    # solver переведён на Gemini (по просьбе пользователя); repair остаётся deepseek.
    assert router.logical_model_for_role("solver") == "gemini-3.7-flash"
    assert router.logical_model_for_role("repair") == "deepseek-v4-pro"


def test_base_chain_starts_with_odirouter():
    assert router.ROLE_PROVIDER_ORDER["base"][0] == "odirouter"
    assert router.ROLE_PROVIDER_ORDER["solver"][0] == "odirouter"


def test_odirouter_models_no_prefix():
    assert router.resolve_provider_model("gemini-3.7-flash", "odirouter") == "gemini-3.7-flash"


# ── 27. build_provider_chain учитывает provider::model блокировку ──
def test_chain_excludes_blocked_pair(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    _set_key(monkeypatch, "odirouter")
    router.mark_provider_model_unreachable("odirouter", "gemini-3.7-flash", 600)
    chain = router.build_provider_chain(
        "gemini-3.7-flash", providers=("odirouter", "deepseek_direct")
    )
    providers = [c["provider"] for c in chain]
    # gemini-3.7-flash заблокирована только у odirouter; у deepseek_direct
    # нет маппинга для этой модели, поэтому цепочка пуста.
    assert "odirouter" not in providers


# ── 28. empty content -> SolverEmptyResponse (не тихий None) ──
def test_empty_content_raises_solver_empty(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    import requests

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "", "finish_reason": "stop"}}],
                    "usage": {}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(sg.SolverEmptyResponse) as exc:
        sg.solve_problem("Найдите угол B.")
    assert exc.value.code == "SOLVER_EMPTY_RESPONSE"


# ── 29. response_format json_object попадает в payload ──
def test_response_format_json_object_in_payload(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    import requests
    captured = {}

    def fake_post(url, **kw):
        captured["payload"] = kw["json"]
        return _ok_resp('{"solvable": true}')

    monkeypatch.setattr(requests, "post", fake_post)
    router.call_llm(
        "deepseek-v4-pro", [{"role": "user", "content": "x"}],
        role="solver", response_format={"type": "json_object"},
    )
    assert captured["payload"].get("response_format") == {"type": "json_object"}


# ── 30. max_tokens роли solver применяется (REC-8) ──
def test_solver_max_tokens_applied(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    import requests
    captured = {}

    def fake_post(url, **kw):
        captured["payload"] = kw["json"]
        return _ok_resp('{"solvable": true}')

    monkeypatch.setattr(requests, "post", fake_post)
    sg.solve_problem("Найдите угол B.")
    assert captured["payload"]["max_tokens"] == router.max_tokens_for_role("solver")
    assert captured["payload"]["max_tokens"] == 3500


# ── 31. solver-v2 промпт: геометрический, с few-shot и ключевыми правилами ──
def test_solver_prompt_v2_content():
    prompt = sg._load_solver_prompt()
    assert "PROMPT_VERSION: solver-v2" in prompt
    # REC-1: геометрическое, а не алгебраическое решение.
    assert "ГЕОМЕТРИЧЕСКИМ" in prompt and "алгебраическим" in prompt
    # few-shot с радиусом AO.
    assert "Проведём радиус AO" in prompt
    # правило «является радиусом — не построение».
    assert "MC является радиусом" in prompt
    # список операций из закрытого словаря.
    assert "segment" in prompt and "angle_bisector" in prompt


def test_solver_prompt_version_constant_matches():
    assert sg.SOLVER_PROMPT_VERSION == "solver-v2"


# ── 32. shadow-режим выключен по умолчанию ──
def test_shadow_disabled_by_default(monkeypatch):
    import importlib
    importlib.reload(sg)
    assert sg.FIGURE_SOLVER_GEMINI_SHADOW is False


def test_shadow_enabled_via_env(monkeypatch):
    import importlib
    monkeypatch.setenv("FIGURE_SOLVER_GEMINI_SHADOW", "true")
    importlib.reload(sg)
    assert sg.FIGURE_SOLVER_GEMINI_SHADOW is True
    monkeypatch.setenv("FIGURE_SOLVER_GEMINI_SHADOW", "false")
    importlib.reload(sg)


# ── 33. shadow-роль резолвится в gemini + только odirouter ──
def test_shadow_role_resolves_gemini():
    assert router.logical_model_for_role("solver_shadow") == "gemini-3.7-flash"
    assert router.ROLE_PROVIDER_ORDER["solver_shadow"] == ("odirouter",)


# ── 34. shadow-прогон не влияет на основной результат ──
def test_solve_problem_shadow_does_not_break_main(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    import requests

    content = (
        '{"solvable": true, "target": {"kind": "angle", "object": "B"}, '
        '"answer": {"value": 67.5, "is_numeric": true}, "steps": [], '
        '"aux_needed": false, "aux_constructions": []}'
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: _ok_resp(content))
    result = sg.solve_problem("Найдите угол B.")
    assert result["answer"]["value"] == 67.5
    assert result["_model"] == "deepseek-v4-pro"


# ── 35. bad JSON -> SolverError SOLVER_BAD_JSON ──
def test_bad_json_raises_solver_error(monkeypatch):
    _set_key(monkeypatch, "deepseek_direct")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _ok_resp("not json"))
    with pytest.raises(sg.SolverError) as exc:
        sg.solve_problem("Найдите угол B.")
    assert exc.value.code == "SOLVER_BAD_JSON"


# ── 36. gemini_client (ai/) остаётся OpenRouter — не трогаем pipeline ──
def test_gemini_client_still_openrouter_importable():
    from ai.gemini_client import GeminiClient
    assert GeminiClient is not None


# ── 37. compute_cost знает gemini-3.7-flash ──
def test_cost_gemini_flash():
    p = router.price_for_model("gemini-3.7-flash")
    assert p is not None and p["in"] > 0


# ── 38. describe_roles включает solver и не падает ──
def test_describe_roles_includes_solver_and_shadow():
    rows = router.describe_roles()
    roles = {r["role"] for r in rows}
    assert "solver" in roles
    assert "base" in roles
