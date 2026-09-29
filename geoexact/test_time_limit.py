"""A slow model never leaves the user waiting: the whole request is bounded."""
import subprocess
import time

import pytest

from geoexact import jobs
from geoexact.core import llm, pipeline
from geoexact.core.pipeline import generate
from geoexact.core.schema import PlanError
from geoexact.test_hard_corpus import RATIO, ratio_plan


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    return lambda fn: monkeypatch.setattr(llm, "formalize", fn)


def test_slow_model_stops_after_time_limit(model, monkeypatch):
    monkeypatch.setattr(pipeline, "TIME_LIMIT", 31.0)      # 1 s left for extra attempts
    calls = []

    def slow(*_, **__):
        calls.append(1)
        time.sleep(1.2)
        return ratio_plan(d=1 / 2), []                     # wrong figure: would retry

    model(slow)
    t = time.time()
    r = generate(RATIO, True, sess=object(), use_cache=False, max_retries=5)
    assert len(calls) == 1 and time.time() - t < 10
    assert r.ok and r.verification in {"approximate", "sketch"}


def test_time_limit_inside_api_call_gives_sketch(model):
    def out_of_time(*_, **__):
        raise PlanError("TIME_LIMIT", "время на построение исчерпано")

    model(out_of_time)
    r = generate(RATIO, True, sess=object(), use_cache=False)
    assert r.ok and r.verification == "sketch"


def test_read_timeout_respects_deadline():
    try:
        llm.set_deadline(time.time() + 60)
        assert 50 < llm._read_timeout() <= 60
        llm.set_deadline(time.time() + 3)
        with pytest.raises(PlanError) as e:
            llm._read_timeout()
        assert e.value.code == "TIME_LIMIT"
        llm.set_deadline(None)
        assert llm._read_timeout() == 180
    finally:
        llm.set_deadline(None)


def test_generate_clears_deadline(model):
    model(lambda *_, **__: (ratio_plan(), []))
    generate(RATIO, sess=object(), use_cache=False)
    assert getattr(llm._DEADLINE, "value", None) is None


def test_worker_timeout_returns_sketch(monkeypatch):
    def hang(*_, **kw):
        raise subprocess.TimeoutExpired("worker", kw.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", hang)
    payload = jobs.run_generation(RATIO, True)
    assert payload["ok"] and payload["verification"] == "sketch"
    assert "<svg" in payload["svg"] and "plan" not in payload
    empty = jobs.run_generation("угол 30°", False)
    assert not empty["ok"] and empty["reason"] == "TIMEOUT"
