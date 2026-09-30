"""«Try another auxiliary construction»: the expert chat continues with the user's follow-up."""
import json
import subprocess

import pytest

from geoexact import jobs
from geoexact.core import llm
from geoexact.core.pipeline import generate
from geoexact.core.semantics import _PARALLELOGRAM_PROOF


def test_first_request_is_the_users_prompt_and_retry_appends_the_followup():
    first = llm.expert_messages("Условие задачи.")
    assert len(first) == 1 and first[0]["role"] == "user"
    assert first[0]["content"].startswith("вероятно тут есть доп построение")
    assert "Условие задачи." in first[0]["content"]
    history = first + [{"role": "assistant", "content": "Через D параллельно AC."}]
    again = llm.expert_messages("Условие задачи.", history)
    assert again[:2] == history
    assert again[-1] == {"role": "user", "content":
                         "отлично! но давай использовать какое-нибудь другое тоже удобное доп построение"}
    assert history == first + [{"role": "assistant", "content": "Через D параллельно AC."}]  # not mutated


def test_long_history_keeps_the_first_prompt_and_the_latest_turns():
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(12)]
    msgs = llm.expert_messages("x", hist)
    assert msgs[0]["content"] == "m0" and len(msgs) == llm.MAX_HISTORY + 1
    assert msgs[-2]["content"] == "m11"


def test_job_text_survives_the_queue_with_its_history():
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    stored = jobs.wrap_problem("Задача", hist)
    assert jobs.unwrap_problem(stored) == ("Задача", hist)
    assert jobs.unwrap_problem("Задача") == ("Задача", None)
    assert jobs.wrap_problem("Задача", None) == "Задача"


def test_worker_receives_history(monkeypatch):
    seen = {}

    def fake_run(cmd, input, **kw):
        seen.update(json.loads(input))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    jobs.run_generation(jobs.wrap_problem("Задача", hist), True)
    assert seen == {"problem": "Задача", "with_aux": True, "history": hist}


def test_web_history_validation():
    _clean_history = jobs.clean_history
    ok = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert _clean_history(ok) == ok
    assert _clean_history(None) is None and _clean_history([]) is None
    assert _clean_history(ok[:1]) is None                                  # must end with an answer
    assert _clean_history([ok[1], ok[0]]) is None                          # wrong order
    assert _clean_history([{"role": "user", "content": 5}, ok[1]]) is None
    assert _clean_history([{"role": "user", "content": "x" * 70000}, ok[1]]) is None


def _first_round(monkeypatch, said):
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: said)
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: {
        "idea": "Через D параллельно AC до K на BC.", "steps": [
            {"op": "parallel_intersect", "out": "K", "args": ["D", "A", "C", "B", "C"]}],
        "aux_segments": [["D", "K"]], "_expert_text": said})
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {"idea": "", "steps": []})
    return generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)


def test_result_carries_the_expert_chat(monkeypatch):
    r = _first_round(monkeypatch, "Через D параллельно AC. BK = BD.")
    assert [m["role"] for m in r.expert_history] == ["user", "assistant"]
    assert r.expert_history[1]["content"] == "Через D параллельно AC. BK = BD."
    assert "Условие" in r.expert_history[0]["content"] or "равнобедренном" in r.expert_history[0]["content"]


def test_another_construction_sends_history_and_skips_the_quick_fallback(monkeypatch):
    first = _first_round(monkeypatch, "Первый ответ.")
    seen = {}
    fast_calls = []

    def expert(sess, problem, history=None, **kw):
        seen["history"] = history
        return "Второй ответ: отразить B относительно D."
    monkeypatch.setattr(llm, "expert_text", expert)
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: {
        "idea": "Отразить B относительно D.", "steps": [
            {"op": "reflect_point", "out": "G", "args": ["B", "D"]}],
        "aux_segments": [["B", "G"]], "_expert_text": "Второй ответ"})
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: fast_calls.append(1) or {})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False,
                 aux_history=first.expert_history)
    assert seen["history"] == first.expert_history
    assert fast_calls == []
    assert [m["role"] for m in r.expert_history] == ["user", "assistant", "user", "assistant"]
    assert r.expert_history[2]["content"].startswith("отлично! но давай")
    assert ["B", "G"] in r.plan["draw"]["aux_segments"]


def test_another_construction_never_repeats_an_old_one_when_the_expert_fails(monkeypatch):
    first = _first_round(monkeypatch, "Первый ответ.")
    assert ["D", "K"] in first.plan["draw"]["aux_segments"]

    def fail(*a, **k):
        raise llm.PlanError("EXPERT_HTTP", "HTTP 500")
    monkeypatch.setattr(llm, "expert_text", fail)
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False,
                 aux_history=first.expert_history)
    assert r.ok and r.plan["draw"]["aux_segments"] == []


def test_finished_job_keeps_its_condition_and_is_found_again(tmp_path):
    engine = jobs.create_engine(f"sqlite:///{tmp_path}/q.db")
    jobs.init_db(engine)
    q = jobs.Queue(engine, runner=lambda problem, with_aux: {"ok": True, "svg": "<svg/>"})
    assert q.last_done("u1") is None
    jid = q.submit("u1", "Условие задачи про треугольник.", True)
    assert q.run_once()
    got = q.get(jid, "u1")["result"]
    assert got["problem_text"] == "Условие задачи про треугольник." and got["with_aux"] is True
    assert q.last_done("u1") == jid and q.last_done("u2") is None and q.get(jid, "u2") is None
    failed = jobs.Queue(engine, runner=lambda p, a: {"ok": False, "reason": "X"})
    failed.submit("u3", "Ещё одно условие задачи.", False)
    failed.run_once()
    assert failed.last_done("u3") is None


def test_expert_status_reports_why_there_is_no_construction(monkeypatch):
    def fail(*a, **k):
        raise llm.PlanError("EXPERT_HTTP", "HTTP 500")
    monkeypatch.setattr(llm, "expert_text", fail)
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {"idea": "", "steps": []})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    assert r.expert_status == "EXPERT_HTTP: HTTP 500" and r.expert_history == []


def test_expert_http_error_is_reported_with_status_and_body_but_without_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secretkey")

    class R:
        status_code = 401
        text = '{"error":"Incorrect API key provided: sk-abcdef123456789"}'

    class S:
        def post(self, *a, **k):
            return R()
    with pytest.raises(llm.PlanError) as e:
        llm.expert_text(S(), "задача")
    msg = str(e.value)
    assert "HTTP 401" in msg and "Incorrect API key" in msg and "abcdef123456789" not in msg


def test_expert_status_carries_the_reason(monkeypatch):
    def fail(*a, **k):
        raise llm.PlanError("EXPERT_HTTP", "HTTP 404 model not found")
    monkeypatch.setattr(llm, "expert_text", fail)
    monkeypatch.setattr(llm, "aux_plan", lambda *a, **k: {"idea": "", "steps": []})
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False)
    assert r.expert_status == "EXPERT_HTTP: HTTP 404 model not found"


def test_odirouter_key_wins_and_goes_to_odirouter(monkeypatch):
    monkeypatch.setenv("ODIROUTER_API_KEY", "odi-key")
    monkeypatch.setenv("GEMINI_API_KEY", "google-key")
    monkeypatch.setenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.delenv("ODIROUTER_BASE_URL", raising=False)
    assert llm._expert_credentials() == ("odi-key", "https://api.odirouter.ai/v1/chat/completions")
    monkeypatch.setenv("ODIROUTER_BASE_URL", "https://api.odirouter.ai/v1/")
    assert llm._expert_credentials()[1] == "https://api.odirouter.ai/v1/chat/completions"


def test_without_odirouter_key_the_shared_gemini_pair_is_used(monkeypatch):
    monkeypatch.delenv("ODIROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    monkeypatch.setenv("GEMINI_API_BASE", "https://router.example/v1")
    assert llm._expert_credentials() == ("shared", "https://router.example/v1/chat/completions")


def test_second_variant_with_bisector_op_is_drawn_and_unknown_points_get_a_reason():
    from geoexact.core import auxplan
    from geoexact.core.semantics import proof_parallelogram_plan
    from geoexact.core.solver import solve
    plan = proof_parallelogram_plan(_PARALLELOGRAM_PROOF, True)
    coords = [s for s in solve(plan, n_seeds=4, seed=0) if s.ok][0].coords
    why = []
    ok = auxplan.apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "bisector_point", "out": "K", "args": ["A", "B", "C"]}], "aux_segments": [["A", "K"]]}, why)
    assert ok is not None and why == []
    why = []
    assert auxplan.apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "midpoint", "out": "K", "args": ["Z", "B"]}], "aux_segments": [["Z", "K"]]}, why) is None
    assert "нет точек Z" in why[0]
    why = []
    assert auxplan.apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "magic", "out": "K", "args": ["A", "B"]}]}, why) is None and "magic" in why[0]


def test_refused_answer_is_repaired_once_and_reason_is_reported(monkeypatch):
    first = _first_round(monkeypatch, "Первый ответ.")
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: "Возьмём точку Z из прошлого ответа.")
    bad = {"idea": "x", "steps": [{"op": "midpoint", "out": "G", "args": ["Z", "B"]}],
           "aux_segments": [["Z", "G"]]}
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: dict(bad, _expert_text="t"))
    seen = {}

    def repair(sess, problem, expert, figure, reasons, budget):
        seen["reasons"], seen["figure"] = reasons, figure
        return {"idea": "Отразить B относительно D.", "steps": [
            {"op": "reflect_point", "out": "G", "args": ["B", "D"]}],
            "aux_segments": [["B", "G"]], "_expert_text": expert}
    monkeypatch.setattr(llm, "aux_plan_repair", repair)
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False, aux_history=first.expert_history)
    assert "нет точек Z" in seen["reasons"][0] and "Точки чертежа" in seen["figure"]
    assert ["B", "G"] in r.plan["draw"]["aux_segments"] and r.expert_status == "OK"

    def broken(*a, **k):
        raise llm.PlanError("BAD_JSON", "x")
    monkeypatch.setattr(llm, "aux_plan_repair", broken)
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False, aux_history=first.expert_history)
    assert r.plan["draw"]["aux_segments"] == [] and r.expert_status.startswith("REJECTED:")
    assert "нет точек Z" in r.expert_status
    assert [m["role"] for m in r.expert_history] == ["user", "assistant", "user", "assistant"]


def test_claim_about_original_figure_is_advice_but_claim_about_new_point_vetoes(monkeypatch):
    first = _first_round(monkeypatch, "Первый ответ.")
    steps = {"idea": "Отразить B относительно D.", "steps": [
        {"op": "reflect_point", "out": "G", "args": ["B", "D"]}], "aux_segments": [["B", "G"]]}
    monkeypatch.setattr(llm, "aux_plan_repair", lambda *a, **k: (_ for _ in ()).throw(llm.PlanError("BAD_JSON", "x")))
    # about the original figure only: drawn, with a note
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: "Докажем, что AB = AD.")
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: dict(steps, _expert_text="Докажем, что AB = AD."))
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False, aux_history=first.expert_history)
    assert ["B", "G"] in r.plan["draw"]["aux_segments"] and r.expert_status == "OK"
    assert any(w.startswith("AUX_CLAIM:") and "AB = AD" in w for w in r.warnings)
    # about the new point G (false): the translation is wrong, not drawn, reason shown
    monkeypatch.setattr(llm, "aux_plan_from_text", lambda *a, **k: dict(steps, _expert_text="Отложим G так, что DG = AB."))
    r = generate(_PARALLELOGRAM_PROOF, True, sess=object(), use_cache=False, aux_history=first.expert_history)
    assert r.plan["draw"]["aux_segments"] == [] and r.expert_status.startswith("REJECTED:")
    assert "DG = AB" in r.expert_status


def test_expert_timeout_status_says_where_gemini_was_silent():
    import time
    from geoexact.core.pipeline import _AuxJob
    slot = {"diag": {}}
    assert "не начался" in _AuxJob._diag_text(slot)
    slot["diag"] = {"t0": time.time() - 100, "headers": None}
    assert "заголовками" in _AuxJob._diag_text(slot)
    slot["diag"] = {"t0": time.time() - 100, "headers": 0.8, "first": None, "reasoning": 4000}
    assert "текст не пошёл" in _AuxJob._diag_text(slot) and "4000" in _AuxJob._diag_text(slot)
    slot["diag"] = {"t0": time.time() - 100, "headers": 0.8, "first": 9.5, "chars": 1200}
    assert "1200" in _AuxJob._diag_text(slot)


def test_expert_is_gemini_3_6_thinking_and_falls_back_when_router_does_not_know_it(monkeypatch):
    monkeypatch.setenv("ODIROUTER_API_KEY", "odi")
    assert llm.EXPERT_MODEL == "gemini-3.6-flash-thinking" and "gemini-3.6-flash" in llm.EXPERT_FALLBACKS
    tried = []

    class R:
        def __init__(self, code):
            self.status_code, self.text = code, "model not found"

        def iter_lines(self, decode_unicode=True, chunk_size=512):
            yield 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'

    class S:
        def post(self, url, **kw):
            tried.append(kw["json"]["model"])
            return R(404 if kw["json"]["model"].endswith("thinking") else 200)
    assert llm.expert_text(S(), "задача") == "ok"
    assert tried == ["gemini-3.6-flash-thinking", "gemini-3.6-flash"]


def test_steps_in_odd_shapes_are_understood_or_named():
    from geoexact.core import auxplan
    from geoexact.core.semantics import proof_parallelogram_plan
    from geoexact.core.solver import solve
    plan = proof_parallelogram_plan(_PARALLELOGRAM_PROOF, True)
    coords = [s for s in solve(plan, n_seeds=4, seed=0) if s.ok][0].coords
    # glued names: parallel_intersect(D, AC, BC)
    ok = auxplan.apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "parallel_intersect", "out": "K", "args": ["D", "AC", "BC"]}], "aux_segments": [["D", "K"]]})
    assert ok is not None
    # a step written as text
    ok = auxplan.apply_aux(plan, coords, {"idea": "", "steps": ["K = midpoint(B, D)"],
                                          "aux_segments": [["B", "K"]]})
    assert ok is not None
    # nonsense: the reason names the offending step
    why = []
    assert auxplan.apply_aux(plan, coords, {"idea": "", "steps": [42]}, why) is None
    assert "шаги не разобраны" in why[0] and "42" in why[0]
    why = []
    assert auxplan.apply_aux(plan, coords, {"idea": "", "steps": [
        {"op": "parallel_intersect", "out": "K", "args": ["D", "A"]}]}, why) is None
    assert "5 точек" in why[0] and "args" in why[0]
