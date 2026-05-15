# -*- coding: utf-8 -*-
# Pretty-print the most recent (or arbitrary) row from the
# `drawing_generations` table, including the full Claude<->Gemini dialog.
#
# Usage:
#     python scripts/inspect_drawing_log.py                # last "ok" row
#     python scripts/inspect_drawing_log.py --id 42        # specific row
#     python scripts/inspect_drawing_log.py --any          # last row regardless of status
#     python scripts/inspect_drawing_log.py --save out.txt # also write a text dump
#
# Reads the local SQLite at instance/formyla.db.  For Postgres prod inspect
# rows via your usual DB client — the schema is identical.

import argparse
import json
import os
import sqlite3
import sys
import textwrap


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "instance",
    "formyla.db",
)


def _connect():
    if not os.path.exists(DB_PATH):
        print("[error] sqlite db not found: " + DB_PATH, file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch(row_id=None, any_status=False):
    conn = _connect()
    cur = conn.cursor()
    if row_id is not None:
        cur.execute(
            "SELECT * FROM drawing_generations WHERE id = ?",
            (row_id,),
        )
    elif any_status:
        cur.execute(
            "SELECT * FROM drawing_generations ORDER BY id DESC LIMIT 1"
        )
    else:
        cur.execute(
            "SELECT * FROM drawing_generations "
            "WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
        )
    row = cur.fetchone()
    conn.close()
    return row


def _wrap(s, indent=4, width=100):
    if not s:
        return ""
    s = str(s)
    return textwrap.indent(
        textwrap.fill(s, width=width, replace_whitespace=False,
                      drop_whitespace=False),
        " " * indent,
    )


def _section(title, body):
    bar = "=" * 76
    return bar + "\n  " + title + "\n" + bar + "\n" + body + "\n"


def render_report(row) -> str:
    if row is None:
        return "[no row]"
    out = []

    head = (
        "id            : " + str(row["id"]) + "\n"
        "created_at    : " + str(row["created_at"]) + "\n"
        "status        : " + str(row["status"]) + "\n"
        "model         : " + str(row["model"]) + "\n"
        "user_id       : " + str(row["user_id"]) + "\n"
        "render_ms     : " + str(row["render_ms"]) + "\n"
        "cost_usd      : " + str(row["cost_usd"]) + "\n"
        "repair_iters  : " + str(row["repair_iters"]) + "\n"
    )
    # critique columns may not exist on older databases
    cols = row.keys()
    for c in (
        "critique_rounds", "critique_accepted", "critique_rejected",
        "image_size", "image_path",
    ):
        if c in cols:
            head += c.ljust(14) + ": " + str(row[c]) + "\n"
    out.append(_section("META", head.rstrip()))

    out.append(_section("PROBLEM", _wrap(row["problem"])))

    if "error" in cols and row["error"]:
        out.append(_section("ERROR", _wrap(row["error"])))

    code = row["generated_code"]
    if code:
        out.append(_section(
            "FINAL CODE (after all critique rounds)",
            textwrap.indent(code, "    "),
        ))

    if "critique_findings_json" in cols and row["critique_findings_json"]:
        try:
            findings = json.loads(row["critique_findings_json"])
        except Exception:
            findings = None
        if not findings:
            out.append(_section("CRITIQUE", "    [empty or invalid JSON]"))
        else:
            body_lines = []
            for i, f in enumerate(findings, 1):
                body_lines.append("    [" + str(i) + "] id=" + str(f.get("id"))
                                  + " | severity=" + str(f.get("severity")))
                body_lines.append("        title       : " + str(f.get("title")))
                body_lines.append("        detail      :")
                body_lines.append(_wrap(f.get("detail"), indent=14))
                body_lines.append("        fix_hint    :")
                body_lines.append(_wrap(f.get("fix_hint"), indent=14))
                body_lines.append("        decision    : " + str(f.get("claude_decision")))
                if f.get("claude_reasoning"):
                    body_lines.append("        reasoning   :")
                    body_lines.append(_wrap(f.get("claude_reasoning"), indent=14))
                body_lines.append("")
            out.append(_section(
                "CRITIQUE DIALOG (Gemini findings -> Claude decisions)",
                "\n".join(body_lines),
            ))
    else:
        out.append(_section("CRITIQUE", "    [no critique recorded -- "
                            "row may predate the critic stage]"))

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--id", type=int, default=None,
                        help="inspect specific row id")
    parser.add_argument("--any", action="store_true",
                        help="last row regardless of status (default: last 'ok')")
    parser.add_argument("--save", type=str, default=None,
                        help="also write the report to this file")
    args = parser.parse_args()

    row = _fetch(row_id=args.id, any_status=args.any)
    report = render_report(row)
    print(report)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report)
        print("\n[saved to " + args.save + "]")


if __name__ == "__main__":
    main()
