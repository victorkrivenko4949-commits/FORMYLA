# -*- coding: utf-8 -*-
"""Диагностика битых корней: проходит по активным data-файлам и ищет
повреждённые паттерны \\sqrt[n]{}.

Считаем повреждённым (broken), если в тексте есть один из:
  1. \\sqrt[n] без открывающей { сразу после ]        -> \\sqrt[3] X
  2. \\sqrt[n]{...} с пробелом между sqrt и [          -> \\sqrt [3]{...}
  3. юникод ∛ или ³√
  4. одиночный ^{3}\\sqrt или ^3\\sqrt (потерянный radical-индекс)
  5. потерянный \\sqrt перед [n]{...}                  -> ...[3]{x} без \\sqrt
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Активные источники данных (НЕ бэкапы)
DATA_FILES = [
    "data/olympiads/vsosh_10_11_full.json",
    "data/olympiads/vsosh9_full.json",
    "data/olympiads/master_5345.json",
    "data/olympiads/methods_catalog_105.json",
    "data/olympiads/theory_65_methods.json",
    "data/adaptive/adaptive_full_9120.json",
    "adaptive_data/final/formyla_adaptive_final_polished.json",
]

# ── Битые паттерны ────────────────────────────────────────────────
PATTERNS = {
    # \sqrt[3] X  — нет { после ]
    "sqrt_n_no_brace": re.compile(r"\\sqrt\s*\[[^\]]*\]\s*(?!\{)[A-Za-z0-9\\(]"),
    # \sqrt [3]{ — пробел между sqrt и [
    "sqrt_space_bracket": re.compile(r"\\sqrt\s+\["),
    # юникод корни
    "unicode_cbrt": re.compile(r"∛|³√"),
    # ^{3}\sqrt{ или ^3 \sqrt{ — повисший индекс степени перед radical
    "hanging_cube_index": re.compile(r"\^\{?3\}?\s*\\sqrt\{"),
    # [n]{...} без \sqrt непосредственно перед (потерянный \sqrt)
    # ищем ] {  где перед [ нет \sqrt
    "lost_sqrt": re.compile(r"(?<!\\sqrt)(?<![A-Za-z])\[(\d+)\]\s*\{"),
}

FIELDS = ("text", "solution", "idea", "answer", "task_text", "solution_idea",
          "condition_md", "solution_md", "idea_md", "title", "content")


def scan_file(path: Path):
    hits = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [("__load_error__", str(e), "", "")]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return hits
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        ident = item.get("number") or item.get("id") or item.get("title") or idx
        pcode = item.get("probnik_code", "")
        for fld in FIELDS:
            v = item.get(fld)
            if not isinstance(v, str) or not v:
                continue
            for pname, pat in PATTERNS.items():
                m = pat.search(v)
                if m:
                    s = max(0, m.start() - 30)
                    e = min(len(v), m.end() + 30)
                    hits.append((f"{ident}|{pcode}", fld, pname, v[s:e]))
    return hits


def main():
    total = 0
    for rel in DATA_FILES:
        p = ROOT / rel
        if not p.is_file():
            print(f"  (нет файла) {rel}")
            continue
        hits = scan_file(p)
        if hits:
            print(f"\n=== {rel}  ({len(hits)} hits) ===")
            for ident, fld, pname, snip in hits[:50]:
                print(f"  [{pname}] {ident} .{fld}: ...{snip}...")
            total += len(hits)
        else:
            print(f"  OK  {rel}")
    print(f"\nИТОГО битых совпадений: {total}")


if __name__ == "__main__":
    main()
