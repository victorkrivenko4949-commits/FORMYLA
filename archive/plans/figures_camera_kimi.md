# Plan: Figures + Tutor Camera + Kimi Vision

## Summary of Changes

### Part 1 — Figures page (`/figures`)
| # | File | Change |
|---|------|--------|
| 1.1 | `templates/figures.html` | Remove «Решение» textarea + counter (lines 23-27, 347, 393-395, 532) |
| 1.2 | `templates/figures.html` | Add build_type toggle (2 buttons: «Без доп. построения» / «С доп. построением») |
| 1.3 | `templates/figures.html` | JS: send `build_type` in fetch body |
| 1.4 | `app.py` | Find `/api/figures/build` route, read `build_type` from request, pass to job |
| 1.5 | `routes/figures_generator.py` | `_run_build_job`: pass `build_type` to system prompt |
| 1.6 | Solution prompt file | Load and cache `_REASONER_SYSTEM_PROMPT` — add `{build_type}` parameter |

### Part 2 — Tutor camera
| # | File | Change |
|---|------|--------|
| 2.1 | `templates/tutor_widget.html` | Add camera button SVG next to file upload label |
| 2.2 | `templates/tutor_widget.html` | Add `<video>` modal with capture/cancel buttons |
| 2.3 | `templates/tutor_widget.html` | JS: `openCamera()`, `capturePhoto()`, `closeCamera()`, `attachImage()` |

### Part 3 — Kimi Vision
| # | File | Change |
|---|------|--------|
| 3.1 | `.env` | Check `KIMI_API_KEY` existence |
| 3.2 | `routes/figures_generator.py` or new file | Write `process_photo_with_kimi(image_bytes, mime_type)` |
| 3.3 | `app.py` tutor route | When image arrives: call Kimi -> get text -> prepend to message -> send to DeepSeek |
| 3.4 | `templates/tutor_widget.html` | JS: when camera captures, send to tutor as image, show "Распознаю фото..." |

### Part 4 — Verification
| # | Action |
|---|--------|
| 4.1 | `python -c "import app"` |
| 4.2 | Smoke test: GET /, /login, /figures, /misc, /daily_tasks |
| 4.3 | Search for «Решение» in templates — confirm removed from figures.html |
| 4.4 | Search for `build_type` in templates — confirm present in figures.html |
| 4.5 | Search for `getUserMedia` in templates — confirm present in tutor_widget.html |
| 4.6 | Search for `kimi` in app.py/routes — confirm function defined |

### Key files and their current state:
- `templates/figures.html` (567 lines) — main figures page, has «Решение» textarea
- `templates/figures_generate.html` (285 lines) — simpler figures page, no «Решение»
- `templates/tutor_widget.html` (920 lines) — AI tutor floating widget
- `routes/figures_generator.py` (723 lines) — figure build pipeline
- `app.py` lines 5193-5300 — `/api/tutor/send` route
- `app.py` — `/api/figures/build` route (need to locate)
- `l1_l3_generation/prompts/` — system prompts
