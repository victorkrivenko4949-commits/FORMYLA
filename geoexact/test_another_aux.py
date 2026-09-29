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
