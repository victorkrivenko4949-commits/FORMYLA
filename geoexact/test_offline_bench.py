"""Офлайн-харнесс и бенчмарк: спецификация прогоняется через настоящий конвейер."""
import json
import pathlib

from geoexact.bench import check, parse_svg, summarize
from geoexact.offline import run_spec

DEMO = pathlib.Path(__file__).parent / "bench_corpus" / "demo_medians.json"


def test_demo_spec_builds_clean():
    spec = json.loads(DEMO.read_text(encoding="utf-8"))
    res = run_spec(spec)
    assert res.ok and res.stage == "9-render"
    rep = check(spec, res)
    assert rep["violations"] == [] and rep["missing"] == []
    assert summarize([rep])["built"] == 1.0
    assert "G" in parse_svg(res.svg)["points"]


def test_llm_restored_after_run():
    from geoexact.core import llm as L
    before = L.formalize
    run_spec(json.loads(DEMO.read_text(encoding="utf-8")), with_aux=False)
    assert L.formalize is before
