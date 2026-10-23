# -*- coding: utf-8 -*-
"""«Полное решение»: тот же диалог с экспертом продолжается просьбой решить
задачу, DeepSeek оформляет ответ в LaTeX."""
import json
import subprocess

import pytest

from geoexact import jobs
from geoexact.core import llm
from geoexact.core.solution import generate_solution
from geoexact.core.schema import PlanError


def test_solution_request_is_the_users_phrase_in_the_same_dialog():
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    msgs = llm.solution_messages("Условие задачи.", hist)
    assert msgs[:2] == hist
    assert msgs[-1] == {"role": "user", "content": "а теперь давай полное решение этой задачи"}


def test_solution_without_history_asks_the_problem_afresh():
    msgs = llm.solution_messages("Условие задачи.")
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert "Условие задачи." in msgs[0]["content"]
    assert "полное решение" in msgs[0]["content"]


def test_generate_solution_combines_expert_and_latex(monkeypatch):
    seen = {}

    def expert(sess, problem, history=None, max_out=16000, diag=None, messages=None):
        seen["messages"] = messages
        seen["history"] = history
        return "Треугольники равны по двум катетам, значит AB = CD."

    monkeypatch.setattr(llm, "expert_text", expert)
    monkeypatch.setattr(llm, "latex_solution",
                        lambda sess, said, budget, max_out=8000:
                        "Треугольники равны, значит $AB = CD$.")
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    out = generate_solution("Условие задачи.", hist)
    assert out["ok"] is True and out["kind"] == "solution"
    assert "$AB = CD$" in out["markdown"]
    # ответ Луны попадает в историю того же диалога
    assert out["solution_history"][-2] == {"role": "user", "content":
                                           "а теперь давай полное решение этой задачи"}
    assert out["solution_history"][-1]["role"] == "assistant"
    assert seen["messages"] == llm.solution_messages("Условие задачи.", hist)
    assert seen["history"] == hist


def test_generate_solution_reports_a_paid_failure_without_retry(monkeypatch):
    def fail(*a, **k):
        raise PlanError("EXPERT_HTTP", "HTTP 502")
    monkeypatch.setattr(llm, "expert_text", fail)
    out = generate_solution("Условие задачи.", None)
    assert out["ok"] is False and out["reason"] == "EXPERT_HTTP"
    assert "502" in out["detail"] and "markdown" not in out


def test_generate_solution_requires_a_condition():
    out = generate_solution("   ")
    assert out["ok"] is False and out["reason"] == "INVALID_CONDITION"


def test_latex_solution_strips_markdown_fences(monkeypatch):
    def chat(sess, model, system, user, max_out, stage, budget,
             temperature=0.0, thinking=False, reason=False, json_mode=True):
        assert json_mode is False           # свободный текст, не JSON-режим
        assert stage == "solution-latex"
        return "```markdown\n$AB = CD$\n```", None
    monkeypatch.setattr(llm, "_chat", chat)
    out = llm.latex_solution(object(), "AB = CD", llm.Budget(cap=0.10))
    assert out == "$AB = CD$"


def test_solution_job_survives_the_queue_with_its_dialog():
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    stored = jobs.wrap_solution("Задача", hist)
    assert jobs.is_solution_job(stored) is True
    assert jobs.unwrap_solution(stored) == ("Задача", hist)
    assert jobs.is_solution_job(jobs.wrap_problem("Задача", hist)) is False
    assert jobs.unwrap_solution("Задача") == ("Задача", None)


def test_worker_receives_the_solution_flag(monkeypatch):
    seen = {}

    def fake_run(cmd, input, **kw):
        seen.update(json.loads(input))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    out = jobs.run_generation(jobs.wrap_solution("Задача", hist), 2)
    assert seen == {"solution": True, "problem": "Задача", "history": hist}
    assert out == {"ok": True}


def test_queue_solution_job_runs_and_last_done_prefers_drawings(tmp_path):
    engine = jobs.create_engine(f"sqlite:///{tmp_path}/q.db")
    jobs.init_db(engine)

    def runner(problem, with_aux):
        if jobs.is_solution_job(problem):
            return {"ok": True, "kind": "solution", "markdown": "$x$"}
        return {"ok": True, "svg": "<svg/>"}

    q = jobs.Queue(engine, runner=runner)
    draw = q.submit("u1", "Задача", True)
    q.run_once()
    assert q.get(draw, "u1")["result"]["svg"] == "<svg/>"
    sol = q.submit_solution("u1", "Задача",
                            [{"role": "user", "content": "q"},
                             {"role": "assistant", "content": "a"}])
    q.run_once()
    result = q.get(sol, "u1")["result"]
    assert result["kind"] == "solution" and result["markdown"] == "$x$"
    # условие сохраняется и у решения; последним чертежом остаётся именно чертёж
    assert result["problem_text"] == "Задача"
    assert q.last_done("u1") == draw


def test_solution_submission_shares_the_single_job_limit(tmp_path):
    engine = jobs.create_engine(f"sqlite:///{tmp_path}/q.db")
    jobs.init_db(engine)
    q = jobs.Queue(engine, runner=lambda p, w: {"ok": True})
    first = q.submit("u1", "Задача", False)
    with pytest.raises(jobs.QueueFull):
        q.submit_solution("u1", "Задача", None)
    q.run_once()
    second = q.submit_solution("u1", "Задача", None)
    assert first != second
