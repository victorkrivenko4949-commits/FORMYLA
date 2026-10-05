"""Галочка «Сол»: та же цепочка и те же промпты, другая модель эксперта."""
import json
import subprocess

from geoexact import jobs
from geoexact.core import llm
from geoexact.core.solution import generate_solution


def test_sol_models_do_not_fall_back_to_luna():
    sol = llm.expert_models("sol")
    assert sol == ["gpt-6-sol"] and "gpt-6-luna" not in sol
    luna = llm.expert_models("luna")
    assert luna[0] == "gpt-6-luna"     # Луна по-прежнему может откатиться на Сол, Сол на Луну — нет
    assert llm.expert_models() == luna


def test_expert_text_sends_the_chosen_model_and_same_prompt(monkeypatch):
    monkeypatch.setenv("ODIROUTER_API_KEY", "k")
    sent = []

    class R:
        status_code = 200
        text = ""
        def iter_lines(self, *a, **k):
            yield b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'
            yield b"data: [DONE]"
        def close(self): pass

    class S:
        def post(self, url, json=None, **kw):
            sent.append(json)
            return R()
    for expert, model in (("luna", "gpt-6-luna"), ("sol", llm.SOL_MODEL)):
        assert llm.expert_text(S(), "Задача", expert=expert) == "ok"
        assert sent[-1]["model"] == model
    assert sent[0]["messages"] == sent[1]["messages"]      # промпт один и тот же


def test_job_text_carries_the_expert():
    assert jobs.wrap_problem("Задача", None) == "Задача"            # Луна: как раньше
    stored = jobs.wrap_problem("Задача", None, "sol")
    assert jobs.unwrap_problem(stored) == ("Задача", None)
    assert jobs.unwrap_expert(stored) == "sol"
    assert jobs.unwrap_expert("Задача") == "luna"
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert jobs.unwrap_problem(jobs.wrap_problem("З", hist)) == ("З", hist)
    assert jobs.unwrap_expert(jobs.wrap_problem("З", hist)) == "luna"
    sol = jobs.wrap_solution("З", hist, "sol")
    assert jobs.unwrap_solution(sol) == ("З", hist) and jobs.unwrap_expert(sol) == "sol"


def test_worker_receives_the_expert(monkeypatch):
    seen = {}

    def fake_run(cmd, input, **kw):
        seen.update(json.loads(input))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    jobs.run_generation(jobs.wrap_problem("Задача", None, "sol"), True)
    assert seen["expert"] == "sol"
    seen.clear()
    jobs.run_generation("Задача", True)
    assert "expert" not in seen            # Луна: полезная нагрузка как раньше


def test_solution_uses_the_same_expert(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: seen.update(k) or "решение")
    monkeypatch.setattr(llm, "latex_solution", lambda *a, **k: "md")
    assert generate_solution("Условие.", None, "sol")["ok"]
    assert seen["expert"] == "sol"
