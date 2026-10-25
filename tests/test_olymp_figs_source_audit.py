"""Regression tests for the manual figure-source audit (no production DB writes)."""
from pathlib import Path
import json
from scripts.olymp_figs_validate import validate, ROOT


def task(slug, prefix):
    return next(t for t in json.loads(
        (ROOT / f"data/olymp_catalog/{slug}.json").read_text())
        if t["uid"].startswith(prefix))


def test_catalog_figures_and_archive_are_intact():
    assert validate()["errors"] == []


def test_advisor_false_no_figure_flags_are_corrected():
    for prefix in ("51f2f289", "40a95463", "cfd87cdf"):
        t = task("mmo", prefix)
        assert t["fig_solution"]
        assert not t.get("fig_none_in_source")
        assert all("_solution" in Path(p).stem for p in t["fig_solution"])


def test_foreign_vysshaya_proba_images_are_not_reattached():
    for prefix in ("6f5dea4c", "a5b8ba0f", "34fa3130"):
        t = task("vysshaya-proba", prefix)
        assert not t.get("fig_statement")
        assert not t.get("fig_solution")
        assert t["fig_none_in_source"] is True


def test_final_negative_flags_have_all_own_diagrams():
    for slug, prefix, count in (
        ("matprazdnik", "6694549b39bd", 1),
        ("matprazdnik", "fc8db88393be", 3),
        ("matprazdnik", "c4f28638e9f3", 1),
        ("turgor", "d6b096d75273", 1),
        ("turgor", "f5e2ec30655c", 2),
    ):
        t = task(slug, prefix)
        assert len(t["fig_solution"]) == count
        assert not t.get("fig_none_in_source")


def test_foreign_proof_tails_and_broken_radical_do_not_return():
    t = task("vsosh", "941eca2c31ba")
    assert r"\sqrt{n\sqrt{n\sqrt n}}" in t["text"]
    assert "пирамид" not in t["solution"]
    assert "шестиугольник" not in task("turgor", "42d9fdf62946")["solution"]
    assert len(task("turgor", "b0ed5d15ca1c")["solution"]) < 1000
    for prefix in ("b03ded1a19fe", "2ee4dc895398", "cb1733f02241",
                   "7a4df776908a", "118391aee793", "587ef5fb49bf",
                   "fdaf030be51c", "84d9f8184641", "0659896ca029", "db9319eee977"):
        assert len(task("lomonosov", prefix)["solution"]) < 1000


def test_qualifying_tournament_answer_is_not_incorrect_120():
    assert task("vsosh", "b70b69d44dec")["answer"] == "40 команд; 165 матчей."


def test_boat_has_own_statement_template_and_proof():
    t = task("vsosh", "54158c66b505")
    assert len(t["fig_statement"]) == 1
    assert t["fig_solution"]


def test_audit_workflow_is_read_only_for_catalog():
    text = (ROOT / ".github/workflows/olymp_figs_audit.yml").read_text()
    assert "--fix-orphans" not in text
    assert "git add reports/ data/olymp_catalog/" not in text
    extract = (ROOT / ".github/workflows/olymp_figs_extract.yml").read_text()
    assert "git push" not in extract
    assert "contents: read" in extract
    assert "actions/upload-artifact" in extract


def test_gif_is_a_real_figure_file(tmp_path, monkeypatch):
    from PIL import Image
    from scripts import olymp_catalog_figs_audit as audit
    Image.new("RGB", (12, 12), "white").save(tmp_path / "diagram.GIF")
    monkeypatch.setattr(audit, "FIGS", tmp_path)
    assert "diagram.GIF" in audit.all_fig_files()


def test_algebraic_graph_is_not_a_missing_illustration():
    from scripts import olymp_catalog_figs_audit as audit
    from routes.olymp_catalog_clean import FIG_WORDS as runtime_words
    for words in (audit.FIG_WORDS, runtime_words):
        assert not words.search("Найдите точки пересечения графика функции y=x² с осью.")
        assert words.search("На рисунке изображён график функции.")


def test_all_baseline_catalog_uids_are_preserved():
    scope = json.loads((ROOT / "reports/figures_review_scope.json").read_text())
    current = {
        path.stem: sorted(t["uid"] for t in json.loads(path.read_text()))
        for path in (ROOT / "data/olymp_catalog").glob("*.json")
        if not path.name.startswith("_")
    }
    assert current == scope["baseline_catalog_uids"]


def test_quarantine_dry_run_preserves_original_inventory(monkeypatch):
    from scripts import olymp_figs_quarantine as quarantine
    manifest = json.loads(
        (ROOT / "archive/olymp_figures_review/manifest.json").read_text())
    # This regression test must also work in a shallow CI checkout.
    monkeypatch.setattr(quarantine, "git", lambda *args:
                        manifest["baseline_commit"].encode()
                        if args[0] == "rev-parse" else b"")
    result = quarantine.run(apply=False)
    for key in ("orphans_archived", "previous_versions_preserved", "unique_objects"):
        assert result[key] == manifest[key]
    identities = [(r["original_path"], r["sha256"]) for r in manifest["records"]]
    assert len(identities) == len(set(identities))


def test_figure_routes_and_task_card_without_production_database():
    from flask import Flask
    from flask_login import LoginManager, UserMixin
    from jinja2 import ChoiceLoader, DictLoader
    from routes.olymp_catalog import olymp_catalog_bp
    app = Flask("figure_source_smoke", template_folder=str(ROOT / "templates"))
    app.config.update(TESTING=True, SECRET_KEY="test-only")
    # Exercise the actual task template and macros, without unrelated site chrome.
    app.jinja_loader = ChoiceLoader([
        DictLoader({"base.html": "{% block content %}{% endblock %}"}),
        app.jinja_loader])
    manager = LoginManager(app)
    class Reader(UserMixin):
        id = "test"
        nickname = "victor"
    @manager.request_loader
    def reader(_request):
        return Reader()
    app.register_blueprint(olymp_catalog_bp)
    client = app.test_client()
    for slug, prefix in (("mmo", "51f2f289"), ("vsosh", "54158c66b505"),
                         ("vsosh", "4b2823ae94c3"), ("turgor", "5644b3d5fe33")):
        t = task(slug, prefix)
        response = client.get(f"/olymp-catalog/{slug}/{t['uid'][:12]}")
        assert response.status_code == 200
        assert "▣ нет рисунка" not in response.get_data(as_text=True)
        for name in (t.get("fig_statement") or []) + (t.get("fig_solution") or []):
            image = client.get("/olymp-catalog/figures/" + name)
            assert image.status_code == 200
            assert image.data == (ROOT / "static/olymp_figures" / name).read_bytes()
