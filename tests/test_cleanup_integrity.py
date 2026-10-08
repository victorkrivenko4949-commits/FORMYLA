"""Regression guards for cleanup PR: preserve dependencies, not just imports."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", [
    "_svg_to_png", "geometric_engine.engine", "tasks.prep_tasks",
    "verify.invariant_checker",
])
def test_cleanup_preserves_importable_dependencies(module):
    assert importlib.util.find_spec(module) is not None


@pytest.mark.parametrize("path", [
    "tools/clean_methods_atlas.py",
    "regression_night.py",
    "audit_l1_l3_results.json",
    "audit_l1_l3_failed.json",
    "audit_675_full_results.json",
    "audit_balanced_checkpoint.json",
    "audit_formyla_1_4_double_checkpoint.json",
    "FORMYLA_BANK.jsonl",
    "olympiad_tasks_PERFECT.json",
    "secrets_dump.json",
    "FORMYLA_SREZ_банк_среза.zip",
    "requirements-geoexact.txt",
    "templates/login.html",
])
def test_cleanup_preserves_required_paths(path):
    assert (ROOT / path).is_file(), path


def test_archive_does_not_disable_secret_ignore_rules(tmp_path):
    """Evaluate rules in an empty repo, independent of already tracked files."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8",
    )
    for path in [".env", "archive/.env", "archive/test/.env.production",
                 "archive/test/__pycache__/cached.pyc", "uploads/example.jpg"]:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "--no-index", path],
            capture_output=True,
        )
        assert result.returncode == 0, f"Not ignored: {path}"
    for path in [".env.example", "config/local.env.example", "FORMYLA_BANK.jsonl",
                 "static/example.png", "archive/notes.md"]:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "--no-index", path],
            capture_output=True,
        )
        assert result.returncode == 1, f"Unexpectedly ignored: {path}"
