import json
import threading
import time
import types

import pytest

from geoexact.core import difficulty as D


class _Resp:
    def __init__(self, content, status=200, text=""):
        self.status_code = status
        self.text = text or json.dumps({"choices": [{"message": {"content": content}}]})
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _Sess:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")


@pytest.mark.parametrize("text,n", [("7", 7), (" 9\n", 9), ("10", 10), ("Сложность: 3", 3),
                                    ("0", None), ("11", None), ("", None), (None, None)])
def test_parse_rating(text, n):
    assert D.parse_rating(text) == n


def test_rate_uses_flash_without_thinking_and_one_token():
    s = _Sess(_Resp("4"))
    diag = {}
    assert D.rate_difficulty("задача", diag, session=s) == 4
    body = s.calls[0]["json"]
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] <= 4 and body["temperature"] == 0
    assert diag["difficulty"] == 4 and diag["rate_model"] == "deepseek-v4-flash"
    assert D.diag_text(diag).startswith("сложность 4 -> обычная модель")


def test_rate_retries_once_without_thinking_on_400():
    s = _Sess(_Resp("9", status=400, text="unknown field thinking"), _Resp("9"))
    assert D.rate_difficulty("задача", session=s) == 9
    assert "thinking" not in s.calls[1]["json"] and len(s.calls) == 2


def test_rate_never_raises(monkeypatch):
    diag = {}
    assert D.rate_difficulty("задача", diag, session=_Sess(TimeoutError("slow"))) is None
    assert diag["difficulty"] is None and "TimeoutError" in diag["rate_error"]
    assert D.rate_difficulty("задача", session=_Sess(_Resp("не знаю"))) is None
    assert D.rate_difficulty("задача", session=_Sess(_Resp("5", status=500))) is None
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert D.rate_difficulty("задача", session=_Sess()) is None


def test_pick_expert_threshold():
    fb = ("gpt-6-sol", "gemini-3.7-flash-thinking", "gemini-3.7-flash")
    for n in (None, 1, 3, 5):
        assert D.pick_expert(n, "gpt-6-luna", fb)[0] == "gpt-6-luna", n
    for n in (6, 7, 8, 9, 10):
        assert D.pick_expert(n, "gpt-6-luna", fb) == [
            "gpt-6-sol", "gpt-6-luna", "gemini-3.7-flash-thinking", "gemini-3.7-flash"], n
    assert D.pick_expert(10, "gpt-6-luna", ()) == ["gpt-6-sol", "gpt-6-luna"]


def test_diag_text_without_rating():
    assert D.diag_text({}) == "" and D.diag_text(None) == ""
    assert "не оценена" in D.diag_text({"difficulty": None, "rate_error": "x"})
    assert D.diag_text({"difficulty": 6, "rate_seconds": 1.2}) == "сложность 6 -> gpt-6-sol (1.2 с)"
    assert D.diag_text({"difficulty": 6, "rate_seconds": 1.2, "silent": ["gpt-6-luna"]}).endswith(
        "молчали: gpt-6-luna")


# --- install(): обёртка над llm.expert_text ---------------------------------

def _fake_llm(tried):
    m = types.ModuleType("fake_llm")
    m.EXPERT_MODEL = "gpt-6-luna"
    m.EXPERT_FALLBACKS = ("gpt-6-sol", "gemini-3.7-flash-thinking", "gemini-3.7-flash")

    def expert_text(sess, problem, history=None, max_out=16000, diag=None, messages=None):
        """doc"""
        tried.append([m.EXPERT_MODEL, *m.EXPERT_FALLBACKS])
        return "ok"
    m.expert_text = expert_text
    return m


def test_install_routes_hard_tasks_to_sol_and_restores_globals(monkeypatch):
    tried = []
    m = _fake_llm(tried)
    assert D.install(m) is True and D.install(m) is False      # повторно — no-op
    assert m.expert_text.__doc__ == "doc"

    def rate(problem, diag=None):
        diag["difficulty"] = 8
        return 8
    monkeypatch.setattr(D, "rate_difficulty", rate)
    diag = {}
    assert m.expert_text(object(), "задача", diag=diag) == "ok"
    assert tried[-1] == ["gpt-6-sol", "gpt-6-luna", "gemini-3.7-flash-thinking", "gemini-3.7-flash"]
    assert (m.EXPERT_MODEL, m.EXPERT_FALLBACKS) == (
        "gpt-6-luna", ("gpt-6-sol", "gemini-3.7-flash-thinking", "gemini-3.7-flash"))
    assert diag["difficulty"] == 8


def test_install_keeps_luna_first_for_easy_or_unrated(monkeypatch):
    tried = []
    m = _fake_llm(tried)
    D.install(m)
    for n in (None, 3, 5):
        monkeypatch.setattr(D, "rate_difficulty", lambda problem, diag=None, n=n: n)
        assert m.expert_text(object(), "задача") == "ok"
        assert tried[-1] == ["gpt-6-luna", "gpt-6-sol", "gemini-3.7-flash-thinking", "gemini-3.7-flash"]


def test_install_restores_globals_when_expert_fails(monkeypatch):
    m = _fake_llm([])

    def boom(*a, **k):
        raise RuntimeError("expert down")
    m.expert_text = boom
    D.install(m)
    monkeypatch.setattr(D, "rate_difficulty", lambda problem, diag=None: 9)
    with pytest.raises(RuntimeError):
        m.expert_text(object(), "задача")
    assert m.EXPERT_MODEL == "gpt-6-luna"


def test_install_does_not_call_deepseek_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    calls = []
    monkeypatch.setattr(D.requests, "post", lambda *a, **k: calls.append(1))
    tried = []
    m = _fake_llm(tried)
    D.install(m)
    assert m.expert_text(object(), "задача") == "ok"
    assert calls == [] and tried[-1][0] == "gpt-6-luna"


def test_router_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(D, "ENABLED", False)
    called = []
    monkeypatch.setattr(D, "rate_difficulty", lambda problem, diag=None: called.append(1) or 10)
    tried = []
    m = _fake_llm(tried)
    D.install(m)
    assert m.expert_text(object(), "задача") == "ok"
    assert called == [] and tried[-1][0] == "gpt-6-luna"


def test_core_package_installs_router():
    from geoexact.core import llm
    assert getattr(llm.expert_text, "_difficulty_routed", False) is True


# --- сторож первого токена ---------------------------------------------------

def _sse(delta):
    return "data: " + json.dumps({"choices": [{"delta": delta}]})


class _Stream:
    """Поток роутера: заголовки сразу, строки — по расписанию (пауза, строка)."""

    def __init__(self, schedule, status=200):
        self.status_code = status
        self.text = ""
        self.schedule = schedule
        self.closed = False

    def iter_lines(self, chunk_size=512, decode_unicode=True):
        for pause, line in self.schedule:
            time.sleep(pause)
            if self.closed:
                raise ConnectionError("closed")
            yield line

    def close(self):
        self.closed = True


class _Router:
    def __init__(self, streams):
        self.streams, self.models = streams, []

    def post(self, url, **kw):
        model = kw["json"]["model"]
        self.models.append(model)
        return self.streams[model]


def _llm_like_real(tried):
    """Укороченная копия цикла llm.expert_text: stream, diag, iter_lines, delta."""
    m = types.ModuleType("fake_llm")
    m.EXPERT_MODEL = "gpt-6-luna"
    m.EXPERT_FALLBACKS = ("gpt-6-sol", "gemini-3.7-flash")

    def expert_text(sess, problem, history=None, max_out=16000, diag=None, messages=None):
        models = [m.EXPERT_MODEL] + [x for x in m.EXPERT_FALLBACKS if x != m.EXPERT_MODEL]
        for model in models:
            tried.append(model)
            diag.update(t0=time.time(), headers=None, first=None, chars=0, lines=0, reasoning=0,
                        model=model)
            r = sess.post("url", json={"model": model, "stream": True}, stream=True, timeout=(15, 60))
            diag["headers"] = 0.1
            if r.status_code != 200:
                continue
            parts = []
            for raw in r.iter_lines(chunk_size=1, decode_unicode=True):
                diag["lines"] += 1
                if not raw.startswith("data: "):
                    continue
                d = json.loads(raw[6:])
                for ch in d["choices"]:
                    delta = ch.get("delta") or {}
                    if delta.get("reasoning_content"):
                        diag["reasoning"] += len(delta["reasoning_content"])
                    if delta.get("content"):
                        if diag["first"] is None:
                            diag["first"] = 0.2
                        parts.append(delta["content"])
            return "".join(parts)
        raise RuntimeError("all failed")
    m.expert_text = expert_text
    return m


@pytest.fixture
def quick_guard(monkeypatch):
    monkeypatch.setattr(D, "FIRST_TOKEN_LIMIT", 0.4)
    monkeypatch.setattr(D, "rate_difficulty", lambda problem, diag=None: None)


def test_silent_model_is_cut_and_next_model_answers(quick_guard):
    tried = []
    m = _llm_like_real(tried)
    D.install(m)
    silent = _Stream([(5.0, _sse({"content": "поздно"}))])       # заголовки есть, текста нет
    router = _Router({"gpt-6-luna": silent,
                      "gpt-6-sol": _Stream([(0.05, _sse({"content": "AB = CD"}))])})
    diag = {}
    t0 = time.time()
    assert m.expert_text(router, "задача", diag=diag) == "AB = CD"
    assert time.time() - t0 < 2.0                                  # не ждали 5 с
    assert tried == ["gpt-6-luna", "gpt-6-sol"] and silent.closed
    assert diag["silent"] == ["gpt-6-luna"] and diag["model"] == "gpt-6-sol"


def test_reasoning_counts_as_life_even_without_text(quick_guard):
    tried = []
    m = _llm_like_real(tried)
    D.install(m)
    thinking = _Stream([(0.1, _sse({"reasoning_content": "думаю..."})),
                        (0.8, _sse({"content": "ответ"}))])       # текст позже лимита, но думает
    router = _Router({"gpt-6-luna": thinking})
    assert m.expert_text(router, "задача", diag={}) == "ответ"
    assert tried == ["gpt-6-luna"]


def test_keepalive_lines_without_payload_do_not_count(quick_guard):
    tried = []
    m = _llm_like_real(tried)
    D.install(m)
    pings = _Stream([(0.1, ": ping")] * 10 + [(0.0, _sse({"content": "x"}))])
    router = _Router({"gpt-6-luna": pings, "gpt-6-sol": _Stream([(0.0, _sse({"content": "ok"}))])})
    assert m.expert_text(router, "задача", diag={}) == "ok"
    assert tried == ["gpt-6-luna", "gpt-6-sol"]


def test_all_models_silent_raises_expert_silent(quick_guard):
    tried = []
    m = _llm_like_real(tried)
    D.install(m)
    router = _Router({k: _Stream([(5.0, _sse({"content": "x"}))])
                      for k in ("gpt-6-luna", "gpt-6-sol", "gemini-3.7-flash")})
    diag = {}
    with pytest.raises(D.ExpertSilent):
        m.expert_text(router, "задача", diag=diag)
    assert tried == ["gpt-6-luna", "gpt-6-sol", "gemini-3.7-flash"]
    assert diag["silent"] == tried and m.EXPERT_MODEL == "gpt-6-luna"


def test_http_fallback_inside_expert_text_still_works(quick_guard):
    tried = []
    m = _llm_like_real(tried)
    D.install(m)
    router = _Router({"gpt-6-luna": _Stream([], status=404),
                      "gpt-6-sol": _Stream([(0.0, _sse({"content": "ok"}))])})
    assert m.expert_text(router, "задача", diag={}) == "ok"
    assert tried == ["gpt-6-luna", "gpt-6-sol"]


def test_guard_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(D, "FIRST_TOKEN_LIMIT", 0)
    monkeypatch.setattr(D, "rate_difficulty", lambda problem, diag=None: None)
    seen = {}
    m = _fake_llm([])
    m.expert_text = lambda sess, problem, history=None, max_out=16000, diag=None, messages=None: \
        seen.setdefault("sess", sess) and "ok"
    D.install(m)
    router = object()
    assert m.expert_text(router, "задача") == "ok"
    assert seen["sess"] is router                                  # сессия без прокси
