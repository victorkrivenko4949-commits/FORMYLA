"""Non-destructive archive for unreferenced and replaced catalog illustrations.

Default is dry-run. --apply archives bytes under archive/, records their SHA-256,
and removes only currently unreferenced files from the public static directory.
No match based merely on a UID-looking filename is approved or attached.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "static/olymp_figures"
DEST = ROOT / "archive/olymp_figures_review"
EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".gif"}


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(apply=False, baseline="201e19a5^"):
    refs = {}
    tasks = {}
    for path in (ROOT / "data/olymp_catalog").glob("*.json"):
        if path.name.startswith("_"):
            continue
        for task in json.loads(path.read_text()):
            tasks[task["uid"]] = task
            for role in ("statement", "solution"):
                for name in task.get("fig_" + role) or []:
                    refs.setdefault(name, []).append(
                        {"slug": path.stem, "uid": task["uid"], "role": role})
    files = {p.relative_to(FIGS).as_posix(): p for p in FIGS.rglob("*")
             if p.is_file() and p.suffix.lower() in EXTENSIONS}
    linked_hashes = {}
    for name, owners in refs.items():
        linked_hashes.setdefault(sha(files[name].read_bytes()), []).extend(owners)
    previous_manifest = DEST / "manifest.json"
    records = (json.loads(previous_manifest.read_text())["records"]
               if previous_manifest.exists() else [])
    blobs = {}
    unreferenced = sorted(set(files) - set(refs))
    for name in unreferenced:
        data = files[name].read_bytes()
        digest = sha(data)
        records.append({
            "original_path": "static/olymp_figures/" + name,
            "sha256": digest,
            "reason": ("exact_linked_duplicate" if digest in linked_hashes
                       else "unreferenced_no_unique_verified_assignment"),
            "origin": "working_tree_orphan",
            "same_bytes_linked_to": linked_hashes.get(digest, []),
            "filename_uid_present_in_catalog": Path(name).stem[:64] in tasks,
        })
        blobs[digest + files[name].suffix.lower()] = data
    commit = git("rev-parse", baseline).decode().strip()
    replaced = git("diff", "--name-only", "--diff-filter=DM", commit,
                   "--", "static/olymp_figures/").decode().splitlines()
    for name in replaced:
        if Path(name).suffix.lower() not in EXTENSIONS:
            continue
        data = git("show", f"{commit}:{name}")
        digest = sha(data)
        records.append({
            "original_path": name,
            "sha256": digest,
            "reason": "previous_version_preserved_before_source_correction",
            "origin": "git_baseline",
            "baseline_commit": commit,
        })
        blobs[digest + Path(name).suffix.lower()] = data
    # Preserve the first archive's inventory on subsequent runs.
    records = list({(r["origin"], r["original_path"], r["sha256"]): r
                    for r in records}.values())
    # Once an orphan leaves static/, git diff also calls it a deleted baseline
    # file. It is still one original orphan, not a newly replaced illustration.
    original_orphans = {(r["original_path"], r["sha256"]) for r in records
                        if r["origin"] == "working_tree_orphan"}
    records = [r for r in records if r["origin"] != "git_baseline"
               or (r["original_path"], r["sha256"]) not in original_orphans]
    for record in records:
        extension = Path(record["original_path"]).suffix.lower()
        record["archived_path"] = (
            "archive/olymp_figures_review/objects/" + record["sha256"] + extension)
    manifest = {
        "version": 1, "baseline_commit": commit,
        "policy": "Archive, never infer an attachment from filename or image similarity.",
        "orphans_archived": sum(r["origin"] == "working_tree_orphan" for r in records),
        "previous_versions_preserved": sum(r["origin"] == "git_baseline" for r in records),
        "unique_objects": len({r["archived_path"] for r in records}),
        "records": records,
    }
    if apply:
        (DEST / "objects").mkdir(parents=True, exist_ok=True)
        for name, data in blobs.items():
            path = DEST / "objects" / name
            if path.exists() and path.read_bytes() != data:
                raise RuntimeError("Archive collision: " + str(path))
            path.write_bytes(data)
            assert sha(path.read_bytes()) == name.split(".")[0]
        (DEST / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        # Archive verification must complete before anything leaves static/.
        for record in records:
            assert sha((ROOT / record["archived_path"]).read_bytes()) == record["sha256"]
        for name in unreferenced:
            assert name not in refs
            files[name].unlink()
    return {k: v for k, v in manifest.items() if k != "records"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--baseline", default="201e19a5^")
    args = parser.parse_args()
    print(json.dumps(run(args.apply, args.baseline), ensure_ascii=False, indent=2))
