"""Offline integrity checks for figure references, source journals and quarantine."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "static/olymp_figures"


def validate(root=ROOT):
    errors = []
    refs = set()
    task_count = 0
    verified_count = 0
    for catalog in (root / "data/olymp_catalog").glob("*.json"):
        if catalog.name.startswith("_"):
            continue
        tasks = json.loads(catalog.read_text())
        journal = root / f"reports/figures_verified_{catalog.stem}.json"
        evidence = json.loads(journal.read_text()) if journal.exists() else {}
        seen = set()
        for task in tasks:
            task_count += 1
            uid = task["uid"]
            if uid in seen:
                errors.append(f"{catalog.stem}: duplicate UID {uid}")
            seen.add(uid)
            figures = (task.get("fig_statement") or []) + (task.get("fig_solution") or [])
            if figures and task.get("fig_none_in_source"):
                errors.append(f"{uid}: figures contradict fig_none_in_source")
            if uid in evidence:
                verified_count += 1
                if not evidence[uid].get("source", "").startswith(("https://", "http://")):
                    errors.append(f"{uid}: missing evidence URL")
                expected = {(role, name) for role in ("statement", "solution")
                            for name in task.get("fig_" + role) or []}
                actual = {(item["role"], item["path"])
                          for item in evidence[uid].get("attachments", [])}
                if actual != expected:
                    errors.append(f"{uid}: source ledger attachment list is stale")
                for item in evidence[uid].get("attachments", []):
                    path = root / "static/olymp_figures" / item["path"]
                    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                        errors.append(f"{uid}: source ledger SHA mismatch {item['path']}")
            for role in ("statement", "solution"):
                names = task.get("fig_" + role) or []
                if len(names) != len(set(names)):
                    errors.append(f"{uid}: duplicate reference in {role}")
                for name in names:
                    path = root / "static/olymp_figures" / name
                    if path.resolve().is_relative_to((root / "static/olymp_figures").resolve()) is False:
                        errors.append(f"{uid}: path escapes figure directory")
                    if not path.is_file() or path.stat().st_size == 0:
                        errors.append(f"{uid}: missing/empty {name}")
                    refs.add(name)
                    # The historical figures_all SVG set is retained unchanged.
                    if uid in evidence and Path(name).parent.name == "FINAL_FIGURES":
                        if not re.fullmatch(uid + "_" + role + r"(?:_\d+)?",
                                            Path(name).stem):
                            errors.append(f"{uid}: role/name mismatch {name}")
        unknown = set(evidence) - seen
        if unknown:
            errors.append(f"{catalog.stem}: journal contains unknown UIDs {unknown}")
    for name in refs:
        path = root / "static/olymp_figures" / name
        if not path.exists():
            continue
        try:
            if path.suffix.lower() == ".svg":
                ET.parse(path)
            else:
                from PIL import Image
                with Image.open(path) as image:
                    image.verify()
        except Exception as exc:
            errors.append(f"Invalid illustration {name}: {exc}")
    manifest_path = root / "archive/olymp_figures_review/manifest.json"
    archived = 0
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for record in manifest["records"]:
            path = root / record["archived_path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                errors.append(f"Archive integrity: {record['original_path']}")
            archived += 1
    return {"tasks": task_count, "linked_files": len(refs),
            "source_journal_tasks": verified_count,
            "archive_records": archived, "errors": errors}


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
