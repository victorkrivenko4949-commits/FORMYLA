import json

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
