# -*- coding: utf-8 -*-
"""Журнал воркера: план формализатора и лог вызовов — в stderr сервиса,
не клиенту. Без плана сбои формализатора на проде не воспроизводимы."""
import json
import subprocess
from dataclasses import dataclass, field

import geoexact.jobs as jobs
from geoexact import worker


@dataclass
class _FakeResult:
    ok: bool = True
    plan: dict | None = field(default_factory=lambda: {"points": ["A", "B"]})
    usage: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class _FakeResultWithNotes:
    ok: bool = True
    plan: dict = field(default_factory=lambda: {
        "points": ["A", "B"], "notes": "текст задачи с секретами",
        "draw": {"length_marks": [{"text": "AG = 6 (секретная подпись)"}]}})
    usage: list = field(default_factory=list)


def test_journal_logs_plan_to_stderr_not_stdout(capsys):
    payload = worker._journal(_FakeResult())
    err = capsys.readouterr().err
    assert "WORKER_PLAN" in err and '"points"' in err
    assert capsys.readouterr().out == ""          # клиенту план не уходит
    assert payload["plan"] == {"points": ["A", "B"]}   # asdict-совместимо


def test_journal_silent_without_plan(capsys):
    worker._journal(_FakeResult(plan=None))
    assert capsys.readouterr().err == ""


def test_journal_never_raises():
    @dataclass
    class Boom:
        ok: bool = True

        @property
        def plan(self):
            raise RuntimeError("boom")
    assert worker._journal(Boom()) == {"ok": True}  # журнал не ломает воркер


def test_run_generation_forwards_worker_journal(monkeypatch, capsys):
    """jobs.py пересылает stderr воркера в журнал сервиса — иначе лог
    вызовов (model=...) и план терялись в перехваченной трубе."""
    def fake_run(cmd, input, **kw):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"ok": True}),
            stderr="llm call model=deepseek-v4-pro stage=formalize-A\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = jobs.run_generation("Задача", False)
    assert out == {"ok": True}
    assert "model=deepseek-v4-pro" in capsys.readouterr().err


def test_journal_excludes_free_text_fields(capsys):
    """Свободный текст плана (notes — почти весь текст задачи; подписи
    draw.length_marks) в журнал сервера не попадает: только разрешённый
    набор структурных полей."""
    worker._journal(_FakeResultWithNotes())
    err = capsys.readouterr().err
    assert "WORKER_PLAN" in err and '"points"' in err
    assert "текст задачи" not in err and "секрет" not in err and "draw" not in err
