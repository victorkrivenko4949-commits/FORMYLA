"""Re-parse adaptive_data/_generated/_parse_errors.log with the improved
parser, normalize tasks, insert into DB and append to per-grade JSONL files.

Each block in _parse_errors.log has format:
    --- TIMESTAMP grade=N topic=TOPIC batch=K ---
    <raw model output>
"""
import datetime as _dt
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from scripts.generate_missing_adaptive_tasks import (  # noqa: E402
    parse_json_array, normalize, insert_task, INSERT_COLS, OUT_DIR,
    UI_TOPIC_NAMES_RU,
)

LOG = os.path.join("adaptive_data", "_generated", "_parse_errors.log")
DB = os.path.join("instance", "formyla.db")

HEADER_RE = re.compile(
    r"---\s+(?P<ts>\S+(?:\s+\S+)?)\s+grade=(?P<grade>\d+)\s+topic=(?P<topic>\S+)"
    r"(?:\s+level=(?P<level>\d+))?"
    r"\s+batch=(?P<batch>\d+)"
    r"(?:\s+thread=(?P<thread>\d+))?"
    r"\s+---"
)


def split_blocks(text: str):
    """Yield (header_dict, body_str)."""
    matches = list(HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield {
            "ts": m.group("ts"),
            "grade": int(m.group("grade")),
            "topic": m.group("topic"),
            "batch": int(m.group("batch")),
        }, text[start:end].strip()


def main():
    if not os.path.exists(LOG):
        print(f"No log: {LOG}")
        return
    raw = open(LOG, encoding="utf-8").read()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    existing = {row[0] for row in cur.execute("SELECT task_text FROM adaptive_tasks").fetchall()}
    print(f"DB tasks before: {len(existing)}")

    blocks = list(split_blocks(raw))
    print(f"Blocks in log: {len(blocks)}")

    total_inserted = 0
    per_combo: dict[tuple[int, str], int] = {}

    for hdr, body in blocks:
        grade = hdr["grade"]; topic = hdr["topic"]
        try:
            recs = parse_json_array(body)
        except Exception as e:
            print(f"  [still-failed] grade={grade} {topic}: {e}")
            continue
        if not recs:
            continue

        primary = f"{UI_TOPIC_NAMES_RU.get(topic, topic)} ({grade} класс)"
        ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(OUT_DIR, f"g{grade}_{topic}_recovered_{ts}.jsonl")
        kept = 0
        with open(out, "a", encoding="utf-8") as fp:
            for r in recs:
                norm = normalize(r, grade, primary)
                if not norm:
                    continue
                if insert_task(cur, norm, existing):
                    fp.write(json.dumps(norm, ensure_ascii=False) + "\n")
                    kept += 1
        conn.commit()
        if kept:
            per_combo[(grade, topic)] = per_combo.get((grade, topic), 0) + kept
            total_inserted += kept
            print(f"  recovered {kept} from grade={grade} {topic} batch={hdr['batch']}  → {out}")

    print(f"\n=== Recovered tasks inserted: {total_inserted} ===")
    for (g, t), n in sorted(per_combo.items()):
        print(f"  grade {g} {t}: +{n}")


if __name__ == "__main__":
    main()
