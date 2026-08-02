# Code-first regeneration of course diagrams

`services/drawing_service.py` is the live, LLM-driven pipeline that
generates a diagram for an arbitrary problem text on demand (Claude
Opus + Gemini critic, see `docs/DRAWING_PIPELINE.md`). It needs an
OpenRouter API key and the production DB, so it cannot be exercised
from a CI/dev sandbox.

This document describes the **code-first** pipeline that lives entirely
in this repo and can regenerate a curated catalog of diagrams without
any LLM call. It is what produces the method-illustration assets under
`static/images/methods/`.

## Components

| File | Role |
|---|---|
| `scripts/diagram_specs/primitives.py` | Shared drawing helpers (segment, circle, angle_mark, right_angle, tick, circumcircle, incircle, midpoint, …). Strict style (black 2 px, sans-serif 20 px, white margins, no chartjunk). |
| `scripts/diagram_specs/triangles.py`, `circles.py`, `quads.py`, `combinatorial.py` | Pure-Python generators. Each is `(params: dict) -> matplotlib.figure.Figure`. |
| `scripts/diagram_specs/registry.py` | Name → generator map. Add a new generator by importing it and adding an entry. |
| `scripts/diagram_qa.py` | Per-image strict QA (`qa_check(path)`): non-blank, min-side, aspect ≤ 3:1, no boundary-touching ink, has-ink, not over-inked. Returns `QAResult` with the list of issues. |
| `scripts/regen_diagrams.py` | Batch runner. Reads `diagram_manifest.json`, renders each entry, runs QA, retries up to 3 times with relaxed padding, writes the target only on accept. Produces `_regen_report.{json,md}`. |
| `scripts/diagram_manifest.json` | Catalog of diagrams. Schema below. |

## Manifest schema

```json
[
  {
    "id":        "method_F1_circumcircle",
    "target":    "static/images/methods/F1_circumcircle.png",
    "mode":      "code",
    "generator": "triangle_with_circumcircle",
    "params":    {"a": [0, 0], "b": [4.0, 0], "c": [1.4, 3.0]}
  }
]
```

- `mode = "code"` — render via `scripts/diagram_specs.get_generator(generator)`.
- `mode = "llm"` — reserved for entries that need
  `services/drawing_service.py` (OpenRouter key required). The runner
  records these under `needs_manual_or_api` in the report and leaves
  the original file untouched.
- `mode = "keep"` — explicitly skip.

`params` are passed verbatim to the generator. See each
`scripts/diagram_specs/*.py` for accepted keys.

## Strict geometry naming rules

The matplotlib generators follow the course conventions:

- circles: `ω`, `Ω`, `описанная окружность ABCD`, `окружность с диаметром BC`, etc. — no decorative names;
- vertices: single Latin letters (`A B C O M H T₁ T₂`);
- right angles: small square marker via `primitives.right_angle`;
- equal segments: tick-mark counts via `primitives.tick`;
- inscribed angles: arc + Greek letter via `primitives.angle_mark`.

## Workflow

```bash
# Dry-run (no files written, just QA on rendered bytes)
python3 scripts/regen_diagrams.py --dry-run

# Apply: writes targets, backs up originals as <name>.bak.png
python3 scripts/regen_diagrams.py --apply

# Skip backups
python3 scripts/regen_diagrams.py --apply --no-backup

# Custom manifest
python3 scripts/regen_diagrams.py --manifest path/to/my_manifest.json --apply
```

The runner:

1. Renders the figure.
2. Saves to `/tmp/regen_attempt_<pid>_<i>.png`.
3. Runs `qa_check`.
4. If QA fails, retries with progressively larger margins
   (`pad ∈ {0.18, 0.28, 0.40}`, three attempts).
5. On accept, copies the original to `<target>.bak.png` (unless
   `--no-backup`) and overwrites the target.
6. On reject after all retries, leaves the original untouched and
   records the failure in `_regen_report.{json,md}`.

## QA report format

`scripts/_regen_report.md` lists, in order:

- counts: total / accepted / rejected / needs_api / errors,
- accepted entries (target path, final pixel size, number of retry attempts),
- rejected entries (issue list),
- entries pending LLM/API access,
- internal errors with truncated tracebacks.

## Adding a new generator

1. Write a function `name(params: dict) -> Figure` in one of the
   `scripts/diagram_specs/*.py` files; build it from the helpers in
   `primitives.py` so the style stays consistent.
2. Register it in `scripts/diagram_specs/registry.py`.
3. Add an entry to `scripts/diagram_manifest.json` with `mode: "code"`.
4. Run `python3 scripts/regen_diagrams.py --dry-run` and check the report.
5. If accepted, `--apply` writes it. Commit the manifest entry and the
   generated PNG (PNGs are part of the deploy artifact).

## Why we do not LLM-regenerate the `static/images/problems/*.png` set offline

Those PNGs are scans/screenshots of specific olympiad problems from
multiple sources (FU, Kurchatov, Lomonosov, PvG, Высшая проба, ВсОШ,
Эйлер, Турнир городов). Their *correct* replacement requires the exact
geometric construction from each problem's statement, which lives in the
production database and needs the `services/drawing_service.py` LLM
pipeline (OpenRouter + Gemini critic). When the key is present, the
manifest entries with `mode: "llm"` will be picked up by a future
LLM-driven runner; for now they are listed under `needs_manual_or_api`
in `_regen_report.md` so the gap is visible.
